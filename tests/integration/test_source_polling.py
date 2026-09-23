from datetime import UTC, datetime
from pathlib import Path

import pytest

import industrial_phm.application.source_polling as source_polling_module
from industrial_phm.application import (
    FileSourceConfig,
    JsonSourceRepository,
    OpcUaSourceConfig,
    ReceivedRegisteredOpcUaObservation,
    RegisteredOpcUaObservation,
    JsonSourceRuntimeRepository,
    RegisteredSource,
    SourceLifecycleState,
    SourcePollingPolicy,
    SourceReceiptEvidence,
    SourceRuntimeCycleResult,
    SourceRuntimeCycleFailureScope,
    SourceRuntimeCycleState,
    poll_registered_file_source,
    poll_registered_source,
    transition_source_lifecycle,
)
from industrial_phm.connectors import (
    OpcUaNodeMapping,
    OpcUaNodeObservation,
    OpcUaReadSnapshot,
)


def _write_source(path: Path) -> None:
    path.write_text(
        "timestamp,vibration_x\n2026-09-23T10:00:00+09:00,-1.0\n2026-09-23T10:00:01+09:00,1.0\n",
        encoding="utf-8",
    )


def _repositories(
    tmp_path: Path,
) -> tuple[JsonSourceRepository, JsonSourceRuntimeRepository, RegisteredSource]:
    source_path = tmp_path / "pump.csv"
    _write_source(source_path)
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
    source_repository = JsonSourceRepository(tmp_path / "source-registry.json")
    source_repository.register(source)
    runtime_repository = JsonSourceRuntimeRepository(tmp_path / "source-runtime.json")
    return source_repository, runtime_repository, source


def _opcua_repositories(
    tmp_path: Path,
) -> tuple[JsonSourceRepository, JsonSourceRuntimeRepository, RegisteredSource]:
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
    source_repository = JsonSourceRepository(tmp_path / "opcua-source-registry.json")
    source_repository.register(source)
    runtime_repository = JsonSourceRuntimeRepository(tmp_path / "opcua-source-runtime.json")
    return source_repository, runtime_repository, source


def _opcua_received() -> ReceivedRegisteredOpcUaObservation:
    snapshot = OpcUaReadSnapshot(
        endpoint_url="opc.tcp://plc.example.test:4840",
        connected_at=datetime.fromisoformat("2026-09-23T01:00:00+00:00"),
        completed_at=datetime.fromisoformat("2026-09-23T01:00:01+00:00"),
        observations=(
            OpcUaNodeObservation(
                channel_id="vibration_x",
                node_id="ns=2;s=Machine/VibrationX",
                value=12.5,
                status_code=0,
                status_good=True,
                status_text="Good",
                variant_type="Double",
                source_timestamp=datetime.fromisoformat("2026-09-23T00:59:59+00:00"),
                server_timestamp=None,
                received_at=datetime.fromisoformat("2026-09-23T01:00:01+00:00"),
            ),
        ),
    )
    return ReceivedRegisteredOpcUaObservation(
        observation=RegisteredOpcUaObservation(
            source_id="opcua-source",
            asset_id="pump-01",
            measurement_point_id="drive-end",
            snapshot=snapshot,
        ),
        receipt=SourceReceiptEvidence(
            source_id="opcua-source",
            received_at=datetime.fromisoformat("2026-09-23T01:00:02+00:00"),
            observed_at=datetime.fromisoformat("2026-09-23T00:59:59+00:00"),
        ),
    )


def _activate(repository: JsonSourceRepository, source_id: str) -> None:
    transition_source_lifecycle(
        repository,
        source_id,
        SourceLifecycleState.ACTIVE,
        changed_at=datetime.fromisoformat("2026-09-23T09:30:00+09:00"),
    )


@pytest.mark.parametrize("interval_seconds", [0.0, -1.0, float("inf"), float("nan")])
def test_source_polling_policy_requires_positive_finite_interval(
    interval_seconds: float,
) -> None:
    with pytest.raises(ValueError, match="positive finite"):
        SourcePollingPolicy(interval_seconds=interval_seconds)


@pytest.mark.parametrize("max_cycles", [0, -1, True])
def test_source_polling_policy_requires_positive_cycle_limit(max_cycles: int) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        SourcePollingPolicy(interval_seconds=1.0, max_cycles=max_cycles)


def test_source_polling_runs_bounded_successful_cycles_and_sleeps_between(
    tmp_path: Path,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)
    _activate(source_repository, source.source_id)
    sleeps: list[float] = []

    results = tuple(
        poll_registered_file_source(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            SourcePollingPolicy(interval_seconds=0.25, max_cycles=3),
            sleep_fn=sleeps.append,
        )
    )

    assert [result.state for result in results] == [
        SourceRuntimeCycleState.SUCCEEDED,
        SourceRuntimeCycleState.SUCCEEDED,
        SourceRuntimeCycleState.SUCCEEDED,
    ]
    assert sleeps == [0.25, 0.25]
    assert runtime_repository.get_latest_receipt(source.source_id) is not None
    assert source_repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE


