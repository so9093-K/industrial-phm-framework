from dataclasses import replace
from functools import cache

import pytest

from industrial_phm.adapters import XJTU_SY_CHANNELS, get_xjtu_expected_acquisition_count
from industrial_phm.experiments import (
    XJTU_FEATURE_RIDGE_RUL_METHOD_ID,
    FitPartition,
    ModelFamily,
    ReferenceStrategy,
    ScalingStrategy,
    XjtuFeatureRulBaselineError,
    build_xjtu_recorded_end_rul_targets,
    evaluate_xjtu_rul_point_predictions,
    fit_xjtu_age_only_rul_baseline,
    fit_xjtu_feature_rul_baseline,
    get_xjtu_feature_rul_configuration,
    get_xjtu_reference_split,
    predict_xjtu_age_only_rul,
    predict_xjtu_feature_rul,
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
        run_length = get_xjtu_expected_acquisition_count(asset_id)
        for acquisition_index in range(1, run_length + 1):
            target_signal = float(run_length - acquisition_index)
            vectors.append(
                VibrationFeatureVector(
                    feature_set_id=VIBRATION_STATISTICAL_FEATURE_SET_ID,
                    asset_id=asset_id,
                    feature_names=_FEATURE_NAMES,
                    values=tuple(
                        target_signal + (feature_index * 0.01)
                        for feature_index in range(len(_FEATURE_NAMES))
                    ),
                    metadata={
                        "dataset_id": "xjtu-sy",
                        "acquisition_index": acquisition_index,
                        "operating_condition": "synthetic-condition",
                    },
                )
            )
    return tuple(vectors)


@cache
def _train_targets() -> tuple[RulTargetSeries, ...]:
    return build_xjtu_recorded_end_rul_targets(_vectors("train"), partition="train")


def test_xjtu_feature_rul_configuration_is_frozen_before_numerical_evidence() -> None:
    config = get_xjtu_feature_rul_configuration()

    assert config.experiment_id == XJTU_FEATURE_RIDGE_RUL_METHOD_ID
    assert config.fit_partition is FitPartition.TRAIN
    assert config.reference_strategy is ReferenceStrategy.ALL_TRAIN_OBSERVATIONS
    assert config.sampling_policy_id == "bearing-balanced-resample-v1"
    assert config.scaling_strategy is ScalingStrategy.ROBUST
    assert config.model_family is ModelFamily.RIDGE_REGRESSION
    assert config.random_seed == 42
    assert tuple(config.selected_features) == _FEATURE_NAMES
    assert dict(config.model_parameters) == {
        "alpha": 1.0,
        "fit_intercept": True,
        "solver": "svd",
    }


def test_xjtu_feature_rul_fit_uses_complete_train_only_preprocessing() -> None:
    fitted = fit_xjtu_feature_rul_baseline(_vectors("train"), _train_targets())

    assert fitted.config.experiment_id == XJTU_FEATURE_RIDGE_RUL_METHOD_ID
    assert fitted.preprocessing_state.observation_count == 3_246
    assert fitted.preprocessing_state.fit_partition is FitPartition.TRAIN
    assert fitted.preprocessing_state.scaling_strategy is ScalingStrategy.ROBUST
    assert fitted.model.source_observation_count == 3_246
    assert fitted.model.reference_observation_count == 3_246
    assert fitted.model.fit_observation_count == 3_246
    assert fitted.model.sampling_policy_id == "bearing-balanced-resample-v1"


def test_xjtu_feature_rul_uses_same_evaluator_and_beats_age_on_feature_signal() -> None:
    train_vectors = _vectors("train")
    validation_vectors = _vectors("validation")
    train_targets = _train_targets()
    validation_targets = build_xjtu_recorded_end_rul_targets(
        validation_vectors,
        partition="validation",
    )

    feature_fit = fit_xjtu_feature_rul_baseline(train_vectors, train_targets)
    feature_predictions = predict_xjtu_feature_rul(
        feature_fit,
        validation_vectors,
        partition="validation",
    )
    feature_evaluation = evaluate_xjtu_rul_point_predictions(
        validation_targets,
        feature_predictions,
        partition="validation",
    )

    age_fit = fit_xjtu_age_only_rul_baseline(train_targets)
    age_predictions = predict_xjtu_age_only_rul(
        age_fit,
        validation_vectors,
        partition="validation",
    )
    age_evaluation = evaluate_xjtu_rul_point_predictions(
        validation_targets,
        age_predictions,
        partition="validation",
    )

    assert feature_evaluation.prediction_method_id == XJTU_FEATURE_RIDGE_RUL_METHOD_ID
    assert feature_evaluation.mean_asset_mean_absolute_error < (
        age_evaluation.mean_asset_mean_absolute_error
    )
    assert feature_evaluation.mean_asset_normalized_mean_absolute_error < (
        age_evaluation.mean_asset_normalized_mean_absolute_error
    )


def test_xjtu_feature_rul_prediction_canonicalizes_reversed_input() -> None:
    fitted = fit_xjtu_feature_rul_baseline(_vectors("train"), _train_targets())
    expected = predict_xjtu_feature_rul(
        fitted,
        _vectors("validation"),
        partition="validation",
    )
    reordered = predict_xjtu_feature_rul(
        fitted,
        tuple(reversed(_vectors("validation"))),
        partition="validation",
    )

    assert reordered == expected


def test_xjtu_feature_rul_current_prediction_does_not_depend_on_future_feature_rows() -> None:
    fitted = fit_xjtu_feature_rul_baseline(_vectors("train"), _train_targets())
    original_vectors = _vectors("validation")
    mutated_vectors = tuple(
        replace(
            vector,
            values=tuple(value + 1_000_000.0 for value in vector.values),
        )
        if int(vector.metadata["acquisition_index"]) > 5
        else vector
        for vector in original_vectors
    )

    original = predict_xjtu_feature_rul(
        fitted,
        original_vectors,
        partition="validation",
    )
    mutated = predict_xjtu_feature_rul(
        fitted,
        mutated_vectors,
        partition="validation",
    )

    for original_series, mutated_series in zip(original, mutated, strict=True):
        assert original_series.asset_id == mutated_series.asset_id
        assert original_series.observations[:5] == mutated_series.observations[:5]


def test_xjtu_feature_rul_prediction_does_not_use_operating_condition_metadata() -> None:
    fitted = fit_xjtu_feature_rul_baseline(_vectors("train"), _train_targets())
    original_vectors = _vectors("validation")
    changed_condition = tuple(
        replace(
            vector,
            metadata={
                **dict(vector.metadata),
                "operating_condition": "changed-after-fit",
            },
        )
        for vector in original_vectors
    )

    original = predict_xjtu_feature_rul(
        fitted,
        original_vectors,
        partition="validation",
    )
    changed = predict_xjtu_feature_rul(
        fitted,
        changed_condition,
        partition="validation",
    )

    assert changed == original


def test_xjtu_feature_rul_fit_rejects_validation_targets() -> None:
    validation_targets = build_xjtu_recorded_end_rul_targets(
        _vectors("validation"),
        partition="validation",
    )

    with pytest.raises(XjtuFeatureRulBaselineError, match="train RUL targets"):
        fit_xjtu_feature_rul_baseline(
            _vectors("train"),
            validation_targets,
        )


def test_xjtu_feature_rul_prediction_rejects_feature_schema_drift() -> None:
    fitted = fit_xjtu_feature_rul_baseline(_vectors("train"), _train_targets())
    validation = _vectors("validation")
    invalid = replace(
        validation[0],
        feature_names=tuple(reversed(validation[0].feature_names)),
        values=tuple(reversed(validation[0].values)),
    )

    with pytest.raises(XjtuFeatureRulBaselineError, match="feature schema"):
        predict_xjtu_feature_rul(
            fitted,
            (invalid, *validation[1:]),
            partition="validation",
        )
