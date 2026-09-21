from dataclasses import replace
from functools import cache
from statistics import fmean

import pytest

from industrial_phm.adapters import XJTU_SY_CHANNELS, get_xjtu_expected_acquisition_count
from industrial_phm.experiments import (
    XJTU_AGE_ONLY_RUL_METHOD_ID,
    XjtuAgeOnlyRulBaselineError,
    build_xjtu_recorded_end_rul_targets,
    evaluate_xjtu_rul_point_predictions,
    fit_xjtu_age_only_rul_baseline,
    get_xjtu_reference_split,
    predict_xjtu_age_only_rul,
)
from industrial_phm.features import (
    VIBRATION_STATISTICAL_FEATURE_SET_ID,
    VibrationFeatureVector,
    vibration_feature_names,
)
from industrial_phm.prognostics import RulTargetSeries

_FEATURE_NAMES = vibration_feature_names(XJTU_SY_CHANNELS)


@cache
def _vectors(partition: str) -> tuple[VibrationFeatureVector, ...]:
    fold = get_xjtu_reference_split().folds[0]
    vectors: list[VibrationFeatureVector] = []
    for asset_id in getattr(fold, partition):
        for acquisition_index in range(1, get_xjtu_expected_acquisition_count(asset_id) + 1):
            vectors.append(_vector(asset_id, acquisition_index))
    return tuple(vectors)


def _prefix_vectors(partition: str, length: int) -> tuple[VibrationFeatureVector, ...]:
    fold = get_xjtu_reference_split().folds[0]
    return tuple(
        _vector(asset_id, acquisition_index)
        for asset_id in getattr(fold, partition)
        for acquisition_index in range(1, length + 1)
    )


def _vector(
    asset_id: str,
    acquisition_index: int,
    *,
    value_offset: float = 0.0,
) -> VibrationFeatureVector:
    return VibrationFeatureVector(
        feature_set_id=VIBRATION_STATISTICAL_FEATURE_SET_ID,
        asset_id=asset_id,
        feature_names=_FEATURE_NAMES,
        values=tuple(
            value_offset + acquisition_index + feature_index
            for feature_index in range(len(_FEATURE_NAMES))
        ),
        metadata={
            "dataset_id": "xjtu-sy",
            "acquisition_index": acquisition_index,
        },
    )


@cache
def _train_targets() -> tuple[RulTargetSeries, ...]:
    return build_xjtu_recorded_end_rul_targets(_vectors("train"), partition="train")


def test_xjtu_age_only_baseline_fits_equal_bearing_mean_train_endpoint() -> None:
    baseline = fit_xjtu_age_only_rul_baseline(_train_targets())
    train_assets = get_xjtu_reference_split().folds[0].train
    expected_endpoints = tuple(
        float(get_xjtu_expected_acquisition_count(asset_id)) for asset_id in train_assets
    )

    assert baseline.prediction_method_id == XJTU_AGE_ONLY_RUL_METHOD_ID
    assert baseline.train_asset_ids == train_assets
    assert baseline.train_endpoint_acquisitions == expected_endpoints
    assert baseline.fitted_mean_endpoint_acquisition == fmean(expected_endpoints)


def test_xjtu_age_only_prediction_does_not_depend_on_feature_values() -> None:
    baseline = fit_xjtu_age_only_rul_baseline(_train_targets())
    original = _prefix_vectors("validation", 5)
    shifted = tuple(
        replace(
            vector,
            values=tuple(value + 1_000_000.0 for value in vector.values),
        )
        for vector in original
    )

    original_predictions = predict_xjtu_age_only_rul(
        baseline,
        original,
        partition="validation",
    )
    shifted_predictions = predict_xjtu_age_only_rul(
        baseline,
        shifted,
        partition="validation",
    )

    assert shifted_predictions == original_predictions


