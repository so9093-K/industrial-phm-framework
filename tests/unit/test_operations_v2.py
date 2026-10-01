from datetime import UTC, datetime, timedelta

from industrial_phm.application import (
    AnalysisRun,
    FileSourceConfig,
    RegisteredSource,
    SourceFreshnessPolicy,
    SourceLifecycleRecord,
    SourceLifecycleState,
    SourceReceiptEvidence,
    build_operations_attention_queue,
    build_operations_overview,
)
from industrial_phm.application.operations_v2 import (
    OperationsMonitorStageKind,
    OperationsMonitorStatus,
    build_operations_monitor_view,
)
from industrial_phm.application.window_analysis_runtime import (
    WindowAnalysisRunnerState,
    WindowAnalysisRunnerTelemetry,
)
from industrial_phm.contracts import DataQualityAssessment

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def _source(
    source_id: str = "source-a",
    asset_id: str = "boiler-01",
) -> RegisteredSource:
    return RegisteredSource(
        source_id=source_id,
        name=source_id,
        config=FileSourceConfig(
            source_path=f"data/{source_id}.csv",
            asset_id=asset_id,
            channel_columns=("value",),
            sampling_rate_hz=1.0,
        ),
        registered_at=NOW - timedelta(days=1),
    )


def _overview(
    *,
    source: RegisteredSource | None = None,
    observed_at: datetime,
    max_age_seconds: float,
):
    selected = source or _source()
    lifecycle = SourceLifecycleRecord(
        source_id=selected.source_id,
        state=SourceLifecycleState.ACTIVE,
        changed_at=NOW - timedelta(hours=1),
    )
    receipt = SourceReceiptEvidence(
        source_id=selected.source_id,
        observed_at=observed_at,
        received_at=observed_at + timedelta(seconds=1),
    )
    policy = SourceFreshnessPolicy(
        source_id=selected.source_id,
        max_observation_age_seconds=max_age_seconds,
        changed_at=NOW - timedelta(hours=1),
    )
    return selected, build_operations_overview(
        sources=(selected,),
        lifecycle_records=(lifecycle,),
        receipts=(receipt,),
        freshness_policies=(policy,),
        connection_attempts=(),
        analysis_runs=(),
        findings=(),
        review_events=(),
        as_of=NOW,
    )


def _analysis_run() -> AnalysisRun:
    return AnalysisRun(
        analysis_run_id="analysis-1",
        asset_id="boiler-01",
        source_id="source-a",
        observed_start_at=NOW - timedelta(minutes=1),
        observed_end_at=NOW - timedelta(seconds=10),
        started_at=NOW - timedelta(seconds=5),
        completed_at=NOW - timedelta(seconds=2),
        data_quality=DataQualityAssessment(),
        capability_ids=("three-phase-unbalance-v1",),
    )


def _runner(*, heartbeat_at: datetime) -> WindowAnalysisRunnerTelemetry:
    return WindowAnalysisRunnerTelemetry(
        state=WindowAnalysisRunnerState.RUNNING,
        started_at=NOW - timedelta(minutes=10),
        heartbeat_at=heartbeat_at,
        cycle_count=4,
        analyzed_count=1,
        skipped_count=0,
        last_cycle_completed_at=heartbeat_at,
        last_analysis_at=heartbeat_at - timedelta(seconds=1),
        last_analysis_run_id="analysis-1",
    )


