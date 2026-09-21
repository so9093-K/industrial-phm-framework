"""Model-independent point evaluation for Remaining Useful Life predictions."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from statistics import fmean

from industrial_phm.prognostics.predictions import RulPredictionSeries
from industrial_phm.prognostics.targets import RulTargetSeries

_SeriesKey = tuple[str, str]


class RulEvaluationError(ValueError):
    """Raised when RUL targets and predictions cannot be evaluated safely."""


@dataclass(frozen=True, slots=True)
class RulAssetPointEvaluation:
    """Point-prediction error evidence for one asset and partition."""

    asset_id: str
    partition_id: str
    prediction_count: int
    mean_absolute_error: float
    root_mean_squared_error: float
    mean_signed_error: float
    normalized_mean_absolute_error: float | None = None

    def __post_init__(self) -> None:
        _validate_text(self.asset_id, "asset_id")
        _validate_text(self.partition_id, "partition_id")
        if (
            isinstance(self.prediction_count, bool)
            or not isinstance(self.prediction_count, int)
            or self.prediction_count <= 0
        ):
            raise RulEvaluationError("prediction_count must be a positive integer")
        for field_name in ("mean_absolute_error", "root_mean_squared_error"):
            value = getattr(self, field_name)
            if not math.isfinite(value) or value < 0.0:
                raise RulEvaluationError(f"{field_name} must be finite and non-negative")
        if not math.isfinite(self.mean_signed_error):
            raise RulEvaluationError("mean_signed_error must be finite")
        if self.normalized_mean_absolute_error is not None and (
            not math.isfinite(self.normalized_mean_absolute_error)
            or self.normalized_mean_absolute_error < 0.0
        ):
            raise RulEvaluationError(
                "normalized_mean_absolute_error must be finite and non-negative when recorded"
            )


@dataclass(frozen=True, slots=True)
class RulPointEvaluation:
    """Equal-asset aggregate of identity-aligned point-prediction error evidence."""

    prediction_method_id: str
    target_definition_id: str
    unit: str
    asset_results: Sequence[RulAssetPointEvaluation]
    mean_asset_mean_absolute_error: float
    mean_asset_root_mean_squared_error: float
    mean_asset_mean_signed_error: float
    mean_asset_normalized_mean_absolute_error: float | None = None

    def __post_init__(self) -> None:
        for field_name in ("prediction_method_id", "target_definition_id", "unit"):
            _validate_text(getattr(self, field_name), field_name)

        asset_results = tuple(self.asset_results)
        if not asset_results:
            raise RulEvaluationError("asset_results must contain at least one asset evaluation")
        if not all(isinstance(result, RulAssetPointEvaluation) for result in asset_results):
            raise RulEvaluationError(
                "asset_results must contain only RulAssetPointEvaluation values"
            )
        identities = tuple((result.asset_id, result.partition_id) for result in asset_results)
        if len(identities) != len(set(identities)):
            raise RulEvaluationError("asset evaluation identities must be unique")

        for field_name in (
            "mean_asset_mean_absolute_error",
            "mean_asset_root_mean_squared_error",
        ):
            value = getattr(self, field_name)
            if not math.isfinite(value) or value < 0.0:
                raise RulEvaluationError(f"{field_name} must be finite and non-negative")
        if not math.isfinite(self.mean_asset_mean_signed_error):
            raise RulEvaluationError("mean_asset_mean_signed_error must be finite")
        if self.mean_asset_normalized_mean_absolute_error is not None and (
            not math.isfinite(self.mean_asset_normalized_mean_absolute_error)
            or self.mean_asset_normalized_mean_absolute_error < 0.0
        ):
            raise RulEvaluationError(
                "mean_asset_normalized_mean_absolute_error must be finite and non-negative"
            )

        object.__setattr__(self, "asset_results", asset_results)


def evaluate_rul_point_predictions(
    targets: Sequence[RulTargetSeries],
    predictions: Sequence[RulPredictionSeries],
    *,
    normalization_scale_by_series: Mapping[_SeriesKey, float] | None = None,
) -> RulPointEvaluation:
    """Evaluate source-aligned predictions, aggregating metrics with equal asset weight."""
    target_series = tuple(targets)
    prediction_series = tuple(predictions)
    if not target_series:
        raise RulEvaluationError("RUL evaluation requires target series")
    if not prediction_series:
        raise RulEvaluationError("RUL evaluation requires prediction series")
    if not all(isinstance(series, RulTargetSeries) for series in target_series):
        raise RulEvaluationError("targets must contain only RulTargetSeries values")
    if not all(isinstance(series, RulPredictionSeries) for series in prediction_series):
        raise RulEvaluationError("predictions must contain only RulPredictionSeries values")

    targets_by_key = _unique_series_by_key(target_series, kind="target")
    predictions_by_key = _unique_series_by_key(prediction_series, kind="prediction")
    if set(targets_by_key) != set(predictions_by_key):
        raise RulEvaluationError(
            "target and prediction asset/partition identities must match exactly; "
            f"missing={sorted(set(targets_by_key) - set(predictions_by_key))}, "
            f"unexpected={sorted(set(predictions_by_key) - set(targets_by_key))}"
        )

    method_ids = {series.prediction_method_id for series in prediction_series}
    if len(method_ids) != 1:
        raise RulEvaluationError("all prediction series must share one prediction_method_id")
    target_definition_ids = {series.target_definition_id for series in target_series}
    target_definition_ids.update(series.target_definition_id for series in prediction_series)
    if len(target_definition_ids) != 1:
        raise RulEvaluationError("targets and predictions must share one target_definition_id")
    units = {series.unit for series in target_series}
    units.update(series.unit for series in prediction_series)
    if len(units) != 1:
        raise RulEvaluationError("targets and predictions must share one RUL unit")

    scales = _validated_normalization_scales(
        normalization_scale_by_series,
        expected_keys=set(targets_by_key),
    )
    results = tuple(
        _evaluate_series(
            targets_by_key[key],
            predictions_by_key[key],
            normalization_scale=None if scales is None else scales[key],
        )
        for key in sorted(targets_by_key)
    )
    normalized = tuple(
        result.normalized_mean_absolute_error
        for result in results
        if result.normalized_mean_absolute_error is not None
    )
    mean_normalized = float(fmean(normalized)) if len(normalized) == len(results) else None

    return RulPointEvaluation(
        prediction_method_id=next(iter(method_ids)),
        target_definition_id=next(iter(target_definition_ids)),
        unit=next(iter(units)),
        asset_results=results,
        mean_asset_mean_absolute_error=float(
            fmean(result.mean_absolute_error for result in results)
        ),
        mean_asset_root_mean_squared_error=float(
            fmean(result.root_mean_squared_error for result in results)
        ),
        mean_asset_mean_signed_error=float(fmean(result.mean_signed_error for result in results)),
        mean_asset_normalized_mean_absolute_error=mean_normalized,
    )


def _unique_series_by_key(
    series_values: Sequence[RulTargetSeries] | Sequence[RulPredictionSeries],
    *,
    kind: str,
) -> dict[_SeriesKey, RulTargetSeries | RulPredictionSeries]:
    result: dict[_SeriesKey, RulTargetSeries | RulPredictionSeries] = {}
    for series in series_values:
        key = (series.asset_id, series.partition_id)
        if key in result:
            raise RulEvaluationError(f"{kind} series identities must be unique; duplicate={key}")
        result[key] = series
    return result


def _validated_normalization_scales(
    values: Mapping[_SeriesKey, float] | None,
    *,
    expected_keys: set[_SeriesKey],
) -> dict[_SeriesKey, float] | None:
    if values is None:
        return None
    if set(values) != expected_keys:
        raise RulEvaluationError(
            "normalization scale identities must exactly match evaluated series"
        )

    result: dict[_SeriesKey, float] = {}
    for key, value in values.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(float(value))
            or float(value) <= 0.0
        ):
            raise RulEvaluationError(
                f"normalization scale for {key} must be a finite positive number"
            )
        result[key] = float(value)
    return result


def _evaluate_series(
    targets: RulTargetSeries | RulPredictionSeries,
    predictions: RulTargetSeries | RulPredictionSeries,
    *,
    normalization_scale: float | None,
) -> RulAssetPointEvaluation:
    if not isinstance(targets, RulTargetSeries) or not isinstance(
        predictions, RulPredictionSeries
    ):
        raise RulEvaluationError("internal RUL evaluation series types are inconsistent")

    target_ids = tuple(observation.source_observation_id for observation in targets.observations)
    target_index = {observation_id: index for index, observation_id in enumerate(target_ids)}
    target_by_id = {
        observation.source_observation_id: observation for observation in targets.observations
    }
    prediction_ids = tuple(
        observation.source_observation_id for observation in predictions.observations
    )
    unexpected = tuple(
        observation_id for observation_id in prediction_ids if observation_id not in target_by_id
    )
    if unexpected:
        raise RulEvaluationError(
            f"RUL predictions contain source identities absent from targets: {unexpected[:10]}"
        )

    target_positions = tuple(target_index[observation_id] for observation_id in prediction_ids)
    if any(current <= previous for previous, current in zip(target_positions, target_positions[1:])):
        raise RulEvaluationError(
            "RUL prediction observations must preserve target lifecycle order"
        )

    errors = tuple(
        prediction.predicted_remaining_useful_life
        - target_by_id[prediction.source_observation_id].remaining_useful_life
        for prediction in predictions.observations
    )
    count = len(errors)
    mae = math.fsum(abs(error) for error in errors) / count
    rmse = math.sqrt(math.fsum(error * error for error in errors) / count)
    mean_signed_error = math.fsum(errors) / count

    return RulAssetPointEvaluation(
        asset_id=targets.asset_id,
        partition_id=targets.partition_id,
        prediction_count=count,
        mean_absolute_error=float(mae),
        root_mean_squared_error=float(rmse),
        mean_signed_error=float(mean_signed_error),
        normalized_mean_absolute_error=(
            None if normalization_scale is None else float(mae / normalization_scale)
        ),
    )


def _validate_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RulEvaluationError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise RulEvaluationError(f"{field_name} must not contain surrounding whitespace")
