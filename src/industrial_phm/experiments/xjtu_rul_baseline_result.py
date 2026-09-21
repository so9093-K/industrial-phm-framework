"""Versioned XJTU RUL baseline validation evidence and execution contract."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from industrial_phm.adapters import (
    XjtuSyAdapter,
    get_xjtu_expected_acquisition_count,
    validate_xjtu_source,
)
from industrial_phm.experiments.config import ExperimentParameter
from industrial_phm.experiments.xjtu import get_xjtu_reference_split
from industrial_phm.experiments.xjtu_rul import (
    XJTU_RUL_PROTOCOL_ID,
    XJTU_RUL_TARGET_DEFINITION_ID,
    XJTU_RUL_TARGET_UNIT,
    build_xjtu_recorded_end_rul_targets,
)
from industrial_phm.experiments.xjtu_rul_age_baseline import (
    XJTU_AGE_ONLY_RUL_METHOD_ID,
    XjtuAgeOnlyRulBaseline,
    fit_xjtu_age_only_rul_baseline,
    predict_xjtu_age_only_rul,
)
from industrial_phm.experiments.xjtu_rul_evaluation import (
    evaluate_xjtu_rul_point_predictions,
)
from industrial_phm.experiments.xjtu_rul_feature_baseline import (
    XJTU_FEATURE_RIDGE_RUL_METHOD_ID,
    XjtuFeatureRulBaselineFit,
    fit_xjtu_feature_rul_baseline,
    predict_xjtu_feature_rul,
)
from industrial_phm.features import iter_vibration_features
from industrial_phm.prognostics import (
    RulPointEvaluation,
    RulPredictionSeries,
)

XJTU_RUL_BASELINE_VALIDATION_RESULT_SCHEMA_ID = "xjtu-rul-baseline-validation-result-v1"
XJTU_RUL_BASELINE_VALIDATION_EVIDENCE_CLASS = (
    "protocol-frozen-retrospective-development-evidence"
)

_FULL_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")
_AVAILABLE_CAPABILITIES = (
    "prognostics-rul-point-estimate",
    "retrospective-validation-error-evidence",
)
_UNSUPPORTED_CAPABILITIES = (
    "prediction-interval",
    "uncertainty-calibration",
    "validated-physical-failure-threshold",
    "field-rul-validation",
    "maintenance-decision-recommendation",
)


class XjtuRulBaselineValidationResultError(ValueError):
    """Raised when frozen XJTU RUL baseline evidence violates its contract."""


@dataclass(frozen=True, slots=True)
class XjtuRulBaselineValidationResult:
    """Serializable train/validation evidence for the two frozen RUL baselines."""

    code_revision: str
    source_acquisition_count: int
    dataset_id: str
    split_id: str
    fold_id: str
    target_definition_id: str
    target_unit: str
    train_source_acquisition_count: int
    validation_source_acquisition_count: int
    age_train_asset_ids: Sequence[str]
    age_train_endpoint_acquisitions: Sequence[float]
    age_fitted_mean_endpoint_acquisition: float
    age_predictions: Sequence[RulPredictionSeries]
    age_evaluation: RulPointEvaluation
    feature_set_id: str
    selected_features: Sequence[str]
    feature_fit_partition: str
    feature_scaling_strategy: str
    feature_preprocessing_fit_observation_count: int
    feature_fitted_center: Sequence[float]
    feature_fitted_scale: Sequence[float]
    feature_zero_iqr_features: Sequence[str]
    feature_reference_strategy: str
    feature_sampling_policy_id: str
    feature_model_family: str
    feature_model_parameters: Sequence[tuple[str, ExperimentParameter]]
    feature_random_seed: int
    feature_model_fit_observation_count: int
    feature_predictions: Sequence[RulPredictionSeries]
    feature_evaluation: RulPointEvaluation

    def __post_init__(self) -> None:
        _validate_code_revision(self.code_revision)
        for field_name in (
            "source_acquisition_count",
            "train_source_acquisition_count",
            "validation_source_acquisition_count",
            "feature_preprocessing_fit_observation_count",
            "feature_model_fit_observation_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise XjtuRulBaselineValidationResultError(
                    f"{field_name} must be a positive integer"
                )

        expected_text = {
            "dataset_id": "xjtu-sy",
            "split_id": "xjtu-sy-condition-stratified-5fold-v1",
            "fold_id": "fold-1",
            "target_definition_id": XJTU_RUL_TARGET_DEFINITION_ID,
            "target_unit": XJTU_RUL_TARGET_UNIT,
            "feature_fit_partition": "train",
            "feature_scaling_strategy": "robust",
            "feature_reference_strategy": "all-train-observations",
            "feature_sampling_policy_id": "bearing-balanced-resample-v1",
            "feature_model_family": "ridge-regression",
        }
        for field_name, expected in expected_text.items():
            if getattr(self, field_name) != expected:
                raise XjtuRulBaselineValidationResultError(
                    f"{field_name} must equal {expected!r}"
                )

        age_train_asset_ids = tuple(self.age_train_asset_ids)
        age_endpoints = tuple(float(value) for value in self.age_train_endpoint_acquisitions)
        selected_features = tuple(self.selected_features)
        fitted_center = tuple(float(value) for value in self.feature_fitted_center)
        fitted_scale = tuple(float(value) for value in self.feature_fitted_scale)
        zero_iqr_features = tuple(self.feature_zero_iqr_features)
        model_parameters = tuple(self.feature_model_parameters)
        age_predictions = tuple(self.age_predictions)
        feature_predictions = tuple(self.feature_predictions)

        fold = get_xjtu_reference_split().folds[0]
        if age_train_asset_ids != fold.train:
            raise XjtuRulBaselineValidationResultError(
                "age baseline train assets must match the configured fold-1 train order"
            )
        if len(age_endpoints) != len(age_train_asset_ids):
            raise XjtuRulBaselineValidationResultError(
                "age baseline endpoint values must align one-to-one with train assets"
            )
        if self.age_fitted_mean_endpoint_acquisition <= 0.0:
            raise XjtuRulBaselineValidationResultError(
                "age_fitted_mean_endpoint_acquisition must be positive"
            )

        if not selected_features:
            raise XjtuRulBaselineValidationResultError(
                "selected_features must contain at least one feature"
            )
        if len(fitted_center) != len(selected_features) or len(fitted_scale) != len(
            selected_features
        ):
            raise XjtuRulBaselineValidationResultError(
                "feature preprocessing state must align with selected_features"
            )
        if any(scale <= 0.0 for scale in fitted_scale):
            raise XjtuRulBaselineValidationResultError(
                "feature fitted_scale values must be positive"
            )
        if set(zero_iqr_features) - set(selected_features):
            raise XjtuRulBaselineValidationResultError(
                "feature_zero_iqr_features contains unknown features"
            )
        if dict(model_parameters) != {
            "alpha": 1.0,
            "fit_intercept": True,
            "solver": "svd",
        }:
            raise XjtuRulBaselineValidationResultError(
                "feature model parameters must match the frozen protocol"
            )
        if self.feature_random_seed != 42:
            raise XjtuRulBaselineValidationResultError(
                "feature_random_seed must match the frozen protocol"
            )

        _validate_prediction_evaluation_pair(
            age_predictions,
            self.age_evaluation,
            method_id=XJTU_AGE_ONLY_RUL_METHOD_ID,
        )
        _validate_prediction_evaluation_pair(
            feature_predictions,
            self.feature_evaluation,
            method_id=XJTU_FEATURE_RIDGE_RUL_METHOD_ID,
        )

        if self.train_source_acquisition_count != 3_246:
            raise XjtuRulBaselineValidationResultError(
                "train_source_acquisition_count must match the fold-1 train population"
            )
        if self.validation_source_acquisition_count != 2_818:
            raise XjtuRulBaselineValidationResultError(
                "validation_source_acquisition_count must match the fold-1 validation population"
            )

        object.__setattr__(self, "age_train_asset_ids", age_train_asset_ids)
        object.__setattr__(self, "age_train_endpoint_acquisitions", age_endpoints)
        object.__setattr__(self, "selected_features", selected_features)
        object.__setattr__(self, "feature_fitted_center", fitted_center)
        object.__setattr__(self, "feature_fitted_scale", fitted_scale)
        object.__setattr__(self, "feature_zero_iqr_features", zero_iqr_features)
        object.__setattr__(self, "feature_model_parameters", model_parameters)
        object.__setattr__(self, "age_predictions", age_predictions)
        object.__setattr__(self, "feature_predictions", feature_predictions)


def run_xjtu_rul_baseline_validation(
    source: Path,
    output_path: Path,
    *,
    code_revision: str,
) -> XjtuRulBaselineValidationResult:
    """Run frozen age-only and feature-Ridge baselines on fold-1 validation only."""
    _validate_code_revision(code_revision)
    source_report = validate_xjtu_source(source)
    if not source_report.profile_matches:
        raise XjtuRulBaselineValidationResultError(
            "XJTU-SY source does not match the observed complete profile: "
            + "; ".join(source_report.profile_issues)
        )

    fold = get_xjtu_reference_split().folds[0]
    adapter = XjtuSyAdapter()
    train_vectors = tuple(iter_vibration_features(adapter.iter_asset_series(source, fold.train)))
    validation_vectors = tuple(
        iter_vibration_features(adapter.iter_asset_series(source, fold.validation))
    )
    train_targets = build_xjtu_recorded_end_rul_targets(
        train_vectors,
        partition="train",
    )
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

    result = build_xjtu_rul_baseline_validation_result(
        age_fitted,
        age_predictions,
        age_evaluation,
        feature_fitted,
        feature_predictions,
        feature_evaluation,
        code_revision=code_revision,
        source_acquisition_count=source_report.acquisition_count,
    )
    write_xjtu_rul_baseline_validation_result(result, output_path)
    return result


def build_xjtu_rul_baseline_validation_result(
    age_fitted: XjtuAgeOnlyRulBaseline,
    age_predictions: Sequence[RulPredictionSeries],
    age_evaluation: RulPointEvaluation,
    feature_fitted: XjtuFeatureRulBaselineFit,
    feature_predictions: Sequence[RulPredictionSeries],
    feature_evaluation: RulPointEvaluation,
    *,
    code_revision: str,
    source_acquisition_count: int,
) -> XjtuRulBaselineValidationResult:
    """Resolve immutable evidence from already completed fit, prediction, and evaluation."""
    _validate_code_revision(code_revision)
    if not isinstance(age_fitted, XjtuAgeOnlyRulBaseline):
        raise XjtuRulBaselineValidationResultError(
            "age_fitted must be an XjtuAgeOnlyRulBaseline"
        )
    if not isinstance(feature_fitted, XjtuFeatureRulBaselineFit):
        raise XjtuRulBaselineValidationResultError(
            "feature_fitted must be an XjtuFeatureRulBaselineFit"
        )

    config = feature_fitted.config
    state = feature_fitted.preprocessing_state
    model = feature_fitted.model
    return XjtuRulBaselineValidationResult(
        code_revision=code_revision,
        source_acquisition_count=source_acquisition_count,
        dataset_id=config.dataset_id,
        split_id=config.split_id,
        fold_id=config.fold_id,
        target_definition_id=XJTU_RUL_TARGET_DEFINITION_ID,
        target_unit=XJTU_RUL_TARGET_UNIT,
        train_source_acquisition_count=state.observation_count,
        validation_source_acquisition_count=sum(
            len(series.observations) for series in feature_predictions
        ),
        age_train_asset_ids=tuple(age_fitted.train_asset_ids),
        age_train_endpoint_acquisitions=tuple(age_fitted.train_endpoint_acquisitions),
        age_fitted_mean_endpoint_acquisition=age_fitted.fitted_mean_endpoint_acquisition,
        age_predictions=tuple(age_predictions),
        age_evaluation=age_evaluation,
        feature_set_id=config.feature_set_id,
        selected_features=tuple(config.selected_features),
        feature_fit_partition=config.fit_partition.value,
        feature_scaling_strategy=config.scaling_strategy.value,
        feature_preprocessing_fit_observation_count=state.observation_count,
        feature_fitted_center=tuple(state.fitted_center),
        feature_fitted_scale=tuple(state.fitted_scale),
        feature_zero_iqr_features=tuple(state.zero_iqr_features),
        feature_reference_strategy=config.reference_strategy.value,
        feature_sampling_policy_id=config.sampling_policy_id,
        feature_model_family=config.model_family.value,
        feature_model_parameters=tuple(sorted(config.model_parameters.items())),
        feature_random_seed=config.random_seed,
        feature_model_fit_observation_count=model.fit_observation_count,
        feature_predictions=tuple(feature_predictions),
        feature_evaluation=feature_evaluation,
    )


def write_xjtu_rul_baseline_validation_result(
    result: XjtuRulBaselineValidationResult,
    output_path: Path,
) -> None:
    """Write deterministic JSON for protocol-frozen retrospective validation evidence."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_result_document(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _result_document(result: XjtuRulBaselineValidationResult) -> dict[str, Any]:
    fold = get_xjtu_reference_split().folds[0]
    return {
        "schema_id": XJTU_RUL_BASELINE_VALIDATION_RESULT_SCHEMA_ID,
        "provenance": {
            "code_revision": result.code_revision,
            "protocol_id": XJTU_RUL_PROTOCOL_ID,
            "dataset_id": result.dataset_id,
            "split_id": result.split_id,
            "fold_id": result.fold_id,
            "evidence_class": XJTU_RUL_BASELINE_VALIDATION_EVIDENCE_CLASS,
        },
        "source_scope": {
            "verified_source_acquisition_count": result.source_acquisition_count,
            "train_bearings": list(fold.train),
            "validation_bearings": list(fold.validation),
            "excluded": [f"test:{asset_id}" for asset_id in fold.test],
        },
        "target": {
            "definition_id": result.target_definition_id,
            "unit": result.target_unit,
            "endpoint_semantics": "last-recorded-acquisition",
            "formula": "N-k",
            "prediction_alignment": "acquisition",
            "target_clipping": False,
            "target_normalization": False,
        },
        "methods": [
            {
                "method_id": XJTU_AGE_ONLY_RUL_METHOD_ID,
                "kind": "age-only-baseline",
                "fit": {
                    "train_assets": list(result.age_train_asset_ids),
                    "train_endpoint_acquisitions": list(
                        result.age_train_endpoint_acquisitions
                    ),
                    "fitted_mean_endpoint_acquisition": (
                        result.age_fitted_mean_endpoint_acquisition
                    ),
                },
                "evaluation": _evaluation_document(result.age_evaluation),
                "predictions": _prediction_documents(result.age_predictions),
            },
            {
                "method_id": XJTU_FEATURE_RIDGE_RUL_METHOD_ID,
                "kind": "current-acquisition-feature-ridge-baseline",
                "feature_schema": {
                    "feature_set_id": result.feature_set_id,
                    "selected_features": list(result.selected_features),
                    "selected_feature_count": len(result.selected_features),
                },
                "preprocessing": {
                    "fit_partition": result.feature_fit_partition,
                    "scaling_strategy": result.feature_scaling_strategy,
                    "fit_observation_count": (
                        result.feature_preprocessing_fit_observation_count
                    ),
                    "fitted_center": list(result.feature_fitted_center),
                    "fitted_scale": list(result.feature_fitted_scale),
                    "zero_iqr_features": list(result.feature_zero_iqr_features),
                },
                "model": {
                    "family": result.feature_model_family,
                    "parameters": dict(result.feature_model_parameters),
                    "random_seed": result.feature_random_seed,
                    "reference_strategy": result.feature_reference_strategy,
                    "sampling_policy_id": result.feature_sampling_policy_id,
                    "fit_observation_count": result.feature_model_fit_observation_count,
                },
                "evaluation": _evaluation_document(result.feature_evaluation),
                "predictions": _prediction_documents(result.feature_predictions),
            },
        ],
        "comparison": {
            "feature_minus_age_mean_asset_mae": (
                result.feature_evaluation.mean_asset_mean_absolute_error
                - result.age_evaluation.mean_asset_mean_absolute_error
            ),
            "feature_minus_age_mean_asset_rmse": (
                result.feature_evaluation.mean_asset_root_mean_squared_error
                - result.age_evaluation.mean_asset_root_mean_squared_error
            ),
            "feature_minus_age_mean_asset_normalized_mae": (
                _required_normalized_mae(result.feature_evaluation)
                - _required_normalized_mae(result.age_evaluation)
            ),
        },
        "capability_scope": {
            "available": list(_AVAILABLE_CAPABILITIES),
            "unsupported_or_not_validated": list(_UNSUPPORTED_CAPABILITIES),
        },
        "interpretation": (
            "Protocol-frozen retrospective development evidence on the fold-1 validation "
            "bearing runs. It compares an age-only baseline with a current-acquisition "
            "sensor-feature Ridge baseline using the same recorded-end RUL target and "
            "bearing-first evaluator. Test bearings are excluded, no prediction interval is "
            "claimed, and this result is not field or physical-failure-threshold validation."
        ),
    }


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