def test_generic_source_polling_dispatches_bounded_opcua_cycles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_repository, runtime_repository, source = _opcua_repositories(tmp_path)
    _activate(source_repository, source.source_id)
    received = _opcua_received()
    call_count = 0
    sleeps: list[float] = []

    async def _run(
        _source_repository: JsonSourceRepository,
        _lifecycle_repository: JsonSourceRepository,
        _runtime_repository: JsonSourceRuntimeRepository,
        source_id: str,
    ) -> SourceRuntimeCycleResult:
        nonlocal call_count
        call_count += 1
        lifecycle = source_repository.get_lifecycle(source_id)
        return SourceRuntimeCycleResult(
            source_id=source_id,
            state=SourceRuntimeCycleState.SUCCEEDED,
            executed_at=datetime.now(UTC),
            lifecycle_before=lifecycle,
            lifecycle_after=lifecycle,
            received=received,
        )

    monkeypatch.setattr(
        source_polling_module,
        "run_registered_opcua_source_cycle",
        _run,
    )

    results = tuple(
        poll_registered_source(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            SourcePollingPolicy(interval_seconds=0.25, max_cycles=3),
            sleep_fn=sleeps.append,
        )
    )

    assert [result.state for result in results] == [
        SourceRuntimeCycleState.SUCCEEDED,
        SourceRuntimeCycleState.SUCCEEDED,
        SourceRuntimeCycleState.SUCCEEDED,
    ]
    assert call_count == 3
    assert sleeps == [0.25, 0.25]


def test_source_polling_stops_without_sleep_for_non_active_source(tmp_path: Path) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)
    sleeps: list[float] = []

    results = tuple(
        poll_registered_file_source(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            SourcePollingPolicy(interval_seconds=0.25),
            sleep_fn=sleeps.append,
        )
    )

    assert len(results) == 1
    assert results[0].state == SourceRuntimeCycleState.SKIPPED
    assert sleeps == []


def test_source_polling_stops_after_source_failure_and_preserves_error_lifecycle(
    tmp_path: Path,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)
    _activate(source_repository, source.source_id)
    Path(source.config.source_path).write_text(
        "timestamp,vibration_x\n2026-09-23T10:00:00+09:00,not-numeric\n",
        encoding="utf-8",
    )
    sleeps: list[float] = []

    results = tuple(
        poll_registered_file_source(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            SourcePollingPolicy(interval_seconds=0.25),
            sleep_fn=sleeps.append,
        )
    )

    assert len(results) == 1
    assert results[0].state == SourceRuntimeCycleState.FAILED
    assert results[0].failure_scope == SourceRuntimeCycleFailureScope.SOURCE
    assert source_repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ERROR
    assert sleeps == []


def test_source_polling_stops_after_platform_failure_without_retry(
    tmp_path: Path,
) -> None:
    source_repository, _, source = _repositories(tmp_path)
    _activate(source_repository, source.source_id)
    runtime_path = tmp_path / "runtime-as-directory"
    runtime_path.mkdir()
    runtime_repository = JsonSourceRuntimeRepository(runtime_path)
    sleeps: list[float] = []

    results = tuple(
        poll_registered_file_source(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            SourcePollingPolicy(interval_seconds=0.25),
            sleep_fn=sleeps.append,
        )
    )

    assert len(results) == 1
    assert results[0].state == SourceRuntimeCycleState.FAILED
    assert results[0].failure_scope == SourceRuntimeCycleFailureScope.PLATFORM
    assert source_repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE
    assert sleeps == []


def test_source_polling_observes_pause_between_cycles(tmp_path: Path) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)
    _activate(source_repository, source.source_id)
    sleep_calls = 0

    def pause_on_first_sleep(interval_seconds: float) -> None:
        nonlocal sleep_calls
        assert interval_seconds == 0.25
        sleep_calls += 1
        transition_source_lifecycle(
            source_repository,
            source.source_id,
            SourceLifecycleState.PAUSED,
            changed_at=datetime.now(UTC),
        )

    results = tuple(
        poll_registered_file_source(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            SourcePollingPolicy(interval_seconds=0.25),
            sleep_fn=pause_on_first_sleep,
        )
    )

    assert [result.state for result in results] == [
        SourceRuntimeCycleState.SUCCEEDED,
        SourceRuntimeCycleState.SKIPPED,
    ]
    assert sleep_calls == 1
    assert source_repository.get_lifecycle(source.source_id).state == SourceLifecycleState.PAUSED
