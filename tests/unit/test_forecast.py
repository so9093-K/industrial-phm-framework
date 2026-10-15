"""Future values continue a stored series; reach of a management level; a check on the past."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

pytest.importorskip("prophet", reason="install the forecast extra")

from industrial_phm.application.forecast import (
    ForecastUnavailable,
    forecast_values,
    horizon_reasons,
)

T0 = datetime(2026, 10, 1, tzinfo=UTC)


def _minutes(count: int, step: int = 1) -> list[datetime]:
    return [T0 + timedelta(minutes=step * index) for index in range(count)]


def test_horizons_need_twice_their_length_of_history_and_twenty_points() -> None:
    assert horizon_reasons(3 * 3600, 200) == {
        "1h": None,
        "24h": "short-history",
        "7d": "short-history",
        "30d": "short-history",
    }
    assert set(horizon_reasons(90 * 86_400, 19).values()) == {"few-points"}
    with pytest.raises(ForecastUnavailable, match="short-history"):
        forecast_values(_minutes(100), [1.0] * 100, 3600)
    with pytest.raises(ForecastUnavailable, match="few-points"):
        forecast_values(_minutes(10, 60), [1.0] * 10, 3600)


def test_a_rising_series_rises_and_its_level_is_reached_inside_the_horizon() -> None:
    times = _minutes(180)
    values = [1.0 + 0.01 * index for index in range(180)]  # 2.79 at the last minute
    result = forecast_values(times, values, 3600, threshold=3.1)
    assert result["trend"]["direction"] == "up"
    assert result["trend"]["end"] == pytest.approx(1.0 + 0.01 * 239, abs=0.05)
    reached = result["threshold"]
    assert reached["state"] == "expected" and reached["direction"] == "up"
    # 3.1 is 31 minutes past the last measurement on this line.
    expected = datetime.fromisoformat(reached["expected_at"]) - times[-1]
    assert timedelta(minutes=25) < expected < timedelta(minutes=37)
    assert len(result["forecast"]) == 201
    assert result["fitted"][-1][0] == result["history"][-1][0]
    check = result["backtest"]
    assert check["hidden_seconds"] == 2685.0 and check["points"] >= 40
    assert check["mean_absolute_error"] < check["naive_mean_absolute_error"]


def test_noise_without_a_trend_stays_flat_and_a_level_already_passed_is_named() -> None:
    rng = np.random.default_rng(5)
    values = [5.0 + rng.normal(0, 0.3) for _ in range(180)]
    result = forecast_values(_minutes(180), values, 3600, threshold=values[-1] - 0.01)
    assert result["trend"]["direction"] == "flat"
    assert result["threshold"]["state"] in {"already", "possible", "not-reached"}
    low = forecast_values(_minutes(180), values, 3600, threshold=100.0)
    assert low["threshold"]["state"] == "not-reached"
    assert low["threshold"]["expected_at"] is None
    assert all(math.isfinite(point[1]) for point in low["forecast"])


def test_a_daily_pattern_is_used_once_two_days_are_stored() -> None:
    times = _minutes(4 * 24 * 2, 30)  # four days every 30 minutes
    values = [10 + 3 * math.sin(2 * math.pi * index / 48) for index in range(len(times))]
    result = forecast_values(times, values, 86_400)
    assert result["model"]["seasonality"] == ["daily"]
    peak = max(point[1] for point in result["forecast"])
    trough = min(point[1] for point in result["forecast"])
    assert peak - trough > 4
