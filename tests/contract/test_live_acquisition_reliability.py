from datetime import UTC, datetime, timedelta
from importlib.util import find_spec
from pathlib import Path

import pytest

from industrial_phm.application import (
    InMemorySourceRepository,
    JsonObservationWindowRepository,
    ObservationWindowCoordinatorPolicy,
    ObservationWindowEventDisposition,
    OpcUaPersistentSessionEvidence,
    OpcUaPersistentSessionState,
    OpcUaSourceConfig,
    RegisteredOpcUaDataChangeEvent,
    RegisteredSource,
    SourceConnectionState,
    SourceDataFlowState,
    SourceLifecycleRecord,
    SourceLifecycleState,
    SpoolToHistoryWriterPolicy,
    assess_source_health,
)
from industrial_phm.connectors import (
    OpcUaNodeMapping,
    OpcUaNodeObservation,
    OpcUaSubscriptionNotification,
)
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime import (
    SqliteAcquisitionSpool,
    SqliteAcquisitionSpoolConfig,
    SqliteAcquisitionTelemetryRepository,
    rebuild_registered_opcua_observation_windows,
    write_next_spool_batch,
)

BASE = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)
EVENT_COUNT = 192
RESTART_AT = EVENT_COUNT // 2
BATCH_SIZE = 24


def _require_duckdb() -> None:
    if find_spec("duckdb") is None:
        pytest.skip("DuckLake history runtime is not installed")


def _source_repository() -> InMemorySourceRepository:
    repository = InMemorySourceRepository()
    repository.register(
        RegisteredSource(
            source_id="source-a",
            name="Reliability soak source",
            config=OpcUaSourceConfig(
                endpoint_url="opc.tcp://127.0.0.1:4840",
                asset_id="pump-01",
                measurement_point_id="drive-end",
                node_mappings=(
                    OpcUaNodeMapping("vibration_x", "ns=2;s=vibration_x"),
                    OpcUaNodeMapping("temperature", "ns=2;s=temperature"),
                ),
            ),
            registered_at=BASE,
        )
    )
    return repository


def _registered_event(index: int) -> RegisteredOpcUaDataChangeEvent:
    nominal_event_at = BASE + timedelta(milliseconds=500 * index)
    event_at = (
        nominal_event_at - timedelta(milliseconds=1_500)
        if index > 0 and index % 17 == 0
        else nominal_event_at
    )
    received_at = BASE + timedelta(seconds=200, milliseconds=10 * index)
    channel_id = "vibration_x" if index % 2 == 0 else "temperature"
    return RegisteredOpcUaDataChangeEvent(
        source_id="source-a",
        asset_id="pump-01",
        endpoint_url="opc.tcp://127.0.0.1:4840",
        measurement_point_id="drive-end",
        collection_index=index,
        notification=OpcUaSubscriptionNotification(
            observation=OpcUaNodeObservation(
                channel_id=channel_id,
                node_id=f"ns=2;s={channel_id}",
                value=float(index),
                status_code=0,
                status_good=True,
                status_text="Good",
                variant_type="Double",
                source_timestamp=event_at,
                server_timestamp=event_at + timedelta(milliseconds=1),
                received_at=received_at,
            ),
            replayed=index == 150,
        ),
    )


def _record_worker_start(
    telemetry: SqliteAcquisitionTelemetryRepository,
    *,
    epoch_baseline: int,
    connected_epoch: int,
    started_at: datetime,
) -> None:
    telemetry.record_session_configuration(
        "source-a",
        callback_queue_maxsize=64,
        recorded_at=started_at,
    )
    telemetry.record_session_evidence(
        OpcUaPersistentSessionEvidence(
            source_id="source-a",
            state=OpcUaPersistentSessionState.DISCONNECTED,
            changed_at=started_at,
            connection_epoch=epoch_baseline,
        )
    )
    telemetry.record_session_evidence(
        OpcUaPersistentSessionEvidence(
            source_id="source-a",
            state=OpcUaPersistentSessionState.CONNECTING,
            changed_at=started_at + timedelta(milliseconds=1),
            connection_epoch=epoch_baseline,
        )
    )
    telemetry.record_session_evidence(
        OpcUaPersistentSessionEvidence(
            source_id="source-a",
            state=OpcUaPersistentSessionState.CONNECTED,
            changed_at=started_at + timedelta(milliseconds=2),
            connection_epoch=connected_epoch,
        )
    )


