"""Dataset-neutral Remaining Useful Life prediction contracts."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


class RulPredictionError(ValueError):
    """Raised when RUL prediction evidence violates its contract."""


@dataclass(frozen=True, slots=True)
class RulPredictionObservation:
    """One source-aligned point prediction for remaining useful life."""

    asset_id: str
    partition_id: str
    source_observation_id: str
    predicted_remaining_useful_life: float

    def __post_init__(self) -> None:
        for field_name in ("asset_id", "partition_id", "source_observation_id"):
            _validate_text(getattr(self, field_name), field_name)

        value = self.predicted_remaining_useful_life
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise RulPredictionError("predicted_remaining_useful_life must be numerical")
        predicted = float(value)
        if not math.isfinite(predicted):
            raise RulPredictionError("predicted_remaining_useful_life must be finite")
        object.__setattr__(self, "predicted_remaining_useful_life", predicted)


@dataclass(frozen=True, slots=True)
class RulPredictionSeries:
    """Ordered point predictions for one asset, partition, and RUL target definition."""

    prediction_method_id: str
    target_definition_id: str
    unit: str
    asset_id: str
    partition_id: str
    observations: Sequence[RulPredictionObservation]

    def __post_init__(self) -> None:
        for field_name in (
            "prediction_method_id",
            "target_definition_id",
            "unit",
            "asset_id",
            "partition_id",
        ):
            _validate_text(getattr(self, field_name), field_name)

        observations = tuple(self.observations)
        if not observations:
            raise RulPredictionError("observations must contain at least one RUL prediction")
        if not all(isinstance(observation, RulPredictionObservation) for observation in observations):
            raise RulPredictionError(
                "observations must contain only RulPredictionObservation values"
            )

        source_observation_ids: list[str] = []
        for observation in observations:
            if observation.asset_id != self.asset_id:
                raise RulPredictionError(
                    "RUL prediction observation asset_id must match its series"
                )
            if observation.partition_id != self.partition_id:
                raise RulPredictionError(
                    "RUL prediction observation partition_id must match its series"
                )
            source_observation_ids.append(observation.source_observation_id)

        if len(source_observation_ids) != len(set(source_observation_ids)):
            raise RulPredictionError(
                "RUL prediction source observation identities must be unique"
            )

        object.__setattr__(self, "observations", observations)


def _validate_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RulPredictionError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise RulPredictionError(f"{field_name} must not contain surrounding whitespace")
