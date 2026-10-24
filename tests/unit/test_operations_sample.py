import socket
from pathlib import Path

import pytest

import industrial_phm.runtime.operations_sample as sample_module
from industrial_phm.runtime import (
    OperationsRuntimeConfig,
    OperationsUiConfig,
    OperationsWorkspace,
    initialize_operations_workspace,
)
from industrial_phm.runtime.operations_config import write_operations_runtime_config
from industrial_phm.runtime.operations_sample import (
    launch_first_run_sample,
    stop_first_run_sample,
)


class FakeProcess:
    pid = 12345

    def __init__(self) -> None:
        self.return_code = None
        self.stopped = False

    def poll(self):
        return self.return_code

    def send_signal(self, _sig):
        self.stopped = True
        self.return_code = 0

    def terminate(self):
        self.stopped = True
        self.return_code = 0

    def kill(self):
        self.stopped = True
        self.return_code = -9

    def wait(self, timeout=None):
        del timeout
        return 0 if self.return_code is None else self.return_code


def test_first_run_sample_reuses_existing_demo_command_in_isolated_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = OperationsWorkspace(tmp_path / "operations")
    initialize_operations_workspace(workspace)
    write_operations_runtime_config(
        workspace.config_path,
        OperationsRuntimeConfig(ui=OperationsUiConfig(port=2718)),
    )
    process = FakeProcess()
    captured = {}

    def fake_launch(argv, log_path):
        captured["argv"] = argv
        captured["log_path"] = log_path
        return process

    def fake_wait(port, child, *, timeout_seconds):
        assert port == 2719
        assert child is process
        assert timeout_seconds == 60.0

    ports = iter((2719, 4842))

    monkeypatch.setattr(sample_module, "_SAMPLE_PROCESS", None)
    monkeypatch.setattr(sample_module, "_SAMPLE_LAUNCH", None)
    launch = launch_first_run_sample(
        workspace,
        process_launcher=fake_launch,
        listener_waiter=fake_wait,
        port_resolver=lambda _start, _excluded: next(ports),
    )

    assert launch.workspace == tmp_path / "demo-synthetic-2719-4842"
    assert launch.url == "http://127.0.0.1:2719/web/"
    assert launch.opcua_port == 4842
    assert launch.ui_port == 2719
    assert captured["log_path"] == workspace.logs_path / "first-run-sample.log"
    argv = captured["argv"]
    assert argv[3:5] == ("demo", "synthetic")
    assert "--workspace" in argv
    assert str(launch.workspace) in argv
    assert "--opcua-port" in argv
    assert "--ui-port" in argv

    stop_first_run_sample()
    assert process.stopped


def test_first_run_sample_returns_running_launch_without_starting_duplicate(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = OperationsWorkspace(tmp_path / "operations")
    initialize_operations_workspace(workspace)
    process = FakeProcess()
    calls = []

    def fake_launch(argv, log_path):
        calls.append((argv, log_path))
        return process

    ports = iter((2720, 4843))
    monkeypatch.setattr(sample_module, "_SAMPLE_PROCESS", None)
    monkeypatch.setattr(sample_module, "_SAMPLE_LAUNCH", None)

    first = launch_first_run_sample(
        workspace,
        process_launcher=fake_launch,
        listener_waiter=lambda *_args, **_kwargs: None,
        port_resolver=lambda _start, _excluded: next(ports),
    )
    second = launch_first_run_sample(
        workspace,
        process_launcher=fake_launch,
        listener_waiter=lambda *_args, **_kwargs: None,
        port_resolver=lambda _start, _excluded: 6000,
    )

    assert second == first
    assert len(calls) == 1
    stop_first_run_sample()


def test_stopped_listener_keeps_its_port_despite_time_wait() -> None:
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        listener.listen()
        with socket.create_connection(("127.0.0.1", port)) as client:
            peer, _ = listener.accept()
            with peer:
                peer.shutdown(socket.SHUT_WR)
                assert client.recv(1) == b""
    assert sample_module._first_available_loopback_port(port, set()) == port


def test_container_example_never_launches_on_an_unpublished_port(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = OperationsWorkspace(tmp_path / "parent")
    initialize_operations_workspace(workspace)
    monkeypatch.setenv("INDUSTRIAL_PHM_SAMPLE_UI_PORT", "2719")
    monkeypatch.setattr(sample_module, "_SAMPLE_PROCESS", None)
    monkeypatch.setattr(sample_module, "_SAMPLE_LAUNCH", None)
    with pytest.raises(RuntimeError, match="2719"):
        launch_first_run_sample(workspace, scenario="bearing", port_resolver=lambda *_args: 2720)
    assert sample_module.current_first_run_sample() is None


def test_prepared_real_replay_uses_actual_asset_and_retains_parent_and_reviews(
    tmp_path: Path, monkeypatch
) -> None:
    from industrial_phm.demo.bearing import write_journey
    from industrial_phm.runtime.operations_config import load_operations_runtime_config
    from industrial_phm.runtime.operations_sample import prepared_xjtu_workspace

    parent = OperationsWorkspace(tmp_path / "parent")
    real = OperationsWorkspace(tmp_path / "real")
    initialize_operations_workspace(parent)
    initialize_operations_workspace(real)
    real.acquisition_snapshot_path.touch()
    write_journey(
        real, asset="Bearing1_1", bindings=("forest", "lstm"), first=1, last=100, dataset="xjtu-sy"
    )
    reviews = real.root / "finding-review.json"
    reviews.write_text('{"review":"preserve"}')
    original = parent.config_path.read_bytes()
    monkeypatch.setenv("INDUSTRIAL_PHM_XJTU_WORKSPACE", str(real.root))
    monkeypatch.setattr(sample_module, "_SAMPLE_PROCESS", None)
    monkeypatch.setattr(sample_module, "_SAMPLE_LAUNCH", None)
    assert prepared_xjtu_workspace(parent) == real
    captured = []
    process = FakeProcess()
    ports = iter((2719, 4841))
    launch = launch_first_run_sample(
        parent,
        scenario="xjtu",
        process_launcher=lambda argv, _log: (captured.append(argv), process)[1],
        listener_waiter=lambda *_args, **_kwargs: None,
        port_resolver=lambda *_args: next(ports),
    )
    try:
        assert launch.scenario == "xjtu" and launch.asset_id == "Bearing1_1"
        assert captured[0][3:] == ("operations", "up", str(real.root))
        assert load_operations_runtime_config(real.config_path).ui.port == 2719
        assert parent.config_path.read_bytes() == original
        assert reviews.read_text() == '{"review":"preserve"}'
    finally:
        stop_first_run_sample()


def test_missing_or_nested_real_dataset_never_falls_back_to_generated_data(
    tmp_path: Path, monkeypatch
) -> None:
    from industrial_phm.runtime.operations_sample import prepared_xjtu_workspace

    parent = OperationsWorkspace(tmp_path / "parent")
    initialize_operations_workspace(parent)
    monkeypatch.setattr(sample_module, "_SAMPLE_PROCESS", None)
    monkeypatch.setattr(sample_module, "_SAMPLE_LAUNCH", None)
    for configured in (parent.root, parent.root / "nested", tmp_path / "missing"):
        monkeypatch.setenv("INDUSTRIAL_PHM_XJTU_WORKSPACE", str(configured))
        assert prepared_xjtu_workspace(parent) is None
        with pytest.raises(ValueError, match="준비된 XJTU-SY"):
            launch_first_run_sample(
                parent,
                scenario="xjtu",
                port_resolver=lambda start, _: start,
                process_launcher=lambda *_args: pytest.fail("no process may start"),
            )
