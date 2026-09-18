"""Dataset-neutral descriptive statistics for aligned anomaly-score sequences."""

from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import StatisticsError, correlation


class ScoreStatisticsError(ValueError):
    """Raised when a descriptive score statistic receives invalid aligned input."""


def spearman_rho(
    left: Sequence[int | float],
    right: Sequence[int | float],
) -> float | None:
    """Return rank correlation for aligned sequences, or None when variance is zero."""
    if len(left) != len(right) or len(left) < 2:
        raise ScoreStatisticsError(
            "Spearman correlation requires equal sequences with at least two values"
        )
    try:
        return float(correlation(_average_ranks(left), _average_ranks(right)))
    except StatisticsError:
        return None


def late_vs_middle_rank_probability(
    middle_scores: Sequence[float],
    late_scores: Sequence[float],
) -> float | None:
    """Return P(late > middle) + 0.5 * P(late = middle) over all cross-segment pairs."""
    middle_count = len(middle_scores)
    late_count = len(late_scores)
    if middle_count == 0 or late_count == 0:
        return None

    pooled_ranks = _average_ranks(tuple(middle_scores) + tuple(late_scores))
    late_rank_sum = math.fsum(pooled_ranks[middle_count:])
    favourable = late_rank_sum - late_count * (late_count + 1) / 2.0
    return float(favourable / (middle_count * late_count))


def _average_ranks(values: Sequence[int | float]) -> tuple[float, ...]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(indexed)
    position = 0
    while position < len(indexed):
        end = position + 1
        while end < len(indexed) and indexed[end][1] == indexed[position][1]:
            end += 1
        average_rank = ((position + 1) + end) / 2.0
        for ranked_position in range(position, end):
            ranks[indexed[ranked_position][0]] = average_rank
        position = end
    return tuple(ranks)