def test_monitor_translates_current_evidence_into_small_operator_vocabulary() -> None:
    source, overview = _overview(
        observed_at=NOW - timedelta(seconds=5),
        max_age_seconds=60,
    )
    run = _analysis_run()

    monitor = build_operations_monitor_view(
        sources=(source,),
        overview=overview,
        attention=build_operations_attention_queue(overview=overview),
        analysis_runs=(run,),
        analysis_runtime=_runner(heartbeat_at=NOW - timedelta(seconds=1)),
        as_of=NOW,
    )

    assert tuple(stage.kind for stage in monitor.stages) == tuple(OperationsMonitorStageKind)
    assert monitor.stages[0].status == OperationsMonitorStatus.RUNNING
    assert monitor.stages[1].status == OperationsMonitorStatus.WAITING
    assert monitor.stages[2].status == OperationsMonitorStatus.UNAVAILABLE
    assert monitor.stages[3].status == OperationsMonitorStatus.RUNNING
    assert monitor.stages[4].status == OperationsMonitorStatus.WAITING

    asset = monitor.assets[0]
    assert asset.asset_id == "boiler-01"
    assert asset.status == OperationsMonitorStatus.RUNNING
    assert asset.latest_analysis_at == run.completed_at
    assert asset.attention_count == 0
    assert monitor.attention_count == 0
    assert monitor.activities[0].title == "Analysis completed"


def test_monitor_marks_stale_runner_heartbeat_as_delayed_attention() -> None:
    source, overview = _overview(
        observed_at=NOW - timedelta(seconds=5),
        max_age_seconds=60,
    )
    monitor = build_operations_monitor_view(
        sources=(source,),
        overview=overview,
        attention=build_operations_attention_queue(overview=overview),
        analysis_runtime=_runner(heartbeat_at=NOW - timedelta(seconds=45)),
        as_of=NOW,
    )

    analysis = next(
        stage for stage in monitor.stages if stage.kind == OperationsMonitorStageKind.ANALYSIS
    )
    assert analysis.status == OperationsMonitorStatus.DELAYED
    assert "45s old" in analysis.summary
    assert monitor.attention_count == 1
    assert monitor.attention[0].title == "Analysis service is not updating"


def test_monitor_surfaces_stale_source_as_asset_attention_not_asset_health() -> None:
    source, overview = _overview(
        observed_at=NOW - timedelta(minutes=2),
        max_age_seconds=30,
    )
    monitor = build_operations_monitor_view(
        sources=(source,),
        overview=overview,
        attention=build_operations_attention_queue(overview=overview),
        analysis_runtime=None,
        as_of=NOW,
    )

    assert monitor.stages[0].status == OperationsMonitorStatus.DELAYED
    assert monitor.attention_count == 1
    assert monitor.attention[0].title == "Data is delayed"
    assert monitor.assets[0].status == OperationsMonitorStatus.DELAYED
    assert monitor.assets[0].attention_count == 1
    assert monitor.stages[3].status == OperationsMonitorStatus.UNAVAILABLE


def test_monitor_handles_assets_with_and_without_data_time_without_comparing_none() -> None:
    first = _source("source-a", "asset-a")
    second = _source("source-b", "asset-b")
    lifecycles = (
        SourceLifecycleRecord(
            source_id="source-a",
            state=SourceLifecycleState.ACTIVE,
            changed_at=NOW - timedelta(hours=1),
        ),
        SourceLifecycleRecord(
            source_id="source-b",
            state=SourceLifecycleState.ACTIVE,
            changed_at=NOW - timedelta(hours=1),
        ),
    )
    receipt = SourceReceiptEvidence(
        source_id="source-a",
        observed_at=NOW - timedelta(seconds=3),
        received_at=NOW - timedelta(seconds=2),
    )
    policy = SourceFreshnessPolicy(
        source_id="source-a",
        max_observation_age_seconds=60,
        changed_at=NOW - timedelta(hours=1),
    )
    overview = build_operations_overview(
        sources=(first, second),
        lifecycle_records=lifecycles,
        receipts=(receipt,),
        freshness_policies=(policy,),
        connection_attempts=(),
        analysis_runs=(),
        findings=(),
        review_events=(),
        as_of=NOW,
    )

    monitor = build_operations_monitor_view(
        sources=(first, second),
        overview=overview,
        attention=build_operations_attention_queue(overview=overview),
        as_of=NOW,
    )

    assert tuple(item.asset_id for item in monitor.assets) == ("asset-a", "asset-b")
    assert monitor.assets[0].last_data_at == receipt.received_at
    assert monitor.assets[1].last_data_at is None


