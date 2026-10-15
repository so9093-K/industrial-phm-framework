"""Where stored measurements leave their usual range, without a trained model.

Each signal is compared with a baseline part of its own record: the distance from the baseline
median in units of the baseline spread (median absolute deviation, scaled to a standard
deviation for normal data). Values at least ``THRESHOLD`` away are marked, and neighbouring
marks become one interval named by the signal that went furthest. This is an exploration aid,
not a fault diagnosis: the baseline is only the part of the record the user chose to compare
against.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from itertools import pairwise
from typing import Any

import numpy as np

THRESHOLD = 3.5
BASELINES = {"first-30": 0.3, "first-50": 0.5, "all": 1.0}
_MAD_TO_SIGMA = 1.4826


def _spread(values: np.ndarray) -> float:
    """Baseline spread: MAD, then mean absolute deviation, then standard deviation."""
    median = float(np.median(values))
    for spread in (
        _MAD_TO_SIGMA * float(np.median(np.abs(values - median))),
        1.2533 * float(np.mean(np.abs(values - median))),
        float(np.std(values)),
    ):
        if spread > 0:
            return spread
    return 0.0


def find_departures(
    series: Mapping[str, Sequence[tuple[datetime, datetime, float]]],
    *,
    baseline: str = "first-30",
    gap: timedelta | None = None,
) -> dict[str, Any]:
    """Score each signal against its baseline and merge marked points into intervals.

    ``series`` maps a signal to ``(start, end, value)`` points (a time bucket or one
    observation). Points of different signals are combined by their start time; marks no more
    than ``gap`` apart join one interval; by default, 1.5 times the usual spacing of values.
    """
    if baseline not in BASELINES:
        raise ValueError("unknown baseline")
    starts = [point[0] for points in series.values() for point in points]
    if not starts:
        raise LookupError("no stored values")
    first, last = min(starts), max(point[1] for points in series.values() for point in points)
    if gap is None:
        ordered = sorted(set(starts))
        steps = [(b - a).total_seconds() for a, b in pairwise(ordered)]
        gap = timedelta(seconds=1.5 * float(np.median(steps))) if steps else timedelta(0)
    cut = first + (last - first) * BASELINES[baseline]
    channels = []
    marks: dict[datetime, dict[str, Any]] = {}
    involved: dict[datetime, set[str]] = {}
    score: dict[datetime, tuple[float, str, datetime]] = {}
    for name, points in series.items():
        values = np.asarray([value for _, _, value in points], dtype=float)
        reference = np.asarray(
            [value for start, _, value in points if baseline == "all" or start < cut], dtype=float
        )
        if reference.size < 5:
            channels.append({"key": name, "state": "short-baseline", "marked": 0})
            continue
        median, spread = float(np.median(reference)), _spread(reference)
        if spread == 0:
            channels.append({"key": name, "state": "constant", "median": median, "marked": 0})
            continue
        distance = (values - median) / spread
        marked = 0
        for (start, end, value), z in zip(points, distance, strict=True):
            size = abs(float(z))
            if size > score.get(start, (-1.0, "", end))[0]:
                score[start] = (size, name, end)
            if size >= THRESHOLD:
                marked += 1
                current = marks.get(start)
                if current is None or size > current["distance"]:
                    marks[start] = {
                        "start": start,
                        "end": end,
                        "channel": name,
                        "value": float(value),
                        "median": median,
                        "distance": size,
                        "direction": "up" if z > 0 else "down",
                    }
                involved.setdefault(start, set()).add(name)
        channels.append(
            {"key": name, "state": "scored", "median": median, "spread": spread, "marked": marked}
        )
    intervals: list[dict[str, Any]] = []
    for start in sorted(marks):
        mark = marks[start]
        previous = intervals[-1] if intervals else None
        if previous is not None and start - previous["end"] <= gap:
            previous["end"] = max(previous["end"], mark["end"])
            previous["points"] += 1
            previous["channels"] |= involved[start]
            if mark["distance"] > previous["peak"]["distance"]:
                previous["peak"] = mark
            continue
        intervals.append(
            {
                "start": start,
                "end": mark["end"],
                "points": 1,
                "channels": set(involved[start]),
                "peak": mark,
            }
        )
    intervals.sort(key=lambda item: -item["peak"]["distance"])
    return {
        "threshold": THRESHOLD,
        "baseline": {"name": baseline, "from": first, "to": last if baseline == "all" else cut},
        "channels": channels,
        "score": [(start, value, name) for start, (value, name, _) in sorted(score.items())],
        "intervals": [
            {
                "start": item["start"],
                "end": item["end"],
                "points": item["points"],
                "channels": sorted(item["channels"]),
                "channel": item["peak"]["channel"],
                "value": item["peak"]["value"],
                "median": item["peak"]["median"],
                "distance": item["peak"]["distance"],
                "direction": item["peak"]["direction"],
            }
            for item in intervals
        ],
    }
