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


def robust_spread(values: np.ndarray) -> float:
    """Baseline spread: MAD, then mean absolute deviation, then standard deviation."""
    median = float(np.median(values))
    # Rounding noise of a constant record is no spread.
    floor = 1e-9 * max(1.0, abs(median))
    for spread in (
        _MAD_TO_SIGMA * float(np.median(np.abs(values - median))),
        1.2533 * float(np.mean(np.abs(values - median))),
        float(np.std(values)),
    ):
        if spread > floor:
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
        median, spread = float(np.median(reference)), robust_spread(reference)
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


# Units of an energy register, which counts up for as long as the equipment draws power.
_REGISTER_UNITS = frozenset({"Wh", "kWh", "MWh", "varh", "kvarh", "Mvarh", "VAh", "kVAh"})
_RUNNING_TOTAL_WORDS = ("누적", "적산", "cumulative", "accumulated")


def declared_running_total(*, name: str, unit: str | None, meaning: str | None) -> bool:
    """Whether the source declares a signal as a running total, like a cumulative energy register.

    A running total leaves its early range for as long as the equipment runs, so that departure
    says nothing about a change. Only what the source states decides it, never the values: a
    measured quantity that keeps rising, such as a temperature or a vibration RMS, is exactly
    the change the summary has to find.

    Args:
        name: The signal's names as the source and any registration give them.
        unit: Declared unit, if any.
        meaning: Declared observed property, if any.

    Returns:
        True when the unit is an energy register's or a name or the meaning says running total.
    """
    words = " ".join(text for text in (name, meaning) if text).lower()
    return unit in _REGISTER_UNITS or any(word in words for word in _RUNNING_TOTAL_WORDS)


def record_changes(
    series: Mapping[str, Sequence[tuple[datetime, datetime, float]]],
    *,
    limit: int = 3,
) -> dict[str, Any]:
    """Select distinct sustained, end-of-record and large changes across every signal.

    Each signal keeps its own runs: a succession of unrelated deviations across channels
    must not glue the entire record into one apparent event. Selection reasons describe
    observed changes, not equipment criticality or fault severity.
    """
    analyses = {name: find_departures({name: points}) for name, points in series.items() if points}
    if not analyses:
        raise LookupError("no stored values")
    candidates = [
        {**interval, "baseline": read["baseline"]}
        for read in analyses.values()
        for interval in read["intervals"]
    ]
    selected: list[dict[str, Any]] = []

    def distinct(item: dict[str, Any]) -> bool:
        for chosen in selected:
            intersection = max(
                0.0,
                (
                    min(item["end"], chosen["end"]) - max(item["start"], chosen["start"])
                ).total_seconds(),
            )
            union = (
                max(item["end"], chosen["end"]) - min(item["start"], chosen["start"])
            ).total_seconds()
            if union and intersection / union >= 0.6:
                return False
        return True

    def take(items: list[dict[str, Any]], reason: str) -> None:
        item = next((item for item in items if distinct(item)), None)
        if item is not None and len(selected) < limit:
            selected.append({**item, "reason": reason})

    sustained = sorted(
        candidates,
        key=lambda item: (
            -item["points"],
            -item["distance"],
            item["channel"],
            item["start"],
        ),
    )
    take(sustained, "sustained")
    last = max(point[1] for points in series.values() for point in points)
    spacing = max(
        (point[1] - point[0] for points in series.values() for point in points),
        default=timedelta(0),
    )
    recent = sorted(
        [item for item in candidates if last - item["end"] <= spacing * 1.5],
        key=lambda item: (-item["points"], -item["distance"], item["channel"]),
    )
    take(recent, "record-end")
    take(
        sorted(
            candidates,
            key=lambda item: (
                -item["distance"],
                -item["points"],
                item["channel"],
                item["start"],
            ),
        ),
        "largest",
    )
    if len(selected) < limit:
        for item in sustained:
            take([item], "sustained")
    return {
        "channels": [row for read in analyses.values() for row in read["channels"]],
        "threshold": THRESHOLD,
        "intervals": selected,
        "interval_count": len(candidates),
        "baseline": min(
            (read["baseline"] for read in analyses.values()), key=lambda row: row["from"]
        ),
    }


def interval_comparison(
    points: Sequence[tuple[datetime, datetime, float]],
    reference: tuple[datetime, datetime],
    interval: tuple[datetime, datetime],
) -> dict[str, Any] | None:
    """Compare the typical bucket mean in a change's period with its reference period."""
    before = np.asarray(
        [value for start, _, value in points if reference[0] <= start < reference[1]], dtype=float
    )
    after = np.asarray(
        [value for start, _, value in points if interval[0] <= start < interval[1]], dtype=float
    )
    if len(before) < 5 or len(after) < 3:
        return None
    median, current = float(np.median(before)), float(np.median(after))
    spread = robust_spread(before)
    if spread <= 0:
        return None
    distance = (current - median) / spread
    return {
        "reference": median,
        "current": current,
        "state": "higher"
        if distance >= THRESHOLD
        else "lower"
        if distance <= -THRESHOLD
        else "within",
        "distance": abs(distance),
    }


def latest_departure(found: Mapping[str, Any]) -> dict[str, Any] | None:
    """The departure the record ends in, if its last values are still outside the baseline.

    A record that left its baseline and came back needs no look now; one whose latest value is
    still far away does. Returns the signal furthest away at the end, how far, and since when.
    """
    score = found["score"]
    if not score:
        return None
    at, distance, channel = score[-1]
    if distance < found["threshold"]:
        return None
    holding = next(
        (item for item in found["intervals"] if item["start"] <= at <= item["end"]), None
    )
    return {
        "channel": channel,
        "distance": float(distance),
        "since": holding["start"] if holding else at,
        "direction": holding["direction"] if holding else None,
    }
