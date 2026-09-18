"""Dataset-neutral train-only feature scaling state."""

from __future__ import annotations

import math
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, field
from statistics import median

from industrial_phm.experiments.config import (
    ExperimentConfig,
    FitPartition,
    ReferenceStrategy,
    ScalingStrategy,
)

PREPROCESSING_STATE_SCHEMA_ID = "preprocessing-state-v1"


class PreprocessingError(ValueError):
    """Raised when preprocessing input or fitted state violates its contract."""


@dataclass(frozen=True, slots=True)
class PreprocessingFitProvenance:
    """Identity of the feature partition supplied to preprocessing fit."""

    dataset_id: str
    split_id: str
    fold_id: str
    partition: str
    feature_set_id: str

    def __post_init__(self) -> None:
        for field_name in ("dataset_id", "split_id", "fold_id", "partition", "feature_set_id"):
            _validate_text(getattr(self, field_name), field_name)


@dataclass(frozen=True, slots=True)
class PreprocessingState:
    """Immutable train-fitted scaling state with experiment provenance."""

    experiment_id: str
    dataset_id: str
    split_id: str
    fold_id: str
    fit_partition: FitPartition
    reference_strategy: ReferenceStrategy
    feature_set_id: str
    feature_names: Sequence[str]
    scaling_strategy: ScalingStrategy
    observation_count: int
    fitted_center: Sequence[float]
    fitted_scale: Sequence[float]
    zero_iqr_features: Sequence[str]
    schema_id: str = field(default=PREPROCESSING_STATE_SCHEMA_ID, init=False)

    def __post_init__(self) -> None:
        for field_name in (
            "experiment_id",
            "dataset_id",
            "split_id",
            "fold_id",
            "feature_set_id",
        ):
            _validate_text(getattr(self, field_name), field_name)
        if self.fit_partition is not FitPartition.TRAIN:
            raise PreprocessingError("preprocessing state fit_partition must be train")
        if not isinstance(self.reference_strategy, ReferenceStrategy):
            raise PreprocessingError("reference_strategy must be a supported ReferenceStrategy")
        if not isinstance(self.scaling_strategy, ScalingStrategy):
            raise PreprocessingError("scaling_strategy must be a supported ScalingStrategy")
        if (
            isinstance(self.observation_count, bool)
            or not isinstance(self.observation_count, int)
            or self.observation_count <= 0
        ):
            raise PreprocessingError("observation_count must be a positive integer")

        feature_names = _validated_names(self.feature_names, "feature_names")
        fitted_center = _finite_values(self.fitted_center, "fitted_center")
        fitted_scale = _finite_values(self.fitted_scale, "fitted_scale")
        zero_iqr_features = _validated_names(
            self.zero_iqr_features,
            "zero_iqr_features",
            allow_empty=True,
        )
        expected_width = len(feature_names)
        if len(fitted_center) != expected_width or len(fitted_scale) != expected_width:
            raise PreprocessingError(
                "feature_names, fitted_center, and fitted_scale must have the same length"
            )
        if any(scale <= 0.0 for scale in fitted_scale):
            raise PreprocessingError("fitted_scale values must be positive")
        unknown_zero_iqr = sorted(set(zero_iqr_features) - set(feature_names))
        if unknown_zero_iqr:
            raise PreprocessingError(
                f"zero_iqr_features contains unknown feature(s): {unknown_zero_iqr}"
            )
        if self.scaling_strategy is ScalingStrategy.IDENTITY and zero_iqr_features:
            raise PreprocessingError("identity scaling must not record zero-IQR features")
        zero_iqr_set = set(zero_iqr_features)
        for feature_name, scale in zip(feature_names, fitted_scale, strict=True):
            if feature_name in zero_iqr_set and scale != 1.0:
                raise PreprocessingError("zero-IQR features must use unit fitted scale")

        object.__setattr__(self, "feature_names", feature_names)
        object.__setattr__(self, "fitted_center", fitted_center)
        object.__setattr__(self, "fitted_scale", fitted_scale)
        object.__setattr__(self, "zero_iqr_features", zero_iqr_features)

    def transform(
        self,
        feature_names: Sequence[str],
        rows: Iterable[Sequence[float]],
    ) -> tuple[tuple[float, ...], ...]:
        """Apply fitted scaling without changing or refitting state."""
        _require_feature_schema(self.feature_names, feature_names)
        matrix = _materialize_rows(rows, width=len(self.feature_names))
        transformed: list[tuple[float, ...]] = []
        for row_index, row in enumerate(matrix):
            transformed_row = tuple(
                (value - center) / scale
                for value, center, scale in zip(
                    row,
                    self.fitted_center,
                    self.fitted_scale,
                    strict=True,
                )
            )
            if not all(math.isfinite(value) for value in transformed_row):
                raise PreprocessingError(
                    f"transformed feature row {row_index} contains non-finite values"
                )
            transformed.append(transformed_row)
        return tuple(transformed)


