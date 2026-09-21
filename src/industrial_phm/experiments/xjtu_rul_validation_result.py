"""Three-model XJTU RUL validation evidence for frozen prognostics protocol v1."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from industrial_phm.adapters import (
    XjtuSyAdapter,
    get_xjtu_expected_acquisition_count,
    validate_xjtu_source,
)
from industrial_phm.experiments.config import ExperimentParameter
from industrial_phm.experiments.xjtu import get_xjtu_reference_split
from industrial_phm.experiments.xjtu_rul import (
    XJTU_RUL_PROTOCOL_ID,
    build_xjtu_recorded_end_rul_targets,
)
from industrial_phm.experiments.xjtu_rul_age_baseline import (
    XJTU_AGE_ONLY_RUL_METHOD_ID,
    fit_xjtu_age_only_rul_baseline,
    predict_xjtu_age_only_rul,
)
from industrial_phm.experiments.xjtu_rul_baseline_result import (
    XjtuRulBaselineValidationResult,
    build_xjtu_rul_baseline_validation_result,
    xjtu_rul_baseline_validation_document,
)
from industrial_phm.experiments.xjtu_rul_evaluation import (
    evaluate_xjtu_rul_point_predictions,
)
from industrial_phm.experiments.xjtu_rul_feature_baseline import (
    XJTU_FEATURE_RIDGE_RUL_METHOD_ID,
    fit_xjtu_feature_rul_baseline,
    predict_xjtu_feature_rul,
)
from industrial_phm.experiments.xjtu_rul_lstm import (
    XJTU_RUL_LSTM_METHOD_ID,
    XjtuRulLstmFit,
    fit_xjtu_rul_lstm_model,
    predict_xjtu_rul_lstm,
)
from industrial_phm.features import iter_vibration_features
from industrial_phm.prognostics import RulPointEvaluation, RulPredictionSeries

XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID = (
    "xjtu-rul-three-model-validation-result-v1"
)
XJTU_RUL_THREE_MODEL_VALIDATION_EVIDENCE_CLASS = (
    "protocol-frozen-retrospective-three-model-development-evidence"
)
_FULL_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")

_EXPECTED_TEMPORAL_PARAMETERS: dict[str, ExperimentParameter] = {
    "sequence_length": 8,
    "hidden_size": 32,
    "layer_count": 1,
    "dropout": 0.0,
    "loss": "mean-squared-error",
    "optimizer": "adam",
    "learning_rate": 0.001,
    "adam_beta1": 0.9,
    "adam_beta2": 0.999,
    "adam_epsilon": 1e-8,
    "weight_decay": 0.0,
    "gradient_clip_norm": 1.0,
    "batch_size": 64,
    "epochs": 50,
    "shuffle": True,
    "checkpoint": "final-epoch",
    "numeric_precision": "float32",
    "device": "cpu",
    "deterministic_algorithms": True,
}


class XjtuRulThreeModelValidationResultError(ValueError):
    """Raised when three-model XJTU RUL evidence violates its contract."""


@dataclass(frozen=True, slots=True)
class XjtuRulThreeModelValidationResult:
    """Serializable comparison evidence for age, Ridge, and temporal LSTM RUL."""

    baseline_result: XjtuRulBaselineValidationResult
    temporal_experiment_id: str
    temporal_feature_set_id: str
    temporal_selected_features: Sequence[str]
    temporal_fit_partition: str
    temporal_scaling_strategy: str
    temporal_preprocessing_fit_observation_count: int
    temporal_fitted_center: Sequence[float]
    temporal_fitted_scale: Sequence[float]
    temporal_zero_iqr_features: Sequence[str]
    temporal_sequence_length: int
    temporal_sequence_stride: int
    temporal_sequence_alignment: str
    temporal_train_source_observation_count: int
    temporal_train_sequence_count: int
    temporal_train_window_count: int
    temporal_train_dropped_prefix_observation_count: int
    temporal_model_family: str
    temporal_model_parameters: Sequence[tuple[str, ExperimentParameter]]
    temporal_random_seed: int
    temporal_sampling_policy_id: str
    temporal_runtime: str
    temporal_runtime_version: str
    temporal_device: str
    temporal_numeric_precision: str
    temporal_deterministic_algorithms: bool
    temporal_parameter_count: int
    temporal_batch_size: int
    temporal_epochs: int
    temporal_epoch_losses: Sequence[float]
    temporal_predictions: Sequence[RulPredictionSeries]
    temporal_evaluation: RulPointEvaluation

    def __post_init__(self) -> None:
        if not isinstance(self.baseline_result, XjtuRulBaselineValidationResult):
            raise XjtuRulThreeModelValidationResultError(
                "baseline_result must be an XjtuRulBaselineValidationResult"
            )

        expected_text = {
            "temporal_experiment_id": XJTU_RUL_LSTM_METHOD_ID,
            "temporal_fit_partition": "train",
            "temporal_scaling_strategy": "robust",
            "temporal_sequence_alignment": "right-edge",
            "temporal_model_family": "lstm-regression",
            "temporal_sampling_policy_id": "sequence-window-uniform-v1",
            "temporal_runtime": "pytorch",
            "temporal_device": "cpu",
            "temporal_numeric_precision": "float32",
        }
        for field_name, expected in expected_text.items():
            if getattr(self, field_name) != expected:
                raise XjtuRulThreeModelValidationResultError(
                    f"{field_name} must equal {expected!r}"
                )

        expected_int = {
            "temporal_preprocessing_fit_observation_count": 3_246,
            "temporal_sequence_length": 8,
            "temporal_sequence_stride": 1,
            "temporal_train_source_observation_count": 3_246,
            "temporal_train_sequence_count": 9,
            "temporal_train_window_count": 3_183,
            "temporal_train_dropped_prefix_observation_count": 63,
            "temporal_random_seed": 42,
            "temporal_batch_size": 64,
            "temporal_epochs": 50,
        }
        for field_name, expected in expected_int.items():
            if getattr(self, field_name) != expected:
                raise XjtuRulThreeModelValidationResultError(
                    f"{field_name} must equal {expected}"
                )

        selected_features = tuple(self.temporal_selected_features)
        fitted_center = tuple(float(value) for value in self.temporal_fitted_center)
        fitted_scale = tuple(float(value) for value in self.temporal_fitted_scale)
        zero_iqr_features = tuple(self.temporal_zero_iqr_features)
        model_parameters = tuple(self.temporal_model_parameters)
        epoch_losses = tuple(float(value) for value in self.temporal_epoch_losses)
        predictions = tuple(self.temporal_predictions)

        if selected_features != tuple(self.baseline_result.selected_features):
            raise XjtuRulThreeModelValidationResultError(
                "temporal selected features must match the baseline feature schema"
            )
        if self.temporal_feature_set_id != self.baseline_result.feature_set_id:
            raise XjtuRulThreeModelValidationResultError(
                "temporal feature_set_id must match baseline feature evidence"
            )
        if len(fitted_center) != len(selected_features) or len(fitted_scale) != len(
            selected_features
        ):
            raise XjtuRulThreeModelValidationResultError(
                "temporal preprocessing state must align with selected_features"
            )
        if any(scale <= 0.0 for scale in fitted_scale):
            raise XjtuRulThreeModelValidationResultError(
                "temporal fitted_scale values must be positive"
            )
        if set(zero_iqr_features) - set(selected_features):
            raise XjtuRulThreeModelValidationResultError(
                "temporal_zero_iqr_features contains unknown features"
            )
        if dict(model_parameters) != _EXPECTED_TEMPORAL_PARAMETERS:
            raise XjtuRulThreeModelValidationResultError(
                "temporal model parameters must match the frozen protocol"
            )
        if not self.temporal_deterministic_algorithms:
            raise XjtuRulThreeModelValidationResultError(
                "temporal deterministic_algorithms must be true"
            )
        if (
            isinstance(self.temporal_parameter_count, bool)
            or not isinstance(self.temporal_parameter_count, int)
            or self.temporal_parameter_count <= 0
        ):
            raise XjtuRulThreeModelValidationResultError(
                "temporal_parameter_count must be a positive integer"
            )
        if (
            not isinstance(self.temporal_runtime_version, str)
            or not self.temporal_runtime_version.strip()
            or self.temporal_runtime_version != self.temporal_runtime_version.strip()
        ):
            raise XjtuRulThreeModelValidationResultError(
                "temporal_runtime_version must be a trimmed non-empty string"
            )
        if len(epoch_losses) != self.temporal_epochs:
            raise XjtuRulThreeModelValidationResultError(
                "temporal_epoch_losses must contain one value per epoch"
            )
        if any(not math.isfinite(loss) or loss < 0.0 for loss in epoch_losses):
            raise XjtuRulThreeModelValidationResultError(
                "temporal_epoch_losses must be finite and non-negative"
            )

        _validate_temporal_prediction_evaluation(
            predictions,
            self.temporal_evaluation,
            baseline_result=self.baseline_result,
        )

        object.__setattr__(self, "temporal_selected_features", selected_features)
        object.__setattr__(self, "temporal_fitted_center", fitted_center)
        object.__setattr__(self, "temporal_fitted_scale", fitted_scale)
        object.__setattr__(self, "temporal_zero_iqr_features", zero_iqr_features)
        object.__setattr__(self, "temporal_model_parameters", model_parameters)
        object.__setattr__(self, "temporal_epoch_losses", epoch_losses)
        object.__setattr__(self, "temporal_predictions", predictions)

    @property
    def code_revision(self) -> str:
        """Return the authoritative revision inherited from baseline evidence."""
        return self.baseline_result.code_revision


def run_xjtu_rul_three_model_validation(
    source: Path,
    output_path: Path,
    *,
    code_revision: str,
) -> XjtuRulThreeModelValidationResult:
    """Run all three frozen RUL methods on fold-1 validation without reading test."""
    _validate_code_revision(code_revision)
    source_report = validate_xjtu_source(source)
    if not source_report.profile_matches:
        raise XjtuRulThreeModelValidationResultError(
            "XJTU-SY source does not match the observed complete profile: "
            + "; ".join(source_report.profile_issues)
        )

    fold = get_xjtu_reference_split().folds[0]
    adapter = XjtuSyAdapter()
    train_vectors = tuple(iter_vibration_features(adapter.iter_asset_series(source, fold.train)))
    validation_vectors = tuple(
        iter_vibration_features(adapter.iter_asset_series(source, fold.validation))
    )
    train_targets = build_xjtu_recorded_end_rul_targets(train_vectors, partition="train")
    validation_targets = build_xjtu_recorded_end_rul_targets(
        validation_vectors,
        partition="validation",
    )

    age_fitted = fit_xjtu_age_only_rul_baseline(train_targets)
    age_predictions = predict_xjtu_age_only_rul(
        age_fitted,
        validation_vectors,
        partition="validation",
    )
    age_evaluation = evaluate_xjtu_rul_point_predictions(
        validation_targets,
        age_predictions,
        partition="validation",
    )

    feature_fitted = fit_xjtu_feature_rul_baseline(train_vectors, train_targets)
    feature_predictions = predict_xjtu_feature_rul(
        feature_fitted,
        validation_vectors,
        partition="validation",
    )
    feature_evaluation = evaluate_xjtu_rul_point_predictions(
        validation_targets,
        feature_predictions,
        partition="validation",
    )

    baseline_result = build_xjtu_rul_baseline_validation_result(
        age_fitted,
        age_predictions,
        age_evaluation,
        feature_fitted,
        feature_predictions,
        feature_evaluation,
        code_revision=code_revision,
        source_acquisition_count=source_report.acquisition_count,
    )

    temporal_fitted = fit_xjtu_rul_lstm_model(train_vectors, train_targets)
    temporal_predictions = predict_xjtu_rul_lstm(
        temporal_fitted,
        validation_vectors,
        partition="validation",
    )
    temporal_evaluation = evaluate_xjtu_rul_point_predictions(
        validation_targets,
        temporal_predictions,
        partition="validation",
    )

    result = build_xjtu_rul_three_model_validation_result(
        baseline_result,
        temporal_fitted,
        temporal_predictions,
        temporal_evaluation,
    )
    write_xjtu_rul_three_model_validation_result(result, output_path)
    return result


def build_xjtu_rul_three_model_validation_result(
    baseline_result: XjtuRulBaselineValidationResult,
    temporal_fitted: XjtuRulLstmFit,
    temporal_predictions: Sequence[RulPredictionSeries],
    temporal_evaluation: RulPointEvaluation,
) -> XjtuRulThreeModelValidationResult:
    """Build immutable three-model evidence from completed frozen executions."""
    if not isinstance(temporal_fitted, XjtuRulLstmFit):
        raise XjtuRulThreeModelValidationResultError(
            "temporal_fitted must be an XjtuRulLstmFit"
        )

    config = temporal_fitted.config
    state = temporal_fitted.preprocessing_state
    sequence = temporal_fitted.train_sequence
    training = temporal_fitted.model.training
    return XjtuRulThreeModelValidationResult(
        baseline_result=baseline_result,
        temporal_experiment_id=config.experiment_id,
        temporal_feature_set_id=config.feature_set_id,
        temporal_selected_features=tuple(config.selected_features),
        temporal_fit_partition=config.fit_partition.value,
        temporal_scaling_strategy=config.scaling_strategy.value,
        temporal_preprocessing_fit_observation_count=state.observation_count,
        temporal_fitted_center=tuple(state.fitted_center),
        temporal_fitted_scale=tuple(state.fitted_scale),
        temporal_zero_iqr_features=tuple(state.zero_iqr_features),
        temporal_sequence_length=sequence.spec.length,
        temporal_sequence_stride=sequence.spec.stride,
        temporal_sequence_alignment=sequence.spec.alignment.value,
        temporal_train_source_observation_count=sequence.source_observation_count,
        temporal_train_sequence_count=sequence.sequence_count,
        temporal_train_window_count=sequence.window_count,
        temporal_train_dropped_prefix_observation_count=(
            sequence.dropped_prefix_observation_count
        ),
        temporal_model_family=config.model_family.value,
        temporal_model_parameters=tuple(sorted(config.model_parameters.items())),
        temporal_random_seed=config.random_seed,
        temporal_sampling_policy_id=config.sampling_policy_id,
        temporal_runtime=training.runtime,
        temporal_runtime_version=training.runtime_version,
        temporal_device=training.device,
        temporal_numeric_precision=training.numeric_precision,
        temporal_deterministic_algorithms=training.deterministic_algorithms,
        temporal_parameter_count=training.parameter_count,
        temporal_batch_size=training.batch_size,
        temporal_epochs=training.epochs,
        temporal_epoch_losses=tuple(training.epoch_losses),
        temporal_predictions=tuple(temporal_predictions),
        temporal_evaluation=temporal_evaluation,
    )


def write_xjtu_rul_three_model_validation_result(
    result: XjtuRulThreeModelValidationResult,
    output_path: Path,
) -> None:
    """Write deterministic three-model retrospective validation evidence."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            xjtu_rul_three_model_validation_document(result),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def xjtu_rul_three_model_validation_document(
    result: XjtuRulThreeModelValidationResult,
) -> dict[str, Any]:
    """Return the JSON-compatible three-model comparison document."""
    baseline = xjtu_rul_baseline_validation_document(result.baseline_result)
    provenance = dict(cast(dict[str, Any], baseline["provenance"]))
    provenance["evidence_class"] = XJTU_RUL_THREE_MODEL_VALIDATION_EVIDENCE_CLASS

    methods = list(cast(list[dict[str, Any]], baseline["methods"]))
    methods.append(_temporal_method_document(result))

    comparison = dict(cast(dict[str, Any], baseline["comparison"]))
    comparison.update(
        {
            "temporal_minus_age_mean_asset_mae": (
                result.temporal_evaluation.mean_asset_mean_absolute_error
                - result.baseline_result.age_evaluation.mean_asset_mean_absolute_error
            ),
            "temporal_minus_feature_mean_asset_mae": (
                result.temporal_evaluation.mean_asset_mean_absolute_error
                - result.baseline_result.feature_evaluation.mean_asset_mean_absolute_error
            ),
            "temporal_minus_age_mean_asset_rmse": (
                result.temporal_evaluation.mean_asset_root_mean_squared_error
                - result.baseline_result.age_evaluation.mean_asset_root_mean_squared_error
            ),
            "temporal_minus_feature_mean_asset_rmse": (
                result.temporal_evaluation.mean_asset_root_mean_squared_error
                - result.baseline_result.feature_evaluation.mean_asset_root_mean_squared_error
            ),
            "temporal_minus_age_mean_asset_normalized_mae": (
                _required_normalized_mae(result.temporal_evaluation)
                - _required_normalized_mae(result.baseline_result.age_evaluation)
            ),
            "temporal_minus_feature_mean_asset_normalized_mae": (
                _required_normalized_mae(result.temporal_evaluation)
                - _required_normalized_mae(result.baseline_result.feature_evaluation)
            ),
        }
    )

    return {
        "schema_id": XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID,
        "provenance": provenance,
        "source_scope": baseline["source_scope"],
        "target": baseline["target"],
        "methods": methods,
        "comparison": comparison,
        "capability_scope": baseline["capability_scope"],
        "interpretation": (
            "Protocol-frozen retrospective development evidence on fold-1 validation "
            "bearing runs. It compares age-only, current-acquisition feature Ridge, and "
            "8-acquisition temporal LSTM point estimates with the same recorded-end RUL "
            "target and bearing-first evaluator. The temporal method begins at acquisition "
            "8 because earlier rows do not have complete sequence context. Test bearings "
            "remain excluded, and no uncertainty, physical-failure-threshold, field, or "
            "maintenance-decision validation is claimed."
        ),
    }


