"""Departures from a chosen baseline: marks, merged intervals and refusals."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application.exploratory_anomaly import THRESHOLD, find_departures

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
    assert found["channels"] == [{"key": "flat", "state": "constant", "median": 2.0, "marked": 0}]
    with pytest.raises(ValueError, match="baseline"):
        find_departures({"x": _points([1.0] * 10)}, baseline="last-10")
    with pytest.raises(LookupError):
        find_departures({"x": []})
