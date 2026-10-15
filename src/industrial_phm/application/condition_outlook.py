"""How far one stored signal has moved, and how much room it has left before set conditions.

The outlook joins what the record already shows with forecasts of what comes next:

- the degradation indicator: the move of the recent level away from the signal's own early
  baseline, how fast it moves now and before, how much wider it swings, and since when it stays
  outside its usual range (the same baseline distance as the exploratory departure search);
- the remaining margin: for each condition the user sets (a management level and an end
  condition), when a forecast reaches it. The forecast distance to the end condition is the
  remaining useful life (RUL) under that definition of end.

Several forecasts are compared side by side, because the margin depends on how the record is
read: the chosen settings, only the recent part of the record, a forecast that follows trend
changes more readily, and the recent rate carried on from the last value. Every number is
computed here; the Web and the AI briefing only word it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from industrial_phm.application.exploratory_anomaly import THRESHOLD, robust_spread

BASELINE_SHARE = 0.3
RECENT_SHARE = 0.2
MIN_WINDOW = 10
MAX_WINDOW = 200
MIN_POINTS = 20
# A departure counts as lasting from the first point after which most points stay outside.
SUSTAINED_SHARE = 0.8


def theil_sen(xs: np.ndarray, ys: np.ndarray) -> float:
    """Median of the pairwise slopes, so a single jump does not tilt the rate."""
    first, second = np.triu_indices(len(xs), k=1)
    run = xs[second] - xs[first]
    keep = run != 0
    if not keep.any():
        return 0.0
    return float(np.median((ys[second] - ys[first])[keep] / run[keep]))


def _windows(xs: np.ndarray) -> tuple[int, int]:
    """Baseline length (the first 30% of the axis, at least five points) and recent length."""
    cut = xs[0] + (xs[-1] - xs[0]) * BASELINE_SHARE
    baseline = max(5, int(np.count_nonzero(xs < cut)))
    recent = min(MAX_WINDOW, max(MIN_WINDOW, int(len(xs) * RECENT_SHARE)))
    return baseline, recent


def degradation(xs: Sequence[float], values: Sequence[float]) -> dict[str, Any]:
    """The degradation indicator of one signal, with window bounds as indices into ``xs``.

    ``xs`` is the axis in the unit rates are stated in (acquisitions, hours or days).
    """
    x = np.asarray(xs, dtype=float)
    y = np.asarray(values, dtype=float)
    if len(y) < MIN_POINTS:
        raise ValueError("a degradation indicator needs at least 20 values")
    base_n, recent_n = _windows(x)
    baseline, recent = y[:base_n], y[-recent_n:]
    base_median, base_spread = float(np.median(baseline)), robust_spread(baseline)
    recent_median, recent_spread = float(np.median(recent)), robust_spread(recent)
    # A relative change only means something for a level that cannot go below zero.
    level = bool(np.all(y >= 0)) and base_median > 0
    rate = theil_sen(x[-recent_n:], recent)
    earlier = None
    if len(y) >= 2 * recent_n + 5:
        earlier = theil_sen(x[-2 * recent_n : -recent_n], y[-2 * recent_n : -recent_n])
    departure: dict[str, Any] | None = None
    if base_spread > 0:
        distance = (y - base_median) / base_spread
        outside = np.abs(distance) >= THRESHOLD
        # Share of outside points from each index to the end.
        share = np.cumsum(outside[::-1])[::-1] / np.arange(len(y), 0, -1)
        lasting = np.flatnonzero(outside & (share >= SUSTAINED_SHARE))
        lasting = lasting[lasting <= len(y) - 3]
        since = int(lasting[0]) if lasting.size else None
        departure = {
            "threshold": THRESHOLD,
            "outside": int(np.count_nonzero(outside)),
            "since_index": since,
            "since_share": None if since is None else float(share[since]),
            "latest_distance": float(distance[-1]),
            "latest_outside": bool(outside[-1]),
        }
    return {
        "points": len(y),
        "baseline": {
            "first_index": 0,
            "last_index": base_n - 1,
            "points": base_n,
            "median": base_median,
            "spread": base_spread,
        },
        "recent": {
            "first_index": len(y) - recent_n,
            "last_index": len(y) - 1,
            "points": recent_n,
            "median": recent_median,
            "spread": recent_spread,
        },
        "latest": float(y[-1]),
        "change": recent_median - base_median,
        "change_ratio": (recent_median - base_median) / base_median if level else None,
        "rate": rate,
        "earlier_rate": earlier,
        "spread_ratio": recent_spread / base_spread if base_spread > 0 else None,
        "departure": departure,
    }


def reach(
    limit: float,
    latest: float,
    offsets: np.ndarray,
    expected: np.ndarray,
    fast: np.ndarray | None = None,
    slow: np.ndarray | None = None,
    *,
    upper: bool,
) -> dict[str, Any]:
    """When a forecast first reaches ``limit``, as offsets from the last measurement.

    ``fast`` is the interval edge that reaches the limit first and ``slow`` the one that
    reaches it last; either may be missing for a forecast without an interval.
    """
    if not math.isfinite(limit):
        raise ValueError("a condition must be finite")
    if (latest >= limit) if upper else (latest <= limit):
        return {"state": "already", "expected": None, "earliest": None, "latest": None}

    def first(series: np.ndarray | None) -> float | None:
        if series is None:
            return None
        hits = np.flatnonzero(series >= limit if upper else series <= limit)
        return float(offsets[int(hits[0])]) if hits.size else None

    at, earliest, last = first(expected), first(fast), first(slow)
    return {
        "state": "expected" if at is not None else "possible" if earliest is not None else "beyond",
        "expected": at,
        "earliest": earliest,
        "latest": last,
    }


def linear_reach(
    seconds: Sequence[float],
    values: Sequence[float],
    limits: Mapping[str, float],
    *,
    upper: bool,
    search_seconds: float,
) -> dict[str, Any]:
    """The recent rate carried on from the last value, against each condition."""
    x = np.asarray(seconds, dtype=float)
    y = np.asarray(values, dtype=float)
    _, recent_n = _windows(x)
    rate = theil_sen(x[-recent_n:], y[-recent_n:])
    latest = float(y[-1])
    results: dict[str, dict[str, Any]] = {}
    for name, limit in limits.items():
        if (latest >= limit) if upper else (latest <= limit):
            results[name] = {"state": "already", "expected": None, "earliest": None, "latest": None}
            continue
        toward = rate > 0 if upper else rate < 0
        at = (limit - latest) / rate if toward else math.inf
        results[name] = {
            "state": "expected" if at <= search_seconds else "beyond",
            "expected": at if at <= search_seconds else None,
            "earliest": None,
            "latest": None,
        }
    return {"start": latest, "rate_per_second": rate, "points": recent_n, "limits": results}
