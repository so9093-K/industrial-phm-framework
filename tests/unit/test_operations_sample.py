from pathlib import Path

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
        assert timeout_seconds == 15.0

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
    assert launch.url == "http://127.0.0.1:2719"
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
