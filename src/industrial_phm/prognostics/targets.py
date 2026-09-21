"""Dataset-neutral Remaining Useful Life target contracts."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


class RulTargetError(ValueError):
    """Raised when RUL target evidence violates its contract."""


@dataclass(frozen=True, slots=True)
class RulTargetObservation:
    """One source-aligned RUL target value."""

    asset_id: str
    partition_id: str
    source_observation_id: str
    remaining_useful_life: float

    def __post_init__(self) -> None:
        for field_name in ("asset_id", "partition_id", "source_observation_id"):
            _validate_text(getattr(self, field_name), field_name)

        value = self.remaining_useful_life
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise RulTargetError("remaining_useful_life must be numerical")
        remaining_useful_life = float(value)
        if not math.isfinite(remaining_useful_life) or remaining_useful_life < 0.0:
            raise RulTargetError("remaining_useful_life must be finite and non-negative")
        object.__setattr__(self, "remaining_useful_life", remaining_useful_life)


@dataclass(frozen=True, slots=True)
class RulTargetSeries:
    """Ordered RUL targets for one asset and partition under one target definition."""

    target_definition_id: str
    unit: str
    asset_id: str
    partition_id: str
    observations: Sequence[RulTargetObservation]

    def __post_init__(self) -> None:
        for field_name in ("target_definition_id", "unit", "asset_id", "partition_id"):
            _validate_text(getattr(self, field_name), field_name)

        observations = tuple(self.observations)
        if not observations:
            raise RulTargetError("observations must contain at least one RUL target")
        if not all(isinstance(observation, RulTargetObservation) for observation in observations):
            raise RulTargetError("observations must contain only RulTargetObservation values")

        source_observation_ids: list[str] = []
        for observation in observations:
            if observation.asset_id != self.asset_id:
                raise RulTargetError("RUL target observation asset_id must match its series")
            if observation.partition_id != self.partition_id:
                raise RulTargetError("RUL target observation partition_id must match its series")
            source_observation_ids.append(observation.source_observation_id)

        if len(source_observation_ids) != len(set(source_observation_ids)):
            raise RulTargetError("RUL target source observation identities must be unique")

        object.__setattr__(self, "observations", observations)


def _validate_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RulTargetError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise RulTargetError(f"{field_name} must not contain surrounding whitespace")
