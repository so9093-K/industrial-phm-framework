from datetime import UTC, datetime, timedelta
from pathlib import Path

from industrial_phm.application import (
    AcquisitionFailureComponent,
    AcquisitionFailureTelemetry,
    CollectionServiceRuntimeState,
    HistoricalBatchCommit,
    ObservationWindowCoordinatorCycleResult,
    ObservationWindowEventDisposition,
    ObservationWindowIngestResult,
    OpcUaEventTimePolicy,
    OpcUaPersistentSessionEvidence,
    OpcUaPersistentSessionState,
    RegisteredOpcUaDataChangeEvent,
    SpoolHistoryBatchWriteResult,
    build_acquisition_telemetry_surface,
)
from industrial_phm.connectors import (
    OpcUaNodeObservation,
    OpcUaSubscriptionNotification,
)
from industrial_phm.runtime import (
    SqliteAcquisitionSpool,
    SqliteAcquisitionSpoolConfig,
    SqliteAcquisitionTelemetryRepository,
)

BASE = datetime(2026, 9, 28, 6, 0, tzinfo=UTC)


def _session(
    state: OpcUaPersistentSessionState,
    *,
    seconds: float,
    epoch: int,
    reconnect_attempt: int = 0,
    detail: str | None = None,
) -> OpcUaPersistentSessionEvidence:
    return OpcUaPersistentSessionEvidence(
        source_id="source-a",
        state=state,
        changed_at=BASE + timedelta(seconds=seconds),
        connection_epoch=epoch,
        reconnect_attempt_index=reconnect_attempt,
        detail=detail,
    )


def _registered_event(
    *,
    event_index: int,
    status_good: bool = True,
    replayed: bool = False,
) -> RegisteredOpcUaDataChangeEvent:
    received_at = BASE + timedelta(seconds=1 + event_index)
    return RegisteredOpcUaDataChangeEvent(
        source_id="source-a",
        asset_id="pump-01",
        endpoint_url="opc.tcp://127.0.0.1:4840",
        measurement_point_id="drive-end",
        collection_index=event_index,
        notification=OpcUaSubscriptionNotification(
            observation=OpcUaNodeObservation(
                channel_id="vibration_x",
                node_id="ns=2;s=vibration_x",
                value=float(event_index + 1) if status_good else None,
                status_code=0 if status_good else 0x8000_0000,
                status_good=status_good,
                status_text="Good" if status_good else "Bad",
                variant_type="Double",
                source_timestamp=received_at - timedelta(milliseconds=20),
                server_timestamp=received_at - timedelta(milliseconds=10),
                received_at=received_at,
            ),
            replayed=replayed,
        ),
    )


