"""Degradation indicator of one stored signal and its margin to user-set conditions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from industrial_phm.application.condition_outlook import (
    degradation,
    linear_reach,
    reach,
    theil_sen,
)


def test_a_single_jump_does_not_tilt_the_rate() -> None:
    xs = np.arange(30, dtype=float)
    ys = 2.0 + 0.5 * xs
    ys[17] += 40.0
    assert theil_sen(xs, ys) == pytest.approx(0.5)
    assert theil_sen(np.ones(4), np.arange(4, dtype=float)) == 0.0


def test_a_record_that_leaves_its_baseline_names_when_and_how_fast() -> None:
    rng = np.random.default_rng(3)
    flat = 1.0 + rng.normal(0, 0.02, 70)
    rising = 1.0 + 0.05 * np.arange(1, 31) + rng.normal(0, 0.02, 30)
    values = np.concatenate([flat, rising])
    result = degradation(list(range(1, 101)), list(values))
    assert result["baseline"]["points"] == 30
    assert result["baseline"]["median"] == pytest.approx(1.0, abs=0.02)
    assert result["recent"]["first_index"] == 80 and result["recent"]["points"] == 20
    assert result["change_ratio"] == pytest.approx(result["change"] / result["baseline"]["median"])
    assert result["change"] > 0.8
    # The recent rate is the rise; the stretch before it straddles the bend and is slower.
    assert result["rate"] == pytest.approx(0.05, abs=0.005)
    assert result["earlier_rate"] < result["rate"]
    departure = result["departure"]
    assert departure["latest_outside"] and departure["latest_distance"] > 3.5
    # Values stay outside from a few acquisitions into the rise onwards.
    assert 70 <= departure["since_index"] <= 76
    assert departure["since_share"] >= 0.8


def test_a_signed_or_constant_baseline_states_only_what_it_supports() -> None:
    signed = degradation(list(range(40)), [(-1) ** i * 0.5 + 0.01 * i for i in range(40)])
    assert signed["change_ratio"] is None
    constant = degradation(list(range(40)), [2.0] * 30 + [3.0] * 10)
    assert constant["departure"] is None and constant["spread_ratio"] is None
    assert constant["change"] == pytest.approx(1.0)
    with pytest.raises(ValueError, match="20 values"):
        degradation(list(range(10)), [1.0] * 10)


def test_a_limit_is_already_reached_expected_possible_or_beyond_the_search() -> None:
    offsets = np.arange(5, dtype=float) * 60
    expected = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    fast, slow = expected + 1, expected - 1
    assert reach(0.5, 0.9, offsets, expected, fast, slow, upper=True)["state"] == "already"
    hit = reach(3.5, 1.0, offsets, expected, fast, slow, upper=True)
    assert hit == {"state": "expected", "expected": 180.0, "earliest": 120.0, "latest": 240.0}
    assert reach(5.5, 1.0, offsets, expected, fast, slow, upper=True) == {
        "state": "possible",
        "expected": None,
        "earliest": 240.0,
        "latest": None,
    }
    assert reach(9.0, 1.0, offsets, expected, fast, slow, upper=True)["state"] == "beyond"
    falling = reach(2.5, 5.0, offsets, expected[::-1], slow[::-1], fast[::-1], upper=False)
    assert falling["state"] == "expected" and falling["expected"] == 180.0
    with pytest.raises(ValueError):
        reach(float("nan"), 1.0, offsets, expected, upper=True)


def test_the_recent_rate_is_carried_on_from_the_last_value() -> None:
    seconds = [60.0 * i for i in range(50)]
    values = [1.0 + 0.1 * i for i in range(50)]  # 5.9 last, 0.1 per minute
    carried = linear_reach(
        seconds,
        values,
        {"management": 7.0, "end": 20.0, "passed": 2.0},
        upper=True,
        search_seconds=1800,
    )
    assert carried["rate_per_second"] == pytest.approx(0.1 / 60)
    assert carried["limits"]["management"]["expected"] == pytest.approx(660.0)
    assert carried["limits"]["end"]["state"] == "beyond"
    assert carried["limits"]["passed"]["state"] == "already"
    away = linear_reach(seconds, values, {"low": 0.0}, upper=False, search_seconds=1800)
    assert away["limits"]["low"]["state"] == "beyond"


def test_a_forecast_reaches_each_limit_past_the_chart_horizon() -> None:
    pytest.importorskip("prophet", reason="install the forecast extra")
    from industrial_phm.application.forecast import ForecastUnavailable, limit_reach

    start = datetime(2026, 10, 1, tzinfo=UTC)
    times = [start + timedelta(minutes=i) for i in range(180)]
    values = [1.0 + 0.01 * i for i in range(180)]  # 2.79 last, 0.01 a minute
    result = limit_reach(
        times,
        values,
        {"management": 3.1, "end": 3.5, "passed": 2.0},
        upper=True,
        search_seconds=90 * 60,
        steps=90,
    )
    assert result["points"] == 180
    management = result["limits"]["management"]
    assert management["state"] == "expected"
    assert 25 * 60 <= management["expected"] <= 37 * 60
    assert management["earliest"] <= management["expected"]
    assert 65 * 60 <= result["limits"]["end"]["expected"] <= 77 * 60
    assert result["limits"]["passed"]["state"] == "already"
    falling = limit_reach(
        times,
        values[::-1],
        {"low": 0.7},
        upper=False,
        search_seconds=90 * 60,
        steps=90,
    )
    assert falling["limits"]["low"]["state"] == "expected"
    with pytest.raises(ForecastUnavailable, match="few-points"):
        limit_reach(times[:10], values[:10], {}, upper=True, search_seconds=60, steps=1)
