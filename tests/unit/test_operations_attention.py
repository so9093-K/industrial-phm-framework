from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application import (
    AnalysisRun,
    AssetObservationSummary,
    AttentionHandlingState,
    AttentionKind,
    FileSourceConfig,
    FindingReviewAction,
    FindingReviewEvent,
    OperationalFinding,
    RegisteredSource,
    SourceFreshnessPolicy,
    SourceLifecycleRecord,
    SourceLifecycleState,
    SourceReceiptEvidence,
    SystemStateErrorEvidence,
    build_operations_attention_queue,
    build_operations_overview,
)
from industrial_phm.application.finding_review import (
    HUMAN_REVIEW_FINDING_SEMANTICS_ID,
    HUMAN_REVIEW_FINDING_STATE,
)
from industrial_phm.contracts import (
    DataQualityAssessment,
    DataQualityIssue,
    DataQualitySeverity,
)

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
        registered_at=NOW - timedelta(hours=2),
    )


def _lifecycle(
    source_id: str,
    state: SourceLifecycleState,
    *,
    changed_at: datetime,
    detail: str | None = None,
) -> SourceLifecycleRecord:
    return SourceLifecycleRecord(
        source_id=source_id,
        state=state,
        changed_at=changed_at,
        detail=detail,
    )


def _run() -> AnalysisRun:
    return AnalysisRun(
        analysis_run_id="analysis-1",
        asset_id="pump-review",
        source_id="source-review",
        measurement_point_id="drive-end",
        observed_start_at=NOW - timedelta(minutes=6),
        observed_end_at=NOW - timedelta(minutes=5),
        started_at=NOW - timedelta(minutes=4),
        completed_at=NOW - timedelta(minutes=3),
        data_quality=DataQualityAssessment(),
        capability_ids=("field-vibration-statistical-features-v1",),
    )


def _finding(finding_id: str, *, observed_at: datetime) -> OperationalFinding:
    return OperationalFinding(
        finding_id=finding_id,
        analysis_run_id="analysis-1",
        asset_id="pump-review",
        measurement_point_id="drive-end",
        observed_at=observed_at,
        capability_id="field-vibration-statistical-features-v1",
        finding_semantics_id=HUMAN_REVIEW_FINDING_SEMANTICS_ID,
        state=HUMAN_REVIEW_FINDING_STATE,
        evidence_refs=(f"evidence-{finding_id}",),
    )


def _overview():
    sources = (
        _source("source-error", "pump-error"),
        _source("source-no-receipt", "pump-no-receipt"),
        _source("source-stale", "pump-stale"),
        _source("source-fresh", "pump-fresh"),
    )
    lifecycle = (
        _lifecycle(
            "source-error",
            SourceLifecycleState.ERROR,
            changed_at=NOW - timedelta(minutes=10),
            detail="source contract rejected current payload",
        ),
        _lifecycle(
            "source-no-receipt",
            SourceLifecycleState.ACTIVE,
            changed_at=NOW - timedelta(minutes=9),
        ),
        _lifecycle(
            "source-stale",
            SourceLifecycleState.ACTIVE,
            changed_at=NOW - timedelta(hours=1),
        ),
        _lifecycle(
            "source-fresh",
            SourceLifecycleState.ACTIVE,
            changed_at=NOW - timedelta(hours=1),
        ),
    )
    receipts = (
        SourceReceiptEvidence(
            source_id="source-stale",
            observed_at=NOW - timedelta(minutes=30),
            received_at=NOW - timedelta(minutes=29),
        ),
        SourceReceiptEvidence(
            source_id="source-fresh",
            observed_at=NOW - timedelta(seconds=20),
            received_at=NOW - timedelta(seconds=10),
        ),
    )
    policies = (
        SourceFreshnessPolicy(
            source_id="source-stale",
            max_observation_age_seconds=300.0,
            changed_at=NOW - timedelta(hours=1),
        ),
        SourceFreshnessPolicy(
            source_id="source-fresh",
            max_observation_age_seconds=60.0,
            changed_at=NOW - timedelta(hours=1),
        ),
    )
    open_finding = _finding(
        "finding-open",
        observed_at=NOW - timedelta(minutes=20),
    )
    acknowledged_finding = _finding(
        "finding-acknowledged",
        observed_at=NOW - timedelta(minutes=2),
    )
    closed_finding = _finding(
        "finding-closed",
        observed_at=NOW - timedelta(minutes=1),
    )
    events = (
        FindingReviewEvent(
            event_id="event-ack-1",
            finding_id=acknowledged_finding.finding_id,
            action=FindingReviewAction.ACKNOWLEDGE,
            recorded_at=NOW - timedelta(minutes=1),
        ),
        FindingReviewEvent(
            event_id="event-ack-2",
            finding_id=closed_finding.finding_id,
            action=FindingReviewAction.ACKNOWLEDGE,
            recorded_at=NOW,
        ),
        FindingReviewEvent(
            event_id="event-close",
            finding_id=closed_finding.finding_id,
            action=FindingReviewAction.CLOSE,
            recorded_at=NOW + timedelta(seconds=1),
        ),
    )
    return build_operations_overview(
        sources=sources,
        lifecycle_records=lifecycle,
        receipts=receipts,
        freshness_policies=policies,
        connection_attempts=(),
        analysis_runs=(_run(),),
        findings=(open_finding, acknowledged_finding, closed_finding),
        review_events=events,
        as_of=NOW,
    )


