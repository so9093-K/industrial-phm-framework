"""How stored results moved across a selected range, not only between its two ends.

Two results say which direction a value took; the analyzed results in between say whether it
moved that way throughout, where its level changed and where the largest single step was.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import timedelta, timezone
from typing import Any

from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore, StepResult
from industrial_phm.models.package import StepKind

MAX_POINTS = 512
MIN_POINTS = 5
_KST = timezone(timedelta(hours=9))


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        for index in order[start : end + 1]:
            ranks[index] = (start + end) / 2
        start = end + 1
    return ranks


def rank_correlation(values: Sequence[float]) -> float:
    """Spearman correlation with order: +1 always rising, -1 always falling."""
    ranks = _ranks(values)
    n = len(ranks)
    mean = (n - 1) / 2
    spread = math.sqrt(sum((r - mean) ** 2 for r in ranks) * sum((i - mean) ** 2 for i in range(n)))
    if spread == 0:
        return 0.0
    return sum((i - mean) * (r - mean) for i, r in enumerate(ranks)) / spread


def level_shift(values: Sequence[float]) -> tuple[int, float] | None:
    """The split that best explains the values as two levels, and the share it explains."""
    n = len(values)
    total = math.fsum(values)
    mean = total / n
    variance = math.fsum((v - mean) ** 2 for v in values)
    if variance == 0:
        return None
    best: tuple[float, int] | None = None
    left_sum = left_square = 0.0
    square = math.fsum(v * v for v in values)
    for k in range(1, n):
        left_sum += values[k - 1]
        left_square += values[k - 1] ** 2
        if k < 2 or n - k < 2:
            continue
        right_sum, right_square = total - left_sum, square - left_square
        error = (left_square - left_sum**2 / k) + (right_square - right_sum**2 / (n - k))
        if best is None or error < best[0]:
            best = (error, k)
    if best is None:
        return None
    return best[1], 1 - best[0] / variance


def _line_error(values: Sequence[float]) -> float:
    """Squared error left by the best straight line through the values."""
    n = len(values)
    mean_x, mean_y = (n - 1) / 2, math.fsum(values) / n
    spread = math.fsum((i - mean_x) ** 2 for i in range(n))
    slope = math.fsum((i - mean_x) * (v - mean_y) for i, v in enumerate(values)) / spread
    return math.fsum((v - (mean_y + slope * (i - mean_x))) ** 2 for i, v in enumerate(values))


def series_shape(positions: Sequence[int], values: Sequence[float]) -> dict[str, Any]:
    """How one stored value moved across the range.

    ``flat`` when it did not move. A level shift is reported only when two levels explain the
    values clearly better than a straight line, so a gradual rise is not called a jump.
    ``steady`` means nearly every step went the overall way with no large step back.
    """
    n = len(values)
    if n < MIN_POINTS:
        return {"count": n, "trend": "insufficient"}
    span = max(values) - min(values)
    if span <= 1e-9 * max(1.0, max(abs(v) for v in values)):
        return {"count": n, "trend": "flat", "largest_step": None, "level_shift": None}
    rho = rank_correlation(values)
    trend = "increasing" if rho >= 0.6 else "decreasing" if rho <= -0.6 else "mixed"
    steps = [values[i + 1] - values[i] for i in range(n - 1)]
    jump = max(range(n - 1), key=lambda i: abs(steps[i]))
    share = abs(steps[jump]) / span
    shape: dict[str, Any] = {
        "count": n,
        "trend": trend,
        "rank_correlation": round(rho, 3),
        # A largest step is worth naming only when it is a sizeable part of the whole move.
        "largest_step": {
            "from": positions[jump],
            "to": positions[jump + 1],
            "direction": "increase" if steps[jump] > 0 else "decrease",
            "share_of_span": round(share, 3),
        }
        if share >= 0.3
        else None,
        "level_shift": None,
    }
    if trend != "mixed":
        sign = 1 if trend == "increasing" else -1
        along = sum(1 for step in steps if sign * step > 0) / len(steps)
        back = max((-sign * step for step in steps if sign * step < 0), default=0.0)
        shape["steady"] = along >= 0.8 and back <= 0.2 * span
    split = level_shift(values)
    if split is not None and split[1] >= 0.5:
        k, explained = split
        mean = math.fsum(values) / n
        step_error = (1 - explained) * math.fsum((v - mean) ** 2 for v in values)
        if step_error <= 0.5 * _line_error(values):
            before, after = math.fsum(values[:k]) / k, math.fsum(values[k:]) / (n - k)
            shape["level_shift"] = {
                "at": positions[k],
                "direction": "increase" if after > before else "decrease",
                "explained": round(explained, 3),
            }
    return shape


def position_label(result: StepResult, step_kind: StepKind) -> str:
    """What people call a step: an acquisition number, or a window's KST start time."""
    if step_kind is StepKind.OBSERVATION_WINDOW and result.event_start is not None:
        return result.event_start.astimezone(_KST).strftime("%m-%d %H:%M")
    return f"#{result.position}"


