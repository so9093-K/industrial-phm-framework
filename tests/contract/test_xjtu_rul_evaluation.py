from functools import cache
from statistics import fmean

import pytest

from industrial_phm.adapters import XJTU_SY_CHANNELS, get_xjtu_expected_acquisition_count
from industrial_phm.experiments import (
    XJTU_RUL_TARGET_DEFINITION_ID,
    XjtuRulEvaluationError,
    build_xjtu_recorded_end_rul_targets,
    evaluate_xjtu_rul_lifecycle_position_errors,
    evaluate_xjtu_rul_point_predictions,
    get_xjtu_reference_split,
)
from industrial_phm.features import (
    VIBRATION_STATISTICAL_FEATURE_SET_ID,
    VibrationFeatureVector,
    vibration_feature_names,
)
from industrial_phm.prognostics import (
    RulPredictionObservation,
    RulPredictionSeries,
    RulTargetSeries,
)

_FEATURE_NAMES = vibration_feature_names(XJTU_SY_CHANNELS)


@cache
def _vectors(partition: str) -> tuple[VibrationFeatureVector, ...]:
    fold = get_xjtu_reference_split().folds[0]
    vectors: list[VibrationFeatureVector] = []
    for asset_id in getattr(fold, partition):
        for acquisition_index in range(1, get_xjtu_expected_acquisition_count(asset_id) + 1):
            vectors.append(
                VibrationFeatureVector(
                    feature_set_id=VIBRATION_STATISTICAL_FEATURE_SET_ID,
                    asset_id=asset_id,
                    feature_names=_FEATURE_NAMES,
                    values=tuple(
                        float(acquisition_index + feature_index)
                        for feature_index in range(len(_FEATURE_NAMES))
                    ),
                    metadata={
                        "dataset_id": "xjtu-sy",
                        "acquisition_index": acquisition_index,
                    },
                )
            )
    return tuple(vectors)


def _predictions(
    targets: tuple[RulTargetSeries, ...],
    *,
    offset: float = 0.0,
    drop_prefix: int = 0,
) -> tuple[RulPredictionSeries, ...]:
    return tuple(
        RulPredictionSeries(
            prediction_method_id="test-rul-method-v1",
            target_definition_id=series.target_definition_id,
            unit=series.unit,
            asset_id=series.asset_id,
            partition_id=series.partition_id,
            observations=tuple(
                RulPredictionObservation(
                    asset_id=series.asset_id,
                    partition_id=series.partition_id,
                    source_observation_id=observation.source_observation_id,
                    predicted_remaining_useful_life=observation.remaining_useful_life + offset,
                )
                for observation in series.observations[drop_prefix:]
            ),
        )
        for series in targets
    )


def test_xjtu_rul_evaluator_records_equal_bearing_metrics_and_normalization() -> None:
    targets = build_xjtu_recorded_end_rul_targets(
        _vectors("validation"),
        partition="validation",
    )
    result = evaluate_xjtu_rul_point_predictions(
        targets,
        _predictions(targets, offset=1.0),
        partition="validation",
    )

    assert result.target_definition_id == XJTU_RUL_TARGET_DEFINITION_ID
    assert result.prediction_method_id == "test-rul-method-v1"
    assert result.mean_asset_mean_absolute_error == 1.0
    assert result.mean_asset_root_mean_squared_error == 1.0
    assert result.mean_asset_mean_signed_error == 1.0

    expected_normalized = fmean(
        1.0 / (get_xjtu_expected_acquisition_count(asset_id) - 1)
        for asset_id in ("Bearing1_2", "Bearing2_2", "Bearing3_2")
    )
    assert result.mean_asset_normalized_mean_absolute_error == pytest.approx(expected_normalized)


def test_xjtu_rul_evaluator_accepts_sequence_like_right_edge_subset() -> None:
    targets = build_xjtu_recorded_end_rul_targets(
        _vectors("validation"),
        partition="validation",
    )
    result = evaluate_xjtu_rul_point_predictions(
        targets,
        _predictions(targets, drop_prefix=7),
        partition="validation",
    )

    counts = {item.asset_id: item.prediction_count for item in result.asset_results}
    assert counts == {
        "Bearing1_2": 154,
        "Bearing2_2": 154,
        "Bearing3_2": 2_489,
    }
    assert result.mean_asset_mean_absolute_error == 0.0


def test_xjtu_rul_lifecycle_diagnostics_use_full_recorded_thirds() -> None:
    targets = build_xjtu_recorded_end_rul_targets(
        _vectors("validation"),
        partition="validation",
    )
    result = evaluate_xjtu_rul_lifecycle_position_errors(
        targets,
        _predictions(targets, offset=1.0, drop_prefix=7),
        partition="validation",
    )

    counts = {
        (item.asset_id, item.position): item.prediction_count for item in result.asset_results
    }
    assert counts == {
        ("Bearing1_2", "early"): 47,
        ("Bearing1_2", "middle"): 54,
        ("Bearing1_2", "late"): 53,
        ("Bearing2_2", "early"): 47,
        ("Bearing2_2", "middle"): 54,
        ("Bearing2_2", "late"): 53,
        ("Bearing3_2", "early"): 825,
        ("Bearing3_2", "middle"): 832,
        ("Bearing3_2", "late"): 832,
    }
    assert tuple(item.position for item in result.position_summaries) == (
        "early",
        "middle",
        "late",
    )
    assert all(item.bearing_count == 3 for item in result.position_summaries)
    assert all(item.mean_asset_mean_absolute_error == 1.0 for item in result.position_summaries)
    assert all(item.mean_asset_mean_signed_error == 1.0 for item in result.position_summaries)


def test_xjtu_rul_lifecycle_diagnostics_are_diagnostic_not_selection_weighting() -> None:
    targets = build_xjtu_recorded_end_rul_targets(
        _vectors("validation"),
        partition="validation",
    )
    result = evaluate_xjtu_rul_lifecycle_position_errors(
        targets,
        _predictions(targets, offset=2.0),
        partition="validation",
    )

    for summary in result.position_summaries:
        assert summary.mean_asset_mean_absolute_error == 2.0
        assert summary.mean_asset_root_mean_squared_error == 2.0
        assert summary.mean_asset_mean_signed_error == 2.0


def test_xjtu_rul_evaluator_rejects_incomplete_target_lifecycle() -> None:
    targets = build_xjtu_recorded_end_rul_targets(
        _vectors("validation"),
        partition="validation",
    )
    incomplete = (
        RulTargetSeries(
            target_definition_id=targets[0].target_definition_id,
            unit=targets[0].unit,
            asset_id=targets[0].asset_id,
            partition_id=targets[0].partition_id,
            observations=targets[0].observations[1:],
        ),
        *targets[1:],
    )

    with pytest.raises(XjtuRulEvaluationError, match="complete ordered acquisition"):
        evaluate_xjtu_rul_point_predictions(
            incomplete,
            _predictions(incomplete),
            partition="validation",
        )


def test_xjtu_rul_evaluator_rejects_target_semantics_drift() -> None:
    targets = build_xjtu_recorded_end_rul_targets(
        _vectors("validation"),
        partition="validation",
    )
    invalid = (
        RulTargetSeries(
            target_definition_id="another-target",
            unit=targets[0].unit,
            asset_id=targets[0].asset_id,
            partition_id=targets[0].partition_id,
            observations=targets[0].observations,
        ),
        *targets[1:],
    )

    with pytest.raises(XjtuRulEvaluationError, match="recorded-end target definition"):
        evaluate_xjtu_rul_point_predictions(
            invalid,
            _predictions(invalid),
            partition="validation",
        )
