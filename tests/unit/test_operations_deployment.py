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
        if name in {"asyncua", "duckdb", "marimo"}:
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
        if name in {"asyncua", "duckdb"}:
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