def test_attention_queue_projects_supported_factual_categories_without_severity() -> None:
    observation = AssetObservationSummary(
        asset_id="pump-fresh",
        source_id="source-fresh",
        measurement_point_id="drive-end",
        channels=("vibration_x",),
        sample_count=10,
        observed_start_at=NOW - timedelta(minutes=4),
        observed_end_at=NOW - timedelta(minutes=3),
        data_quality=DataQualityAssessment(
            (
                DataQualityIssue(
                    code="missing-values",
                    severity=DataQualitySeverity.WARNING,
                    message="missing values were observed",
                ),
            )
        ),
    )
    system_error = SystemStateErrorEvidence(
        scope="finding-review-state",
        detail="finding review state could not be read",
        detected_at=NOW - timedelta(seconds=30),
    )

    queue = build_operations_attention_queue(
        overview=_overview(),
        latest_observations=(observation,),
        system_errors=(system_error,),
    )

    assert queue.unhandled_count == 1
    assert queue.count(AttentionKind.SOURCE_ERROR) == 1
    assert queue.count(AttentionKind.NO_RECEIPT) == 1
    assert queue.count(AttentionKind.STALE) == 1
    assert queue.count(AttentionKind.DATA_QUALITY_ISSUE) == 1
    assert queue.count(AttentionKind.REVIEW_REQUIRED) == 2
    assert queue.count(AttentionKind.SYSTEM_STATE_ERROR) == 1
    assert all(not hasattr(item, "severity") for item in queue.items)
    assert all(not hasattr(item, "risk_score") for item in queue.items)


def test_attention_queue_orders_unhandled_then_active_by_evidence_time() -> None:
    queue = build_operations_attention_queue(overview=_overview())

    assert queue.items[0].attention_id == "review-required:finding-open"
    assert queue.items[0].handling_state == AttentionHandlingState.UNHANDLED

    active_ids = [item.attention_id for item in queue.items[1:]]
    assert active_ids == [
        "review-required:finding-acknowledged",
        "no-receipt:source-no-receipt",
        "source-error:source-error",
        "stale:source-stale",
    ]


def test_stale_attention_uses_threshold_crossing_time_not_assessment_time() -> None:
    queue = build_operations_attention_queue(overview=_overview())
    stale = next(item for item in queue.items if item.kind == AttentionKind.STALE)

    assert stale.occurred_at == NOW - timedelta(minutes=25)
    assert stale.occurred_at != NOW


def test_closed_review_and_fresh_source_do_not_enter_attention_queue() -> None:
    queue = build_operations_attention_queue(overview=_overview())

    ids = {item.attention_id for item in queue.items}
    assert "review-required:finding-closed" not in ids
    assert "stale:source-fresh" not in ids
    assert "no-receipt:source-fresh" not in ids


def test_data_quality_attention_requires_unique_latest_observation_scope() -> None:
    observation = AssetObservationSummary(
        asset_id="pump-fresh",
        source_id="source-fresh",
        measurement_point_id="drive-end",
        channels=("vibration_x",),
        sample_count=1,
        data_quality=DataQualityAssessment(),
    )

    with pytest.raises(ValueError, match="at most one value"):
        build_operations_attention_queue(
            overview=_overview(),
            latest_observations=(observation, observation),
        )


def test_data_quality_attention_rejects_unregistered_current_source() -> None:
    observation = AssetObservationSummary(
        asset_id="pump-missing",
        source_id="missing-source",
        channels=("vibration_x",),
        sample_count=1,
        data_quality=DataQualityAssessment(),
    )

    with pytest.raises(ValueError, match="current overview"):
        build_operations_attention_queue(
            overview=_overview(),
            latest_observations=(observation,),
        )


def test_system_state_error_requires_timezone_aware_detection_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SystemStateErrorEvidence(
            scope="source-runtime-state",
            detail="unreadable state",
            detected_at=datetime(2026, 9, 27, 10, 0),
        )