def test_xjtu_age_only_prediction_accepts_contiguous_prefix_without_target_endpoint() -> None:
    baseline = fit_xjtu_age_only_rul_baseline(_train_targets())
    predictions = predict_xjtu_age_only_rul(
        baseline,
        _prefix_vectors("validation", 5),
        partition="validation",
    )

    assert {series.asset_id for series in predictions} == {
        "Bearing1_2",
        "Bearing2_2",
        "Bearing3_2",
    }
    assert all(len(series.observations) == 5 for series in predictions)
    for series in predictions:
        assert series.observations[0].source_observation_id == (f"{series.asset_id}:acquisition-1")
        assert series.observations[-1].source_observation_id == (f"{series.asset_id}:acquisition-5")


def test_xjtu_age_only_prediction_preserves_negative_outputs_without_clamping() -> None:
    baseline = fit_xjtu_age_only_rul_baseline(_train_targets())
    predictions = predict_xjtu_age_only_rul(
        baseline,
        _vectors("validation"),
        partition="validation",
    )

    bearing3 = next(series for series in predictions if series.asset_id == "Bearing3_2")
    assert any(
        observation.predicted_remaining_useful_life < 0.0 for observation in bearing3.observations
    )


def test_xjtu_age_only_predictions_use_existing_model_independent_evaluator() -> None:
    baseline = fit_xjtu_age_only_rul_baseline(_train_targets())
    validation_vectors = _vectors("validation")
    targets = build_xjtu_recorded_end_rul_targets(
        validation_vectors,
        partition="validation",
    )
    predictions = predict_xjtu_age_only_rul(
        baseline,
        validation_vectors,
        partition="validation",
    )

    evaluation = evaluate_xjtu_rul_point_predictions(
        targets,
        predictions,
        partition="validation",
    )

    assert evaluation.prediction_method_id == XJTU_AGE_ONLY_RUL_METHOD_ID
    assert len(evaluation.asset_results) == 3
    assert evaluation.mean_asset_mean_absolute_error > 0.0


def test_xjtu_age_only_fit_rejects_non_train_targets() -> None:
    validation_targets = build_xjtu_recorded_end_rul_targets(
        _vectors("validation"),
        partition="validation",
    )

    with pytest.raises(XjtuAgeOnlyRulBaselineError, match="train targets"):
        fit_xjtu_age_only_rul_baseline(validation_targets)


def test_xjtu_age_only_prediction_rejects_missing_partition_asset() -> None:
    baseline = fit_xjtu_age_only_rul_baseline(_train_targets())
    vectors = tuple(
        vector for vector in _prefix_vectors("validation", 5) if vector.asset_id != "Bearing3_2"
    )

    with pytest.raises(XjtuAgeOnlyRulBaselineError, match="configured validation"):
        predict_xjtu_age_only_rul(
            baseline,
            vectors,
            partition="validation",
        )


def test_xjtu_age_only_prediction_rejects_acquisition_gap() -> None:
    baseline = fit_xjtu_age_only_rul_baseline(_train_targets())
    vectors = tuple(
        vector
        for vector in _prefix_vectors("validation", 5)
        if not (vector.asset_id == "Bearing2_2" and vector.metadata["acquisition_index"] == 3)
    )

    with pytest.raises(XjtuAgeOnlyRulBaselineError, match="contiguous prefix"):
        predict_xjtu_age_only_rul(
            baseline,
            vectors,
            partition="validation",
        )


def test_xjtu_age_only_prediction_rejects_dataset_identity_drift() -> None:
    baseline = fit_xjtu_age_only_rul_baseline(_train_targets())
    vectors = list(_prefix_vectors("validation", 2))
    vectors[0] = replace(
        vectors[0],
        metadata={"dataset_id": "another-dataset", "acquisition_index": 1},
    )

    with pytest.raises(XjtuAgeOnlyRulBaselineError, match="dataset_id"):
        predict_xjtu_age_only_rul(
            baseline,
            vectors,
            partition="validation",
        )
