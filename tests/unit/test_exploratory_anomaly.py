"""Departures from a chosen baseline: marks, merged intervals and refusals."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application.exploratory_anomaly import (
    THRESHOLD,
    copied_spans,
    declared_running_total,
    find_departures,
    interval_comparison,
    latest_departure,
    record_changes,
)

T0 = datetime(2026, 10, 14, tzinfo=UTC)


def _points(values: list[float]) -> list[tuple[datetime, datetime, float]]:
    return [
        (T0 + timedelta(minutes=i), T0 + timedelta(minutes=i, seconds=30), value)
        for i, value in enumerate(values)
    ]


def test_neighbouring_marks_join_one_interval_named_by_the_furthest_signal() -> None:
    base = [10 + (i % 5) * 0.1 for i in range(100)]
    current = [*base[:60], 18.0, 19.0, 18.5, *base[63:]]
    voltage = [380 + (i % 5) * 0.1 for i in range(100)]
    voltage[61] = 381.5  # moves with the surge, less far
    found = find_departures({"current": _points(current), "voltage": _points(voltage)})
    (interval,) = found["intervals"]
    assert interval["points"] == 3 and interval["channel"] == "current"
    assert interval["channels"] == ["current", "voltage"]
    assert interval["direction"] == "up" and interval["value"] == 19.0
    assert interval["start"] == T0 + timedelta(minutes=60)
    assert interval["distance"] >= THRESHOLD
    assert {c["key"]: c["marked"] for c in found["channels"]} == {"current": 3, "voltage": 1}


def test_the_baseline_choice_moves_what_counts_as_usual() -> None:
    # A step up halfway: against the first 30 % it departs; against the whole record it is usual.
    values = [1.0 + (i % 3) * 0.01 for i in range(50)] + [5.0 + (i % 3) * 0.01 for i in range(50)]
    assert find_departures({"x": _points(values)}, baseline="first-30")["intervals"]
    assert find_departures({"x": _points(values)}, baseline="all")["intervals"] == []


def test_constant_or_unknown_inputs_are_named_not_scored() -> None:
    found = find_departures({"flat": _points([2.0] * 40)})
    assert found["channels"][0]["state"] == "constant"
    assert found["channels"][0]["median"] == 2.0
    assert found["channels"][0]["marked"] == 0
    assert found["score"] == [] and found["intervals"] == []
    with pytest.raises(ValueError, match="baseline"):
        find_departures({"x": _points([1.0] * 10)}, baseline="last-10")
    with pytest.raises(LookupError):
        find_departures({"x": []})


def test_only_a_record_that_ends_away_from_its_baseline_needs_a_look_now() -> None:
    steady = [10.0 + 0.1 * (i % 3) for i in range(60)]
    drifting = steady[:40] + [10.0 + 0.5 * i for i in range(1, 21)]
    returned = steady[:40] + [20.0] * 10 + steady[:10]
    now = latest_departure(find_departures({"current": _points(drifting)}))
    assert now is not None and now["channel"] == "current" and now["direction"] == "up"
    assert now["distance"] >= THRESHOLD
    assert now["since"] <= _points(drifting)[-1][0]
    assert latest_departure(find_departures({"current": _points(returned)})) is None
    assert latest_departure(find_departures({"current": _points(steady)})) is None


def test_record_changes_find_late_signals_and_keep_sustained_changes_ahead_of_spikes() -> None:
    base = [10 + (i % 5) * 0.1 for i in range(100)]
    signals = {f"signal-{i:02}": _points(base) for i in range(35)}
    signals["signal-34"] = _points(base[:40] + [20.0] * 30 + base[70:])
    signals["signal-00"] = _points([*base[:85], 1000.0, *base[86:]])
    found = record_changes(signals)
    assert len(found["channels"]) == 35
    assert found["intervals"][0]["channel"] == "signal-34"
    assert found["intervals"][0]["reason"] == "sustained"
    assert any(item["channel"] == "signal-00" for item in found["intervals"])
    assert len(found["intervals"]) <= 3
    # Similar signals in one event do not consume all three cards.
    signals["signal-33"] = signals["signal-34"]
    found = record_changes(signals)
    starts = [item["start"] for item in found["intervals"]]
    assert starts.count(T0 + timedelta(minutes=40)) == 1


def test_related_signal_comparison_separates_typical_change_from_stable_values() -> None:
    base = [10 + (i % 5) * 0.1 for i in range(100)]
    reference = (T0, T0 + timedelta(minutes=30))
    interval = (T0 + timedelta(minutes=60), T0 + timedelta(minutes=90))
    same = interval_comparison(_points(base), reference, interval)
    changed = interval_comparison(_points(base[:60] + [20.0] * 30 + base[90:]), reference, interval)
    assert same is not None and same["state"] == "within"
    assert changed is not None and changed["state"] == "higher"
    assert changed["current"] == 20.0
    assert interval_comparison([], reference, interval) is None


def test_only_a_signal_the_source_declares_a_running_total_is_left_unjudged() -> None:
    # AI-Hub leaves the energy unit unresolved; its item name still says what it is.
    assert declared_running_total(name="누적전력량 누적전력량", unit=None, meaning=None)
    assert declared_running_total(name="kwh_total", unit="kWh", meaning=None)
    assert declared_running_total(name="e1", unit=None, meaning="Accumulated active energy")
    # A temperature that keeps rising is a change to find, whatever its values look like.
    assert not declared_running_total(name="온도 온도", unit=None, meaning=None)
    assert not declared_running_total(name="vib_rms", unit="g", meaning="vibration RMS")


def test_a_constant_baseline_finds_level_changes_without_inventing_a_score() -> None:
    found = find_departures({"x": _points([0.0] * 40 + [1.0] * 10 + [-2.0] * 10 + [0.0] * 20)})
    assert found["channels"][0]["state"] == "level-change"
    assert found["score"] == []
    assert [
        (item["direction"], item["value"], item["distance"]) for item in found["intervals"]
    ] == [("up", 1.0, None), ("down", -2.0, None)]
    assert latest_departure(found) is None
    assert (
        latest_departure(find_departures({"x": _points([0.0] * 40 + [1.0] * 40)}))["kind"]
        == "level-change"
    )
    assert find_departures({"x": _points([1.0] * 40 + [1.0 + 1e-11] * 40)})["intervals"] == []


def test_overlapping_changes_from_distinct_sources_keep_their_own_reference() -> None:
    values = [0.0] * 40 + [1.0] * 40
    later = [
        (start + timedelta(days=1), end + timedelta(days=1), value)
        for start, end, value in _points(values)
    ]
    found = record_changes(
        {"a": _points(values), "b": later}, streams={"a": ("a", None), "b": ("b", None)}
    )
    assert found["baseline"] is None
    assert {item["channel"] for item in found["intervals"]} == {"a", "b"}
    assert {item["baseline"]["from"] for item in found["intervals"]} == {T0, T0 + timedelta(days=1)}
    same_time = record_changes(
        {"a": _points(values), "b": _points(values)}, streams={"a": ("a", None), "b": ("b", None)}
    )
    assert len(same_time["intervals"]) == 2


def test_sustained_changes_use_duration_and_constant_changes_get_no_size_ranking() -> None:
    short = _points([0.0] * 40 + [1.0] * 40)
    sparse = [
        (T0 + (start - T0) * 10, T0 + (end - T0) * 10, value)
        for start, end, value in _points([0.0] * 40 + [1.0] * 20)
    ]
    brief = _points([0.0] * 70 + [1.0] * 10)
    found = record_changes(
        {"short": short, "sparse": sparse, "brief": brief},
        streams={name: (name, None) for name in ("short", "sparse", "brief")},
    )
    assert found["intervals"][0]["channel"] == "sparse"
    assert len(found["intervals"]) == 3
    assert all(item["reason"] != "largest" for item in found["intervals"])


def test_related_channels_share_a_card_but_versions_of_one_channel_do_not() -> None:
    points = _points([0.0] * 40 + [1.0] * 40)
    related = record_changes(
        {"r": points, "s": points},
        streams={
            "r": ("source", None, "R", "phase-r"),
            "s": ("source", None, "S", "phase-s"),
        },
    )
    assert len(related["intervals"]) == 1
    versions = record_changes(
        {"old": points, "new": points},
        streams={
            "old": ("source", None, "R", "old-meaning"),
            "new": ("source", None, "R", "new-meaning"),
        },
    )
    assert len(versions["intervals"]) == 2


def test_a_signal_that_held_another_items_values_for_a_while_is_named_as_a_copy() -> None:
    phase = [220 + (i % 5) * 0.2 for i in range(100)]
    # The line voltage column held the phase voltage until the 40th point, then its own level.
    line = [phase[i] if i < 40 else 380 + (i % 5) * 0.3 for i in range(100)]
    # The harmonic column held the current, including stops where both read 0.
    current = [0.0 if 10 <= i < 15 else 50 + (i % 7) for i in range(100)]
    harmonic = [current[i] if i < 40 else 45 + (i % 7) * 0.5 for i in range(100)]
    found = copied_spans(
        {
            name: _points(values)
            for name, values in {
                "phase": phase,
                "line": line,
                "current": current,
                "harmonic": harmonic,
            }.items()
        },
        declared={"phase", "current"},
    )
    assert set(found) == {"line", "harmonic"}
    assert found["line"]["origin"] == "phase" and found["harmonic"]["origin"] == "current"
    assert found["line"]["from"] == T0
    assert found["line"]["to"] == T0 + timedelta(minutes=39, seconds=30)
    # Equal to the phase voltage and to the line column at once, the copy names the declared one.
    harmonic_v = [phase[i] if i < 40 else 7.5 + (i % 5) * 0.1 for i in range(100)]
    three = copied_spans(
        {"line": _points(line), "phase": _points(phase), "vharm": _points(harmonic_v)},
        declared={"phase"},
    )
    assert three["vharm"]["origin"] == "phase" and three["line"]["origin"] == "phase"
    # Without declared meanings the copy is the one whose own level differs afterwards.
    undeclared = copied_spans({"phase": _points(phase), "line": _points(line)})
    assert list(undeclared) == ["line"] and undeclared["line"]["origin"] == "phase"


def test_equal_throughout_or_nearly_equal_signals_are_not_copies() -> None:
    phase = [220 + (i % 5) * 0.2 for i in range(100)]
    # The same values all along say nothing about a change in how the record was kept.
    assert copied_spans({"a": _points(phase), "b": _points(phase)}) == {}
    # Balanced phases a fraction of a volt apart are different measurements.
    near = [value + 0.25 for value in phase]
    assert copied_spans({"a": _points(phase), "b": _points(near)}) == {}
    # Equal for a while, but neither changes level afterwards: no copy can be named.
    later = [phase[i] if i < 40 else phase[i] + 0.5 for i in range(100)]
    assert copied_spans({"a": _points(phase), "b": _points(later)}) == {}


def test_ranked_signals_are_chosen_before_longer_changes_in_other_items() -> None:
    base = [10 + (i % 5) * 0.1 for i in range(100)]
    # The derived item leaves its range for 60 points, the current for only 15.
    derived = [*base[:40], *[30.0] * 60]
    current = [*base[:80], *[25.0] * 15, *base[95:]]
    series = {"derived": _points(derived), "current": _points(current)}
    unranked = record_changes(series)
    assert unranked["intervals"][0]["channel"] == "derived"
    ranked = record_changes(series, priority={"current": 0})
    assert ranked["intervals"][0]["channel"] == "current"
    assert ranked["intervals"][0]["reason"] == "sustained"
