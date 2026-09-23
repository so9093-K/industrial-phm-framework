from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import industrial_phm.commands.operations as operations_module
from industrial_phm.application import (
    FileSourceConfig,
    JsonSourceRepository,
    OpcUaSourceConfig,
    RegisteredSource,
    SourceRuntimeCycleState,
    SourceLifecycleState,
    transition_source_lifecycle,
)
from industrial_phm.connectors import OpcUaNodeMapping
from industrial_phm.cli import main


def _register_source(tmp_path: Path) -> tuple[Path, Path, RegisteredSource]:
    source_path = tmp_path / "pump.csv"
    source_path.write_text(
        "timestamp,vibration_x\n2026-09-23T10:00:00+09:00,-1.0\n2026-09-23T10:00:01+09:00,1.0\n",
        encoding="utf-8",
    )
    source = RegisteredSource(
        source_id="source-a",
        name="Pump source",
        config=FileSourceConfig(
            source_path=str(source_path),
            asset_id="pump-01",
            measurement_point_id="drive-end",
            channel_columns=("vibration_x",),
            timestamp_column="timestamp",
        ),
        registered_at=datetime.fromisoformat("2026-09-23T09:00:00+09:00"),
    )
    registry_path = tmp_path / "source-registry.json"
    runtime_path = tmp_path / "source-runtime.json"
    JsonSourceRepository(registry_path).register(source)
    return registry_path, runtime_path, source


def _register_opcua_source(
    tmp_path: Path,
) -> tuple[Path, Path, RegisteredSource]:
    source = RegisteredSource(
        source_id="opcua-source",
        name="Pump OPC UA",
        config=OpcUaSourceConfig(
            endpoint_url="opc.tcp://plc.example.test:4840",
            asset_id="pump-01",
            measurement_point_id="drive-end",
            node_mappings=(
                OpcUaNodeMapping(
                    channel_id="vibration_x",
                    node_id="ns=2;s=Machine/VibrationX",
                ),
            ),
        ),
        registered_at=datetime.fromisoformat("2026-09-23T09:00:00+09:00"),
    )
    registry_path = tmp_path / "opcua-source-registry.json"
    runtime_path = tmp_path / "opcua-source-runtime.json"
    JsonSourceRepository(registry_path).register(source)
    return registry_path, runtime_path, source


def test_operations_poll_source_runs_bounded_active_cycles(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry_path, runtime_path, source = _register_source(tmp_path)
    repository = JsonSourceRepository(registry_path)
    transition_source_lifecycle(
        repository,
        source.source_id,
        SourceLifecycleState.ACTIVE,
        changed_at=datetime.fromisoformat("2026-09-23T09:30:00+09:00"),
    )

    exit_code = main(
        [
            "operations",
            "poll-source",
            "--registry",
            str(registry_path),
            "--runtime-state",
            str(runtime_path),
            "--source-id",
            source.source_id,
            "--interval-seconds",
            "0.001",
            "--max-cycles",
            "2",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "cycle 1: succeeded" in captured.out
    assert "cycle 2: succeeded" in captured.out
    assert captured.err == ""


def test_operations_poll_source_dispatches_registered_opcua_source(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry_path, runtime_path, source = _register_opcua_source(tmp_path)
    repository = JsonSourceRepository(registry_path)
    transition_source_lifecycle(
        repository,
        source.source_id,
        SourceLifecycleState.ACTIVE,
        changed_at=datetime.fromisoformat("2026-09-23T09:30:00+09:00"),
    )
    dispatched: list[str] = []

    def _poll(
        source_repository,
        _lifecycle_repository,
        _runtime_repository,
        source_id,
        policy,
    ):
        registered = source_repository.get(source_id)
        assert isinstance(registered.config, OpcUaSourceConfig)
        assert policy.max_cycles == 1
        dispatched.append(source_id)
        yield SimpleNamespace(
            state=SourceRuntimeCycleState.SUCCEEDED,
            received=SimpleNamespace(
                receipt=SimpleNamespace(
                    received_at=datetime.fromisoformat("2026-09-23T10:00:02+09:00")
                )
            ),
            failure_scope=None,
            message=None,
        )

    monkeypatch.setattr(operations_module, "poll_registered_source", _poll)

    exit_code = main(
        [
            "operations",
            "poll-source",
            "--registry",
            str(registry_path),
            "--runtime-state",
            str(runtime_path),
            "--source-id",
            source.source_id,
            "--max-cycles",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert dispatched == [source.source_id]
    assert "cycle 1: succeeded" in captured.out
    assert "received_at=2026-09-23T10:00:02+09:00" in captured.out
    assert captured.err == ""


def test_operations_poll_source_returns_action_required_for_non_active_source(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry_path, runtime_path, source = _register_source(tmp_path)

    exit_code = main(
        [
            "operations",
            "poll-source",
            "--registry",
            str(registry_path),
            "--runtime-state",
            str(runtime_path),
            "--source-id",
            source.source_id,
            "--max-cycles",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "cycle 1: skipped" in captured.err
    assert "requires active" in captured.err


def test_operations_poll_source_rejects_shared_registry_runtime_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry_path, _, source = _register_source(tmp_path)

    exit_code = main(
        [
            "operations",
            "poll-source",
            "--registry",
            str(registry_path),
            "--runtime-state",
            str(registry_path),
            "--source-id",
            source.source_id,
            "--max-cycles",
            "1",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "must differ" in captured.err
