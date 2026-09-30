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


def _source() -> RegisteredSource:
    return RegisteredSource(
        source_id="source-a",
        name="Source A",
        config=FileSourceConfig(
            source_path="data/source.csv",
            asset_id="boiler-01",
            channel_columns=("value",),
            sampling_rate_hz=1.0,
        ),
        registered_at=NOW - timedelta(days=1),
    )


def _overview(*, observed_at: datetime, max_age_seconds: float):
    source = _source()
    lifecycle = SourceLifecycleRecord(
        source_id=source.source_id,
        state=SourceLifecycleState.ACTIVE,
        changed_at=NOW - timedelta(hours=1),
    )
    receipt = SourceReceiptEvidence(
        source_id=source.source_id,
        observed_at=observed_at,
        received_at=observed_at + timedelta(seconds=1),
    )
    policy = SourceFreshnessPolicy(
        source_id=source.source_id,
        max_observation_age_seconds=max_age_seconds,
        changed_at=NOW - timedelta(hours=1),
    )
    return source, build_operations_overview(
        sources=(source,),
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
        last_analysis_at=NOW - timedelta(seconds=2),
        last_analysis_run_id="analysis-1",
    )


def test_monitor_translates_current_evidence_into_small_operator_vocabulary() -> None:
    source, overview = _overview(
        observed_at=NOW - timedelta(seconds=5),
        max_age_seconds=60,
    )
    attention = build_operations_attention_queue(overview=overview)
    run = _analysis_run()

    monitor = build_operations_monitor_view(
        sources=(source,),
        overview=overview,
        attention=attention,
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

    assert len(monitor.assets) == 1
    asset = monitor.assets[0]
    assert asset.asset_id == "boiler-01"
    assert asset.status == OperationsMonitorStatus.RUNNING
    assert asset.latest_analysis_at == run.completed_at
    assert asset.attention_count == 0
    assert monitor.activities[0].title == "Analysis completed"


def test_monitor_marks_stale_runner_heartbeat_as_delayed() -> None:
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


def test_monitor_surfaces_stale_source_as_asset_attention_not_asset_health() -> None:
    source, overview = _overview(
        observed_at=NOW - timedelta(minutes=2),
        max_age_seconds=30,
    )
    attention = build_operations_attention_queue(overview=overview)

    monitor = build_operations_monitor_view(
        sources=(source,),
        overview=overview,
        attention=attention,
        analysis_runtime=None,
        as_of=NOW,
    )

    assert monitor.stages[0].status == OperationsMonitorStatus.DELAYED
    assert monitor.attention_count == 1
    assert monitor.assets[0].status == OperationsMonitorStatus.DELAYED
    assert monitor.assets[0].attention_count == 1
    assert monitor.stages[3].status == OperationsMonitorStatus.UNAVAILABLE