def _temporal_method_document(
    result: XjtuRulThreeModelValidationResult,
) -> dict[str, Any]:
    return {
        "method_id": XJTU_RUL_LSTM_METHOD_ID,
        "kind": "temporal-sequence-lstm-regression",
        "feature_schema": {
            "feature_set_id": result.temporal_feature_set_id,
            "selected_features": list(result.temporal_selected_features),
            "selected_feature_count": len(result.temporal_selected_features),
        },
        "preprocessing": {
            "fit_partition": result.temporal_fit_partition,
            "scaling_strategy": result.temporal_scaling_strategy,
            "fit_observation_count": result.temporal_preprocessing_fit_observation_count,
            "fitted_center": list(result.temporal_fitted_center),
            "fitted_scale": list(result.temporal_fitted_scale),
            "zero_iqr_features": list(result.temporal_zero_iqr_features),
        },
        "sequence": {
            "length": result.temporal_sequence_length,
            "stride": result.temporal_sequence_stride,
            "alignment": result.temporal_sequence_alignment,
            "train_source_observation_count": (
                result.temporal_train_source_observation_count
            ),
            "train_sequence_count": result.temporal_train_sequence_count,
            "train_window_count": result.temporal_train_window_count,
            "train_dropped_prefix_observation_count": (
                result.temporal_train_dropped_prefix_observation_count
            ),
            "validation_prediction_alignment": "right-edge-acquisition",
            "validation_dropped_prefix_per_bearing": result.temporal_sequence_length - 1,
        },
        "model": {
            "family": result.temporal_model_family,
            "parameters": dict(result.temporal_model_parameters),
            "random_seed": result.temporal_random_seed,
            "sampling_policy_id": result.temporal_sampling_policy_id,
            "runtime": result.temporal_runtime,
            "runtime_version": result.temporal_runtime_version,
            "device": result.temporal_device,
            "numeric_precision": result.temporal_numeric_precision,
            "deterministic_algorithms": result.temporal_deterministic_algorithms,
            "parameter_count": result.temporal_parameter_count,
            "batch_size": result.temporal_batch_size,
            "epochs": result.temporal_epochs,
            "epoch_losses": list(result.temporal_epoch_losses),
            "final_epoch_mean_training_loss": result.temporal_epoch_losses[-1],
        },
        "evaluation": _evaluation_document(result.temporal_evaluation),
        "predictions": _prediction_documents(result.temporal_predictions),
    }