def fit_preprocessing_state(
    config: ExperimentConfig,
    provenance: PreprocessingFitProvenance,
    feature_names: Sequence[str],
    rows: Iterable[Sequence[float]],
) -> PreprocessingState:
    """Fit identity or global robust scaling from the configured train partition."""
    _require_fit_provenance(config, provenance)
    selected_features = tuple(config.selected_features)
    _require_feature_schema(selected_features, feature_names)
    matrix = _materialize_rows(rows, width=len(selected_features))

    if config.scaling_strategy is ScalingStrategy.IDENTITY:
        fitted_center = (0.0,) * len(selected_features)
        fitted_scale = (1.0,) * len(selected_features)
        zero_iqr_features: tuple[str, ...] = ()
    elif config.scaling_strategy is ScalingStrategy.ROBUST:
        columns = tuple(zip(*matrix, strict=True))
        fitted_center = tuple(float(median(column)) for column in columns)
        raw_scale = tuple(
            _linear_percentile(column, 0.75) - _linear_percentile(column, 0.25)
            for column in columns
        )
        zero_iqr_features = tuple(
            feature_name
            for feature_name, scale in zip(selected_features, raw_scale, strict=True)
            if scale == 0.0
        )
        fitted_scale = tuple(1.0 if scale == 0.0 else scale for scale in raw_scale)
    else:  # pragma: no cover - ExperimentConfig validates the closed v1 enum.
        raise PreprocessingError(f"unsupported scaling strategy: {config.scaling_strategy!r}")

    return PreprocessingState(
        experiment_id=config.experiment_id,
        dataset_id=provenance.dataset_id,
        split_id=provenance.split_id,
        fold_id=provenance.fold_id,
        fit_partition=config.fit_partition,
        reference_strategy=config.reference_strategy,
        feature_set_id=provenance.feature_set_id,
        feature_names=selected_features,
        scaling_strategy=config.scaling_strategy,
        observation_count=len(matrix),
        fitted_center=fitted_center,
        fitted_scale=fitted_scale,
        zero_iqr_features=zero_iqr_features,
    )


def _require_fit_provenance(
    config: ExperimentConfig,
    provenance: PreprocessingFitProvenance,
) -> None:
    expected = (
        ("dataset_id", provenance.dataset_id, config.dataset_id),
        ("split_id", provenance.split_id, config.split_id),
        ("fold_id", provenance.fold_id, config.fold_id),
        ("partition", provenance.partition, config.fit_partition.value),
        ("feature_set_id", provenance.feature_set_id, config.feature_set_id),
    )
    for field_name, value, configured in expected:
        if value != configured:
            raise PreprocessingError(
                f"preprocessing fit {field_name} {value!r} does not match config {configured!r}"
            )


def _require_feature_schema(expected: Sequence[str], observed: Sequence[str]) -> None:
    expected_names = tuple(expected)
    observed_names = _validated_names(observed, "feature_names")
    if observed_names == expected_names:
        return
    missing = sorted(set(expected_names) - set(observed_names))
    unexpected = sorted(set(observed_names) - set(expected_names))
    if not missing and not unexpected:
        raise PreprocessingError("feature order does not match fitted preprocessing state")
    raise PreprocessingError(
        f"feature schema does not match fitted preprocessing state; "
        f"missing={missing}, unexpected={unexpected}"
    )


def _materialize_rows(
    rows: Iterable[Sequence[float]],
    *,
    width: int,
) -> tuple[tuple[float, ...], ...]:
    matrix: list[tuple[float, ...]] = []
    for row_index, row in enumerate(rows):
        values: list[float] = []
        for value in row:
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise PreprocessingError(
                    f"feature row {row_index} must contain only numerical values"
                )
            number = float(value)
            if not math.isfinite(number):
                raise PreprocessingError(f"feature row {row_index} contains non-finite values")
            values.append(number)
        if len(values) != width:
            raise PreprocessingError(
                f"feature row {row_index} width must be {width}, got {len(values)}"
            )
        matrix.append(tuple(values))
    if not matrix:
        raise PreprocessingError("preprocessing requires at least one feature row")
    return tuple(matrix)


def _linear_percentile(values: Sequence[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return float(ordered[lower_index])
    fraction = position - lower_index
    return float(ordered[lower_index] + (ordered[upper_index] - ordered[lower_index]) * fraction)


def _validated_names(
    values: Collection[str],
    field_name: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    result = tuple(values)
    if not result and not allow_empty:
        raise PreprocessingError(f"{field_name} must contain at least one value")
    for value in result:
        _validate_text(value, field_name)
    if len(result) != len(set(result)):
        raise PreprocessingError(f"{field_name} must contain unique values")
    return result


def _finite_values(values: Sequence[float], field_name: str) -> tuple[float, ...]:
    result: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise PreprocessingError(f"{field_name} must contain only numerical values")
        number = float(value)
        if not math.isfinite(number):
            raise PreprocessingError(f"{field_name} must contain only finite values")
        result.append(number)
    return tuple(result)


def _validate_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise PreprocessingError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise PreprocessingError(f"{field_name} must not contain surrounding whitespace")
