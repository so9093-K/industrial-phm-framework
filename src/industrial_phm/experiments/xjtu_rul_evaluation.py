"""XJTU-SY policy edge for model-independent RUL point evaluation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from industrial_phm.adapters import get_xjtu_expected_acquisition_count
from industrial_phm.experiments.xjtu_rul import (
    XJTU_RUL_TARGET_DEFINITION_ID,
    XJTU_RUL_TARGET_UNIT,
    get_xjtu_rul_partition_assets,
)
from industrial_phm.prognostics import (
    RulEvaluationError,
    RulPointEvaluation,
    RulPredictionSeries,
    RulTargetSeries,
    evaluate_rul_point_predictions,
)

_Partition = Literal["train", "validation", "test"]


class XjtuRulEvaluationError(ValueError):
    """Raised when RUL evaluation inputs violate the XJTU prognostics protocol."""


def evaluate_xjtu_rul_point_predictions(
    targets: Sequence[RulTargetSeries],
    predictions: Sequence[RulPredictionSeries],
    *,
    partition: _Partition,
) -> RulPointEvaluation:
    """Evaluate one fold-1 partition with protocol-defined equal-bearing normalization."""
    target_series = tuple(targets)
    prediction_series = tuple(predictions)
    expected_assets = get_xjtu_rul_partition_assets(partition)
    expected_asset_set = set(expected_assets)

    observed_target_assets = {series.asset_id for series in target_series}
    if observed_target_assets != expected_asset_set:
        raise XjtuRulEvaluationError(
            f"XJTU RUL evaluation requires configured {partition} target bearings; "
            f"missing={sorted(expected_asset_set - observed_target_assets)}, "
            f"unexpected={sorted(observed_target_assets - expected_asset_set)}"
        )
    if len(target_series) != len(expected_assets):
        raise XjtuRulEvaluationError("XJTU RUL target series must contain unique bearing runs")

    for series in target_series:
        _validate_target_series(series, partition=partition)

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

    normalization_scales = {
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


def _validate_target_series(series: RulTargetSeries, *, partition: str) -> None:
    if series.partition_id != partition:
        raise XjtuRulEvaluationError(
            f"XJTU RUL target series must preserve partition {partition!r}"
        )
    if series.target_definition_id != XJTU_RUL_TARGET_DEFINITION_ID:
        raise XjtuRulEvaluationError(
            "XJTU RUL target series must use the recorded-end target definition"
        )
    if series.unit != XJTU_RUL_TARGET_UNIT:
        raise XjtuRulEvaluationError("XJTU RUL target series must use acquisition-interval unit")

    run_length = get_xjtu_expected_acquisition_count(series.asset_id)
    expected_ids = tuple(
        f"{series.asset_id}:acquisition-{acquisition_index}"
        for acquisition_index in range(1, run_length + 1)
    )
    observed_ids = tuple(observation.source_observation_id for observation in series.observations)
    if observed_ids != expected_ids:
        raise XjtuRulEvaluationError(
            f"XJTU RUL targets for {series.asset_id} must cover complete ordered acquisition 1.."
            f"{run_length}"
        )

    expected_values = tuple(float(run_length - index) for index in range(1, run_length + 1))
    observed_values = tuple(
        observation.remaining_useful_life for observation in series.observations
    )
    if observed_values != expected_values:
        raise XjtuRulEvaluationError(
            f"XJTU RUL targets for {series.asset_id} must preserve N-k recorded-end semantics"
        )
