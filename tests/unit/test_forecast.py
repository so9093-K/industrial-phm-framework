"""Future values continue a stored series; reach of a management level; a check on the past."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from itertools import pairwise

import numpy as np
import pytest

pytest.importorskip("prophet", reason="install the forecast extra")

from industrial_phm.application.forecast import (
    ForecastUnavailable,
    _threshold,
    forecast_values,
    horizon_reasons,
)
from industrial_phm.runtime.operations_web_forecast import measurement_version

T0 = datetime(2026, 10, 1, tzinfo=UTC)


def _minutes(count: int, step: int = 1) -> list[datetime]:
    return [T0 + timedelta(minutes=step * index) for index in range(count)]


def test_measurement_version_identifies_corrected_input_without_a_new_last_observation() -> None:
    times = _minutes(30)
    values = [float(index) for index in range(30)]
    meta = {"source_id": "sensor-a", "measurement_point_id": "drive-end"}
    identity = ("pump-1", "history", "current")
    original = measurement_version(*identity, times, values, meta)
    corrected = values.copy()
    corrected[12] += 0.5
    assert times[-1] == times[-1] and corrected[-1] == values[-1]
    assert measurement_version(*identity, times, corrected, meta) != original
    assert measurement_version(*identity, times, values, meta) == original
    assert (
        measurement_version(*identity, times, values, {**meta, "source_id": "sensor-b"})
        != original
    )
    assert measurement_version("pump-2", "history", "current", times, values, meta) != original


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


def test_forecast_scenario_settings_are_applied_to_fit_and_history_check() -> None:
    times = _minutes(240)
    values = [1.0 + index * 0.02 for index in range(240)]
    result = forecast_values(
        times,
        values,
        3600,
        changepoint_prior_scale=0.1,
        changepoint_range=0.8,
        training_points=160,
        rolling_backtests=True,
    )
    assert result["model"]["points"] == 160
    assert result["model"]["changepoint_prior_scale"] == 0.1
    assert result["model"]["changepoint_range"] == 0.8
    assert len(result["rolling_backtests"]) == 3
    assert all(fold["points"] >= 5 for fold in result["rolling_backtests"])
    assert result["history"][0][0] == times[80].isoformat()
    assert result["trend"]["slope_direction"] == "up"
    assert math.isfinite(result["trend"]["level_gap"])


@pytest.mark.parametrize(
    "params",
    [
        {"changepoint_prior_scale": 0.0},
        {"changepoint_prior_scale": float("nan")},
        {"changepoint_prior_scale": 1.0},
        {"changepoint_range": 0.1},
        {"changepoint_range": float("inf")},
        {"training_points": 1},
        {"training_points": 1001},
    ],
)
def test_invalid_forecast_scenario_settings_are_rejected(params: dict[str, float | int]) -> None:
    with pytest.raises(ValueError):
        forecast_values(_minutes(180), [float(i) for i in range(180)], 3600, **params)


def test_upper_limit_uses_last_observation_not_model_start_to_report_already() -> None:
    future = _minutes(2)
    crossing = _threshold(
        4.0,
        3.9,
        future,
        np.array([4.1, 4.2]),
        np.array([3.8, 4.0]),
        np.array([4.3, 4.4]),
        direction="upper",
    )
    assert crossing["state"] == "expected"
    assert crossing["expected_at"] == future[0].isoformat()
    assert crossing["limit_kind"] == "upper"
    assert (
        _threshold(
            4.0,
            4.1,
            future,
            np.array([3.9, 3.8]),
            np.array([3.7, 3.6]),
            np.array([4.1, 4.0]),
            direction="upper",
        )["state"]
        == "already"
    )


def test_lower_limit_is_explicit_and_does_not_infer_direction_from_prediction() -> None:
    future = _minutes(2)
    crossing = _threshold(
        4.0,
        4.1,
        future,
        np.array([3.9, 3.8]),
        np.array([3.7, 3.6]),
        np.array([4.1, 4.0]),
        direction="lower",
    )
    assert crossing["state"] == "expected"
    assert crossing["expected_at"] == future[0].isoformat()
    assert crossing["direction"] == "down"
    assert (
        _threshold(
            4.0,
            3.9,
            future,
            np.array([4.1, 4.2]),
            np.array([3.8, 4.0]),
            np.array([4.3, 4.4]),
            direction="lower",
        )["state"]
        == "already"
    )


def test_count_horizon_forecasts_only_whole_acquisition_steps() -> None:
    times = _minutes(140)
    values = [1.0 + 0.01 * index for index in range(140)]
    result = forecast_values(
        times,
        values,
        30 * 60,
        seasonal=False,
        future_acquisitions=30,
        threshold=3.0,
        threshold_direction="upper",
    )
    future = [datetime.fromisoformat(point[0]) for point in result["forecast"]]
    assert len(future) == 31
    assert future[0] == times[-1]
    assert future[-1] == times[-1] + timedelta(minutes=30)
    assert all(right - left == timedelta(minutes=1) for left, right in pairwise(future))
    assert result["model"]["future_acquisitions"] == 30
