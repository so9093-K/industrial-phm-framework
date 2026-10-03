from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application import AnalysisRun, OperationalFinding
from industrial_phm.application.maintenance_review import (
    FindingReviewAction,
    FindingReviewEvent,
)
from industrial_phm.application.operations_investigations import (
    InvestigationReviewState,
    build_investigation_queue,
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


def _result(
    suffix: str,
    *,
    completed_at: datetime,
    asset_id: str = "boiler-01",
    capability_id: str = "three-phase-unbalance-v1",
) -> _Result:
    run = AnalysisRun(
        analysis_run_id=f"run-{suffix}",
        asset_id=asset_id,
        source_id=f"source-{suffix}",
        observed_start_at=completed_at - timedelta(minutes=10),
        observed_end_at=completed_at - timedelta(minutes=5),
        started_at=completed_at - timedelta(seconds=2),
        completed_at=completed_at,
        data_quality=DataQualityAssessment(),
        capability_ids=(capability_id,),
    )
    return _Result(
        run=run,
        evidence=_Evidence(
            evidence_id=f"evidence-{suffix}",
            capability_id=capability_id,
        ),
    )


def _finding(result: _Result) -> OperationalFinding:
    return OperationalFinding(
        finding_id=f"finding-{result.run.analysis_run_id}",
        analysis_run_id=result.run.analysis_run_id,
        asset_id=result.run.asset_id,
        observed_at=result.run.observed_end_at,
        capability_id=result.evidence.capability_id,
        finding_semantics_id="human-review-request-v1",
        state="REVIEW_REQUIRED",
        evidence_refs=(result.evidence.evidence_id,),
    )


def test_queue_orders_latest_first_and_keeps_review_state_separate_from_analysis() -> None:
    older = _result("old", completed_at=NOW - timedelta(hours=1))
    newer = _result(
        "new",
        completed_at=NOW,
        asset_id="motor-01",
        capability_id="field-vibration-statistical-features-v1",
    )
    finding = _finding(older)
    events = (
        FindingReviewEvent(
            event_id="review-ack",
            finding_id=finding.finding_id,
            action=FindingReviewAction.ACKNOWLEDGE,
            recorded_at=NOW - timedelta(minutes=20),
        ),
    )

    queue = build_investigation_queue(
        analysis_results=(older, newer),
        findings=(finding,),
        review_events=events,
    )

    assert tuple(item.analysis_run_id for item in queue.items) == ("run-new", "run-old")
    assert queue.items[0].review_state == InvestigationReviewState.NOT_REQUESTED
    assert queue.items[1].review_state == InvestigationReviewState.ACKNOWLEDGED
    assert queue.items[1].review_updated_at == events[0].recorded_at
    assert queue.asset_ids == ("boiler-01", "motor-01")
    assert queue.capability_ids == (
        "field-vibration-statistical-features-v1",
        "three-phase-unbalance-v1",
    )


def test_queue_filters_without_reordering_or_inventing_priority() -> None:
    first = _result("a", completed_at=NOW, asset_id="asset-a")
    second = _result(
        "b",
        completed_at=NOW - timedelta(minutes=1),
        asset_id="asset-b",
        capability_id="field-vibration-statistical-features-v1",
    )
    finding = _finding(second)

    queue = build_investigation_queue(
        analysis_results=(first, second),
        findings=(finding,),
        review_events=(),
    )

    assert queue.filter(review_state=InvestigationReviewState.OPEN) == (queue.items[1],)
    assert queue.filter(asset_id="asset-a") == (queue.items[0],)
    assert queue.filter(capability_id="field-vibration-statistical-features-v1") == (
        queue.items[1],
    )


def test_queue_groups_repeated_windows_without_losing_exact_runs() -> None:
    latest = _result("latest", completed_at=NOW)
    earlier = _result("earlier", completed_at=NOW - timedelta(seconds=30))

    queue = build_investigation_queue(
        analysis_results=(earlier, latest),
        findings=(),
        review_events=(),
    )

    groups = queue.groups()
    assert len(groups) == 1
    group = groups[0]
    assert group.asset_id == "boiler-01"
    assert group.capability_id == "three-phase-unbalance-v1"
    assert group.review_state == InvestigationReviewState.NOT_REQUESTED
    assert group.run_count == 2
    assert tuple(item.analysis_run_id for item in group.items) == (
        "run-latest",
        "run-earlier",
    )
    assert group.latest.analysis_run_id == "run-latest"


def test_queue_rejects_ambiguous_duplicate_human_review_findings() -> None:
    result = _result("a", completed_at=NOW)
    first = _finding(result)
    second = OperationalFinding(
        finding_id="finding-duplicate",
        analysis_run_id=result.run.analysis_run_id,
        asset_id=result.run.asset_id,
        observed_at=result.run.observed_end_at,
        capability_id=result.evidence.capability_id,
        finding_semantics_id="human-review-request-v1",
        state="REVIEW_REQUIRED",
        evidence_refs=(result.evidence.evidence_id,),
    )

    with pytest.raises(ValueError, match="multiple human-review findings"):
        build_investigation_queue(
            analysis_results=(result,),
            findings=(first, second),
            review_events=(),
        )