def _validate_temporal_prediction_evaluation(
    predictions: Sequence[RulPredictionSeries],
    evaluation: RulPointEvaluation,
    *,
    baseline_result: XjtuRulBaselineValidationResult,
) -> None:
    if not isinstance(evaluation, RulPointEvaluation):
        raise XjtuRulThreeModelValidationResultError(
            "temporal_evaluation must be a RulPointEvaluation"
        )
    if evaluation.prediction_method_id != XJTU_RUL_LSTM_METHOD_ID:
        raise XjtuRulThreeModelValidationResultError(
            "temporal evaluation method identity must match the frozen LSTM"
        )
    if evaluation.target_definition_id != baseline_result.target_definition_id:
        raise XjtuRulThreeModelValidationResultError(
            "temporal evaluation target definition must match baseline evidence"
        )
    if evaluation.unit != baseline_result.target_unit:
        raise XjtuRulThreeModelValidationResultError(
            "temporal evaluation unit must match baseline evidence"
        )
    _required_normalized_mae(evaluation)

    prediction_series = tuple(predictions)
    fold = get_xjtu_reference_split().folds[0]
    if tuple(series.asset_id for series in prediction_series) != fold.validation:
        raise XjtuRulThreeModelValidationResultError(
            "temporal prediction bearing order must match fold-1 validation"
        )
    if any(series.partition_id != "validation" for series in prediction_series):
        raise XjtuRulThreeModelValidationResultError(
            "temporal evidence may only contain validation predictions"
        )
    if any(
        series.prediction_method_id != XJTU_RUL_LSTM_METHOD_ID
        for series in prediction_series
    ):
        raise XjtuRulThreeModelValidationResultError(
            "all temporal predictions must use the frozen LSTM method identity"
        )
    if any(
        series.target_definition_id != baseline_result.target_definition_id
        for series in prediction_series
    ):
        raise XjtuRulThreeModelValidationResultError(
            "temporal prediction target definition must match baseline evidence"
        )
    if any(series.unit != baseline_result.target_unit for series in prediction_series):
        raise XjtuRulThreeModelValidationResultError(
            "temporal prediction unit must match baseline evidence"
        )

    evaluation_assets = tuple(item.asset_id for item in evaluation.asset_results)
    if evaluation_assets != tuple(sorted(fold.validation)):
        raise XjtuRulThreeModelValidationResultError(
            "temporal evaluation bearing population must match fold-1 validation"
        )

    evaluation_count_by_asset = {
        item.asset_id: item.prediction_count for item in evaluation.asset_results
    }
    for series in prediction_series:
        run_length = get_xjtu_expected_acquisition_count(series.asset_id)
        expected_count = run_length - 7
        if len(series.observations) != expected_count:
            raise XjtuRulThreeModelValidationResultError(
                f"temporal validation predictions for {series.asset_id} must contain "
                f"{expected_count} right-edge acquisitions"
            )
        expected_ids = tuple(
            f"{series.asset_id}:acquisition-{index}"
            for index in range(8, run_length + 1)
        )
        if evaluation_count_by_asset[series.asset_id] != expected_count:
            raise XjtuRulThreeModelValidationResultError(
                f"temporal evaluation count for {series.asset_id} must equal "
                f"{expected_count}"
            )
        observed_ids = tuple(
            observation.source_observation_id for observation in series.observations
        )
        if observed_ids != expected_ids:
            raise XjtuRulThreeModelValidationResultError(
                f"temporal validation predictions for {series.asset_id} must preserve "
                "acquisition 8..N right-edge order"
            )