def _live_surface(
    source_id: str,
    *,
    last_received_at: datetime,
    state=None,
    state_changed_at: datetime | None = None,
    failure=None,
):
    from industrial_phm.application import (
        AcquisitionFlowTelemetry,
        AcquisitionSessionTelemetry,
        AcquisitionSpoolTelemetrySnapshot,
        AcquisitionTelemetrySnapshot,
        AcquisitionTelemetrySurface,
        OpcUaPersistentSessionState,
    )

    started = NOW - timedelta(hours=1)
    state = OpcUaPersistentSessionState.CONNECTED if state is None else state
    connected = state == OpcUaPersistentSessionState.CONNECTED
    return AcquisitionTelemetrySurface(
        source=AcquisitionTelemetrySnapshot(
            source_id=source_id,
            failure=failure,
            session=AcquisitionSessionTelemetry(
                source_id=source_id,
                worker_started_at=started,
                state=state,
                state_changed_at=state_changed_at or started,
                connection_epoch=3,
                reconnect_attempt_index=0 if connected else 2,
                callback_queue_overflow_count=0,
                connected_since=started if connected else None,
                callback_queue_maxsize=128,
            ),
            flow=AcquisitionFlowTelemetry(
                source_id=source_id,
                worker_started_at=started,
                accepted_event_count=600,
                replayed_event_count=0,
                bad_status_event_count=0,
                updated_at=last_received_at,
                last_delivery_identity=(source_id, 3, 599),
                last_source_timestamp=last_received_at,
                last_received_at=last_received_at,
                last_ingested_at=last_received_at,
            ),
        ),
        spool=AcquisitionSpoolTelemetrySnapshot(
            sampled_at=NOW,
            pending_event_count=0,
            payload_bytes=0,
            oldest_accepted_at=None,
            active_batch_id=None,
            active_batch_event_count=0,
            active_batch_payload_bytes=0,
        ),
    )


def test_connected_session_silence_is_distinct_from_observation_freshness() -> None:
    # Observation freshness and platform receive silence are different facts.
    source, overview = _overview(
        observed_at=NOW - timedelta(seconds=5),
        max_age_seconds=3600,
    )
    silent = _live_surface(source.source_id, last_received_at=NOW - timedelta(minutes=11))

    monitor = build_operations_monitor_view(
        sources=(source,),
        overview=overview,
        attention=build_operations_attention_queue(overview=overview),
        acquisition_surfaces=(silent,),
        collection_service=_collection_service(heartbeat_at=NOW - timedelta(seconds=1)),
        as_of=NOW,
    )

    assert monitor.stages[0].status == OperationsMonitorStatus.DELAYED
    assert monitor.assets[0].status == OperationsMonitorStatus.DELAYED
    (attention,) = monitor.attention
    assert attention.title == "No new data"
    assert "11m ago (limit 30s)" in attention.detail

    fresh = _live_surface(source.source_id, last_received_at=NOW - timedelta(seconds=5))
    monitor = build_operations_monitor_view(
        sources=(source,),
        overview=overview,
        attention=build_operations_attention_queue(overview=overview),
        acquisition_surfaces=(fresh,),
        collection_service=_collection_service(heartbeat_at=NOW - timedelta(seconds=1)),
        as_of=NOW,
    )
    assert monitor.stages[0].status == OperationsMonitorStatus.RUNNING
    assert monitor.attention == ()

    monitor = build_operations_monitor_view(
        sources=(source,),
        overview=overview,
        attention=build_operations_attention_queue(overview=overview),
        acquisition_surfaces=(silent,),
        live_flow_silence_timeout=timedelta(minutes=20),
        collection_service=_collection_service(heartbeat_at=NOW - timedelta(seconds=1)),
        as_of=NOW,
    )
    assert monitor.stages[0].status == OperationsMonitorStatus.RUNNING
    assert monitor.attention == ()


def _collection_service(*, heartbeat_at: datetime, state=None):
    from industrial_phm.application import (
        CollectionServiceRuntimeState,
        CollectionServiceRuntimeTelemetry,
    )

    return CollectionServiceRuntimeTelemetry(
        state=CollectionServiceRuntimeState.RUNNING if state is None else state,
        started_at=NOW - timedelta(hours=1),
        heartbeat_at=heartbeat_at,
        reconcile_count=100,
        owned_source_count=1,
    )


