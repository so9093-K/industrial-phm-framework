"""Immutable dataset-neutral input contract for model fitting."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


class ModelFitInputError(ValueError):
    """Raised when prepared model-fit input violates its contract."""


@dataclass(frozen=True, slots=True)
class ModelFitInput:
    """Prepared numerical rows and opaque source identities for one model fit."""

    experiment_id: str
    feature_set_id: str
    feature_names: Sequence[str]
    rows: Sequence[Sequence[float]]
    source_observation_ids: Sequence[str]
    sampling_policy_id: str
    random_seed: int
    input_observation_count: int

    def __post_init__(self) -> None:
        for field_name in ("experiment_id", "feature_set_id", "sampling_policy_id"):
            _validate_text(getattr(self, field_name), field_name)
        if isinstance(self.random_seed, bool) or not isinstance(self.random_seed, int):
            raise ModelFitInputError("random_seed must be an integer")
        if self.random_seed < 0:
            raise ModelFitInputError("random_seed must be non-negative")
        if (
            isinstance(self.input_observation_count, bool)
            or not isinstance(self.input_observation_count, int)
            or self.input_observation_count <= 0
        ):
            raise ModelFitInputError("input_observation_count must be a positive integer")

        feature_names = _validated_names(self.feature_names, "feature_names", unique=True)
        rows = _validated_rows(self.rows, width=len(feature_names))
        source_observation_ids = _validated_names(
            self.source_observation_ids,
            "source_observation_ids",
            unique=False,
        )
        if len(rows) != len(source_observation_ids):
            raise ModelFitInputError(
                "rows and source_observation_ids must contain the same number of values"
            )

        object.__setattr__(self, "feature_names", feature_names)
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "source_observation_ids", source_observation_ids)

    @property
    def output_observation_count(self) -> int:
        """Return the number of rows presented to the model."""
        return len(self.rows)


def _validated_rows(
    rows: Sequence[Sequence[float]],
    *,
    width: int,
) -> tuple[tuple[float, ...], ...]:
    result: list[tuple[float, ...]] = []
    for row_index, row in enumerate(rows):
        values: list[float] = []
        for value in row:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ModelFitInputError(
                    f"model-fit row {row_index} must contain only numerical values"
                )
            number = float(value)
            if not math.isfinite(number):
                raise ModelFitInputError(f"model-fit row {row_index} contains non-finite values")
            values.append(number)
        if len(values) != width:
            raise ModelFitInputError(
                f"model-fit row {row_index} width must be {width}, got {len(values)}"
            )
        result.append(tuple(values))
    if not result:
        raise ModelFitInputError("model-fit input requires at least one row")
    return tuple(result)


def _validated_names(
    values: Sequence[str],
    field_name: str,
    *,
    unique: bool,
) -> tuple[str, ...]:
    result = tuple(values)
    if not result:
        raise ModelFitInputError(f"{field_name} must contain at least one value")
    for value in result:
        _validate_text(value, field_name)
    if unique and len(result) != len(set(result)):
        raise ModelFitInputError(f"{field_name} must contain unique values")
    return result


def _validate_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ModelFitInputError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise ModelFitInputError(f"{field_name} must not contain surrounding whitespace")
