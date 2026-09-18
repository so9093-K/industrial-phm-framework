"""Dataset-neutral observation-level model output contracts."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field


class AnomalyScoresError(ValueError):
    """Raised when observation-level anomaly scores violate their contract."""


@dataclass(frozen=True, slots=True)
class AnomalyScores:
    """Observation-aligned scores whose larger values mean greater anomalousness."""

    experiment_id: str
    source_observation_ids: Sequence[str]
    scores: Sequence[float]
    higher_is_more_anomalous: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        _validate_text(self.experiment_id, "experiment_id")
        observation_ids = _validated_observation_ids(self.source_observation_ids)
        scores = _validated_scores(self.scores)
        if len(observation_ids) != len(scores):
            raise AnomalyScoresError(
                "source_observation_ids and scores must contain the same number of values"
            )
        object.__setattr__(self, "source_observation_ids", observation_ids)
        object.__setattr__(self, "scores", scores)

    @property
    def observation_count(self) -> int:
        """Return the number of scored source observations."""
        return len(self.scores)


def _validated_observation_ids(values: Sequence[str]) -> tuple[str, ...]:
    result = tuple(values)
    if not result:
        raise AnomalyScoresError("source_observation_ids must contain at least one value")
    for value in result:
        _validate_text(value, "source_observation_ids")
    if len(result) != len(set(result)):
        raise AnomalyScoresError("source_observation_ids must contain unique values")
    return result


def _validated_scores(values: Sequence[float]) -> tuple[float, ...]:
    result: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise AnomalyScoresError("scores must contain only numerical values")
        score = float(value)
        if not math.isfinite(score):
            raise AnomalyScoresError("scores must contain only finite values")
        result.append(score)
    if not result:
        raise AnomalyScoresError("scores must contain at least one value")
    return tuple(result)


def _validate_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise AnomalyScoresError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise AnomalyScoresError(f"{field_name} must not contain surrounding whitespace")