def _evaluation_document(evaluation: RulPointEvaluation) -> dict[str, Any]:
    return {
        "aggregation": "equal-bearing-mean",
        "prediction_method_id": evaluation.prediction_method_id,
        "target_definition_id": evaluation.target_definition_id,
        "unit": evaluation.unit,
        "mean_asset_mean_absolute_error": evaluation.mean_asset_mean_absolute_error,
        "mean_asset_root_mean_squared_error": (
            evaluation.mean_asset_root_mean_squared_error
        ),
        "mean_asset_mean_signed_error": evaluation.mean_asset_mean_signed_error,
        "mean_asset_normalized_mean_absolute_error": (
            evaluation.mean_asset_normalized_mean_absolute_error
        ),
        "bearings": [
            {
                "asset_id": item.asset_id,
                "partition_id": item.partition_id,
                "prediction_count": item.prediction_count,
                "mean_absolute_error": item.mean_absolute_error,
                "root_mean_squared_error": item.root_mean_squared_error,
                "mean_signed_error": item.mean_signed_error,
                "normalized_mean_absolute_error": item.normalized_mean_absolute_error,
            }
            for item in evaluation.asset_results
        ],
    }


def _prediction_documents(
    predictions: Sequence[RulPredictionSeries],
) -> list[dict[str, Any]]:
    return [
        {
            "asset_id": series.asset_id,
            "partition_id": series.partition_id,
            "observations": [
                {
                    "source_observation_id": observation.source_observation_id,
                    "acquisition_index": _acquisition_index(
                        series.asset_id,
                        observation.source_observation_id,
                    ),
                    "predicted_remaining_useful_life": (
                        observation.predicted_remaining_useful_life
                    ),
                }
                for observation in series.observations
            ],
        }
        for series in predictions
    ]


def _required_normalized_mae(evaluation: RulPointEvaluation) -> float:
    value = evaluation.mean_asset_normalized_mean_absolute_error
    if value is None:
        raise XjtuRulThreeModelValidationResultError(
            "XJTU RUL three-model evidence requires normalized MAE"
        )
    return value


def _acquisition_index(asset_id: str, source_observation_id: str) -> int:
    prefix = f"{asset_id}:acquisition-"
    if not source_observation_id.startswith(prefix):
        raise XjtuRulThreeModelValidationResultError(
            "prediction source identity does not match its bearing"
        )
    suffix = source_observation_id.removeprefix(prefix)
    if not suffix.isdigit() or int(suffix) <= 0:
        raise XjtuRulThreeModelValidationResultError(
            "prediction source identity must end in a positive acquisition index"
        )
    return int(suffix)


def _validate_code_revision(value: str) -> None:
    if not _FULL_GIT_REVISION.fullmatch(value):
        raise XjtuRulThreeModelValidationResultError(
            "code_revision must be a full 40-character lowercase Git commit SHA"
        )
