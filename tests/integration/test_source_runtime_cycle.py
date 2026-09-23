from datetime import datetime
from pathlib import Path

import pytest

from industrial_phm.application import (
    FileSourceConfig,
    JsonSourceRepository,
    JsonSourceRuntimeRepository,
    OpcUaSourceConfig,
    RegisteredSource,
    SourceLifecycleState,
    SourceRuntimeCycleFailureScope,
    SourceRuntimeCycleState,
    run_registered_file_source_cycle,
    transition_source_lifecycle,
)
from industrial_phm.connectors import OpcUaNodeMapping


def _write_valid_source(path: Path) -> None:
    path.write_text(
        "timestamp,vibration_x\n2026-09-23T10:00:00+09:00,-1.0\n2026-09-23T10:00:01+09:00,1.0\n",
        encoding="utf-8",
    )


def _registered_source(path: Path) -> RegisteredSource:
    return RegisteredSource(
        source_id="source-a",
        name="Pump source",
        config=FileSourceConfig(
            source_path=str(path),
            asset_id="pump-01",
            measurement_point_id="drive-end",
            channel_columns=("vibration_x",),
            timestamp_column="timestamp",
        ),
        registered_at=datetime.fromisoformat("2026-09-23T09:00:00+09:00"),
    )


def _repositories(
    tmp_path: Path,
) -> tuple[JsonSourceRepository, JsonSourceRuntimeRepository, RegisteredSource]:
    source_path = tmp_path / "pump.csv"
    _write_valid_source(source_path)
    source = _registered_source(source_path)
    source_repository = JsonSourceRepository(tmp_path / "source-registry.json")
    source_repository.register(source)
    runtime_repository = JsonSourceRuntimeRepository(tmp_path / "source-runtime.json")
    return source_repository, runtime_repository, source


def _activate(
    repository: JsonSourceRepository,
    source_id: str,
    *,
    at: str = "2026-09-23T09:30:00+09:00",
) -> None:
    transition_source_lifecycle(
        repository,
        source_id,
        SourceLifecycleState.ACTIVE,
        changed_at=datetime.fromisoformat(at),
    )


def test_registered_source_cycle_skips_non_active_source_without_io(
    tmp_path: Path,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)
    Path(source.config.source_path).unlink()

    result = run_registered_file_source_cycle(
        source_repository,
        source_repository,
        runtime_repository,
        source.source_id,
        executed_at=datetime.fromisoformat("2026-09-23T10:00:00+09:00"),
    )

    assert result.state == SourceRuntimeCycleState.SKIPPED
    assert result.lifecycle_before.state == SourceLifecycleState.REGISTERED
    assert result.lifecycle_after == result.lifecycle_before
    assert result.received is None
    assert result.failure_scope is None
    assert runtime_repository.list_latest_receipts() == ()


def test_registered_source_cycle_records_receipt_for_active_source(
    tmp_path: Path,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)
    _activate(source_repository, source.source_id)

    result = run_registered_file_source_cycle(
        source_repository,
        source_repository,
        runtime_repository,
        source.source_id,
        executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
        received_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
    )

    assert result.state == SourceRuntimeCycleState.SUCCEEDED
    assert result.received is not None
    assert result.failure_scope is None
    assert result.received.receipt.lag_seconds == 4.0
    assert source_repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE
    assert runtime_repository.get_latest_receipt(source.source_id) == result.received.receipt


def test_registered_source_cycle_transitions_active_source_to_error_on_source_failure(
    tmp_path: Path,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)
    _activate(source_repository, source.source_id)
    Path(source.config.source_path).write_text(
        "timestamp,vibration_x\n2026-09-23T10:00:00+09:00,not-numeric\n",
        encoding="utf-8",
    )

    result = run_registered_file_source_cycle(
        source_repository,
        source_repository,
        runtime_repository,
        source.source_id,
        executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
    )

    assert result.state == SourceRuntimeCycleState.FAILED
    assert result.received is None
    assert result.failure_scope == SourceRuntimeCycleFailureScope.SOURCE
    assert result.message is not None
    assert "numeric" in result.message
    lifecycle = source_repository.get_lifecycle(source.source_id)
    assert lifecycle.state == SourceLifecycleState.ERROR
    assert lifecycle.detail == result.message
    assert runtime_repository.get_latest_receipt(source.source_id) is None


