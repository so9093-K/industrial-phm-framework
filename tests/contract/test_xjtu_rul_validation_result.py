import json
from dataclasses import replace
from pathlib import Path
from statistics import fmean
from typing import cast

import pytest

from industrial_phm.adapters import get_xjtu_expected_acquisition_count
from industrial_phm.experiments import (
    XJTU_AGE_ONLY_RUL_METHOD_ID,
    XJTU_FEATURE_RIDGE_RUL_METHOD_ID,
    XJTU_RUL_LSTM_METHOD_ID,
    XJTU_RUL_TARGET_DEFINITION_ID,
    XJTU_RUL_TARGET_UNIT,
    XJTU_RUL_THREE_MODEL_VALIDATION_EVIDENCE_CLASS,
    XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID,
    XjtuRulBaselineValidationResult,
    XjtuRulThreeModelValidationResult,
    XjtuRulThreeModelValidationResultError,
    evaluate_xjtu_rul_point_predictions,
    get_xjtu_feature_rul_configuration,
    get_xjtu_reference_split,
    write_xjtu_rul_three_model_validation_result,
)
from industrial_phm.prognostics import (
    RulPredictionObservation,
    RulPredictionSeries,
    RulTargetObservation,
    RulTargetSeries,
)


def _targets() -> tuple[RulTargetSeries, ...]:
    return tuple(
        RulTargetSeries(
            target_definition_id=XJTU_RUL_TARGET_DEFINITION_ID,
            unit=XJTU_RUL_TARGET_UNIT,
            asset_id=asset_id,
            partition_id="validation",
            observations=tuple(
                RulTargetObservation(
                    asset_id=asset_id,
                    partition_id="validation",
                    source_observation_id=f"{asset_id}:acquisition-{index}",
                    remaining_useful_life=float(run_length - index),
                )
                for index in range(1, run_length + 1)
            ),
        )
        for asset_id in get_xjtu_reference_split().folds[0].validation
        for run_length in (get_xjtu_expected_acquisition_count(asset_id),)
    )


def _predictions(
    method_id: str,
    *,
    offset: float,
    first_acquisition: int = 1,
) -> tuple[RulPredictionSeries, ...]:
    return tuple(
        RulPredictionSeries(
            prediction_method_id=method_id,
            target_definition_id=series.target_definition_id,
            unit=series.unit,
            asset_id=series.asset_id,
            partition_id=series.partition_id,
            observations=tuple(
                RulPredictionObservation(
                    asset_id=series.asset_id,
                    partition_id=series.partition_id,
                    source_observation_id=observation.source_observation_id,
                    predicted_remaining_useful_life=(
                        observation.remaining_useful_life + offset
                    ),
                )
                for index, observation in enumerate(series.observations, start=1)
                if index >= first_acquisition
            ),
        )
        for series in _targets()
    )


def _baseline_result() -> XjtuRulBaselineValidationResult:
    fold = get_xjtu_reference_split().folds[0]
    config = get_xjtu_feature_rul_configuration()
    targets = _targets()
    age_predictions = _predictions(XJTU_AGE_ONLY_RUL_METHOD_ID, offset=2.0)
    feature_predictions = _predictions(XJTU_FEATURE_RIDGE_RUL_METHOD_ID, offset=1.0)
    endpoints = tuple(
        float(get_xjtu_expected_acquisition_count(asset_id)) for asset_id in fold.train
    )
    feature_count = len(config.selected_features)
    return XjtuRulBaselineValidationResult(
        code_revision="a" * 40,
        source_acquisition_count=9_216,
        dataset_id=config.dataset_id,
        split_id=config.split_id,
        fold_id=config.fold_id,
        target_definition_id=XJTU_RUL_TARGET_DEFINITION_ID,
        target_unit=XJTU_RUL_TARGET_UNIT,
        train_source_acquisition_count=3_246,
        validation_source_acquisition_count=2_818,
        age_train_asset_ids=fold.train,
        age_train_endpoint_acquisitions=endpoints,
        age_fitted_mean_endpoint_acquisition=float(fmean(endpoints)),
        age_predictions=age_predictions,
        age_evaluation=evaluate_xjtu_rul_point_predictions(
            targets,
            age_predictions,
            partition="validation",
        ),
        feature_set_id=config.feature_set_id,
        selected_features=tuple(config.selected_features),
        feature_fit_partition=config.fit_partition.value,
        feature_scaling_strategy=config.scaling_strategy.value,
        feature_preprocessing_fit_observation_count=3_246,
        feature_fitted_center=(0.0,) * feature_count,
        feature_fitted_scale=(1.0,) * feature_count,
        feature_zero_iqr_features=(),
        feature_reference_strategy=config.reference_strategy.value,
        feature_sampling_policy_id=config.sampling_policy_id,
        feature_model_family=config.model_family.value,
        feature_model_parameters=tuple(sorted(config.model_parameters.items())),
        feature_random_seed=config.random_seed,
        feature_model_fit_observation_count=3_246,
        feature_predictions=feature_predictions,
        feature_evaluation=evaluate_xjtu_rul_point_predictions(
            targets,
            feature_predictions,
            partition="validation",
        ),
    )


