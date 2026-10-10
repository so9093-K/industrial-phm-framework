"""Supervisor-owned Web synthetic demo isolation and lifecycle contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

import industrial_phm.runtime.operations_sample as sample
import industrial_phm.runtime.operations_web_sample as sample_web
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_sample import execute_web_sample_action


class FakeDemoProcess:
    pid = 12571

    def __init__(self) -> None:
        self.returncode: int | None = None
        self.stopped = False

    def poll(self) -> int | None:
        return self.returncode

    def send_signal(self, _signal: int) -> None:
        self.returncode = 0
        self.stopped = True

    def terminate(self) -> None:
        self.returncode = 0
        self.stopped = True

    def kill(self) -> None:
        self.returncode = -9
        self.stopped = True

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        return self.returncode or 0


def test_web_sample_actions_start_reuse_status_and_stop_isolated_demo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = OperationsWorkspace(tmp_path / "real")
    initialize_operations_workspace(workspace)
    config_before = workspace.config_path.read_bytes()
    process = FakeDemoProcess()
    launched: list[tuple[tuple[str, ...], Path]] = []
    ports = iter([2777, 4888])

    monkeypatch.setattr(sample, "_SAMPLE_PROCESS", None)
    monkeypatch.setattr(sample, "_SAMPLE_LAUNCH", None)
    def launch_demo(root: OperationsWorkspace) -> sample.FirstRunSampleLaunch:
        return sample.launch_first_run_sample(
            root,
            process_launcher=lambda argv, log: launched.append((argv, log)) or process,
            listener_waiter=lambda *_a, **_kw: None,
            port_resolver=lambda *_a: next(ports),
        )

    monkeypatch.setattr(sample_web, "launch_first_run_sample", launch_demo)

    status_route = "/api/v1/demo/synthetic/status"
    start_route = "/api/v1/demo/synthetic/start"
    stop_route = "/api/v1/demo/synthetic/stop"
    assert execute_web_sample_action(workspace.root, status_route, {}) == {
        "schema_version": 1, "state": "stopped", "synthetic": True,
    }
    started = execute_web_sample_action(workspace.root, start_route, {})
    assert started == {
        "schema_version": 1,
        "state": "running",
        "synthetic": True,
        "url": "http://127.0.0.1:2777",
        "separate_workspace": True,
    }
    assert execute_web_sample_action(workspace.root, status_route, {}) == started
    assert execute_web_sample_action(workspace.root, start_route, {}) == started
    assert len(launched) == 1
    args, log = launched[0]
    assert "--workspace" in args
    sample_root = Path(args[args.index("--workspace") + 1])
    assert sample_root != workspace.root
    assert sample_root.parent == workspace.root.parent
    assert log == workspace.logs_path / "first-run-sample.log"
    assert workspace.config_path.read_bytes() == config_before
    assert not workspace.source_registry_path.exists()

    with pytest.raises(ValueError, match="user-supplied paths"):
        execute_web_sample_action(workspace.root, stop_route, {"workspace": "/tmp/not-ours"})
    assert process.stopped is False
    assert execute_web_sample_action(workspace.root, stop_route, {}) == {
        "schema_version": 1, "state": "stopped", "synthetic": True,
    }
    assert process.stopped
    assert execute_web_sample_action(workspace.root, status_route, {})["state"] == "stopped"
    assert execute_web_sample_action(workspace.root, stop_route, {})["state"] == "stopped"
    assert workspace.config_path.read_bytes() == config_before


def test_web_sample_status_rejects_stale_process_and_unknown_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sample, "_SAMPLE_PROCESS", FakeDemoProcess())
    monkeypatch.setattr(sample, "_SAMPLE_LAUNCH", sample.FirstRunSampleLaunch(
        workspace=tmp_path / "synthetic", url="http://127.0.0.1:2777",
        opcua_port=4888, ui_port=2777,
    ))
    assert sample._SAMPLE_PROCESS is not None
    sample._SAMPLE_PROCESS.returncode = 1
    result = execute_web_sample_action(tmp_path, "/api/v1/demo/synthetic/status", {})
    assert result["state"] == "stopped"
    with pytest.raises(ValueError, match="unknown synthetic sample action"):
        execute_web_sample_action(tmp_path, "/api/v1/demo/synthetic/anything", {})
    sample.stop_first_run_sample()
