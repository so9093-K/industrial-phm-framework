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


def _live_surface(source_id: str, *, last_received_at: datetime):
    from industrial_phm.application import (
        AcquisitionFlowTelemetry,
        AcquisitionSessionTelemetry,
        AcquisitionSpoolTelemetrySnapshot,
        AcquisitionTelemetrySnapshot,
        AcquisitionTelemetrySurface,
        OpcUaPersistentSessionState,
    )

    started = NOW - timedelta(hours=1)
    return AcquisitionTelemetrySurface(
        source=AcquisitionTelemetrySnapshot(
            source_id=source_id,
            session=AcquisitionSessionTelemetry(
                source_id=source_id,
                worker_started_at=started,
                state=OpcUaPersistentSessionState.CONNECTED,
                state_changed_at=started,
                connection_epoch=3,
                reconnect_attempt_index=0,
                callback_queue_overflow_count=0,
                connected_since=started,
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


def test_connected_session_without_new_data_beyond_its_policy_is_delayed() -> None:
    # Found in Phase 10: a wedged collector stayed CONNECTED for 11 minutes without
    # data while Monitor reported every stage as receiving data.
    source, overview = _overview(observed_at=NOW - timedelta(hours=2), max_age_seconds=30)
    policy = SourceFreshnessPolicy(
        source_id=source.source_id,
        max_observation_age_seconds=30,
        changed_at=NOW - timedelta(hours=1),
    )
    silent = _live_surface(source.source_id, last_received_at=NOW - timedelta(minutes=11))

    monitor = build_operations_monitor_view(
        sources=(source,),
        overview=overview,
        attention=build_operations_attention_queue(overview=overview),
        acquisition_surfaces=(silent,),
        freshness_policies=(policy,),
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
        freshness_policies=(policy,),
        as_of=NOW,
    )
    assert monitor.stages[0].status == OperationsMonitorStatus.RUNNING
    assert monitor.attention == ()

    # Without a policy nothing is claimed about an unchanged-value source.
    monitor = build_operations_monitor_view(
        sources=(source,),
        overview=overview,
        attention=build_operations_attention_queue(overview=overview),
        acquisition_surfaces=(silent,),
        as_of=NOW,
    )
    assert monitor.stages[0].status == OperationsMonitorStatus.RUNNING
