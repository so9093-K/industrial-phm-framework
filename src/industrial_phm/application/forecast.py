"""Future values of one stored measurement, continued from its own history with Prophet.

A forecast continues the stored flow of one signal: its trend, any daily/weekly pattern the
history is long enough to show, and an interval around it. It is not a failure time, a
remaining life or a maintenance date. Every result carries a check against the signal's own
past: the most recent stretch is hidden, predicted from what came before, and compared.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np

HORIZONS = {"1h": 3_600, "24h": 86_400, "7d": 7 * 86_400, "30d": 30 * 86_400}
MIN_POINTS = 20
INTERVAL_WIDTH = 0.8
DEFAULT_CHANGEPOINT_PRIOR_SCALE = 0.05
DEFAULT_CHANGEPOINT_RANGE = 0.9
FUTURE_POINTS = 200
# A horizon needs at least twice its length of history: a forecast should not reach further
# ahead than it has seen.
HISTORY_PER_HORIZON = 2.0


class ForecastUnavailable(ValueError):
    """The stored history cannot support this forecast; ``reason`` says why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def horizon_reasons(span_seconds: float, points: int) -> dict[str, str | None]:
    """For each horizon, None when the history supports it, otherwise the reason."""
    return {
        name: "few-points"
        if points < MIN_POINTS
        else "short-history"
        if span_seconds < HISTORY_PER_HORIZON * seconds
        else None
        for name, seconds in HORIZONS.items()
    }


def _prophet(
    seasonal: bool,
    span_seconds: float,
    *,
    changepoint_prior_scale: float = DEFAULT_CHANGEPOINT_PRIOR_SCALE,
    changepoint_range: float = DEFAULT_CHANGEPOINT_RANGE,
) -> Any:
    # The engine reports progress and optional plotting support on its own loggers.
    logging.getLogger("prophet").setLevel(logging.ERROR)
    logging.getLogger("prophet.plot").disabled = True
    try:
        from prophet import Prophet
    except ModuleNotFoundError as error:
        raise ForecastUnavailable("engine-unavailable") from error
    logging.getLogger("cmdstanpy").disabled = True
    return Prophet(
        interval_width=INTERVAL_WIDTH,
        uncertainty_samples=300,
        # Trend changes may sit late in the history, where wear tends to show.
        changepoint_range=changepoint_range,
        changepoint_prior_scale=changepoint_prior_scale,
        yearly_seasonality=False,
        weekly_seasonality=seasonal and span_seconds >= 14 * 86_400,
        daily_seasonality=seasonal and span_seconds >= 2 * 86_400,
    )


def _frame(times: Sequence[datetime], values: np.ndarray | None = None) -> Any:
    import pandas as pd  # type: ignore[import-untyped]

    stamps = [t.astimezone(UTC).replace(tzinfo=None) for t in times]
    frame = pd.DataFrame({"ds": stamps})
    if values is not None:
        frame["y"] = list(values)
    return frame


def _fit(
    times: Sequence[datetime],
    values: np.ndarray,
    seasonal: bool,
    *,
    changepoint_prior_scale: float = DEFAULT_CHANGEPOINT_PRIOR_SCALE,
    changepoint_range: float = DEFAULT_CHANGEPOINT_RANGE,
) -> Any:
    span = (times[-1] - times[0]).total_seconds()
    model = _prophet(
        seasonal,
        span,
        changepoint_prior_scale=changepoint_prior_scale,
        changepoint_range=changepoint_range,
    )
    model.fit(_frame(times, values))
    return model


def _predict(model: Any, times: Sequence[datetime]) -> Any:
    return model.predict(_frame(times))


