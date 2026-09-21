"""XJTU-SY policy edge for model-independent RUL point evaluation."""

from __future__ import annotations

from collections.abc import Sequence
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


class XjtuRulEvaluationError(ValueError):
    """Raised when RUL evaluation inputs violate the XJTU prognostics protocol."""


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
