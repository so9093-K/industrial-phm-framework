import socket
from pathlib import Path
from types import SimpleNamespace

from industrial_phm.runtime import (
    OperationsDeploymentCheckState,
    OperationsRuntimeConfig,
    OperationsUiConfig,
    OperationsWorkspace,
    initialize_operations_workspace,
)
from industrial_phm.runtime.operations_config import write_operations_runtime_config
from industrial_phm.runtime.operations_deployment import inspect_operations_deployment


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _stub_runtime_imports(monkeypatch) -> None:
    import industrial_phm.runtime.operations_deployment as deployment_module

    original = deployment_module.importlib.import_module

    def fake_import(name: str):
        if name in {"asyncua", "duckdb", "filelock", "marimo"}:
            return SimpleNamespace()
        return original(name)

    monkeypatch.setattr(deployment_module.importlib, "import_module", fake_import)


def test_deployment_preflight_accepts_initialized_absolute_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _stub_runtime_imports(monkeypatch)
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    initialize_operations_workspace(workspace)
    write_operations_runtime_config(
        workspace.config_path,
        OperationsRuntimeConfig(ui=OperationsUiConfig(port=_free_port())),
    )

    report = inspect_operations_deployment(workspace)

    assert report.ready is True
    by_name = {item.name: item for item in report.checks}
    assert by_name["workspace-path"].state == OperationsDeploymentCheckState.PASS
    assert by_name["config"].state == OperationsDeploymentCheckState.PASS
    assert by_name["supervisor-lock"].state == OperationsDeploymentCheckState.PASS
    assert by_name["ui-port"].state == OperationsDeploymentCheckState.PASS


def test_deployment_preflight_requires_absolute_workspace(monkeypatch) -> None:
    _stub_runtime_imports(monkeypatch)
    workspace = OperationsWorkspace(Path("relative-workspace"))

    report = inspect_operations_deployment(workspace)

    assert report.ready is False
    by_name = {item.name: item for item in report.checks}
    assert by_name["workspace-path"].state == OperationsDeploymentCheckState.FAIL


def test_deployment_preflight_reports_missing_runtime_dependency(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    initialize_operations_workspace(workspace)
    write_operations_runtime_config(
        workspace.config_path,
        OperationsRuntimeConfig(ui=OperationsUiConfig(port=_free_port())),
    )
    import industrial_phm.runtime.operations_deployment as deployment_module

    original = deployment_module.importlib.import_module

    def fake_import(name: str):
        if name == "marimo":
            raise ModuleNotFoundError("marimo")
        if name in {"asyncua", "duckdb", "filelock"}:
            return SimpleNamespace()
        return original(name)

    monkeypatch.setattr(deployment_module.importlib, "import_module", fake_import)

    report = inspect_operations_deployment(workspace)

    assert report.ready is False
    by_name = {item.name: item for item in report.checks}
    assert by_name["dependency-marimo"].state == OperationsDeploymentCheckState.FAIL


def test_deployment_preflight_rejects_occupied_ui_port(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _stub_runtime_imports(monkeypatch)
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    initialize_operations_workspace(workspace)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = int(listener.getsockname()[1])
        write_operations_runtime_config(
            workspace.config_path,
            OperationsRuntimeConfig(ui=OperationsUiConfig(port=port)),
        )

        report = inspect_operations_deployment(workspace)

    assert report.ready is False
    by_name = {item.name: item for item in report.checks}
    assert by_name["ui-port"].state == OperationsDeploymentCheckState.FAIL


def test_deployment_preflight_reuses_recently_closed_web_port() -> None:
    """TIME_WAIT must not fail restart preflight, but a live listener must."""
    import industrial_phm.runtime.operations_deployment as deployment_module

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = int(listener.getsockname()[1])
        # A currently listening HTTPServer-style socket must still win the port.
        assert (
            deployment_module._ui_port_check(port).state == OperationsDeploymentCheckState.FAIL
        )
        with socket.create_connection(("127.0.0.1", port), timeout=3) as client:
            accepted, _ = listener.accept()
            with accepted:
                accepted.sendall(b"ok")
                accepted.shutdown(socket.SHUT_WR)
            assert client.recv(2) == b"ok"
            assert client.recv(1) == b""
    # The listener exited while the server side held the last TIME_WAIT.
    # HTTPServer sets SO_REUSEADDR; its deployment probe must do the same.
    assert deployment_module._ui_port_check(port).state == OperationsDeploymentCheckState.PASS