def test_acquisition_telemetry_is_restart_safe_and_keeps_runtime_dimensions_separate(
    tmp_path: Path,
) -> None:
    path = tmp_path / "acquisition-telemetry.sqlite"
    repository = SqliteAcquisitionTelemetryRepository(path)
    repository.initialize()
    repository.record_session_configuration(
        "source-a",
        callback_queue_maxsize=16,
        recorded_at=BASE,
    )
    repository.record_session_evidence(
        _session(OpcUaPersistentSessionState.DISCONNECTED, seconds=0, epoch=2)
    )
    repository.record_session_evidence(
        _session(OpcUaPersistentSessionState.CONNECTING, seconds=1, epoch=2)
    )
    repository.record_session_evidence(
        _session(OpcUaPersistentSessionState.CONNECTED, seconds=2, epoch=3)
    )

    registered = _registered_event(
        event_index=0,
        status_good=False,
        replayed=True,
    )
    event = SqliteAcquisitionSpool(
        SqliteAcquisitionSpoolConfig(tmp_path / "event-spool.sqlite")
    ).accept_opcua_event(
        registered,
        connection_epoch=3,
        event_index=0,
        accepted_at=BASE + timedelta(seconds=3.1),
        event_time_policy=OpcUaEventTimePolicy(),
    )
    repository.record_opcua_event(event)
    repository.record_callback_queue_overflow(
        "source-a",
        occurred_at=BASE + timedelta(seconds=4),
    )
    repository.record_session_evidence(
        _session(
            OpcUaPersistentSessionState.RECONNECT_WAIT,
            seconds=5,
            epoch=3,
            detail="subscription-queue-overflow",
        )
    )

    snapshot = repository.get("source-a")
    assert snapshot.session is not None
    assert snapshot.session.state == OpcUaPersistentSessionState.RECONNECT_WAIT
    assert snapshot.session.callback_queue_maxsize == 16
    assert snapshot.session.callback_queue_depth is None
    assert snapshot.session.callback_queue_high_watermark is None
    assert snapshot.session.callback_queue_overflow_count == 1
    assert snapshot.session.connected_since is None
    assert snapshot.session.last_disconnect_at == BASE + timedelta(seconds=5)

    assert snapshot.flow is not None
    assert snapshot.flow.accepted_event_count == 1
    assert snapshot.flow.replayed_event_count == 1
    assert snapshot.flow.bad_status_event_count == 1
    assert snapshot.flow.last_delivery_identity == ("source-a", 3, 0)
    assert snapshot.flow.last_source_timestamp == event.event_time.source_timestamp
    assert snapshot.flow.last_received_at == event.event_time.received_at
    assert snapshot.flow.last_ingested_at == event.event_time.ingested_at
    assert snapshot.flow.average_event_rate_hz(as_of=BASE + timedelta(seconds=10)) == 0.1
    assert not hasattr(snapshot, "healthy")

    restarted = SqliteAcquisitionTelemetryRepository(path)
    assert restarted.get("source-a") == snapshot

    # A new worker always starts with DISCONNECTED, even if the previous process died
    # before it could persist STOPPED. Flow counters belong to the new worker session.
    restarted.record_session_evidence(
        _session(OpcUaPersistentSessionState.DISCONNECTED, seconds=10, epoch=3)
    )
    after_restart = restarted.get("source-a")
    assert after_restart.session is not None
    assert after_restart.session.worker_started_at == BASE + timedelta(seconds=10)
    assert after_restart.session.callback_queue_maxsize == 16
    assert after_restart.session.callback_queue_overflow_count == 0
    assert after_restart.flow is not None
    assert after_restart.flow.accepted_event_count == 0


