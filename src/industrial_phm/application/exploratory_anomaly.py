"""Where stored measurements leave their usual range, without a trained model.

Each signal is compared with a baseline part of its own record: the distance from the baseline
median in units of the baseline spread (median absolute deviation, scaled to a standard
deviation for normal data). Values at least ``THRESHOLD`` away are marked, and neighbouring
marks become one interval named by the signal that went furthest. A constant baseline instead
records level changes in measured units, with no standardized distance. This is an exploration aid,
not a fault diagnosis: the baseline is only the part of the record the user chose to compare
against.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
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
        own_first = min((point[0] for point in points), default=first)
        own_last = max((point[1] for point in points), default=own_first)
        own_cut = own_first + (own_last - own_first) * BASELINES[baseline]
        own_baseline = {
            "name": baseline,
            "from": own_first,
            "to": own_last if baseline == "all" else own_cut,
        }
        values = np.asarray([value for _, _, value in points], dtype=float)
        reference = np.asarray(
            [value for start, _, value in points if baseline == "all" or start < own_cut],
            dtype=float,
        )
        if reference.size < 5:
            channels.append(
                {"key": name, "state": "short-baseline", "marked": 0, "baseline": own_baseline}
            )
            continue
        median, spread = float(np.median(reference)), robust_spread(reference)
        constant = spread == 0
        tolerance = 1e-9 * max(1.0, abs(median))
        distance = (values - median) / spread if not constant else values - median
        marked = 0
        for (start, end, value), z in zip(points, distance, strict=True):
            size = abs(float(z))
            if not constant and size > score.get(start, (-1.0, "", end))[0]:
                score[start] = (size, name, end)
            changed = start >= own_cut and size > tolerance if constant else size >= THRESHOLD
            if changed:
                marked += 1
                current = marks.get(start)
                if current is None or (not constant and size > (current["distance"] or 0)):
                    marks[start] = {
                        "start": start,
                        "end": end,
                        "channel": name,
                        "value": float(value),
                        "median": median,
                        "distance": None if constant else size,
                        "kind": "level-change" if constant else "departure",
                        "baseline": own_baseline,
                        "direction": "up" if z > 0 else "down",
                    }
                involved.setdefault(start, set()).add(name)
        channels.append(
            {
                "key": name,
                "state": "level-change"
                if constant and marked
                else "constant"
                if constant
                else "scored",
                "median": median,
                "spread": spread,
                "marked": marked,
                "baseline": own_baseline,
                "ended_changed": constant and abs(float(values[-1]) - median) > tolerance,
            }
        )
    intervals: list[dict[str, Any]] = []
    for start in sorted(marks):
        mark = marks[start]
        previous = intervals[-1] if intervals else None
        if (
            previous is not None
            and start - previous["end"] <= gap
            and not (
                mark["kind"] == "level-change"
                and mark["direction"] != previous["peak"]["direction"]
            )
        ):
            previous["end"] = max(previous["end"], mark["end"])
            previous["points"] += 1
            previous["channels"] |= involved[start]
            if (mark["distance"] or 0) > (previous["peak"]["distance"] or 0) or (
                mark["kind"] == previous["peak"]["kind"] == "level-change"
                and abs(mark["value"] - mark["median"])
                > abs(previous["peak"]["value"] - previous["peak"]["median"])
            ):
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
    intervals.sort(key=lambda item: -(item["peak"]["distance"] or 0))
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
                "kind": item["peak"]["kind"],
                "baseline": item["peak"]["baseline"],
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


def copied_spans(
    series: Mapping[str, Sequence[tuple[datetime, datetime, float]]],
    *,
    declared: Collection[str] = (),
    min_share: float = 0.1,
) -> dict[str, dict[str, Any]]:
    """Signals that hold another signal's exact values for part of the record.

    A source that wrote one item into another item's column for a while leaves the copy equal
    to its origin there and different elsewhere. The copy's departures then describe how it
    was recorded, not the equipment.

    Args:
        series: ``(start, end, value)`` points per signal; only equal start times are compared.
        declared: Signals with a declared measurement meaning. When one of an equal pair has
            one and the other does not, the other is the copy.
        min_share: The equal stretch must cover at least this share of the comparable points.

    Returns:
        Per copied signal, ``origin`` (the signal it equals), ``from``/``to`` (the equal
        stretch) and ``points``.
    """
    grids = {
        name: {start: (end, value) for start, end, value in points}
        for name, points in series.items()
    }
    names = sorted(grids)
    found: dict[str, dict[str, Any]] = {}
    for index, first in enumerate(names):
        for second in names[index + 1 :]:
            left, right = grids[first], grids[second]
            # Both at zero (a stopped machine) says nothing about which item was recorded.
            starts = [
                start
                for start in sorted(left.keys() & right.keys())
                if abs(left[start][1]) > 1e-12 or abs(right[start][1]) > 1e-12
            ]
            if len(starts) < 10:
                continue
            equal = [
                abs(left[t][1] - right[t][1]) <= 1e-6 * max(abs(left[t][1]), abs(right[t][1]))
                for t in starts
            ]
            best, run, begin = (0, 0), 0, 0
            for position, same in enumerate(equal):
                run = run + 1 if same else 0
                if same and run == 1:
                    begin = position
                if run > best[1] - best[0]:
                    best = (begin, position + 1)
            inside = range(*best)
            outside = [same for position, same in enumerate(equal) if position not in inside]
            # Equal throughout, or often equal by coincidence, is no change of recording.
            if len(inside) < max(3, min_share * len(starts)) or len(outside) < 3:
                continue
            if sum(outside) > 0.1 * len(outside):
                continue
            copy = _copied_one(first, second, left, right, starts, inside, declared)
            if copy is None:
                continue
            origin = second if copy == first else first
            span = {
                "origin": origin,
                "from": starts[inside.start],
                "to": grids[copy][starts[inside.stop - 1]][0],
                "points": len(inside),
            }
            # Equal to several items at once, the copy names the one with a declared meaning.
            held = found.get(copy)
            if (
                held is None
                or held["points"] < span["points"]
                or (
                    held["points"] == span["points"]
                    and origin in declared
                    and held["origin"] not in declared
                )
            ):
                found[copy] = span
    return found


def _copied_one(
    first: str,
    second: str,
    left: Mapping[datetime, tuple[datetime, float]],
    right: Mapping[datetime, tuple[datetime, float]],
    starts: Sequence[datetime],
    inside: range,
    declared: Collection[str],
) -> str | None:
    if (first in declared) != (second in declared):
        return second if first in declared else first

    def shift(grid: Mapping[datetime, tuple[datetime, float]]) -> float:
        within = np.median([abs(grid[starts[i]][1]) for i in inside])
        beyond = np.median([abs(grid[t][1]) for i, t in enumerate(starts) if i not in inside])
        if within <= 0 or beyond <= 0:
            return float("inf") if within != beyond else 0.0
        return abs(float(np.log(beyond / within)))

    # The copy is the one whose own level differs once it is recorded correctly.
    moved = {first: shift(left), second: shift(right)}
    copy = max(moved, key=lambda name: moved[name])
    other = second if copy == first else first
    if moved[copy] < np.log(1.05) or moved[copy] - moved[other] < np.log(1.05):
        return None
    return copy


def record_changes(
    series: Mapping[str, Sequence[tuple[datetime, datetime, float]]],
    *,
    limit: int = 3,
    streams: Mapping[str, tuple[str, str | None] | tuple[str, str | None, str, str]] | None = None,
    priority: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """Select distinct sustained, end-of-record and large changes across every signal.

    Each signal keeps its own runs: a succession of unrelated deviations across channels
    must not glue the entire record into one apparent event. Selection reasons describe
    observed changes, not equipment criticality or fault severity.

    Args:
        series: ``(start, end, value)`` points per signal.
        limit: Most changes to select.
        streams: Source and point (and channel and meaning) per signal, so that only changes
            of one stream can stand for each other.
        priority: Rank per signal, lower first. Each kind of change is taken from the
            best-ranked signals that have one, so a measured load change outranks a longer
            change in a derived item. Unranked signals come last.

    Returns:
        Per-signal baseline states, the threshold, the selected intervals and their count.
    """
    worst = max(priority.values(), default=0) + 1 if priority else 0

    def rank(item: dict[str, Any]) -> int:
        return priority.get(item["channel"], worst) if priority else 0

    analyses = {name: find_departures({name: points}) for name, points in series.items() if points}
    if not analyses:
        raise LookupError("no stored values")
    candidates = [
        {**interval, "baseline": interval["baseline"]}
        for read in analyses.values()
        for interval in read["intervals"]
    ]
    selected: list[dict[str, Any]] = []

    def distinct(item: dict[str, Any]) -> bool:
        for chosen in selected:
            if streams is not None:
                own, other = streams[item["channel"]], streams[chosen["channel"]]
                if own[:2] != other[:2]:
                    continue
                # Related channels can describe the same event, even though their measured
                # meanings differ. Versions of the *same* channel remain separate records.
                if len(own) == len(other) == 4 and own[2] == other[2] and own[3] != other[3]:
                    continue
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
            rank(item),
            -(item["end"] - item["start"]).total_seconds(),
            -item["points"],
            -(item["distance"] or 0),
            item["channel"],
            item["start"],
        ),
    )
    take(sustained, "sustained")
    ends = {name: max(point[1] for point in points) for name, points in series.items() if points}
    spacing = {
        name: max(point[1] - point[0] for point in points)
        for name, points in series.items()
        if points
    }
    recent = sorted(
        [
            item
            for item in candidates
            if ends[item["channel"]] - item["end"] <= spacing[item["channel"]] * 1.5
        ],
        key=lambda item: (
            rank(item),
            -(item["end"] - item["start"]).total_seconds(),
            item["channel"],
        ),
    )
    take(recent, "record-end")
    take(
        sorted(
            [item for item in candidates if item["distance"] is not None],
            key=lambda item: (
                rank(item),
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
        "baselines": {name: read["baseline"] for name, read in analyses.items()},
        "baseline": next(iter(analyses.values()))["baseline"]
        if all(
            read["baseline"] == next(iter(analyses.values()))["baseline"]
            for read in analyses.values()
        )
        else None,
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
        delta = current - median
        return {
            "reference": median,
            "current": current,
            "state": "higher"
            if delta > 1e-9 * max(1, abs(median))
            else "lower"
            if delta < -1e-9 * max(1, abs(median))
            else "within",
            "distance": abs(delta),
            "kind": "level-change",
        }
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
    changed = next((row for row in found["channels"] if row.get("ended_changed")), None)
    level_change = None
    if changed is not None:
        last = max(
            (item for item in found["intervals"] if item["channel"] == changed["key"]),
            key=lambda item: item["end"],
        )
        level_change = {
            "channel": changed["key"],
            "distance": None,
            "since": last["start"],
            "direction": last["direction"],
            "kind": "level-change",
        }
    if not score:
        return level_change
    at, distance, channel = score[-1]
    if distance < found["threshold"]:
        return level_change
    holding = next(
        (item for item in found["intervals"] if item["start"] <= at <= item["end"]), None
    )
    return {
        "channel": channel,
        "distance": float(distance),
        "since": holding["start"] if holding else at,
        "direction": holding["direction"] if holding else None,
    }