def _result() -> XjtuRulThreeModelValidationResult:
    baseline = _baseline_result()
    temporal_predictions = _predictions(
        XJTU_RUL_LSTM_METHOD_ID,
        offset=0.5,
        first_acquisition=8,
    )
    temporal_evaluation = evaluate_xjtu_rul_point_predictions(
        _targets(),
        temporal_predictions,
        partition="validation",
    )
    return XjtuRulThreeModelValidationResult(
        baseline_result=baseline,
        temporal_experiment_id=XJTU_RUL_LSTM_METHOD_ID,
        temporal_feature_set_id=baseline.feature_set_id,
        temporal_selected_features=baseline.selected_features,
        temporal_fit_partition="train",
        temporal_scaling_strategy="robust",
        temporal_preprocessing_fit_observation_count=3_246,
        temporal_fitted_center=(0.0,) * len(baseline.selected_features),
        temporal_fitted_scale=(1.0,) * len(baseline.selected_features),
        temporal_zero_iqr_features=(),
        temporal_sequence_length=8,
        temporal_sequence_stride=1,
        temporal_sequence_alignment="right-edge",
        temporal_train_source_observation_count=3_246,
        temporal_train_sequence_count=9,
        temporal_train_window_count=3_183,
        temporal_train_dropped_prefix_observation_count=63,
        temporal_model_family="lstm-regression",
        temporal_model_parameters=(
            ("adam_beta1", 0.9),
            ("adam_beta2", 0.999),
            ("adam_epsilon", 1e-8),
            ("batch_size", 64),
            ("checkpoint", "final-epoch"),
            ("deterministic_algorithms", True),
            ("device", "cpu"),
            ("dropout", 0.0),
            ("epochs", 50),
            ("gradient_clip_norm", 1.0),
            ("hidden_size", 32),
            ("layer_count", 1),
            ("learning_rate", 0.001),
            ("loss", "mean-squared-error"),
            ("numeric_precision", "float32"),
            ("optimizer", "adam"),
            ("sequence_length", 8),
            ("shuffle", True),
            ("weight_decay", 0.0),
        ),
        temporal_random_seed=42,
        temporal_sampling_policy_id="sequence-window-uniform-v1",
        temporal_runtime="pytorch",
        temporal_runtime_version="test-runtime",
        temporal_device="cpu",
        temporal_numeric_precision="float32",
        temporal_deterministic_algorithms=True,
        temporal_parameter_count=6_433,
        temporal_batch_size=64,
        temporal_epochs=50,
        temporal_epoch_losses=tuple(float(50 - index) for index in range(50)),
        temporal_predictions=temporal_predictions,
        temporal_evaluation=temporal_evaluation,
    )


def test_three_model_result_preserves_frozen_methods_and_temporal_prefix(
    tmp_path: Path,
) -> None:
    output = tmp_path / "three-model.json"

    write_xjtu_rul_three_model_validation_result(_result(), output)

    document = cast(dict[str, object], json.loads(output.read_text(encoding="utf-8")))
    assert document["schema_id"] == XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID

    provenance = cast(dict[str, object], document["provenance"])
    assert provenance["evidence_class"] == XJTU_RUL_THREE_MODEL_VALIDATION_EVIDENCE_CLASS
    assert provenance["code_revision"] == "a" * 40

    methods = cast(list[dict[str, object]], document["methods"])
    assert [method["method_id"] for method in methods] == [
        XJTU_AGE_ONLY_RUL_METHOD_ID,
        XJTU_FEATURE_RIDGE_RUL_METHOD_ID,
        XJTU_RUL_LSTM_METHOD_ID,
    ]

    temporal = methods[2]
    sequence = cast(dict[str, object], temporal["sequence"])
    assert sequence["length"] == 8
    assert sequence["train_window_count"] == 3_183
    assert sequence["validation_dropped_prefix_per_bearing"] == 7

    predictions = cast(list[dict[str, object]], temporal["predictions"])
    assert sum(
        len(cast(list[object], series["observations"])) for series in predictions
    ) == 2_797
    for series in predictions:
        observations = cast(list[dict[str, object]], series["observations"])
        assert observations[0]["acquisition_index"] == 8

    comparison = cast(dict[str, object], document["comparison"])
    assert comparison["feature_minus_age_mean_asset_mae"] == pytest.approx(-1.0)
    assert comparison["temporal_minus_age_mean_asset_mae"] == pytest.approx(-1.5)
    assert comparison["temporal_minus_feature_mean_asset_mae"] == pytest.approx(-0.5)


def test_three_model_result_keeps_test_bearings_excluded(tmp_path: Path) -> None:
    output = tmp_path / "three-model.json"

    write_xjtu_rul_three_model_validation_result(_result(), output)

    document = cast(dict[str, object], json.loads(output.read_text(encoding="utf-8")))
    source_scope = cast(dict[str, object], document["source_scope"])
    assert source_scope["excluded"] == [
        "test:Bearing1_1",
        "test:Bearing2_1",
        "test:Bearing3_1",
    ]


def test_three_model_result_rejects_incomplete_temporal_prediction_population() -> None:
    result = _result()
    first = result.temporal_predictions[0]
    incomplete = replace(first, observations=first.observations[:-1])

    with pytest.raises(
        XjtuRulThreeModelValidationResultError,
        match="right-edge acquisitions",
    ):
        replace(
            result,
            temporal_predictions=(incomplete, *result.temporal_predictions[1:]),
        )


def test_three_model_result_rejects_temporal_parameter_drift() -> None:
    result = _result()
    changed = tuple(
        (name, 16 if name == "hidden_size" else value)
        for name, value in result.temporal_model_parameters
    )

    with pytest.raises(
        XjtuRulThreeModelValidationResultError,
        match="parameters",
    ):
        replace(result, temporal_model_parameters=changed)
