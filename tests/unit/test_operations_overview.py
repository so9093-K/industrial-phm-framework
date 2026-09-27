from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application import (
    AnalysisRun,
    FileSourceConfig,
    FindingReviewAction,
    FindingReviewEvent,
    FindingReviewStatus,
    OperationalFinding,
    RegisteredSource,
    SourceDataFlowState,
    SourceFreshnessPolicy,
    SourceLifecycleRecord,
    SourceLifecycleState,
    SourceReceiptEvidence,
    build_operations_overview,
)
from industrial_phm.application.finding_review import (
    HUMAN_REVIEW_FINDING_SEMANTICS_ID,
    HUMAN_REVIEW_FINDING_STATE,
)
from industrial_phm.contracts import DataQualityAssessment

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)


def _source(source_id: str, asset_id: str) -> RegisteredSource:
    return RegisteredSource(
        source_id=source_id,
        name=source_id,
        config=FileSourceConfig(
            source_path=f"data/{source_id}.csv",
            asset_id=asset_id,
            measurement_point_id="drive-end",
            channel_columns=("vibration_x",),
            sampling_rate_hz=1_000.0,
        ),
        registered_at=NOW - timedelta(hours=1),
    )


def _lifecycle(
    source_id: str,
    state: SourceLifecycleState,
    *,
    detail: str | None = None,
) -> SourceLifecycleRecord:
    return SourceLifecycleRecord(
        source_id=source_id,
        state=state,
        changed_at=NOW - timedelta(minutes=10),
        detail=detail,
    )


def _run(run_id: str, *, completed_at: datetime) -> AnalysisRun:
    return AnalysisRun(
        analysis_run_id=run_id,
        asset_id="pump-01",
        source_id="source-a",
        measurement_point_id="drive-end",
        observed_start_at=NOW - timedelta(minutes=2),
        observed_end_at=NOW - timedelta(minutes=1),
        started_at=completed_at - timedelta(seconds=2),
        completed_at=completed_at,
        data_quality=DataQualityAssessment(),
        capability_ids=("field-vibration-statistical-features-v1",),
    )


def _finding(
    finding_id: str,
    *,
    semantics: str = HUMAN_REVIEW_FINDING_SEMANTICS_ID,
    state: str = HUMAN_REVIEW_FINDING_STATE,
) -> OperationalFinding:
    return OperationalFinding(
        finding_id=finding_id,
        analysis_run_id="analysis-2",
        asset_id="pump-01",
        measurement_point_id="drive-end",
        observed_at=NOW - timedelta(minutes=1),
        capability_id="field-vibration-statistical-features-v1",
        finding_semantics_id=semantics,
        state=state,
        evidence_refs=(f"evidence-{finding_id}",),
    )


def _review_event(
    event_id: str,
    finding_id: str,
    action: FindingReviewAction,
    *,
    minute_offset: int,
) -> FindingReviewEvent:
    return FindingReviewEvent(
        event_id=event_id,
        finding_id=finding_id,
        action=action,
        recorded_at=NOW + timedelta(minutes=minute_offset),
    )


def test_operations_overview_summarizes_factual_source_flow_without_health_verdict() -> None:
    sources = (
        _source("source-a", "pump-01"),
        _source("source-b", "pump-02"),
        _source("source-c", "pump-03"),
    )
    lifecycle = (
        _lifecycle("source-a", SourceLifecycleState.ACTIVE),
        _lifecycle("source-b", SourceLifecycleState.ACTIVE),
        _lifecycle("source-c", SourceLifecycleState.ERROR, detail="invalid source payload"),
    )
    receipt = SourceReceiptEvidence(
        source_id="source-a",
        observed_at=NOW - timedelta(seconds=30),
        received_at=NOW - timedelta(seconds=20),
    )
    policy = SourceFreshnessPolicy(
        source_id="source-a",
        max_observation_age_seconds=60.0,
        changed_at=NOW - timedelta(hours=1),
    )

    overview = build_operations_overview(
        sources=sources,
        lifecycle_records=lifecycle,
        receipts=(receipt,),
        freshness_policies=(policy,),
        connection_attempts=(),
        analysis_runs=(),
        findings=(),
        review_events=(),
        as_of=NOW,
    )

    assert overview.registered_source_count == 3
    assert overview.active_source_count == 2
    assert overview.source_data_flow_count(SourceDataFlowState.FRESH) == 1
    assert overview.source_data_flow_count(SourceDataFlowState.NO_RECEIPT) == 1
    assert overview.source_data_flow_count(SourceDataFlowState.SOURCE_ERROR) == 1
    assert [item.source_id for item in overview.source_health_assessments] == [
        "source-a",
        "source-b",
        "source-c",
    ]
    assert not hasattr(overview, "healthy_asset_count")
    assert not hasattr(overview, "fleet_health_score")


