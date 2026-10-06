import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.opcua.fault_harness import (
    MONITOR_RENDER_STATES,
    OPERATIONS_APP,
    SCENARIOS,
    Fault,
    build_parser,
    check_analysis_outcomes,
    check_backlog,
    check_dequeued_loss,
    check_first_render,
    check_live_browser_journey,
    check_live_replay_sequence,
    check_metrics_present,
    check_missing_phase,
    check_missing_within_boundary,
    check_recovered,
    check_review_workflow,
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
    # Screenshot-only states may look like a fault state without breaking distinctness.
    normal = {**snapshots["analysis_stale"], "analyze": "running", "attention": []}
    assert check_ui_states({**snapshots, "normal": normal, "missing_phase": normal})["passed"]
    # Collector down shown like a silent source is exactly the Phase 10 bug.
    snapshots["collector_down"] = dict(snapshots["source_stale"])
    assert not check_ui_states(snapshots)["passed"]


def test_metrics_must_exist_before_the_fault_and_after_its_recovery():
    fault = Fault("x", "source_stall", _t(100), ended=_t(120), recovered_at=_t(130))
    margin = timedelta(seconds=15)
    assert check_metrics_present([fault], [_t(90), _t(140)], margin=margin)["passed"]
    # A record only during the fault proves nothing about either side of it.
    only_during = check_metrics_present([fault], [_t(110)], margin=margin)
    assert only_during["no_record_before"] == ["x"]
    assert only_during["no_record_after_recovery"] == ["x"]
    assert not check_metrics_present([fault], [_t(90)], margin=margin)["passed"]


def test_backlog_is_judged_against_its_pre_fault_baseline():
    built_and_drained = {"baseline_pending": 400, "peak_pending": 650, "drained": True}
    assert check_backlog([built_and_drained])["passed"]
    # A peak that never rose above the existing backlog did not exercise the drain.
    no_backlog = {"baseline_pending": 400, "peak_pending": 450, "drained": True}
    assert not check_backlog([no_backlog])["passed"]
    assert not check_backlog([{**built_and_drained, "drained": False}])["passed"]
    assert not check_backlog([])["passed"]


def test_missing_phase_must_name_the_exact_channel_and_reason():
    explained = {
        "window_id": "w1",
        "missing_channels": ["T상전류"],
        "current_selection": "unresolved",
        "voltage_selection": "semantic-role",
        "current_note": "Not evaluated: no complete R/S/T channel set with this meaning ...",
        "provenance_missing_channels": "T상전류",
    }
    assert check_missing_phase("T상전류", [explained], 0)["passed"]
    for broken in (
        {"missing_channels": ["S상전류"]},
        {"voltage_selection": "unresolved"},
        {"current_selection": None},  # no result for the window at all
        {"current_note": ""},
        {"provenance_missing_channels": "none"},
    ):
        assert not check_missing_phase("T상전류", [{**explained, **broken}], 0)["passed"]
    assert not check_missing_phase("T상전류", [explained], 1)["passed"]  # skipped instead
    assert not check_missing_phase("T상전류", [], 0)["passed"]


def test_review_workflow_must_reach_maintenance_from_a_post_fault_result():
    detail = {
        "before_state": "not-requested",
        "after_state": "open",
        "maintenance_status": "open",
        "result_after_last_fault": True,
    }
    assert check_review_workflow(detail)["passed"]
    assert not check_review_workflow({**detail, "maintenance_status": None})["passed"]
    assert not check_review_workflow({**detail, "result_after_last_fault": False})["passed"]


def test_every_ui_state_must_render_within_five_seconds():
    fast = {
        "within_5s": True,
        "seconds": 2.1,
        "monitor_ready": True,
        "attention_seen": True,
        "signal_value_count": 4,
        "system_data_flow_absent": True,
    }
    names = MONITOR_RENDER_STATES
    assert check_first_render(dict.fromkeys(names, fast))["passed"]
    assert not check_first_render({**dict.fromkeys(names, fast), "collector_down": {}})["passed"]
    assert not check_first_render({"source_stale": fast})["passed"]
    # Normal receiving and a missing phase are required screens of their own.
    without_normal = {name: fast for name in names if name != "normal"}
    assert check_first_render(without_normal)["missing"] == ["normal"]
    # They expect no attention; fault states still must show theirs.
    quiet = {**fast, "attention_seen": None}
    assert check_first_render({**dict.fromkeys(names, fast), "normal": quiet})["passed"]
    assert not check_first_render({**dict.fromkeys(names, fast), "source_stale": quiet})["passed"]


def test_live_replay_sequence_preserves_missing_gap_and_recovers_history():
    before = {
        "source_flow": "Receiving",
        "channel_event_at": _t(10).isoformat(),
        "channel_event_lag": "0s",
        "history_count": 100,
    }
    before_peer = {
        "source_flow": "Receiving",
        "channel_event_at": _t(10).isoformat(),
        "history_count": 100,
    }
    during = {
        "source_flow": "Receiving",
        "channel_event_at": _t(10).isoformat(),
        "channel_event_lag": "12.0s behind latest source timestamp",
        "history_count": 140,
        "omitted_from": _t(12).isoformat(),
    }
    during_peer = {
        "source_flow": "Receiving",
        "channel_event_at": _t(22).isoformat(),
        "history_count": 140,
    }
    states = {
        "before_missing": before,
        "before_missing_peer": before_peer,
        "during_missing": during,
        "during_missing_peer": during_peer,
        "paused": {"source_flow": "No recent source data"},
        "reconnecting": {"source_flow": "Reconnecting"},
        "recovered": {
            "source_flow": "Receiving",
            "channel_event_at": _t(30).isoformat(),
            "history_count": 180,
        },
    }

    assert check_live_replay_sequence(states)["passed"]
    # A value stored after the "before" snapshot but before the omission began is fine.
    assert check_live_replay_sequence(
        {**states, "during_missing": {**during, "channel_event_at": _t(11).isoformat()}}
    )["passed"]
    assert not check_live_replay_sequence(
        {
            **states,
            "during_missing": {
                **during,
                "channel_event_at": _t(20).isoformat(),
            },
        }
    )["passed"]
    assert not check_live_replay_sequence(
        {
            **states,
            "during_missing_peer": {
                **during_peer,
                "channel_event_at": _t(10).isoformat(),
            },
        }
    )["passed"]


def test_live_browser_journey_requires_each_core_state_within_five_seconds():
    fast = {
        "within_5s": True,
        "seconds": 2.0,
        "matched": "Source flow · Receiving",
        "current_observation_seen": True,
        "value_count": 1,
    }
    renders = {
        "before_missing": fast,
        "paused": {**fast, "matched": "Source flow · No recent source data"},
        "reconnecting": {**fast, "matched": "Source flow · Reconnecting"},
        "recovered": fast,
    }

    assert check_live_browser_journey(renders)["passed"]
    slow_pause = {**renders, "paused": {"within_5s": False}}
    assert not check_live_browser_journey(slow_pause)["passed"]
    assert not check_live_browser_journey(
        {name: value for name, value in renders.items() if name != "reconnecting"}
    )["passed"]


def test_harness_uses_packaged_operations_app_path():
    assert OPERATIONS_APP.is_file()
    assert OPERATIONS_APP.parent.name == "apps"
    assert OPERATIONS_APP.parent.parent.name == "industrial_phm"
    source = (
        Path(__file__).resolve().parents[2].joinpath("tools/opcua/fault_harness.py").read_text()
    )
    assert "apps/operations_v2.py" not in source
    assert 'get_by_text("Observed asset", exact=True)' in source
    assert 'get_by_text("Latest stored observations", exact=True)' in source
    assert 'get_by_text("Recent signal trends", exact=True)' in source
    assert 'get_by_text("System data flow", exact=True).count() == 0' in source
    assert 'get_by_text("Current observation", exact=True)' in source
    assert 'get_by_text("Live observation", exact=True)' not in source
    assert 'get_by_role("radio", name="Assets", exact=True)' in source
    assert 'get_by_role("radio", name="Signals", exact=True)' in source


def test_harness_command_line_defaults_reach_every_setting_the_run_needs():
    args = build_parser().parse_args(["--root", "artifacts/x"])
    assert (args.repeat, args.scenarios, args.browser) == (3, list(SCENARIOS), False)
    # The replay selection the stack is prepared from.
    assert args.archive.name == "5.보일러.zip"
    assert args.member == "5.보일러/SourceData_211.json"
    assert args.binding.exists()
    assert (args.start.hour, args.end.hour, args.end.minute) == (6, 12, 30)


def test_monitor_browser_gate_rejects_workflow_only_or_valueless_surfaces():
    ready = {
        "within_5s": True,
        "seconds": 1.5,
        "monitor_ready": True,
        "attention_seen": True,
        "signal_value_count": 3,
        "system_data_flow_absent": True,
    }
    renders = dict.fromkeys(MONITOR_RENDER_STATES, ready)

    assert check_first_render(renders)["passed"]
    assert not check_first_render({**renders, "source_stale": {**ready, "signal_value_count": 0}})[
        "passed"
    ]
    assert not check_first_render(
        {**renders, "source_stale": {**ready, "system_data_flow_absent": False}}
    )["passed"]
    # Content that runs past the 1440px viewport is unreadable even if it rendered.
    clipped = {**ready, "overflow_count": 3, "overflow_examples": ["DIV.phm-grid:1622"]}
    assert not check_first_render({**renders, "normal": clipped})["passed"]


def test_live_browser_gate_rejects_state_without_current_value_surface():
    fast = {
        "within_5s": True,
        "seconds": 2.0,
        "matched": "Source flow · Receiving",
        "current_observation_seen": True,
        "value_count": 1,
    }
    renders = {
        "before_missing": fast,
        "paused": {**fast, "matched": "Source flow · No recent source data"},
        "reconnecting": {**fast, "matched": "Source flow · Reconnecting"},
        "recovered": fast,
    }

    assert check_live_browser_journey(renders)["passed"]
    assert not check_live_browser_journey(
        {**renders, "recovered": {**fast, "current_observation_seen": False}}
    )["passed"]
    assert not check_live_browser_journey({**renders, "recovered": {**fast, "value_count": 0}})[
        "passed"
    ]
