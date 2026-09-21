from dataclasses import replace
from functools import cache
import math

import pytest

pytest.importorskip("torch", reason="install the deep-learning extra")

from industrial_phm.adapters import XJTU_SY_CHANNELS, get_xjtu_expected_acquisition_count
from industrial_phm.experiments import (
    FitPartition,
    ModelFamily,
    ReferenceStrategy,
    ScalingStrategy,
    XJTU_RUL_LSTM_METHOD_ID,
    XJTU_RUL_LSTM_SEQUENCE_SPEC,
    XjtuRulLstmError,
    build_xjtu_recorded_end_rul_targets,
    evaluate_xjtu_rul_point_predictions,
    fit_xjtu_rul_lstm_model,
    get_xjtu_reference_split,
    get_xjtu_rul_lstm_configuration,
    predict_xjtu_rul_lstm,
    prepare_xjtu_rul_sequence_construction,
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
                        (target_signal / max(float(run_length - 1), 1.0))
                        + feature_index * 0.001
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
def _targets(partition: str) -> tuple[RulTargetSeries, ...]:
    return build_xjtu_recorded_end_rul_targets(
        _vectors(partition),
        partition=partition,
    )


@cache
def _fitted():
    return fit_xjtu_rul_lstm_model(_vectors("train"), _targets("train"))


def test_xjtu_rul_lstm_configuration_is_frozen_before_numerical_evidence() -> None:
    config = get_xjtu_rul_lstm_configuration()

    assert config.experiment_id == XJTU_RUL_LSTM_METHOD_ID
    assert config.fit_partition is FitPartition.TRAIN
    assert config.reference_strategy is ReferenceStrategy.ALL_TRAIN_OBSERVATIONS
    assert config.sampling_policy_id == "sequence-window-uniform-v1"
    assert config.scaling_strategy is ScalingStrategy.ROBUST
    assert config.model_family is ModelFamily.LSTM_REGRESSION
    assert config.random_seed == 42
    assert tuple(config.selected_features) == _FEATURE_NAMES
    assert config.model_parameters["sequence_length"] == 8
    assert config.model_parameters["hidden_size"] == 32
    assert config.model_parameters["epochs"] == 50


def test_xjtu_rul_lstm_fit_uses_complete_train_only_sequence_population() -> None:
    fitted = _fitted()

    assert fitted.preprocessing_state.observation_count == 3_246
    assert fitted.preprocessing_state.fit_partition is FitPartition.TRAIN
    assert fitted.preprocessing_state.scaling_strategy is ScalingStrategy.ROBUST
    assert fitted.train_sequence.spec == XJTU_RUL_LSTM_SEQUENCE_SPEC
    assert fitted.train_sequence.source_observation_count == 3_246
    assert fitted.train_sequence.sequence_count == 9
    assert fitted.train_sequence.window_count == 3_183
    assert fitted.train_sequence.dropped_prefix_observation_count == 63
    assert fitted.model.training.fit_window_count == 3_183
    assert fitted.model.training.sampling_policy_id == "sequence-window-uniform-v1"


def test_xjtu_rul_lstm_predicts_right_edge_subset_and_uses_same_evaluator() -> None:
    predictions = predict_xjtu_rul_lstm(
        _fitted(),
        _vectors("validation"),
        partition="validation",
    )
    evaluation = evaluate_xjtu_rul_point_predictions(
        _targets("validation"),
        predictions,
        partition="validation",
    )

    assert tuple(series.asset_id for series in predictions) == (
        get_xjtu_reference_split().folds[0].validation
    )
    assert sum(len(series.observations) for series in predictions) == 2_797
    for series in predictions:
        expected_count = get_xjtu_expected_acquisition_count(series.asset_id) - 7
        assert len(series.observations) == expected_count
        assert series.observations[0].source_observation_id == (
            f"{series.asset_id}:acquisition-8"
        )
        assert series.observations[-1].source_observation_id == (
            f"{series.asset_id}:acquisition-{get_xjtu_expected_acquisition_count(series.asset_id)}"
        )

    assert evaluation.prediction_method_id == XJTU_RUL_LSTM_METHOD_ID
    assert evaluation.mean_asset_mean_absolute_error >= 0.0
    assert math.isfinite(evaluation.mean_asset_root_mean_squared_error)
    assert evaluation.mean_asset_normalized_mean_absolute_error is not None


def test_xjtu_rul_lstm_prediction_canonicalizes_reversed_input() -> None:
    expected = predict_xjtu_rul_lstm(
        _fitted(),
        _vectors("validation"),
        partition="validation",
    )
    reordered = predict_xjtu_rul_lstm(
        _fitted(),
        tuple(reversed(_vectors("validation"))),
        partition="validation",
    )

    assert reordered == expected


def test_xjtu_rul_lstm_current_prediction_does_not_depend_on_future_rows() -> None:
    fitted = _fitted()
    original_vectors = _vectors("validation")
    mutated_vectors = tuple(
        replace(
            vector,
            values=tuple(value + 10_000.0 for value in vector.values),
        )
        if int(vector.metadata["acquisition_index"]) > 12
        else vector
        for vector in original_vectors
    )

    original = predict_xjtu_rul_lstm(
        fitted,
        original_vectors,
        partition="validation",
    )
    mutated = predict_xjtu_rul_lstm(
        fitted,
        mutated_vectors,
        partition="validation",
    )

    for original_series, mutated_series in zip(original, mutated, strict=True):
        assert original_series.asset_id == mutated_series.asset_id
        assert original_series.observations[:5] == mutated_series.observations[:5]


def test_xjtu_rul_lstm_prediction_does_not_use_operating_condition_metadata() -> None:
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

    original = predict_xjtu_rul_lstm(
        _fitted(),
        original_vectors,
        partition="validation",
    )
    changed = predict_xjtu_rul_lstm(
        _fitted(),
        changed_condition,
        partition="validation",
    )

    assert changed == original


def test_xjtu_rul_lstm_fit_rejects_validation_targets() -> None:
    with pytest.raises(XjtuRulLstmError, match="train RUL targets"):
        fit_xjtu_rul_lstm_model(
            _vectors("train"),
            _targets("validation"),
        )


def test_xjtu_rul_lstm_prediction_rejects_feature_schema_drift() -> None:
    validation = _vectors("validation")
    invalid = replace(
        validation[0],
        feature_names=tuple(reversed(validation[0].feature_names)),
        values=tuple(reversed(validation[0].values)),
    )

    with pytest.raises(XjtuRulLstmError, match="feature schema"):
        predict_xjtu_rul_lstm(
            _fitted(),
            (invalid, *validation[1:]),
            partition="validation",
        )


def test_xjtu_rul_sequence_construction_rejects_incomplete_partition() -> None:
    with pytest.raises(XjtuRulLstmError, match="acquisitions 1"):
        prepare_xjtu_rul_sequence_construction(
            _fitted().preprocessing_state,
            _vectors("validation")[:-1],
            partition="validation",
        )