def test_operations_overview_tracks_latest_analysis_and_explicit_review_disposition() -> None:
    source = _source("source-a", "pump-01")
    lifecycle = _lifecycle("source-a", SourceLifecycleState.PAUSED)
    first_run = _run("analysis-1", completed_at=NOW - timedelta(minutes=3))
    latest_run = _run("analysis-2", completed_at=NOW - timedelta(minutes=1))
    open_finding = _finding("finding-open")
    closed_finding = _finding("finding-closed")
    unrelated = _finding(
        "finding-other",
        semantics="other-semantics-v1",
        state="SOME_STATE",
    )
    events = (
        _review_event(
            "event-ack",
            closed_finding.finding_id,
            FindingReviewAction.ACKNOWLEDGE,
            minute_offset=1,
        ),
        _review_event(
            "event-close",
            closed_finding.finding_id,
            FindingReviewAction.CLOSE,
            minute_offset=2,
        ),
    )

    overview = build_operations_overview(
        sources=(source,),
        lifecycle_records=(lifecycle,),
        receipts=(),
        freshness_policies=(),
        connection_attempts=(),
        analysis_runs=(latest_run, first_run),
        findings=(unrelated, closed_finding, open_finding),
        review_events=events,
        as_of=NOW,
    )

    assert overview.analysis_run_count == 2
    assert overview.latest_analysis_run == latest_run
    assert overview.pending_review_count == 1
    assert overview.open_review_count == 1
    assert overview.acknowledged_review_count == 0
    assert overview.closed_review_count == 1
    assert tuple(item.finding.finding_id for item in overview.review_summaries) == (
        "finding-closed",
        "finding-open",
    )
    assert tuple(item.status for item in overview.review_summaries) == (
        FindingReviewStatus.CLOSED,
        FindingReviewStatus.OPEN,
    )


def test_operations_overview_rejects_current_source_population_drift() -> None:
    source = _source("source-a", "pump-01")

    with pytest.raises(ValueError, match="exactly one record"):
        build_operations_overview(
            sources=(source,),
            lifecycle_records=(),
            receipts=(),
            freshness_policies=(),
            connection_attempts=(),
            analysis_runs=(),
            findings=(),
            review_events=(),
            as_of=NOW,
        )

    with pytest.raises(ValueError, match="unregistered source"):
        build_operations_overview(
            sources=(source,),
            lifecycle_records=(_lifecycle("source-a", SourceLifecycleState.ACTIVE),),
            receipts=(
                SourceReceiptEvidence(
                    source_id="missing-source",
                    observed_at=NOW,
                    received_at=NOW,
                ),
            ),
            freshness_policies=(),
            connection_attempts=(),
            analysis_runs=(),
            findings=(),
            review_events=(),
            as_of=NOW,
        )


def test_operations_overview_requires_timezone_aware_assessment_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_operations_overview(
            sources=(),
            lifecycle_records=(),
            receipts=(),
            freshness_policies=(),
            connection_attempts=(),
            analysis_runs=(),
            findings=(),
            review_events=(),
            as_of=datetime(2026, 9, 27, 10, 0),
        )
