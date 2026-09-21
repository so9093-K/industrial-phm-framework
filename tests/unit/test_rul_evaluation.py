from dataclasses import replace

import pytest

from industrial_phm.prognostics import (
    RulEvaluationError,
    RulPredictionObservation,
    RulPredictionSeries,
    RulTargetObservation,
    RulTargetSeries,
    evaluate_rul_point_predictions,
)


def _targets(
    asset_id: str,
    values: tuple[float, ...],
    *,
    partition_id: str = "validation",
) -> RulTargetSeries:
    return RulTargetSeries(
        target_definition_id="recorded-end-v1",
        unit="cycle",
        asset_id=asset_id,
        partition_id=partition_id,
        observations=tuple(
            RulTargetObservation(
                asset_id=asset_id,
                partition_id=partition_id,
                source_observation_id=f"{asset_id}:observation-{index}",
                remaining_useful_life=value,
            )
            for index, value in enumerate(values, start=1)
        ),
    )


def _predictions(
    targets: RulTargetSeries,
    values: tuple[float, ...],
    *,
    method_id: str = "baseline-v1",
    observation_indices: tuple[int, ...] | None = None,
) -> RulPredictionSeries:
    selected = (
        tuple(range(len(targets.observations)))
        if observation_indices is None
        else observation_indices
    )
    return RulPredictionSeries(
        prediction_method_id=method_id,
        target_definition_id=targets.target_definition_id,
        unit=targets.unit,
        asset_id=targets.asset_id,
        partition_id=targets.partition_id,
        observations=tuple(
            RulPredictionObservation(
                asset_id=targets.asset_id,
                partition_id=targets.partition_id,
                source_observation_id=targets.observations[target_index].source_observation_id,
                predicted_remaining_useful_life=value,
            )
            for target_index, value in zip(selected, values, strict=True)
        ),
    )


def test_rul_point_evaluator_accepts_ordered_prediction_subset() -> None:
    targets = _targets("asset-a", (3.0, 2.0, 1.0, 0.0))
    predictions = _predictions(
        targets,
        (2.0, 0.0),
        observation_indices=(1, 3),
    )

    result = evaluate_rul_point_predictions((targets,), (predictions,))

    assert result.prediction_method_id == "baseline-v1"
    assert result.mean_asset_mean_absolute_error == 0.0
    assert result.asset_results[0].prediction_count == 2


def test_rul_point_evaluator_uses_equal_asset_weight_not_row_pooling() -> None:
    asset_a_targets = _targets("asset-a", (0.0,))
    asset_b_targets = _targets("asset-b", (2.0, 1.0, 0.0))
    asset_a_predictions = _predictions(asset_a_targets, (10.0,))
    asset_b_predictions = _predictions(asset_b_targets, (2.0, 1.0, 0.0))

    result = evaluate_rul_point_predictions(
        (asset_a_targets, asset_b_targets),
        (asset_a_predictions, asset_b_predictions),
        normalization_scale_by_series={
            ("asset-a", "validation"): 10.0,
            ("asset-b", "validation"): 2.0,
        },
    )

    assert result.mean_asset_mean_absolute_error == 5.0
    assert result.mean_asset_root_mean_squared_error == 5.0
    assert result.mean_asset_mean_signed_error == 5.0
    assert result.mean_asset_normalized_mean_absolute_error == 0.5


def test_rul_point_evaluator_preserves_signed_error_direction() -> None:
    targets = _targets("asset-a", (2.0, 1.0, 0.0))
    predictions = _predictions(targets, (3.0, 2.0, 1.0))

    result = evaluate_rul_point_predictions((targets,), (predictions,))

    assert result.asset_results[0].mean_absolute_error == 1.0
    assert result.asset_results[0].root_mean_squared_error == 1.0
    assert result.asset_results[0].mean_signed_error == 1.0


def test_rul_point_evaluator_rejects_prediction_order_drift() -> None:
    targets = _targets("asset-a", (2.0, 1.0, 0.0))
    predictions = _predictions(
        targets,
        (0.0, 2.0),
        observation_indices=(2, 0),
    )

    with pytest.raises(RulEvaluationError, match="lifecycle order"):
        evaluate_rul_point_predictions((targets,), (predictions,))


def test_rul_point_evaluator_rejects_unknown_prediction_identity() -> None:
    targets = _targets("asset-a", (1.0, 0.0))
    predictions = _predictions(targets, (1.0, 0.0))
    unknown = replace(
        predictions.observations[-1],
        source_observation_id="asset-a:observation-99",
    )
    invalid = replace(
        predictions,
        observations=(predictions.observations[0], unknown),
    )

    with pytest.raises(RulEvaluationError, match="absent from targets"):
        evaluate_rul_point_predictions((targets,), (invalid,))


def test_rul_point_evaluator_rejects_missing_asset_series() -> None:
    asset_a_targets = _targets("asset-a", (1.0, 0.0))
    asset_b_targets = _targets("asset-b", (1.0, 0.0))
    predictions = _predictions(asset_a_targets, (1.0, 0.0))

    with pytest.raises(RulEvaluationError, match="identities must match exactly"):
        evaluate_rul_point_predictions(
            (asset_a_targets, asset_b_targets),
            (predictions,),
        )


def test_rul_point_evaluator_rejects_mixed_prediction_methods() -> None:
    asset_a_targets = _targets("asset-a", (1.0, 0.0))
    asset_b_targets = _targets("asset-b", (1.0, 0.0))
    asset_a_predictions = _predictions(asset_a_targets, (1.0, 0.0))
    asset_b_predictions = _predictions(
        asset_b_targets,
        (1.0, 0.0),
        method_id="another-method",
    )

    with pytest.raises(RulEvaluationError, match="one prediction_method_id"):
        evaluate_rul_point_predictions(
            (asset_a_targets, asset_b_targets),
            (asset_a_predictions, asset_b_predictions),
        )