def _validate_prediction_evaluation_pair(
    predictions: Sequence[RulPredictionSeries],
    evaluation: RulPointEvaluation,
    *,
    method_id: str,
) -> None:
    if not isinstance(evaluation, RulPointEvaluation):
        raise XjtuRulBaselineValidationResultError(
            "evaluation must be a RulPointEvaluation"
        )
    if evaluation.prediction_method_id != method_id:
        raise XjtuRulBaselineValidationResultError(
            f"evaluation prediction_method_id must equal {method_id!r}"
        )
    if evaluation.target_definition_id != XJTU_RUL_TARGET_DEFINITION_ID:
        raise XjtuRulBaselineValidationResultError(
            "evaluation target definition must match the XJTU RUL protocol"
        )
    if evaluation.unit != XJTU_RUL_TARGET_UNIT:
        raise XjtuRulBaselineValidationResultError(
            "evaluation unit must match the XJTU RUL protocol"
        )

    prediction_series = tuple(predictions)
    fold = get_xjtu_reference_split().folds[0]
    if tuple(series.asset_id for series in prediction_series) != fold.validation:
        raise XjtuRulBaselineValidationResultError(
            "prediction bearing order must match fold-1 validation"
        )
    if any(series.partition_id != "validation" for series in prediction_series):
        raise XjtuRulBaselineValidationResultError(
            "RUL baseline evidence may only contain validation predictions"
        )
    if any(series.prediction_method_id != method_id for series in prediction_series):
        raise XjtuRulBaselineValidationResultError(
            f"all predictions must use method {method_id!r}"
        )

    evaluation_assets = tuple(item.asset_id for item in evaluation.asset_results)
    if evaluation_assets != tuple(sorted(fold.validation)):
        raise XjtuRulBaselineValidationResultError(
            "evaluation bearing population must match fold-1 validation"
        )
    for series in prediction_series:
        expected_count = get_xjtu_expected_acquisition_count(series.asset_id)
        if len(series.observations) != expected_count:
            raise XjtuRulBaselineValidationResultError(
                f"validation predictions for {series.asset_id} must contain "
                f"{expected_count} acquisitions"
            )
        expected_ids = tuple(
            f"{series.asset_id}:acquisition-{index}"
            for index in range(1, expected_count + 1)
        )
        observed_ids = tuple(
            observation.source_observation_id for observation in series.observations
        )
        if observed_ids != expected_ids:
            raise XjtuRulBaselineValidationResultError(
                f"validation predictions for {series.asset_id} must preserve "
                "complete acquisition order"
            )


def _required_normalized_mae(evaluation: RulPointEvaluation) -> float:
    value = evaluation.mean_asset_normalized_mean_absolute_error
    if value is None:
        raise XjtuRulBaselineValidationResultError(
            "XJTU RUL validation evidence requires normalized MAE"
        )
    return value


def _acquisition_index(asset_id: str, source_observation_id: str) -> int:
    prefix = f"{asset_id}:acquisition-"
    if not source_observation_id.startswith(prefix):
        raise XjtuRulBaselineValidationResultError(
            "prediction source identity does not match its bearing"
        )
    suffix = source_observation_id.removeprefix(prefix)
    if not suffix.isdigit() or int(suffix) <= 0:
        raise XjtuRulBaselineValidationResultError(
            "prediction source identity must end in a positive acquisition index"
        )
    return int(suffix)


def _validate_code_revision(value: str) -> None:
    if not _FULL_GIT_REVISION.fullmatch(value):
        raise XjtuRulBaselineValidationResultError(
            "code_revision must be a full 40-character lowercase Git commit SHA"
        )