def range_analysis(
    store: SqlitePhmAnalysisStore,
    binding_id: str,
    step_kind: StepKind,
    first: int,
    last: int,
    features: Sequence[str],
) -> dict[str, Any]:
    """Shape of the model output and the named features across ``first..last``."""
    results, total = store.analyzed_between(binding_id, first, last, max_points=MAX_POINTS)
    positions = [result.position for result in results]
    labels = {result.position: position_label(result, step_kind) for result in results}

    def values(read: Any) -> tuple[list[int], list[float]]:
        pairs = [(r.position, read(r)) for r in results]
        kept = [(p, float(v)) for p, v in pairs if isinstance(v, (int, float)) and math.isfinite(v)]
        return [p for p, _ in kept], [v for _, v in kept]

    task = results[-1].output.get("task") if results else None
    key = "estimate" if task == "rul-estimate" else "score"
    primary = series_shape(*values(lambda r: r.output.get(key)))
    shapes = {
        name: series_shape(*values(lambda r, name=name: (r.features or {}).get(name)))
        for name in features
    }
    exact = store.analyzed_change_stats(binding_id, first, last, output_key=key, features=features)
    for name, shape in [("primary", primary), *shapes.items()]:
        stats = exact[name]
        span = (stats["high"] - stats["low"]) if stats["count"] else 0.0
        delta = stats["delta"]
        shape["largest_step"] = None
        if (
            delta is not None
            and span > 1e-9 * max(1.0, abs(stats["low"]), abs(stats["high"]))
            and abs(delta) / span >= 0.3
        ):
            shape["largest_step"] = {
                "from": stats["from"],
                "to": stats["to"],
                "direction": "increase" if delta > 0 else "decrease",
                "share_of_span": round(abs(delta) / span, 3),
            }
            for position in (stats["from"], stats["to"]):
                if position not in labels:
                    result = store.get_result(binding_id, position)
                    if result is not None:
                        labels[position] = position_label(result, step_kind)
        # A spike omitted from the flow sample still contradicts 'no change'.
        if shape.get("trend") == "flat" and span > 1e-9 * max(
            1.0, abs(stats["low"]), abs(stats["high"])
        ):
            shape["trend"] = "mixed"
        if shape.get("trend") in {"increasing", "decreasing"} and stats["pairs"]:
            increasing = shape["trend"] == "increasing"
            along = (stats["rises"] if increasing else stats["falls"]) / stats["pairs"]
            back = max(0.0, -stats["biggest_fall"] if increasing else stats["biggest_rise"])
            shape["steady"] = along >= 0.8 and back <= 0.2 * span
    named = set(positions[:1] + positions[-1:])
    for shape in (primary, *shapes.values()):
        for moment in (shape.get("largest_step") or {}, shape.get("level_shift") or {}):
            named.update(p for k, p in moment.items() if k in {"from", "to", "at"})
    return {
        "first": first,
        "last": last,
        "steps": total,
        "points": len(positions),
        "sampled": total > len(positions),
        "flow_basis": "sampled-results" if total > len(positions) else "all-results",
        "largest_step_basis": "adjacent-analyzed-results-in-full-range",
        "analyzed_first": positions[0] if positions else None,
        "analyzed_last": positions[-1] if positions else None,
        "labels": {str(p): labels[p] for p in sorted(named) if p in labels},
        "primary": primary,
        "features": shapes,
    }
