import signal
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from industrial_phm.application import (
    CollectionDesiredState,
    JsonSourceRepository,
    SourceLifecycleState,
)
from industrial_phm.demo.aihub_boiler import (
    AIHUB_BOILER_DEMO_MEMBER,
    AIHUB_BOILER_DEMO_SOURCE_ID,
    AihubBoilerDemoConfig,
    prepare_aihub_boiler_demo,
    run_aihub_boiler_demo,
)
from industrial_phm.runtime import (
    OperationsSupervisorStateKind,
    OperationsWorkspace,
    SqliteCollectionControlRepository,
    load_operations_runtime_config,
)

pytest.importorskip("ijson")


class _FakeReplay:
    def __init__(self, *, return_code: int | None = None) -> None:
        self.pid = 9101
        self.return_code = return_code
        self.signals: list[int] = []

    def poll(self) -> int | None:
        return self.return_code

    def send_signal(self, sig: int) -> None:
        self.signals.append(sig)
        self.return_code = 0

    def terminate(self) -> None:
        self.return_code = -15

    def kill(self) -> None:
        self.return_code = -9

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        if self.return_code is None:
            raise AssertionError("fake replay wait requires a prior stop signal")
        return self.return_code


def _archive(tmp_path: Path) -> Path:
    path = tmp_path / "5.보일러.zip"
    rows = []
    for minute in range(4):
        stamp = f"2020-11-14 06:0{minute}:00"
        for phase, voltage, current in (
            ("R", 220 + minute, 10 + minute),
            ("S", 221 + minute, 11 + minute),
            ("T", 222 + minute, 12 + minute),
        ):
            rows.append(
                {
                    "ITEM_NAME": f"{phase}상전압",
                    "ITEM_VALUE": voltage,
                    "TIMESTAMP": stamp,
                }
            )
            rows.append(
                {
                    "ITEM_NAME": f"{phase}상전류",
                    "ITEM_VALUE": current,
                    "TIMESTAMP": stamp,
                }
            )
    with ZipFile(path, "w") as archive:
        import json

        archive.writestr(
            AIHUB_BOILER_DEMO_MEMBER,
            json.dumps(
                {
                    "DEVICE_ID": 2297,
                    "DEVICE_BD_ID": 1,
                    "data": rows,
                },
                ensure_ascii=False,
            ),
        )
    return path


def test_prepare_aihub_boiler_demo_owns_replay_and_runtime_policy(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    preset = AihubBoilerDemoConfig(
        archive=archive,
        workspace=tmp_path / "demo",
        opcua_port=4851,
        ui_port=2721,
        speed=60.0,
    )
    at = datetime(2026, 10, 2, 13, 0, tzinfo=UTC)

    preparation = prepare_aihub_boiler_demo(preset, now=at)

    assert preparation.created_workspace is True
    assert preparation.source_id == AIHUB_BOILER_DEMO_SOURCE_ID
    assert preparation.endpoint == "opc.tcp://127.0.0.1:4851/aihub-replay/"
    assert preparation.selection.archive == archive.resolve()
    assert preparation.selection.member == AIHUB_BOILER_DEMO_MEMBER

    repository = JsonSourceRepository(preparation.workspace.source_registry_path)
    source = repository.get(AIHUB_BOILER_DEMO_SOURCE_ID)
    assert source.asset_id == "aihub-boiler-2297"
    assert (
        repository.get_lifecycle(AIHUB_BOILER_DEMO_SOURCE_ID).state
        == SourceLifecycleState.ACTIVE
    )
    control = SqliteCollectionControlRepository(preparation.workspace.collection_control_path)
    record = control.get(AIHUB_BOILER_DEMO_SOURCE_ID)
    assert record is not None
    assert record.desired_state == CollectionDesiredState.RUNNING

    config = load_operations_runtime_config(preparation.workspace.config_path)
    assert config.collection.window_duration_seconds == 30.0
    assert config.analysis.alignment == "bounded-previous"
    assert config.analysis.max_carry_age_seconds == 5.0
    assert config.analysis.alignment_basis == (
        "AI-Hub 239 replay: every channel is written once per recorded minute "
        "(1 s replay time at 60x); unchanged values raise no DataChange; "
        "carry bounded to 5 recorded minutes (5 s replay time)"
    )
    assert config.ui.port == 2721


def test_aihub_boiler_speed_keeps_recorded_window_and_carry_meaning() -> None:
    preset = AihubBoilerDemoConfig(speed=120.0)

    assert preset.replay_record_interval_seconds == 0.5
    assert preset.window_duration_seconds == 15.0
    assert preset.max_carry_age_seconds == 2.5
    assert "0.5 s replay time at 120x" in preset.alignment_basis
    assert "2.5 s replay time" in preset.alignment_basis


def test_prepare_aihub_boiler_demo_does_not_create_workspace_when_archive_is_missing(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "demo"

    with pytest.raises(OSError, match="archive is unavailable"):
        prepare_aihub_boiler_demo(
            AihubBoilerDemoConfig(
                archive=tmp_path / "missing.zip",
                workspace=workspace,
            )
        )

    assert not workspace.exists()


def test_prepare_aihub_boiler_demo_reuses_only_matching_demo_workspace(
    tmp_path: Path,
) -> None:
    archive = _archive(tmp_path)
    preset = AihubBoilerDemoConfig(archive=archive, workspace=tmp_path / "demo")
    at = datetime(2026, 10, 2, 13, 0, tzinfo=UTC)

    first = prepare_aihub_boiler_demo(preset, now=at)
    second = prepare_aihub_boiler_demo(preset, now=at)

    assert first.created_workspace is True
    assert second.created_workspace is False
    control = SqliteCollectionControlRepository(second.workspace.collection_control_path)
    record = control.get(AIHUB_BOILER_DEMO_SOURCE_ID)
    assert record is not None
    assert record.generation == 1


def test_prepare_aihub_boiler_demo_rejects_non_demo_registered_source(tmp_path: Path) -> None:
    archive = _archive(tmp_path)
    workspace = OperationsWorkspace(tmp_path / "demo")
    from industrial_phm.runtime import initialize_operations_workspace

    initialize_operations_workspace(workspace)
    workspace.source_registry_path.write_text(
        '{"schema":"registered-sources-v1","sources":[],"lifecycles":[]}\n',
        encoding="utf-8",
    )
    workspace.phase_unbalance_state_path.write_text("non-demo", encoding="utf-8")

    with pytest.raises(ValueError, match="runtime/history state"):
        prepare_aihub_boiler_demo(
            AihubBoilerDemoConfig(archive=archive, workspace=workspace.root)
        )


def test_run_aihub_boiler_demo_reuses_normal_operations_supervisor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive = _archive(tmp_path)
    preset = AihubBoilerDemoConfig(
        archive=archive,
        workspace=tmp_path / "demo",
        opcua_port=4852,
        ui_port=2722,
    )
    replay = _FakeReplay()
    captured: dict[str, object] = {}

    def launch(argv: tuple[str, ...], log_path: Path) -> _FakeReplay:
        captured["argv"] = argv
        captured["log_path"] = log_path
        return replay

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

    import industrial_phm.demo.aihub_boiler as demo_module

    monkeypatch.setattr(demo_module, "run_operations_supervisor", fake_supervisor)

    exit_code = run_aihub_boiler_demo(
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
        "industrial_phm.demo.aihub_replay",
        "server",
    )
    assert "--loop" in argv
    assert "--speed" in argv
    plan = captured["plan"]
    assert plan.workspace.root == preset.workspace
    assert plan.ui_url == "http://127.0.0.1:2722"
    assert replay.signals == [signal.SIGINT]
