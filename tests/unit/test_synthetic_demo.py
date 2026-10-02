import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from industrial_phm.application import (
    CollectionDesiredState,
    JsonSourceRepository,
    SourceLifecycleState,
)
from industrial_phm.demo.synthetic import (
    SYNTHETIC_DEMO_SOURCE_ID,
    SyntheticDemoConfig,
    prepare_synthetic_demo,
    run_synthetic_demo,
)
from industrial_phm.runtime import (
    OperationsSupervisorStateKind,
    OperationsWorkspace,
    SqliteCollectionControlRepository,
    load_operations_runtime_config,
)


class _FakeSimulator:
    def __init__(self, *, return_code: int | None = None) -> None:
        self.pid = 9001
        self.return_code = return_code
        self.signals: list[int] = []
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.return_code

    def send_signal(self, sig: int) -> None:
        self.signals.append(sig)
        self.return_code = 0

    def terminate(self) -> None:
        self.terminated = True
        self.return_code = -15

    def kill(self) -> None:
        self.killed = True
        self.return_code = -9

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        if self.return_code is None:
            raise AssertionError("fake simulator wait requires a prior stop signal")
        return self.return_code


def test_prepare_synthetic_demo_creates_active_running_three_phase_source(
    tmp_path: Path,
) -> None:
    preset = SyntheticDemoConfig(
        workspace=tmp_path / "demo",
        opcua_port=4845,
        ui_port=2725,
    )
    at = datetime(2026, 10, 2, 8, 30, tzinfo=UTC)

    preparation = prepare_synthetic_demo(preset, now=at)

    assert preparation.created_workspace is True
    assert preparation.source_id == SYNTHETIC_DEMO_SOURCE_ID
    assert preparation.endpoint == "opc.tcp://127.0.0.1:4845/phm-demo/"
    repository = JsonSourceRepository(preparation.workspace.source_registry_path)
    assert tuple(source.source_id for source in repository.list_sources()) == (
        SYNTHETIC_DEMO_SOURCE_ID,
    )
    assert (
        repository.get_lifecycle(SYNTHETIC_DEMO_SOURCE_ID).state
        == SourceLifecycleState.ACTIVE
    )
    control = SqliteCollectionControlRepository(preparation.workspace.collection_control_path)
    record = control.get(SYNTHETIC_DEMO_SOURCE_ID)
    assert record is not None
    assert record.desired_state == CollectionDesiredState.RUNNING
    config = load_operations_runtime_config(preparation.workspace.config_path)
    assert config.collection.window_duration_seconds == 10.0
    assert config.collection.allowed_lateness_seconds == 2.0
    assert config.analysis.poll_interval_seconds == 1.0
    assert config.ui.port == 2725


def test_prepare_synthetic_demo_reuses_only_matching_demo_workspace(tmp_path: Path) -> None:
    preset = SyntheticDemoConfig(workspace=tmp_path / "demo")
    first_at = datetime(2026, 10, 2, 8, 30, tzinfo=UTC)
    second_at = first_at + timedelta(seconds=5)

    first = prepare_synthetic_demo(preset, now=first_at)
    second = prepare_synthetic_demo(preset, now=second_at)

    assert first.created_workspace is True
    assert second.created_workspace is False
    repository = JsonSourceRepository(second.workspace.source_registry_path)
    assert len(repository.list_sources()) == 1
    control = SqliteCollectionControlRepository(second.workspace.collection_control_path)
    record = control.get(SYNTHETIC_DEMO_SOURCE_ID)
    assert record is not None
    assert record.generation == 1


def test_prepare_synthetic_demo_rejects_existing_non_demo_state(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "demo")
    workspace.root.mkdir(parents=True)
    workspace.config_path.write_text(
        'schema = "industrial-phm-operations-runtime-v2"\n',
        encoding="utf-8",
    )
    workspace.history_data_path.mkdir()
    workspace.logs_path.mkdir()
    workspace.phase_unbalance_state_path.write_text("not-demo", encoding="utf-8")

    with pytest.raises(ValueError, match="contains runtime/history state"):
        prepare_synthetic_demo(SyntheticDemoConfig(workspace=workspace.root))


def test_run_synthetic_demo_uses_normal_operations_supervisor_and_stops_simulator(
    tmp_path: Path,
    monkeypatch,
) -> None:
    preset = SyntheticDemoConfig(workspace=tmp_path / "demo", opcua_port=4846, ui_port=2726)
    simulator = _FakeSimulator()
    captured: dict[str, object] = {}

    def launch(argv: tuple[str, ...], log_path: Path) -> _FakeSimulator:
        captured["argv"] = argv
        captured["log_path"] = log_path
        return simulator

    def fake_supervisor(plan, *, stop_requested):
        captured["plan"] = plan
        assert stop_requested() is False
        return SimpleNamespace(
            state=SimpleNamespace(
                state=OperationsSupervisorStateKind.STOPPED,
                failure=None,
            ),
            exit_code=0,
        )

    import industrial_phm.demo.synthetic as synthetic_module

    monkeypatch.setattr(synthetic_module, "run_operations_supervisor", fake_supervisor)

    exit_code = run_synthetic_demo(
        preset,
        process_launcher=launch,
        listener_probe=lambda _host, _port: True,
    )

    assert exit_code == 0
    argv = captured["argv"]
    assert isinstance(argv, tuple)
    assert argv[:4] == (
        sys.executable,
        "-m",
        "industrial_phm.demo.synthetic",
        "server",
    )
    plan = captured["plan"]
    assert plan.workspace.root == preset.workspace
    assert plan.ui_url == "http://127.0.0.1:2726"
    assert simulator.return_code == 0
    assert simulator.signals


def test_run_synthetic_demo_fails_if_simulator_exits_before_readiness(tmp_path: Path) -> None:
    preset = SyntheticDemoConfig(workspace=tmp_path / "demo", opcua_port=4847)
    simulator = _FakeSimulator(return_code=7)

    with pytest.raises(RuntimeError, match="exited before readiness"):
        run_synthetic_demo(
            preset,
            process_launcher=lambda _argv, _log: simulator,
            listener_probe=lambda _host, _port: False,
        )