def forecast_values(
    times: Sequence[datetime],
    values: Sequence[float],
    horizon_seconds: float,
    *,
    seasonal: bool = True,
    threshold: float | None = None,
    changepoint_prior_scale: float = DEFAULT_CHANGEPOINT_PRIOR_SCALE,
    changepoint_range: float = DEFAULT_CHANGEPOINT_RANGE,
    training_points: int | None = None,
    rolling_backtests: bool = False,
) -> dict[str, Any]:
    """Fit on the whole history, continue it ``horizon_seconds`` ahead and check it on the past.

    ``times`` must be increasing and timezone-aware. Returns plain numbers and UTC times.
    """
    if not math.isfinite(changepoint_prior_scale) or not 0.001 <= changepoint_prior_scale <= 0.5:
        raise ValueError("changepoint_prior_scale must be between 0.001 and 0.5")
    if not math.isfinite(changepoint_range) or not 0.5 <= changepoint_range <= 0.95:
        raise ValueError("changepoint_range must be between 0.5 and 0.95")
    if training_points is not None and not 20 <= training_points <= 1000:
        raise ValueError("training_points must be between 20 and 1000")
    if horizon_seconds <= 0:
        raise ValueError("horizon_seconds must be positive")
    pairs = [(t, float(v)) for t, v in zip(times, values, strict=True) if math.isfinite(v)]
    if training_points is not None:
        pairs = pairs[-training_points:]
    if len(pairs) < MIN_POINTS:
        raise ForecastUnavailable("few-points")
    times = [t for t, _ in pairs]
    observed = np.asarray([v for _, v in pairs], dtype=float)
    span = (times[-1] - times[0]).total_seconds()
    if span < HISTORY_PER_HORIZON * horizon_seconds:
        raise ForecastUnavailable("short-history")

    model = _fit(
        times,
        observed,
        seasonal,
        changepoint_prior_scale=changepoint_prior_scale,
        changepoint_range=changepoint_range,
    )
    # The model's own reading of the history, drawn under the measurements: where it lags them,
    # the forecast starts from that reading, not from the last value.
    shown = list(times[:: max(1, len(times) // 300)])
    if shown[-1] != times[-1]:
        shown.append(times[-1])
    fitted = _predict(model, shown)["yhat"].to_numpy(dtype=float)
    last = times[-1]
    step = horizon_seconds / FUTURE_POINTS
    future = [last + timedelta(seconds=step * index) for index in range(FUTURE_POINTS + 1)]
    predicted = _predict(model, future)
    yhat = predicted["yhat"].to_numpy(dtype=float)
    lower = predicted["yhat_lower"].to_numpy(dtype=float)
    upper = predicted["yhat_upper"].to_numpy(dtype=float)
    trend = predicted["trend"].to_numpy(dtype=float)

    # A direction is only stated when the trend moves more than the forecast's own uncertainty.
    change = float(trend[-1] - trend[0])
    half_width = float(upper[-1] - lower[-1]) / 2
    flat = abs(change) <= max(half_width, 1e-9 * max(1.0, abs(float(yhat[0]))))
    direction = "flat" if flat else "up" if change > 0 else "down"

    return {
        "history": [[t.astimezone(UTC).isoformat(), float(v)] for t, v in pairs],
        "fitted": [
            [t.astimezone(UTC).isoformat(), float(v)] for t, v in zip(shown, fitted, strict=True)
        ],
        "forecast": [
            [t.astimezone(UTC).isoformat(), float(a), float(b), float(c)]
            for t, a, b, c in zip(future, yhat, lower, upper, strict=True)
        ],
        "trend": {
            "direction": direction,
            "start": float(yhat[0]),
            "end": float(yhat[-1]),
            "end_lower": float(lower[-1]),
            "end_upper": float(upper[-1]),
            "change": float(yhat[-1] - yhat[0]),
            "slope_direction": "up" if change > 0 else "down" if change < 0 else "flat",
            "level_gap": float(yhat[0] - observed[-1]),
        },
        "threshold": None
        if threshold is None
        else _threshold(threshold, float(observed[-1]), future, yhat, lower, upper),
        "rolling_backtests": (
            _rolling_backtests(
                times,
                observed,
                horizon_seconds,
                seasonal,
                changepoint_prior_scale=changepoint_prior_scale,
                changepoint_range=changepoint_range,
            )
            if rolling_backtests
            else None
        ),
        "backtest": _backtest(
            times,
            observed,
            horizon_seconds,
            seasonal,
            changepoint_prior_scale=changepoint_prior_scale,
            changepoint_range=changepoint_range,
        ),
        "model": {
            "engine": "prophet",
            "interval_width": INTERVAL_WIDTH,
            "points": len(pairs),
            "changepoint_prior_scale": changepoint_prior_scale,
            "changepoint_range": changepoint_range,
            "training_points": training_points,
            "seasonality": [name for name in ("daily", "weekly") if name in model.seasonalities],
        },
    }


def _threshold(
    value: float,
    latest: float,
    future: Sequence[datetime],
    yhat: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
) -> dict[str, Any]:
    """When the forecast reaches a user's management level, expected and at the earliest."""
    if not math.isfinite(value):
        raise ValueError("threshold must be finite")
    upward = value >= yhat[0]
    if (latest >= value) if upward else (latest <= value):
        return {"value": value, "direction": "up" if upward else "down", "state": "already"}

    def first(series: np.ndarray) -> str | None:
        hits = np.flatnonzero(series >= value if upward else series <= value)
        return future[int(hits[0])].astimezone(UTC).isoformat() if hits.size else None

    expected = first(yhat)
    earliest = first(upper if upward else lower)
    return {
        "value": value,
        "direction": "up" if upward else "down",
        "state": "expected" if expected else "possible" if earliest else "not-reached",
        "expected_at": expected,
        "earliest_at": earliest,
    }


def _backtest(
    times: Sequence[datetime],
    observed: np.ndarray,
    horizon_seconds: float,
    seasonal: bool,
    *,
    changepoint_prior_scale: float = DEFAULT_CHANGEPOINT_PRIOR_SCALE,
    changepoint_range: float = DEFAULT_CHANGEPOINT_RANGE,
) -> dict[str, Any] | None:
    """Hide the most recent stretch, predict it from what came before, and compare."""
    span = (times[-1] - times[0]).total_seconds()
    hidden = min(float(horizon_seconds), 0.25 * span)
    cut = times[-1] - timedelta(seconds=hidden)
    train = [i for i, t in enumerate(times) if t <= cut]
    test = [i for i, t in enumerate(times) if t > cut]
    if len(train) < MIN_POINTS or len(test) < 5:
        return None
    model = _fit(
        [times[i] for i in train],
        observed[train],
        seasonal,
        changepoint_prior_scale=changepoint_prior_scale,
        changepoint_range=changepoint_range,
    )
    predicted = _predict(model, [times[i] for i in test])
    actual = observed[test]
    yhat = predicted["yhat"].to_numpy(dtype=float)
    inside = (actual >= predicted["yhat_lower"].to_numpy(dtype=float)) & (
        actual <= predicted["yhat_upper"].to_numpy(dtype=float)
    )
    return {
        "hidden_seconds": hidden,
        "points": len(test),
        "mean_absolute_error": float(np.mean(np.abs(actual - yhat))),
        "naive_mean_absolute_error": float(np.mean(np.abs(actual - observed[train[-1]]))),
        "inside_interval": float(inside.mean()),
    }


def _rolling_backtests(
    times: Sequence[datetime],
    observed: np.ndarray,
    horizon_seconds: float,
    seasonal: bool,
    *,
    changepoint_prior_scale: float,
    changepoint_range: float,
) -> list[dict[str, Any]]:
    """Three bounded historical cutoffs; each refit reads only observations before its cutoff.

    This is an on-demand product comparison, not a statistical validation claim.
    """
    results: list[dict[str, Any]] = []
    for share in (0.4, 0.6, 0.8):
        cut_index = int((len(times) - 1) * share)
        cutoff = times[cut_index]
        train = [i for i, time in enumerate(times) if time <= cutoff]
        stop = cutoff + timedelta(seconds=horizon_seconds)
        test = [i for i, time in enumerate(times) if cutoff < time <= stop]
        if len(train) < MIN_POINTS or len(test) < 5:
            continue
        model = _fit(
            [times[i] for i in train],
            observed[train],
            seasonal,
            changepoint_prior_scale=changepoint_prior_scale,
            changepoint_range=changepoint_range,
        )
        predicted = _predict(model, [times[i] for i in test])
        actual = observed[test]
        estimated = predicted["yhat"].to_numpy(dtype=float)
        inside = (actual >= predicted["yhat_lower"].to_numpy(dtype=float)) & (
            actual <= predicted["yhat_upper"].to_numpy(dtype=float)
        )
        results.append(
            {
                "cutoff": cutoff.astimezone(UTC).isoformat(),
                "points": len(test),
                "mean_absolute_error": float(np.mean(np.abs(actual - estimated))),
                "naive_mean_absolute_error": float(np.mean(np.abs(actual - observed[train[-1]]))),
                "inside_interval": float(inside.mean()),
            }
        )
    return results
