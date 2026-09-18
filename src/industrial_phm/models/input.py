"""Immutable dataset-neutral input contracts for model fitting and scoring."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


class ModelFitInputError(ValueError):
    """Raised when prepared model-fitting input violates its contract."""


class ModelScoringInputError(ValueError):
    """Raised when prepared model-scoring input violates its contract."""


@dataclass(frozen=True, slots=True)
class ModelFitInput:
    """Prepared feature rows and provenance for one model fit."""

    experiment_id: str
    feature_set_id: str
    feature_names: Sequence[str]
    feature_rows: Sequence[Sequence[float]]
    source_observation_ids: Sequence[str]
    sampling_policy_id: str
    random_seed: int
    source_observation_count: int
    reference_observation_count: int

    def __post_init__(self) -> None:
        for field_name in ("experiment_id", "feature_set_id", "sampling_policy_id"):
            _validate_text(
                getattr(self, field_name),
                field_name,
                error_type=ModelFitInputError,
            )
        if isinstance(self.random_seed, bool) or not isinstance(self.random_seed, int):
            raise ModelFitInputError("random_seed must be an integer")
        if self.random_seed < 0:
            raise ModelFitInputError("random_seed must be non-negative")
        for field_name in ("source_observation_count", "reference_observation_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ModelFitInputError(f"{field_name} must be a positive integer")
        if self.reference_observation_count > self.source_observation_count:
            raise ModelFitInputError(
                "reference_observation_count cannot exceed source_observation_count"
            )

        feature_names = _validated_names(
            self.feature_names,
            "feature_names",
            unique=True,
            error_type=ModelFitInputError,
        )
        feature_rows = _validated_feature_rows(
            self.feature_rows,
            width=len(feature_names),
            context="model-fit",
            error_type=ModelFitInputError,
        )
        source_observation_ids = _validated_names(
            self.source_observation_ids,
            "source_observation_ids",
            unique=False,
            error_type=ModelFitInputError,
        )
        if len(feature_rows) != len(source_observation_ids):
            raise ModelFitInputError(
                "feature_rows and source_observation_ids must contain the same number of values"
            )

        object.__setattr__(self, "feature_names", feature_names)
        object.__setattr__(self, "feature_rows", feature_rows)
        object.__setattr__(self, "source_observation_ids", source_observation_ids)

    @property
    def fit_observation_count(self) -> int:
        """Return the number of observations presented to model fitting.

        ``source_observation_count`` is the complete configured partition,
        ``reference_observation_count`` the subset the reference strategy admits, and this
        the population the sampling policy actually presents to the model.
        """
        return len(self.feature_rows)


@dataclass(frozen=True, slots=True)
class ModelScoringInput:
    """Prepared feature rows and unique source identities for model scoring."""

    experiment_id: str
    feature_set_id: str
    feature_names: Sequence[str]
    feature_rows: Sequence[Sequence[float]]
    source_observation_ids: Sequence[str]

    def __post_init__(self) -> None:
        for field_name in ("experiment_id", "feature_set_id"):
            _validate_text(
                getattr(self, field_name),
                field_name,
                error_type=ModelScoringInputError,
            )

        feature_names = _validated_names(
            self.feature_names,
            "feature_names",
            unique=True,
            error_type=ModelScoringInputError,
        )
        feature_rows = _validated_feature_rows(
            self.feature_rows,
            width=len(feature_names),
            context="model-scoring",
            error_type=ModelScoringInputError,
        )
        source_observation_ids = _validated_names(
            self.source_observation_ids,
            "source_observation_ids",
            unique=True,
            error_type=ModelScoringInputError,
        )
        if len(feature_rows) != len(source_observation_ids):
            raise ModelScoringInputError(
                "feature_rows and source_observation_ids must contain the same number of values"
            )

        object.__setattr__(self, "feature_names", feature_names)
        object.__setattr__(self, "feature_rows", feature_rows)
        object.__setattr__(self, "source_observation_ids", source_observation_ids)

    @property
    def observation_count(self) -> int:
        """Return the number of observations prepared for model scoring."""
        return len(self.feature_rows)


def _validated_feature_rows(
    rows: Sequence[Sequence[float]],
    *,
    width: int,
    context: str,
    error_type: type[ValueError],
) -> tuple[tuple[float, ...], ...]:
    result: list[tuple[float, ...]] = []
    for row_index, row in enumerate(rows):
        values: list[float] = []
        for value in row:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise error_type(
                    f"{context} feature row {row_index} must contain only numerical values"
                )
            number = float(value)
            if not math.isfinite(number):
                raise error_type(f"{context} feature row {row_index} contains non-finite values")
            values.append(number)
        if len(values) != width:
            raise error_type(
                f"{context} feature row {row_index} width must be {width}, got {len(values)}"
            )
        result.append(tuple(values))
    if not result:
        raise error_type(f"{context} input requires at least one feature row")
    return tuple(result)


def _validated_names(
    values: Sequence[str],
    field_name: str,
    *,
    unique: bool,
    error_type: type[ValueError],
) -> tuple[str, ...]:
    result = tuple(values)
    if not result:
        raise error_type(f"{field_name} must contain at least one value")
    for value in result:
        _validate_text(value, field_name, error_type=error_type)
    if unique and len(result) != len(set(result)):
        raise error_type(f"{field_name} must contain unique values")
    return result


def _validate_text(
    value: object,
    field_name: str,
    *,
    error_type: type[ValueError],
) -> None:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise error_type(f"{field_name} must not contain surrounding whitespace")
