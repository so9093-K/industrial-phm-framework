from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application.maintenance_review import (
    FindingReviewAction,
    FindingReviewEvent,
    FindingReviewStatus,
)
from industrial_phm.application.operational import OperationalFinding
from industrial_phm.application.operations_v2_maintenance import build_maintenance_queue

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def _finding(suffix: str, asset_id: str = "boiler-01") -> OperationalFinding:
    return OperationalFinding(
        finding_id=f"finding-{suffix}",
        analysis_run_id=f"run-{suffix}",
        asset_id=asset_id,
        observed_at=NOW - timedelta(hours=1),
        capability_id="three-phase-unbalance-v1",
        finding_semantics_id="human-review-request-v1",
        state="REVIEW_REQUIRED",
        evidence_refs=(f"evidence-{suffix}",),
    )


def _event(
    finding_id: str,
    action: FindingReviewAction,
    minute: int,
    note: str = "",
) -> FindingReviewEvent:
    return FindingReviewEvent(
        event_id=f"event-{finding_id}-{minute}-{action.value}",
        finding_id=finding_id,
        action=action,
        recorded_at=NOW + timedelta(minutes=minute),
        note=note,
    )


def test_maintenance_queue_groups_workflow_state_and_preserves_timeline() -> None:
    open_finding = _finding("open", "asset-a")
    acknowledged = _finding("ack", "asset-b")
    closed = _finding("closed", "asset-c")
    events = (
        _event(acknowledged.finding_id, FindingReviewAction.ACKNOWLEDGE, 1),
        _event(closed.finding_id, FindingReviewAction.ACKNOWLEDGE, 2),
        _event(closed.finding_id, FindingReviewAction.NOTE, 3, "현장 점검 완료"),
        _event(closed.finding_id, FindingReviewAction.CLOSE, 4),
    )

    queue = build_maintenance_queue(
        findings=(closed, open_finding, acknowledged),
        review_events=events,
    )

    assert tuple(item.status for item in queue.items) == (
        FindingReviewStatus.OPEN,
        FindingReviewStatus.ACKNOWLEDGED,
        FindingReviewStatus.CLOSED,
    )
    assert queue.count(FindingReviewStatus.OPEN) == 1
    assert queue.count(FindingReviewStatus.ACKNOWLEDGED) == 1
    assert queue.count(FindingReviewStatus.CLOSED) == 1
    assert queue.items[2].note_count == 1
    assert tuple(item.action for item in queue.items[2].timeline) == (
        FindingReviewAction.ACKNOWLEDGE,
        FindingReviewAction.NOTE,
        FindingReviewAction.CLOSE,
    )


def test_maintenance_queue_filters_by_status_and_asset() -> None:
    first = _finding("a", "asset-a")
    second = _finding("b", "asset-b")
    events = (_event(second.finding_id, FindingReviewAction.ACKNOWLEDGE, 1),)

    queue = build_maintenance_queue(findings=(first, second), review_events=events)

    assert queue.filter(status=FindingReviewStatus.OPEN) == (queue.items[0],)
    assert queue.filter(asset_id="asset-b") == (queue.items[1],)


def test_maintenance_queue_rejects_review_event_without_finding() -> None:
    unknown = _event("missing", FindingReviewAction.ACKNOWLEDGE, 1)

    with pytest.raises(ValueError, match="unknown findings"):
        build_maintenance_queue(findings=(), review_events=(unknown,))