def _monitor(source, overview, surface, **kwargs):
    return build_operations_monitor_view(
        sources=(source,),
        overview=overview,
        attention=build_operations_attention_queue(overview=overview),
        acquisition_surfaces=(surface,),
        as_of=NOW,
        **kwargs,
    )


def test_stopped_collector_process_is_not_shown_as_a_connected_or_silent_source() -> None:
    # Phase 10 soak: killing the collector left its last "CONNECTED" session report,
    # and Monitor showed the same "No new data" as a silent source.
    from industrial_phm.application import CollectionServiceRuntimeState

    source, overview = _overview(observed_at=NOW - timedelta(seconds=5), max_age_seconds=3600)
    last_report = _live_surface(source.source_id, last_received_at=NOW - timedelta(seconds=60))

    monitor = _monitor(
        source,
        overview,
        last_report,
        collection_service=_collection_service(heartbeat_at=NOW - timedelta(seconds=60)),
    )
    sources, collect = monitor.stages[0], monitor.stages[1]
    assert collect.status == OperationsMonitorStatus.ERROR
    assert collect.summary == "Collection service heartbeat is 60s old"
    assert sources.status == OperationsMonitorStatus.UNAVAILABLE
    assert monitor.assets[0].status == OperationsMonitorStatus.UNAVAILABLE
    assert [item.title for item in monitor.attention] == ["Collection service is not running"]

    stopped = _monitor(
        source,
        overview,
        last_report,
        collection_service=_collection_service(
            heartbeat_at=NOW - timedelta(seconds=60),
            state=CollectionServiceRuntimeState.STOPPED,
        ),
    )
    assert stopped.stages[1].status == OperationsMonitorStatus.STOPPED
    assert [item.title for item in stopped.attention] == ["Collection service stopped"]

    # With a current heartbeat the same session silence is the source's.
    alive = _monitor(
        source,
        overview,
        last_report,
        collection_service=_collection_service(heartbeat_at=NOW - timedelta(seconds=1)),
    )
    assert alive.stages[1].status == OperationsMonitorStatus.RUNNING
    assert [item.title for item in alive.attention] == ["No new data"]


def test_reconnecting_session_is_shown_as_connection_loss_not_an_earlier_worker_error() -> None:
    # Phase 10 soak: with the source server down, Collect showed an unrelated
    # earlier worker exception, plus one-shot "waiting for data" attention.
    from industrial_phm.application import (
        AcquisitionFailureComponent,
        AcquisitionFailureTelemetry,
        OpcUaPersistentSessionState,
    )

    source, overview = _overview(observed_at=NOW - timedelta(hours=3), max_age_seconds=30)
    failure = AcquisitionFailureTelemetry(
        source_id=source.source_id,
        component=AcquisitionFailureComponent.OPCUA_WORKER,
        occurred_at=NOW - timedelta(minutes=3),
        detail="RuntimeError: earlier worker failure",
    )
    reconnecting = _live_surface(
        source.source_id,
        last_received_at=NOW - timedelta(minutes=2),
        state=OpcUaPersistentSessionState.RECONNECT_WAIT,
        state_changed_at=NOW - timedelta(minutes=2),
        failure=failure,
    )

    monitor = _monitor(
        source,
        overview,
        reconnecting,
        collection_service=_collection_service(heartbeat_at=NOW - timedelta(seconds=1)),
    )
    assert monitor.stages[1].status == OperationsMonitorStatus.DELAYED
    assert monitor.stages[1].summary == "1 live source session(s) reconnecting"
    assert monitor.stages[0].status == OperationsMonitorStatus.DELAYED
    (attention,) = monitor.attention
    assert attention.title == "Source connection lost"
    assert "last data 2m ago" in attention.detail

    # A worker that failed and did not report any later session state is an error.
    wedged = _live_surface(
        source.source_id,
        last_received_at=NOW - timedelta(minutes=5),
        state=OpcUaPersistentSessionState.CONNECTED,
        state_changed_at=NOW - timedelta(minutes=10),
        failure=failure,
    )
    monitor = _monitor(
        source,
        overview,
        wedged,
        collection_service=_collection_service(heartbeat_at=NOW - timedelta(seconds=1)),
    )
    assert monitor.stages[1].status == OperationsMonitorStatus.ERROR
    assert [item.title for item in monitor.attention] == ["Collection needs attention"]