def test_acquisition_telemetry_records_history_window_failure_and_spool_surface(
    tmp_path: Path,
) -> None:
    telemetry = SqliteAcquisitionTelemetryRepository(tmp_path / "acquisition-telemetry.sqlite")
    telemetry.record_session_configuration(
        "source-a",
        callback_queue_maxsize=8,
        recorded_at=BASE,
    )
    telemetry.record_session_evidence(
        _session(OpcUaPersistentSessionState.DISCONNECTED, seconds=0, epoch=0)
    )

    history_result = SpoolHistoryBatchWriteResult(
        commit=HistoricalBatchCommit(
            batch_id="batch-1",
            snapshot_id=7,
            event_count=2,
            committed_at=BASE + timedelta(seconds=20),
        ),
        payload_bytes=2048,
        write_started_at=BASE + timedelta(seconds=19),
        acknowledged_at=BASE + timedelta(seconds=21),
        recovered_existing_commit=False,
    )
    telemetry.record_history_batch(
        history_result,
        source_event_counts={"source-a": 2},
    )

    cycle = ObservationWindowCoordinatorCycleResult(
        source_id="source-a",
        finalized_windows=(),
        event_results=(
            ObservationWindowIngestResult(
                disposition=ObservationWindowEventDisposition.IN_ORDER,
                local_delivery_identity=("source-a", 1, 0),
                event_at=BASE + timedelta(seconds=2),
                watermark_at_ingest=BASE + timedelta(seconds=1),
            ),
            ObservationWindowIngestResult(
                disposition=ObservationWindowEventDisposition.LATE,
                local_delivery_identity=("source-a", 1, 1),
                event_at=BASE + timedelta(seconds=1),
                watermark_at_ingest=BASE + timedelta(seconds=5),
            ),
        ),
        watermark=BASE + timedelta(seconds=5),
        active_window_count=1,
    )
    telemetry.record_window_cycle(
        cycle,
        recorded_at=BASE + timedelta(seconds=22),
    )
    telemetry.record_failure(
        AcquisitionFailureTelemetry(
            source_id="source-a",
            component=AcquisitionFailureComponent.HISTORY_WRITER,
            occurred_at=BASE + timedelta(seconds=23),
            detail="RuntimeError: storage unavailable",
        )
    )

    spool = SqliteAcquisitionSpool(SqliteAcquisitionSpoolConfig(tmp_path / "spool.sqlite"))
    first = spool.accept_opcua_event(
        _registered_event(event_index=0),
        connection_epoch=1,
        event_index=0,
        accepted_at=BASE + timedelta(seconds=2),
    )
    spool.accept_opcua_event(
        _registered_event(event_index=1),
        connection_epoch=1,
        event_index=1,
        accepted_at=BASE + timedelta(seconds=3),
    )
    batch = spool.assign_next_batch(
        batch_id="active-batch",
        max_events=1,
        created_at=BASE + timedelta(seconds=4),
    )
    assert batch is not None and batch.events == (first,)

    surface = build_acquisition_telemetry_surface(
        telemetry,
        spool,
        "source-a",
        sampled_at=BASE + timedelta(seconds=10),
    )
    assert surface.source.history is not None
    assert surface.source.history.batch_id == "batch-1"
    assert surface.source.history.snapshot_id == 7
    assert surface.source.window is not None
    assert surface.source.window.in_order_count == 1
    assert surface.source.window.late_count == 1
    assert surface.source.window.watermark == BASE + timedelta(seconds=5)
    assert surface.source.failure is not None
    assert surface.source.failure.component == AcquisitionFailureComponent.HISTORY_WRITER

    assert surface.spool.pending_event_count == 2
    assert surface.spool.payload_bytes > 0
    assert surface.spool.active_batch_id == "active-batch"
    assert surface.spool.active_batch_event_count == 1
    assert surface.spool.active_batch_payload_bytes > 0
    assert surface.spool.oldest_accepted_at == BASE + timedelta(seconds=2)
    assert surface.spool.oldest_pending_age_seconds == 8.0


def test_collection_service_runtime_heartbeat_is_separate_and_restart_safe(tmp_path: Path) -> None:
    path = tmp_path / "acquisition-telemetry.sqlite"
    repository = SqliteAcquisitionTelemetryRepository(path)

    assert repository.get_collection_service_runtime() is None
    repository.record_collection_service_start(started_at=BASE)
    started = repository.get_collection_service_runtime()
    assert started is not None
    assert started.state == CollectionServiceRuntimeState.RUNNING
    assert started.started_at == BASE
    assert started.heartbeat_at == BASE
    assert started.reconcile_count == 0
    assert started.owned_source_count == 0

    repository.record_collection_service_heartbeat(
        heartbeat_at=BASE + timedelta(seconds=2),
        reconcile_count=4,
        owned_source_count=2,
    )
    heartbeat = SqliteAcquisitionTelemetryRepository(path).get_collection_service_runtime()
    assert heartbeat is not None
    assert heartbeat.state == CollectionServiceRuntimeState.RUNNING
    assert heartbeat.heartbeat_at == BASE + timedelta(seconds=2)
    assert heartbeat.reconcile_count == 4
    assert heartbeat.owned_source_count == 2

    repository.record_collection_service_stop(
        stopped_at=BASE + timedelta(seconds=3),
        reconcile_count=5,
    )
    stopped = repository.get_collection_service_runtime()
    assert stopped is not None
    assert stopped.state == CollectionServiceRuntimeState.STOPPED
    assert stopped.owned_source_count == 0

    repository.record_collection_service_start(started_at=BASE + timedelta(minutes=1))
    restarted = repository.get_collection_service_runtime()
    assert restarted is not None
    assert restarted.state == CollectionServiceRuntimeState.RUNNING
    assert restarted.started_at == BASE + timedelta(minutes=1)
    assert restarted.reconcile_count == 0

    repository.record_collection_service_failure(
        "RuntimeError: coordinator stopped",
        occurred_at=BASE + timedelta(minutes=1, seconds=2),
    )
    failed = repository.get_collection_service_runtime()
    assert failed is not None
    assert failed.state == CollectionServiceRuntimeState.FAILED
    assert failed.last_failure == "RuntimeError: coordinator stopped"


