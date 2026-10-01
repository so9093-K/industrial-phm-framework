import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.opcua.fault_harness import (
    Fault,
    check_analysis_outcomes,
    check_dequeued_loss,
    check_missing_within_boundary,
    check_recovered,
    check_ui_states,
    check_windows,
)

T0 = datetime(2026, 10, 1, tzinfo=UTC)


def _t(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def test_missing_must_lie_inside_a_loss_allowed_fault_boundary():
    faults = [
        Fault("stall", "source_stall", _t(100), ended=_t(120), recovered_at=_t(130)),
        Fault("runner", "runner_kill", _t(200), recovered_at=_t(210), loss_allowed=False),
    ]
    margins = {"pre_margin": timedelta(seconds=3), "post_margin": timedelta(seconds=2)}
    inside = [("a", _t(98)), ("a", _t(131))]
    assert check_missing_within_boundary(inside, faults, **margins)["passed"]
    outside = [("a", _t(50)), ("b", _t(205))]  # no fault / a fault that allows no loss
    verdict = check_missing_within_boundary(outside, faults, **margins)
    assert not verdict["passed"] and verdict["outside_count"] == 2


def test_dequeued_notifications_must_all_reach_the_spool_in_graceful_processes():
    records = [
        {"pid": 1, "counts": {"dequeued_data_change": 10, "spool_accepted": 9}},
        {"pid": 1, "counts": {"dequeued_data_change": 2, "spool_accepted": 3}, "final": True},
        {"pid": 2, "counts": {"dequeued_data_change": 5, "spool_accepted": 4}},  # killed
    ]
    verdict = check_dequeued_loss(records)
    assert verdict["passed"]
    assert verdict["crashed_processes_excluded"] == 1
    records[1]["counts"]["spool_accepted"] = 2
    assert check_dequeued_loss(records)["mismatched"] == ["1"]


def test_windows_must_not_repeat_or_overlap():
    rows = [("w1", "s", _t(0), _t(30)), ("w2", "s", _t(30), _t(60))]
    assert check_windows(rows)["passed"]
    assert not check_windows([*rows, ("w3", "s", _t(45), _t(75))])["passed"]
    assert not check_windows([*rows, ("w1", "s", _t(0), _t(30))])["passed"]


def test_each_window_gets_exactly_one_outcome_for_one_policy():
    windows = [("w1", _t(30)), ("w2", _t(60)), ("w3", _t(500))]
    analyzed = [("w1", "cap", "alg", "p")]
    skipped = [("w2", "cap", "alg", "p")]
    assert check_analysis_outcomes(windows, analyzed, skipped, covered_before=_t(100))["passed"]
    # A cursor rollback analyzes again; a forward jump leaves a window behind.
    assert not check_analysis_outcomes(
        windows, [*analyzed, ("w1", "cap", "alg", "p")], skipped, covered_before=_t(100)
    )["passed"]
    assert not check_analysis_outcomes(windows, analyzed, [], covered_before=_t(100))["passed"]


def test_a_fault_without_recovery_is_a_wedge():
    assert not check_recovered([Fault("x", "source_stall", _t(0))])["passed"]


def test_ui_states_must_match_and_differ():
    snapshots = {
        "source_stale": {
            "sources": "delayed",
            "collect": "running",
            "collect_summary": "1 live source session(s) connected",
            "analyze": "running",
            "attention": ["No new data"],
        },
        "source_unreachable": {
            "sources": "error",
            "collect": "error",
            "collect_summary": "1 collection worker failure(s)",
            "analyze": "running",
            "attention": ["Collection needs attention"],
        },
        "collector_down": {
            "sources": "unavailable",
            "collect": "error",
            "collect_summary": "Collection service heartbeat is 25s old",
            "analyze": "running",
            "attention": ["Collection service is not running"],
        },
        "analysis_stale": {
            "sources": "running",
            "collect": "running",
            "collect_summary": "1 live source session(s) connected",
            "analyze": "delayed",
            "attention": ["Analysis service is not updating"],
        },
    }
    assert check_ui_states(snapshots)["passed"]
    # Collector down shown like a silent source is exactly the Phase 10 bug.
    snapshots["collector_down"] = dict(snapshots["source_stale"])
    assert not check_ui_states(snapshots)["passed"]