def test_refused_connection_keeps_worker_error_and_last_receive_time() -> None:
    # Phase 10 soak: with the source server down every new worker fails at once
    # and stops; its fresh flow telemetry has no last-data time.
    from dataclasses import replace

    from industrial_phm.application import (
        AcquisitionFailureComponent,
        AcquisitionFailureTelemetry,
        AcquisitionFlowTelemetry,
        AcquisitionHistoryTelemetry,
        AcquisitionLastReceiptTelemetry,
        OpcUaPersistentSessionState,
    )

    source, overview = _overview(observed_at=NOW - timedelta(hours=3), max_age_seconds=30)
    failure = AcquisitionFailureTelemetry(
        source_id=source.source_id,
        component=AcquisitionFailureComponent.OPCUA_WORKER,
        occurred_at=NOW - timedelta(seconds=2),
        detail="ConnectionRefusedError: [Errno 61] Connect call failed",
    )
    stopped = _live_surface(
        source.source_id,
        last_received_at=NOW - timedelta(minutes=5),
        state=OpcUaPersistentSessionState.STOPPED,
        state_changed_at=NOW - timedelta(seconds=1),
        failure=failure,
    )
    received = NOW - timedelta(minutes=5)
    committed = received + timedelta(seconds=2)
    worker_started = NOW - timedelta(seconds=3)
    stopped = replace(
        stopped,
        source=replace(
            stopped.source,
            flow=AcquisitionFlowTelemetry(
                source_id=source.source_id,
                worker_started_at=worker_started,
                accepted_event_count=0,
                replayed_event_count=0,
                bad_status_event_count=0,
                updated_at=worker_started,
            ),
            history=AcquisitionHistoryTelemetry(
                source_id=source.source_id,
                batch_id="batch-9",
                snapshot_id=9,
                batch_event_count=10,
                source_event_count=10,
                committed_at=committed,
                acknowledged_at=committed,
                recovered_existing_commit=False,
            ),
            last_receipt=AcquisitionLastReceiptTelemetry(
                source_id=source.source_id,
                received_at=received,
                source_timestamp=received,
                delivery_identity=(source.source_id, 8, 41),
            ),
        ),
    )

    monitor = _monitor(
        source,
        overview,
        stopped,
        collection_service=_collection_service(heartbeat_at=NOW - timedelta(seconds=1)),
    )
    assert monitor.stages[1].status == OperationsMonitorStatus.ERROR
    assert monitor.stages[0].status == OperationsMonitorStatus.ERROR
    (attention,) = monitor.attention
    assert "ConnectionRefusedError" in attention.detail
    # Receive clock from the earlier worker, not the history commit/ack clock.
    assert monitor.assets[0].last_data_at == received


def test_live_telemetry_without_any_collector_heartbeat_fails_closed() -> None:
    # Upgrade, lost telemetry or a collector not started since instrumentation:
    # an old CONNECTED report must not be shown as a current connection.
    source, overview = _overview(observed_at=NOW - timedelta(seconds=5), max_age_seconds=3600)
    last_report = _live_surface(source.source_id, last_received_at=NOW - timedelta(seconds=2))

    monitor = _monitor(source, overview, last_report)

    assert monitor.stages[1].status == OperationsMonitorStatus.UNAVAILABLE
    assert monitor.stages[1].summary == "No collection-service heartbeat recorded"
    assert monitor.stages[0].status == OperationsMonitorStatus.UNAVAILABLE
    assert [item.title for item in monitor.attention] == [
        "Collection service heartbeat unavailable"
    ]