class _FailFirstAppendHistory:
    def __init__(self, delegate: DuckLakeAssetHistory) -> None:
        self.delegate = delegate
        self.failed = False

    def get_opcua_batch_commit(self, events, *, batch_id, ingestion_mode):
        return self.delegate.get_opcua_batch_commit(
            events,
            batch_id=batch_id,
            ingestion_mode=ingestion_mode,
        )

    def append_opcua_batch(self, events, *, batch_id, ingestion_mode):
        if not self.failed:
            self.failed = True
            raise RuntimeError("simulated temporary DuckLake outage")
        return self.delegate.append_opcua_batch(
            events,
            batch_id=batch_id,
            ingestion_mode=ingestion_mode,
        )


def test_bounded_live_acquisition_soak_survives_restart_and_writer_failure(
    tmp_path: Path,
) -> None:
    _require_duckdb()
    spool_path = tmp_path / "spool.sqlite"
    telemetry_path = tmp_path / "telemetry.sqlite"
    spool = SqliteAcquisitionSpool(
        SqliteAcquisitionSpoolConfig(
            path=spool_path,
            max_events=EVENT_COUNT + 16,
        )
    )
    telemetry = SqliteAcquisitionTelemetryRepository(telemetry_path)
    _record_worker_start(
        telemetry,
        epoch_baseline=0,
        connected_epoch=1,
        started_at=BASE + timedelta(seconds=100),
    )

    accepted = []
    for index in range(RESTART_AT):
        event = _registered_event(index)
        durable = spool.accept_opcua_event(
            event,
            connection_epoch=1,
            event_index=index,
            accepted_at=event.notification.observation.received_at + timedelta(milliseconds=1),
        )
        telemetry.record_opcua_event(durable)
        accepted.append(durable)
        if index == 10:
            repeated = spool.accept_opcua_event(
                event,
                connection_epoch=1,
                event_index=index,
                accepted_at=event.notification.observation.received_at + timedelta(seconds=1),
            )
            assert repeated == durable

    assert spool.pending_event_count() == RESTART_AT

    # Collector process restart: durable spool and telemetry survive, and the new
    # session begins from a new connection epoch. No STOPPED evidence is required
    # from the crashed process.
    spool = SqliteAcquisitionSpool(
        SqliteAcquisitionSpoolConfig(
            path=spool_path,
            max_events=EVENT_COUNT + 16,
        )
    )
    telemetry = SqliteAcquisitionTelemetryRepository(telemetry_path)
    _record_worker_start(
        telemetry,
        epoch_baseline=1,
        connected_epoch=2,
        started_at=BASE + timedelta(seconds=300),
    )

    for index in range(RESTART_AT, EVENT_COUNT):
        event = _registered_event(index)
        event_index = index - RESTART_AT
        durable = spool.accept_opcua_event(
            event,
            connection_epoch=2,
            event_index=event_index,
            accepted_at=event.notification.observation.received_at + timedelta(milliseconds=1),
        )
        telemetry.record_opcua_event(durable)
        accepted.append(durable)

    telemetry.record_session_evidence(
        OpcUaPersistentSessionEvidence(
            source_id="source-a",
            state=OpcUaPersistentSessionState.STOPPED,
            changed_at=BASE + timedelta(seconds=400),
            connection_epoch=2,
            detail="stop-requested",
        )
    )
    assert spool.pending_event_count() == EVENT_COUNT
    assert len({event.local_delivery_identity for event in accepted}) == EVENT_COUNT

    history_config = DuckLakeAssetHistoryConfig(
        catalog_path=tmp_path / "catalog.sqlite",
        data_path=tmp_path / "data",
    )
    history = DuckLakeAssetHistory(history_config)
    failing_history = _FailFirstAppendHistory(history)
    policy = SpoolToHistoryWriterPolicy(
        max_events=BATCH_SIZE,
        max_bytes=10_000_000,
        max_interval_seconds=60.0,
        poll_interval_seconds=0.01,
    )

    with pytest.raises(RuntimeError, match="temporary DuckLake outage"):
        write_next_spool_batch(
            spool,
            failing_history,
            policy=policy,
            batch_id_factory=lambda: "soak-batch-000",
            now_fn=lambda: BASE + timedelta(seconds=500),
            telemetry_recorder=telemetry,
            force=True,
        )

    active = spool.get_active_batch()
    assert active is not None
    assert active.batch_id == "soak-batch-000"
    assert active.event_count == BATCH_SIZE
    failure = telemetry.get("source-a").failure
    assert failure is not None
    assert failure.component.value == "history-writer"

    # Writer process restart: the stable active batch is reused, then the remaining
    # durable backlog is drained in deterministic bounded batches.
    spool = SqliteAcquisitionSpool(
        SqliteAcquisitionSpoolConfig(
            path=spool_path,
            max_events=EVENT_COUNT + 16,
        )
    )
    history = DuckLakeAssetHistory(history_config)
    next_batch_index = 1

    def _next_batch_id() -> str:
        nonlocal next_batch_index
        batch_id = f"soak-batch-{next_batch_index:03d}"
        next_batch_index += 1
        return batch_id

    write_count = 0
    while spool.pending_event_count():
        result = write_next_spool_batch(
            spool,
            history,
            policy=policy,
            batch_id_factory=_next_batch_id,
            now_fn=lambda: BASE + timedelta(seconds=501 + write_count),
            telemetry_recorder=telemetry,
            force=True,
        )
        assert result is not None
        write_count += 1

    assert write_count == EVENT_COUNT // BATCH_SIZE
    assert spool.pending_event_count() == 0
    assert spool.get_active_batch() is None

    raw = history.query_opcua_events("source-a")
    measurements = history.query_measurements(
        "pump-01",
        start_at=BASE - timedelta(seconds=1),
        end_at=BASE + timedelta(seconds=100),
    )
    assert len(raw) == EVENT_COUNT
    assert len(measurements) == EVENT_COUNT
    assert len({event.local_delivery_identity for event in raw}) == EVENT_COUNT
    assert sum(event.event.notification.replayed for event in raw) == 1
    assert {event.connection_epoch for event in raw} == {1, 2}

    source_repository = _source_repository()
    window_path = tmp_path / "windows.json"
    window_repository = JsonObservationWindowRepository(window_path)
    window_policy = ObservationWindowCoordinatorPolicy(
        window_duration_seconds=10.0,
        allowed_lateness_seconds=2.0,
        max_buffered_events=64,
        max_future_skew_seconds=5.0,
        poll_interval_seconds=0.01,
        alignment_origin=BASE,
    )
    first = rebuild_registered_opcua_observation_windows(
        source_repository,
        history,
        window_repository,
        "source-a",
        policy=window_policy,
    )
    assert first.finalized_window_count >= 8
    assert first.disposition_count(ObservationWindowEventDisposition.OUT_OF_ORDER) > 0

    persisted = window_repository.list_windows()
    second = rebuild_registered_opcua_observation_windows(
        source_repository,
        DuckLakeAssetHistory(history_config),
        JsonObservationWindowRepository(window_path),
        "source-a",
        policy=window_policy,
    )
    assert second.finalized_windows == first.finalized_windows
    assert JsonObservationWindowRepository(window_path).list_windows() == persisted

    snapshot = SqliteAcquisitionTelemetryRepository(telemetry_path).get("source-a")
    assert snapshot.session is not None
    assert snapshot.session.state == OpcUaPersistentSessionState.STOPPED
    assert snapshot.session.connection_epoch == 2
    assert snapshot.flow is not None
    assert snapshot.flow.accepted_event_count == EVENT_COUNT - RESTART_AT
    assert snapshot.flow.replayed_event_count == 1
    assert snapshot.history is not None
    assert snapshot.history.snapshot_id >= 0
    assert snapshot.history.source_event_count == BATCH_SIZE
    assert not hasattr(snapshot, "healthy")

    spool_surface = spool.telemetry_snapshot(sampled_at=BASE + timedelta(seconds=600))
    assert spool_surface.pending_event_count == 0
    assert spool_surface.oldest_pending_age_seconds is None

    lifecycle = SourceLifecycleRecord(
        source_id="source-a",
        state=SourceLifecycleState.ACTIVE,
        changed_at=BASE,
    )
    source_health = assess_source_health(
        lifecycle,
        None,
        None,
        as_of=BASE + timedelta(seconds=600),
    )
    assert source_health.connection_state == SourceConnectionState.NOT_INSTRUMENTED
    assert source_health.data_flow_state == SourceDataFlowState.NO_RECEIPT