def test_registered_source_cycle_reports_platform_failure_without_marking_source_error(
    tmp_path: Path,
) -> None:
    source_repository, _, source = _repositories(tmp_path)
    _activate(source_repository, source.source_id)
    runtime_path = tmp_path / "runtime-as-directory"
    runtime_path.mkdir()
    runtime_repository = JsonSourceRuntimeRepository(runtime_path)

    result = run_registered_file_source_cycle(
        source_repository,
        source_repository,
        runtime_repository,
        source.source_id,
        executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
    )

    assert result.state == SourceRuntimeCycleState.FAILED
    assert result.received is not None
    assert result.failure_scope == SourceRuntimeCycleFailureScope.PLATFORM
    assert result.message is not None
    assert "not a file" in result.message
    assert source_repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE


def test_registered_source_cycle_error_state_requires_explicit_reactivation(
    tmp_path: Path,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)
    _activate(source_repository, source.source_id)
    Path(source.config.source_path).unlink()

    failed = run_registered_file_source_cycle(
        source_repository,
        source_repository,
        runtime_repository,
        source.source_id,
        executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
    )
    skipped = run_registered_file_source_cycle(
        source_repository,
        source_repository,
        runtime_repository,
        source.source_id,
        executed_at=datetime.fromisoformat("2026-09-23T10:00:06+09:00"),
    )

    assert failed.state == SourceRuntimeCycleState.FAILED
    assert failed.failure_scope == SourceRuntimeCycleFailureScope.SOURCE
    assert skipped.state == SourceRuntimeCycleState.SKIPPED
    assert skipped.lifecycle_before.state == SourceLifecycleState.ERROR


def test_registered_source_cycle_rejects_naive_received_at_without_marking_source_error(
    tmp_path: Path,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)
    _activate(source_repository, source.source_id)

    with pytest.raises(ValueError, match="received_at override"):
        run_registered_file_source_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
            received_at=datetime.fromisoformat("2026-09-23T10:00:05"),
        )

    assert source_repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE


def test_registered_source_cycle_rejects_received_at_regression_without_marking_source_error(
    tmp_path: Path,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)
    _activate(source_repository, source.source_id)

    first = run_registered_file_source_cycle(
        source_repository,
        source_repository,
        runtime_repository,
        source.source_id,
        executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
        received_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
    )
    assert first.received is not None

    with pytest.raises(ValueError, match="must not move backwards"):
        run_registered_file_source_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T10:00:06+09:00"),
            received_at=datetime.fromisoformat("2026-09-23T10:00:04+09:00"),
        )

    assert source_repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE
    assert runtime_repository.get_latest_receipt(source.source_id) == first.received.receipt


def test_registered_source_cycle_rejects_same_time_conflict_without_marking_source_error(
    tmp_path: Path,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)
    _activate(source_repository, source.source_id)

    first = run_registered_file_source_cycle(
        source_repository,
        source_repository,
        runtime_repository,
        source.source_id,
        executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
        received_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
    )
    assert first.received is not None

    Path(source.config.source_path).write_text(
        "timestamp,vibration_x\n2026-09-23T10:00:02+09:00,-2.0\n2026-09-23T10:00:03+09:00,2.0\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must reproduce persisted evidence"):
        run_registered_file_source_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T10:00:06+09:00"),
            received_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
        )

    assert source_repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE
    assert runtime_repository.get_latest_receipt(source.source_id) == first.received.receipt


def test_registered_source_cycle_rejects_naive_or_regressing_execution_time(
    tmp_path: Path,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)
    _activate(source_repository, source.source_id)

    with pytest.raises(ValueError, match="timezone-aware"):
        run_registered_file_source_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T10:00:00"),
        )

    with pytest.raises(ValueError, match="before the current lifecycle"):
        run_registered_file_source_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T09:29:59+09:00"),
        )



def test_registered_file_source_cycle_skips_active_opcua_without_lifecycle_error(
    tmp_path: Path,
) -> None:
    source_repository = JsonSourceRepository(tmp_path / "source-registry.json")
    runtime_repository = JsonSourceRuntimeRepository(tmp_path / "source-runtime.json")
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
    source_repository.register(source)
    _activate(source_repository, source.source_id)

    result = run_registered_file_source_cycle(
        source_repository,
        source_repository,
        runtime_repository,
        source.source_id,
        executed_at=datetime.fromisoformat("2026-09-23T10:00:00+09:00"),
    )

    assert result.state == SourceRuntimeCycleState.SKIPPED
    assert result.failure_scope is None
    assert result.received is None
    assert result.lifecycle_before.state == SourceLifecycleState.ACTIVE
    assert result.lifecycle_after == result.lifecycle_before
    assert "requires file" in (result.message or "")
    assert source_repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE
    assert runtime_repository.list_latest_receipts() == ()
