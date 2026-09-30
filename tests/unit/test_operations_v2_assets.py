from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from industrial_phm.application import (
    AnalysisRun,
    AssetIdentity,
    FileSourceConfig,
    FindingReviewAction,
    FindingReviewEvent,
    OperationalFinding,
    RegisteredSource,
    SourceFreshnessPolicy,
    SourceLifecycleRecord,
    SourceLifecycleState,
    SourceReceiptEvidence,
    build_asset_detail,
    build_operations_overview,
)
from industrial_phm.application.live_window_analysis import WindowAnalysisState
from industrial_phm.application.measurement_history import HistoryAssetSummary
from industrial_phm.application.operations_v2 import (
    OperationsMonitorAsset,
    OperationsMonitorStatus,
)
from industrial_phm.application.operations_v2_assets import (
    AssetWorkspaceAnalysisAttempt,
    build_asset_workspace_view,
)
from industrial_phm.contracts import DataQualityAssessment

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class _Evidence:
    evidence_id: str
    capability_id: str


@dataclass(frozen=True)
class _Result:
    run: AnalysisRun
    evidence: _Evidence


def _source() -> RegisteredSource:
    return RegisteredSource(
        source_id="source-a",
        name="Line A power",
        config=FileSourceConfig(
            source_path="data/source-a.csv",
            asset_id="boiler-01",
            measurement_point_id="panel-main",
            channel_columns=("voltage-r", "voltage-s", "voltage-t"),
            sampling_rate_hz=1.0,
        ),
        registered_at=NOW - timedelta(days=2),
    )


def _run() -> AnalysisRun:
    return AnalysisRun(
        analysis_run_id="run-1",
        asset_id="boiler-01",
        source_id="source-a",
        measurement_point_id="panel-main",
        observed_start_at=NOW - timedelta(minutes=10),
        observed_end_at=NOW - timedelta(minutes=5),
        started_at=NOW - timedelta(minutes=4),
        completed_at=NOW - timedelta(minutes=3),
        data_quality=DataQualityAssessment(),
        capability_ids=("three-phase-unbalance-v1",),
    )


def _detail():
    source = _source()
    run = _run()
    lifecycle = SourceLifecycleRecord(
        source_id=source.source_id,
        state=SourceLifecycleState.ACTIVE,
        changed_at=NOW - timedelta(days=1),
    )
    receipt = SourceReceiptEvidence(
        source_id=source.source_id,
        observed_at=NOW - timedelta(seconds=4),
        received_at=NOW - timedelta(seconds=3),
    )
    freshness = SourceFreshnessPolicy(
        source_id=source.source_id,
        max_observation_age_seconds=60,
        changed_at=NOW - timedelta(hours=1),
    )
    finding = OperationalFinding(
        finding_id="finding-1",
        analysis_run_id=run.analysis_run_id,
        asset_id=run.asset_id,
        measurement_point_id=run.measurement_point_id,
        observed_at=run.observed_end_at,
        capability_id="three-phase-unbalance-v1",
        finding_semantics_id="human-review-request-v1",
        state="REVIEW_REQUIRED",
        evidence_refs=("evidence-1",),
    )
    review = FindingReviewEvent(
        event_id="review-1",
        finding_id=finding.finding_id,
        action=FindingReviewAction.ACKNOWLEDGE,
        recorded_at=NOW - timedelta(minutes=1),
        note="현장 확인 예정",
    )
    overview = build_operations_overview(
        sources=(source,),
        lifecycle_records=(lifecycle,),
        receipts=(receipt,),
        freshness_policies=(freshness,),
        connection_attempts=(),
        analysis_runs=(run,),
        findings=(finding,),
        review_events=(review,),
        as_of=NOW,
    )
    detail = build_asset_detail(
        AssetIdentity("boiler-01"),
        sources=(source,),
        overview=overview,
        analysis_runs=(run,),
        findings=(finding,),
        review_events=(review,),
    )
    return source, run, detail


def test_asset_workspace_projects_header_history_analysis_and_review() -> None:
    source, run, detail = _detail()
    result = _Result(
        run=run,
        evidence=_Evidence("evidence-1", "three-phase-unbalance-v1"),
    )
    monitor = OperationsMonitorAsset(
        asset_id="boiler-01",
        status=OperationsMonitorStatus.RUNNING,
        source_count=1,
        last_data_at=NOW - timedelta(seconds=3),
        latest_analysis_at=run.completed_at,
        pending_review_count=1,
        attention_count=1,
    )
    history = HistoryAssetSummary(
        asset_id="boiler-01",
        start_at=NOW - timedelta(days=30),
        end_at=NOW - timedelta(seconds=4),
        measurement_count=123456,
    )

    skipped = AssetWorkspaceAnalysisAttempt(
        asset_id="boiler-01",
        state=WindowAnalysisState.SKIPPED,
        capability_id="three-phase-unbalance-v1",
        source_id="source-a",
        measurement_point_id="panel-main",
        observed_start_at=NOW - timedelta(minutes=2),
        observed_end_at=NOW - timedelta(minutes=1),
        recorded_at=NOW - timedelta(seconds=30),
        window_id="window-2",
        reason="missing phase T",
    )
    view = build_asset_workspace_view(
        asset_id="boiler-01",
        detail=detail,
        analysis_results=(result,),
        monitor_asset=monitor,
        history_summary=history,
        history_channels=("voltage-t", "voltage-r", "voltage-s"),
        skipped_analysis_attempts=(skipped,),
    )

    assert view.status == OperationsMonitorStatus.RUNNING
    assert view.source_count == 1
    assert view.attention_count == 1
    assert view.history_measurement_count == 123456
    assert view.history_channels == ("voltage-r", "voltage-s", "voltage-t")
    assert view.latest_analysis_at == run.completed_at
    assert view.open_review_count == 1
    assert view.sources[0].source_id == source.source_id
    assert view.sources[0].channel_count == 3
    assert view.analyses[0].capability_id == "three-phase-unbalance-v1"
    assert tuple(item.state for item in view.analysis_attempts) == (
        WindowAnalysisState.SKIPPED,
        WindowAnalysisState.ANALYZED,
    )
    assert view.analysis_attempts[0].reason == "missing phase T"
    assert view.analysis_attempts[0].window_id == "window-2"
    assert view.reviews[0].status.value == "acknowledged"
    assert any(item.title == "Analysis completed" for item in view.events)
    assert any(item.title == "Review updated" for item in view.events)


def test_history_only_asset_remains_visible_without_inventing_runtime_status() -> None:
    source, _, _detail_value = _detail()
    empty_overview = build_operations_overview(
        sources=(),
        lifecycle_records=(),
        receipts=(),
        freshness_policies=(),
        connection_attempts=(),
        analysis_runs=(),
        findings=(),
        review_events=(),
        as_of=NOW,
    )
    history_only_detail = build_asset_detail(
        AssetIdentity("history-only"),
        sources=(),
        overview=empty_overview,
    )
    history = HistoryAssetSummary(
        asset_id="history-only",
        start_at=NOW - timedelta(days=7),
        end_at=NOW - timedelta(days=1),
        measurement_count=99,
    )

    view = build_asset_workspace_view(
        asset_id="history-only",
        detail=history_only_detail,
        analysis_results=(),
        history_summary=history,
        history_channels=("temperature",),
    )

    assert view.status == OperationsMonitorStatus.UNAVAILABLE
    assert view.source_count == 0
    assert view.last_data_at is None
    assert view.history_measurement_count == 99
    assert view.history_channels == ("temperature",)
    assert source.asset_id != view.asset_id
