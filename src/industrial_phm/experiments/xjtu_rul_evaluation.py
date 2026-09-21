"""XJTU-SY policy edge for model-independent RUL point evaluation."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean
from typing import Literal

from industrial_phm.adapters import get_xjtu_expected_acquisition_count
from industrial_phm.experiments.xjtu_rul import (
    XjtuRulTargetError,
    get_xjtu_rul_partition_assets,
    validate_xjtu_recorded_end_rul_targets,
)
from industrial_phm.prognostics import (
    RulEvaluationError,
    RulPointEvaluation,
    RulPredictionSeries,
    RulTargetSeries,
    evaluate_rul_point_predictions,
)

_Partition = Literal["train", "validation", "test"]
_LifecyclePosition = Literal["early", "middle", "late"]
_LIFECYCLE_POSITIONS: tuple[_LifecyclePosition, ...] = ("early", "middle", "late")


class XjtuRulEvaluationError(ValueError):
    """Raised when RUL evaluation inputs violate the XJTU prognostics protocol."""


@dataclass(frozen=True, slots=True)
class XjtuRulLifecyclePositionAssetEvaluation:
    """Retrospective point-error evidence for one bearing lifecycle third."""

    asset_id: str
    partition_id: str
    position: _LifecyclePosition
    prediction_count: int
    mean_absolute_error: float
    root_mean_squared_error: float
    mean_signed_error: float
    normalized_mean_absolute_error: float


@dataclass(frozen=True, slots=True)
class XjtuRulLifecyclePositionSummary:
    """Equal-bearing aggregate for one recorded lifecycle third."""

    position: _LifecyclePosition
    bearing_count: int
    mean_asset_mean_absolute_error: float
    mean_asset_root_mean_squared_error: float
    mean_asset_mean_signed_error: float
    mean_asset_normalized_mean_absolute_error: float


@dataclass(frozen=True, slots=True)
class XjtuRulLifecyclePositionEvaluation:
    """Protocol §9.1 lifecycle-position diagnostics for one prediction method."""

    prediction_method_id: str
    target_definition_id: str
    unit: str
    asset_results: Sequence[XjtuRulLifecyclePositionAssetEvaluation]
    position_summaries: Sequence[XjtuRulLifecyclePositionSummary]

    def __post_init__(self) -> None:
        asset_results = tuple(self.asset_results)
        position_summaries = tuple(self.position_summaries)
        if not asset_results:
            raise XjtuRulEvaluationError("lifecycle diagnostics require asset results")
        if tuple(summary.position for summary in position_summaries) != _LIFECYCLE_POSITIONS:
            raise XjtuRulEvaluationError(
                "lifecycle diagnostics require early/middle/late aggregate summaries"
            )
        object.__setattr__(self, "asset_results", asset_results)
        object.__setattr__(self, "position_summaries", position_summaries)


def evaluate_xjtu_rul_lifecycle_position_errors(
    targets: Sequence[RulTargetSeries],
    predictions: Sequence[RulPredictionSeries],
    *,
    partition: _Partition,
) -> XjtuRulLifecyclePositionEvaluation:
    """Evaluate error by full recorded-lifecycle early/middle/late thirds."""
    point = evaluate_xjtu_rul_point_predictions(
        targets,
        predictions,
        partition=partition,
    )
    try:
        target_series = validate_xjtu_recorded_end_rul_targets(targets, partition=partition)
    except XjtuRulTargetError as error:
        raise XjtuRulEvaluationError(f"invalid XJTU RUL targets: {error}") from error

    prediction_by_asset = {series.asset_id: series for series in predictions}
    rows: list[XjtuRulLifecyclePositionAssetEvaluation] = []
    for series in target_series:
        predicted = prediction_by_asset[series.asset_id]
        target_by_id = {
            observation.source_observation_id: observation.remaining_useful_life
            for observation in series.observations
        }
        ordinal_by_id = {
            observation.source_observation_id: ordinal
            for ordinal, observation in enumerate(series.observations, start=1)
        }
        grouped: dict[_LifecyclePosition, list[float]] = {
            position: [] for position in _LIFECYCLE_POSITIONS
        }
        run_length = len(series.observations)
        for observation in predicted.observations:
            ordinal = ordinal_by_id[observation.source_observation_id]
            grouped[_lifecycle_position(ordinal, run_length)].append(
                observation.predicted_remaining_useful_life
                - target_by_id[observation.source_observation_id]
            )

        normalization_scale = float(max(run_length - 1, 1))
        for position in _LIFECYCLE_POSITIONS:
            errors = grouped[position]
            if not errors:
                raise XjtuRulEvaluationError(
                    f"{series.asset_id} has no {position} lifecycle predictions"
                )
            count = len(errors)
            mae = math.fsum(abs(error) for error in errors) / count
            rmse = math.sqrt(math.fsum(error * error for error in errors) / count)
            signed = math.fsum(errors) / count
            rows.append(
                XjtuRulLifecyclePositionAssetEvaluation(
                    asset_id=series.asset_id,
                    partition_id=partition,
                    position=position,
                    prediction_count=count,
                    mean_absolute_error=float(mae),
                    root_mean_squared_error=float(rmse),
                    mean_signed_error=float(signed),
                    normalized_mean_absolute_error=float(mae / normalization_scale),
                )
            )

    summaries = tuple(
        XjtuRulLifecyclePositionSummary(
            position=position,
            bearing_count=sum(row.position == position for row in rows),
            mean_asset_mean_absolute_error=float(
                fmean(row.mean_absolute_error for row in rows if row.position == position)
            ),
            mean_asset_root_mean_squared_error=float(
                fmean(row.root_mean_squared_error for row in rows if row.position == position)
            ),
            mean_asset_mean_signed_error=float(
                fmean(row.mean_signed_error for row in rows if row.position == position)
            ),
            mean_asset_normalized_mean_absolute_error=float(
                fmean(
                    row.normalized_mean_absolute_error
                    for row in rows
                    if row.position == position
                )
            ),
        )
        for position in _LIFECYCLE_POSITIONS
    )
    return XjtuRulLifecyclePositionEvaluation(
        prediction_method_id=point.prediction_method_id,
        target_definition_id=point.target_definition_id,
        unit=point.unit,
        asset_results=tuple(rows),
        position_summaries=summaries,
    )


def _lifecycle_position(ordinal: int, run_length: int) -> _LifecyclePosition:
    early_end = math.ceil(run_length / 3)
    middle_end = math.ceil(2 * run_length / 3)
    if ordinal <= early_end:
        return "early"
    if ordinal <= middle_end:
        return "middle"
    return "late"


def evaluate_xjtu_rul_point_predictions(
    targets: Sequence[RulTargetSeries],
    predictions: Sequence[RulPredictionSeries],
    *,
    partition: _Partition,
) -> RulPointEvaluation:
    """Evaluate one fold-1 partition with protocol-defined equal-bearing normalization."""
    try:
        target_series = validate_xjtu_recorded_end_rul_targets(targets, partition=partition)
    except XjtuRulTargetError as error:
        raise XjtuRulEvaluationError(f"invalid XJTU RUL targets: {error}") from error

    prediction_series = tuple(predictions)
    expected_assets = get_xjtu_rul_partition_assets(partition)
    expected_asset_set = set(expected_assets)

    observed_prediction_assets = {series.asset_id for series in prediction_series}
    if observed_prediction_assets != expected_asset_set:
        raise XjtuRulEvaluationError(
            f"XJTU RUL evaluation requires configured {partition} prediction bearings; "
            f"missing={sorted(expected_asset_set - observed_prediction_assets)}, "
            f"unexpected={sorted(observed_prediction_assets - expected_asset_set)}"
        )
    if len(prediction_series) != len(expected_assets):
        raise XjtuRulEvaluationError("XJTU RUL prediction series must contain unique bearing runs")
    if any(series.partition_id != partition for series in prediction_series):
        raise XjtuRulEvaluationError(
            f"XJTU RUL prediction series must preserve partition {partition!r}"
        )

    normalization_scales: dict[tuple[str, str], float] = {
        (asset_id, partition): float(max(get_xjtu_expected_acquisition_count(asset_id) - 1, 1))
        for asset_id in expected_assets
    }
    try:
        return evaluate_rul_point_predictions(
            target_series,
            prediction_series,
            normalization_scale_by_series=normalization_scales,
        )
    except RulEvaluationError as error:
        raise XjtuRulEvaluationError(f"invalid XJTU RUL point evaluation input: {error}") from error
