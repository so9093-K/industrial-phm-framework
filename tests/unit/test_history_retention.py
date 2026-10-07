from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application import (
    FindingReviewAction,
    HistoricalInputReference,
    create_finding_review_event,
    create_human_review_finding,
)
from industrial_phm.application.history_retention import (
    DEFAULT_LIVE_RETENTION,
    ProtectedEvidenceRange,
    open_review_protection,
    retention_cutoff,
)
from industrial_phm.application.phase_unbalance import run_phase_unbalance_on_window
from tests.support.window_analysis import START, finalized_window


def _historical(result, run_id: str, snapshot_id: int):
    reference = HistoricalInputReference(
        snapshot_id=snapshot_id,
        asset_id=result.run.asset_id,
        start_at=result.run.observed_start_at,
        end_at=result.run.observed_end_at,
    )
    return replace(
        result,
        run=replace(result.run, analysis_run_id=run_id),
        evidence=replace(result.evidence, analysis_run_id=run_id, input_reference=reference),
    )


def test_open_and_acknowledged_reviews_protect_their_inputs_closed_ones_do_not() -> None:
    window_result = run_phase_unbalance_on_window(finalized_window("w-open", START))
    closed_result = run_phase_unbalance_on_window(
        finalized_window("w-closed", START + timedelta(hours=1))
    )
    historical_result = _historical(window_result, "history-run", snapshot_id=42)
    unreviewed = run_phase_unbalance_on_window(
        finalized_window("w-unreviewed", START + timedelta(hours=2))
    )
    open_finding = create_human_review_finding(window_result)
    closed_finding = create_human_review_finding(closed_result)
    acknowledged_finding = create_human_review_finding(historical_result)
    events = (
        create_finding_review_event(acknowledged_finding, action=FindingReviewAction.ACKNOWLEDGE),
        create_finding_review_event(closed_finding, action=FindingReviewAction.ACKNOWLEDGE),
        create_finding_review_event(closed_finding, action=FindingReviewAction.CLOSE),
    )

    protection = open_review_protection(
        analysis_results=(window_result, closed_result, historical_result, unreviewed),
        findings=(open_finding, closed_finding, acknowledged_finding),
        review_events=events,
    )

    assert protection.window_ids == frozenset({"w-open"})
    assert protection.snapshot_ids == frozenset({42})
    inside = START + timedelta(seconds=30)
    assert protection.covers("site-opcua", inside, inside)
    closed_start = START + timedelta(hours=1, seconds=1)
    assert not protection.covers("site-opcua", closed_start, closed_start)
    assert not protection.covers("other-source", START, START + timedelta(minutes=1))


def test_open_review_without_its_stored_result_fails_closed() -> None:
    result = run_phase_unbalance_on_window(finalized_window("w-missing", START))
    with pytest.raises(ValueError, match="refusing to delete"):
        open_review_protection(
            analysis_results=(),
            findings=(create_human_review_finding(result),),
            review_events=(),
        )


def test_retention_cutoff_and_range_validation() -> None:
    now = datetime(2026, 10, 7, tzinfo=UTC)
    assert retention_cutoff(now) == now - DEFAULT_LIVE_RETENTION == now - timedelta(days=7)
    with pytest.raises(ValueError, match="positive"):
        retention_cutoff(now, timedelta(0))
    with pytest.raises(ValueError, match="timezone-aware"):
        retention_cutoff(now.replace(tzinfo=None))
    with pytest.raises(ValueError, match="after end_at"):
        ProtectedEvidenceRange("source", now, now - timedelta(seconds=1))
