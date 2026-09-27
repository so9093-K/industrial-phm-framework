from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from industrial_phm.application import OperationalFinding
from industrial_phm.application.maintenance_review import (
    FindingReviewAction,
    FindingReviewEvent,
    FindingReviewHistoryFormatError,
    FindingReviewStatus,
    JsonFindingReviewRepository,
    create_finding_review_event,
    finding_review_status,
)


def _finding() -> OperationalFinding:
    return OperationalFinding(
        finding_id="finding-review-analysis-run-1",
        analysis_run_id="analysis-run-1",
        asset_id="bearing-01",
        measurement_point_id="de",
        observed_at=datetime(2026, 9, 27, 1, 0, 2, tzinfo=UTC),
        capability_id="field-vibration-statistical-features-v1",
        finding_semantics_id="human-review-request-v1",
        state="REVIEW_REQUIRED",
        evidence_refs=("evidence-1",),
    )


def _event(
    *,
    event_id: str,
    action: FindingReviewAction,
    minute: int,
    note: str = "",
) -> FindingReviewEvent:
    return FindingReviewEvent(
        event_id=event_id,
        finding_id=_finding().finding_id,
        action=action,
        recorded_at=datetime(2026, 9, 27, 1, minute, tzinfo=UTC),
        note=note,
    )


def test_finding_review_status_supports_note_acknowledge_note_close() -> None:
    events = (
        _event(
            event_id="event-1",
            action=FindingReviewAction.NOTE,
            minute=10,
            note="inspect bearing housing",
        ),
        _event(
            event_id="event-2",
            action=FindingReviewAction.ACKNOWLEDGE,
            minute=11,
        ),
        _event(
            event_id="event-3",
            action=FindingReviewAction.NOTE,
            minute=12,
            note="reviewed feature evidence",
        ),
        _event(
            event_id="event-4",
            action=FindingReviewAction.CLOSE,
            minute=13,
            note="review completed",
        ),
    )

    assert finding_review_status((), _finding().finding_id) == FindingReviewStatus.OPEN
    assert finding_review_status(events[:1], _finding().finding_id) == FindingReviewStatus.OPEN
    assert (
        finding_review_status(events[:2], _finding().finding_id) == FindingReviewStatus.ACKNOWLEDGED
    )
    assert finding_review_status(events, _finding().finding_id) == FindingReviewStatus.CLOSED


def test_finding_review_repository_round_trips_events_and_status(tmp_path: Path) -> None:
    repository = JsonFindingReviewRepository(tmp_path / "finding-review.json")
    acknowledge = _event(
        event_id="event-1",
        action=FindingReviewAction.ACKNOWLEDGE,
        minute=10,
        note="assigned for review",
    )
    close = _event(
        event_id="event-2",
        action=FindingReviewAction.CLOSE,
        minute=11,
        note="review completed",
    )

    repository.record(acknowledge)
    repository.record(close)

    assert repository.list_events() == (acknowledge, close)
    assert repository.status_for(_finding().finding_id) == FindingReviewStatus.CLOSED


def test_finding_review_repository_rejects_close_before_acknowledge(tmp_path: Path) -> None:
    repository = JsonFindingReviewRepository(tmp_path / "finding-review.json")

    with pytest.raises(ValueError, match="can only be closed from ACKNOWLEDGED"):
        repository.record(
            _event(
                event_id="event-1",
                action=FindingReviewAction.CLOSE,
                minute=10,
            )
        )

    assert repository.list_events() == ()


def test_finding_review_repository_rejects_event_after_close(tmp_path: Path) -> None:
    repository = JsonFindingReviewRepository(tmp_path / "finding-review.json")
    repository.record(
        _event(
            event_id="event-1",
            action=FindingReviewAction.ACKNOWLEDGE,
            minute=10,
        )
    )
    repository.record(
        _event(
            event_id="event-2",
            action=FindingReviewAction.CLOSE,
            minute=11,
        )
    )

    with pytest.raises(ValueError, match="closed finding review cannot accept"):
        repository.record(
            _event(
                event_id="event-3",
                action=FindingReviewAction.NOTE,
                minute=12,
                note="late note",
            )
        )


def test_create_finding_review_event_uses_existing_finding_identity() -> None:
    finding = _finding()
    recorded_at = datetime(2026, 9, 27, 2, 0, tzinfo=UTC)

    event = create_finding_review_event(
        finding,
        action=FindingReviewAction.ACKNOWLEDGE,
        note="  accepted for review  ",
        clock=lambda: recorded_at,
    )

    assert event.finding_id == finding.finding_id
    assert event.action == FindingReviewAction.ACKNOWLEDGE
    assert event.recorded_at == recorded_at
    assert event.note == "accepted for review"


def test_finding_review_repository_rejects_time_regression(tmp_path: Path) -> None:
    repository = JsonFindingReviewRepository(tmp_path / "finding-review.json")
    current = datetime(2026, 9, 27, 2, 0, tzinfo=UTC)
    repository.record(
        FindingReviewEvent(
            event_id="event-1",
            finding_id=_finding().finding_id,
            action=FindingReviewAction.NOTE,
            recorded_at=current,
            note="first",
        )
    )

    with pytest.raises(ValueError, match="must not move backwards"):
        repository.record(
            FindingReviewEvent(
                event_id="event-2",
                finding_id=_finding().finding_id,
                action=FindingReviewAction.ACKNOWLEDGE,
                recorded_at=current - timedelta(seconds=1),
            )
        )


def test_finding_review_repository_rejects_unsupported_schema(tmp_path: Path) -> None:
    path = tmp_path / "finding-review.json"
    path.write_text(
        '{"schema":"industrial-phm-finding-review-v999","events":[]}\n',
        encoding="utf-8",
    )

    with pytest.raises(
        FindingReviewHistoryFormatError,
        match="unsupported finding review schema",
    ):
        JsonFindingReviewRepository(path).list_events()