def test_incremental_window_cycles_accumulate_counts_and_keep_last_finalized(tmp_path):
    # Phase 10 soak: incremental cycles report only new work, so System showed
    # "0 finalized windows" and no latest input after dozens of analyzed windows.
    import sys

    sys.path.insert(0, str(Path(__file__).parents[1] / "unit"))
    from test_window_analysis_input import END, START, _event

    from industrial_phm.application import ObservationWindowBuffer

    buffer = ObservationWindowBuffer(
        window_id="w-1",
        source_id="site-opcua",
        asset_id="motor-7",
        measurement_point_id="mcc-3",
        expected_channel_ids=("va",),
        window_start=START,
        window_end=END,
        max_buffered_events=4,
        max_future_skew_seconds=5.0,
    )
    buffer.ingest(_event("va", 10, 220.0, 0))
    buffer.advance_watermark(END)
    window = buffer.finalize(finalized_at=END)

    def cycle(finalized, events):
        return ObservationWindowCoordinatorCycleResult(
            source_id="site-opcua",
            finalized_windows=finalized,
            event_results=tuple(
                ObservationWindowIngestResult(
                    disposition=ObservationWindowEventDisposition.IN_ORDER,
                    local_delivery_identity=("site-opcua", 1, index),
                    event_at=START + timedelta(seconds=index),
                    watermark_at_ingest=START,
                )
                for index in events
            ),
            watermark=END,
            active_window_count=1,
        )

    telemetry = SqliteAcquisitionTelemetryRepository(tmp_path / "telemetry.sqlite")
    telemetry.record_window_cycle(cycle((window,), (0, 1)), recorded_at=END)
    telemetry.record_window_cycle(cycle((), (2,)), recorded_at=END + timedelta(seconds=1))
    telemetry.record_window_cycle(cycle((), ()), recorded_at=END + timedelta(seconds=2))

    recorded = telemetry.get("site-opcua").window
    assert recorded.finalized_window_count == 1
    assert recorded.historical_event_count == 3
    assert recorded.in_order_count == 3
    assert recorded.last_finalized_window_id == "w-1"
    assert recorded.last_finalized_window_end == END


def test_new_worker_keeps_the_previous_live_receive_time(tmp_path: Path) -> None:
    # Phase 10 soak: while a source refused connections each new worker started with
    # an empty flow, so "last received data" disappeared. The receive clock is kept;
    # history commit times are not substituted for it.
    repository = SqliteAcquisitionTelemetryRepository(tmp_path / "telemetry.sqlite")
    repository.record_session_configuration("source-a", callback_queue_maxsize=16, recorded_at=BASE)
    for state, seconds in (
        (OpcUaPersistentSessionState.DISCONNECTED, 0),
        (OpcUaPersistentSessionState.CONNECTING, 1),
        (OpcUaPersistentSessionState.CONNECTED, 2),
    ):
        repository.record_session_evidence(_session(state, seconds=seconds, epoch=3))
    event = SqliteAcquisitionSpool(
        SqliteAcquisitionSpoolConfig(tmp_path / "spool.sqlite")
    ).accept_opcua_event(
        _registered_event(event_index=0),
        connection_epoch=3,
        event_index=0,
        accepted_at=BASE + timedelta(seconds=3),
        event_time_policy=OpcUaEventTimePolicy(),
    )
    repository.record_opcua_event(event)
    received = repository.get("source-a").flow.last_received_at
    assert received is not None

    # Two refused workers in a row: each restarts with an empty flow.
    for seconds in (10, 20):
        repository.record_session_evidence(
            _session(OpcUaPersistentSessionState.DISCONNECTED, seconds=seconds, epoch=4)
        )
    snapshot = repository.get("source-a")
    assert snapshot.flow.last_received_at is None
    assert snapshot.last_receipt is not None
    assert snapshot.last_receipt.received_at == received
    assert snapshot.last_receipt.delivery_identity == ("source-a", 3, 0)
    assert snapshot.last_received_at == received
