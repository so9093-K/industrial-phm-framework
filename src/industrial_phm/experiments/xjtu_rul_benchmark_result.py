"""Frozen XJTU RUL v1 held-out benchmark evidence for the validation-selected LSTM."""

from __future__ import annotations

import json
import math
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
from industrial_phm.experiments.xjtu_rul_evaluation import (
    XjtuRulLifecyclePositionEvaluation,
    evaluate_xjtu_rul_lifecycle_position_errors,
    evaluate_xjtu_rul_point_predictions,
)
from industrial_phm.experiments.xjtu_rul_lstm import (
    XJTU_RUL_LSTM_METHOD_ID,
    XjtuRulLstmFit,
    fit_xjtu_rul_lstm_model,
    get_xjtu_rul_lstm_configuration,
    predict_xjtu_rul_lstm,
)
from industrial_phm.features import iter_vibration_features
from industrial_phm.prognostics import RulPointEvaluation, RulPredictionSeries

XJTU_RUL_LSTM_BENCHMARK_RESULT_SCHEMA_ID = "xjtu-rul-lstm-fold-1-benchmark-result-v1"
XJTU_RUL_LSTM_BENCHMARK_EVIDENCE_CLASS = "protocol-frozen-retrospective-benchmark-evidence"
_FULL_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")
XJTU_RUL_LSTM_BENCHMARK_AVAILABLE_CAPABILITIES = (
    "prognostics-rul-point-estimate",
    "retrospective-benchmark-error-evidence",
    "lifecycle-position-diagnostics",
)
XJTU_RUL_LSTM_BENCHMARK_UNSUPPORTED_CAPABILITIES = (
    "prediction-interval",
    "uncertainty-calibration",
    "validated-physical-failure-threshold",
    "field-rul-validation",
    "maintenance-decision-recommendation",
)


class XjtuRulLstmBenchmarkResultError(ValueError):
    """Raised when frozen RUL benchmark evidence violates its contract."""


@dataclass(frozen=True, slots=True)
class XjtuRulLstmBenchmarkResult:
    """Serializable point and lifecycle-position evidence for the frozen benchmark."""

    code_revision: str
    source_acquisition_count: int
    dataset_id: str
    split_id: str
    fold_id: str
    train_source_acquisition_count: int
    benchmark_source_acquisition_count: int
    feature_set_id: str
    selected_features: Sequence[str]
    preprocessing_fit_partition: str
    scaling_strategy: str
    preprocessing_fit_observation_count: int
    fitted_center: Sequence[float]
    fitted_scale: Sequence[float]
    zero_iqr_features: Sequence[str]
    sequence_length: int
    sequence_stride: int
    sequence_alignment: str
    train_window_count: int
    model_family: str
    model_parameters: Sequence[tuple[str, ExperimentParameter]]
    random_seed: int
    sampling_policy_id: str
    runtime: str
    runtime_version: str
    device: str
    numeric_precision: str
    deterministic_algorithms: bool
    parameter_count: int
    batch_size: int
    epochs: int
    epoch_losses: Sequence[float]
    predictions: Sequence[RulPredictionSeries]
    point_evaluation: RulPointEvaluation
    lifecycle_evaluation: XjtuRulLifecyclePositionEvaluation

    def __post_init__(self) -> None:
        _validate_code_revision(self.code_revision)
        config = get_xjtu_rul_lstm_configuration()
        fold = get_xjtu_reference_split().folds[0]
        expected_text = (
            ("dataset_id", self.dataset_id, config.dataset_id),
            ("split_id", self.split_id, config.split_id),
            ("fold_id", self.fold_id, config.fold_id),
            ("feature_set_id", self.feature_set_id, config.feature_set_id),
            ("preprocessing_fit_partition", self.preprocessing_fit_partition, "train"),
            ("scaling_strategy", self.scaling_strategy, "robust"),
            ("sequence_alignment", self.sequence_alignment, "right-edge"),
            ("model_family", self.model_family, "lstm-regression"),
            ("sampling_policy_id", self.sampling_policy_id, "sequence-window-uniform-v1"),
            ("device", self.device, "cpu"),
            ("numeric_precision", self.numeric_precision, "float32"),
        )
        for field_name, observed, expected in expected_text:
            if observed != expected:
                raise XjtuRulLstmBenchmarkResultError(
                    f"{field_name} must equal {expected!r}, got {observed!r}"
                )
        if tuple(self.selected_features) != tuple(config.selected_features):
            raise XjtuRulLstmBenchmarkResultError(
                "selected_features must match the frozen LSTM configuration"
            )
        if self.sequence_length != 8 or self.sequence_stride != 1:
            raise XjtuRulLstmBenchmarkResultError(
                "sequence contract must remain length 8 / stride 1"
            )
        if self.random_seed != 42:
            raise XjtuRulLstmBenchmarkResultError("random_seed must remain 42")
        if not self.deterministic_algorithms:
            raise XjtuRulLstmBenchmarkResultError("deterministic_algorithms must remain true")
        if any(not math.isfinite(float(loss)) or float(loss) < 0.0 for loss in self.epoch_losses):
            raise XjtuRulLstmBenchmarkResultError("epoch_losses must be finite and non-negative")

        predictions = tuple(self.predictions)
        if tuple(series.asset_id for series in predictions) != fold.test:
            raise XjtuRulLstmBenchmarkResultError(
                "benchmark predictions must preserve fold-1 test bearing order"
            )
        for series in predictions:
            if series.partition_id != "test":
                raise XjtuRulLstmBenchmarkResultError(
                    "benchmark predictions must use test partition"
                )
            if series.prediction_method_id != XJTU_RUL_LSTM_METHOD_ID:
                raise XjtuRulLstmBenchmarkResultError(
                    "benchmark predictions must use the validation-selected LSTM"
                )
            run_length = get_xjtu_expected_acquisition_count(series.asset_id)
            expected_ids = tuple(
                f"{series.asset_id}:acquisition-{index}"
                for index in range(self.sequence_length, run_length + 1)
            )
            observed_ids = tuple(
                observation.source_observation_id for observation in series.observations
            )
            if observed_ids != expected_ids:
                raise XjtuRulLstmBenchmarkResultError(
                    f"{series.asset_id} benchmark predictions must preserve acquisition 8..N"
                )

        expected_assets = tuple(sorted(fold.test))
        if tuple(item.asset_id for item in self.point_evaluation.asset_results) != expected_assets:
            raise XjtuRulLstmBenchmarkResultError(
                "point evaluation must contain the configured benchmark bearings"
            )
        if self.point_evaluation.prediction_method_id != XJTU_RUL_LSTM_METHOD_ID:
            raise XjtuRulLstmBenchmarkResultError(
                "point evaluation method must match the validation-selected LSTM"
            )
        if self.lifecycle_evaluation.prediction_method_id != XJTU_RUL_LSTM_METHOD_ID:
            raise XjtuRulLstmBenchmarkResultError(
                "lifecycle evaluation method must match the validation-selected LSTM"
            )
        lifecycle_assets = tuple(
            sorted({item.asset_id for item in self.lifecycle_evaluation.asset_results})
        )
        if lifecycle_assets != expected_assets:
            raise XjtuRulLstmBenchmarkResultError(
                "lifecycle evaluation must contain the configured benchmark bearings"
            )

        object.__setattr__(self, "selected_features", tuple(self.selected_features))
        object.__setattr__(
            self,
            "fitted_center",
            tuple(float(value) for value in self.fitted_center),
        )
        object.__setattr__(
            self,
            "fitted_scale",
            tuple(float(value) for value in self.fitted_scale),
        )
        object.__setattr__(self, "zero_iqr_features", tuple(self.zero_iqr_features))
        object.__setattr__(self, "model_parameters", tuple(self.model_parameters))
        object.__setattr__(self, "epoch_losses", tuple(float(value) for value in self.epoch_losses))
        object.__setattr__(self, "predictions", predictions)


def run_xjtu_rul_lstm_heldout_benchmark(
    source: Path,
    output_path: Path,
    *,
    code_revision: str,
) -> XjtuRulLstmBenchmarkResult:
    """Run the frozen validation-selected LSTM once on fold-1 held-out benchmark bearings."""
    _validate_code_revision(code_revision)
    source_report = validate_xjtu_source(source)
    if not source_report.profile_matches:
        raise XjtuRulLstmBenchmarkResultError(
            "XJTU-SY source does not match the observed complete profile: "
            + "; ".join(source_report.profile_issues)
        )

    fold = get_xjtu_reference_split().folds[0]
    adapter = XjtuSyAdapter()
    train_vectors = tuple(iter_vibration_features(adapter.iter_asset_series(source, fold.train)))
    benchmark_vectors = tuple(iter_vibration_features(adapter.iter_asset_series(source, fold.test)))
    train_targets = build_xjtu_recorded_end_rul_targets(train_vectors, partition="train")
    benchmark_targets = build_xjtu_recorded_end_rul_targets(benchmark_vectors, partition="test")

    fitted = fit_xjtu_rul_lstm_model(train_vectors, train_targets)
    predictions = predict_xjtu_rul_lstm(fitted, benchmark_vectors, partition="test")
    point_evaluation = evaluate_xjtu_rul_point_predictions(
        benchmark_targets,
        predictions,
        partition="test",
    )
    lifecycle_evaluation = evaluate_xjtu_rul_lifecycle_position_errors(
        benchmark_targets,
        predictions,
        partition="test",
    )
    result = build_xjtu_rul_lstm_benchmark_result(
        fitted,
        predictions,
        point_evaluation,
        lifecycle_evaluation,
        code_revision=code_revision,
        source_acquisition_count=source_report.acquisition_count,
        benchmark_source_acquisition_count=len(benchmark_vectors),
    )
    write_xjtu_rul_lstm_benchmark_result(result, output_path)
    return result


def build_xjtu_rul_lstm_benchmark_result(
    fitted: XjtuRulLstmFit,
    predictions: Sequence[RulPredictionSeries],
    point_evaluation: RulPointEvaluation,
    lifecycle_evaluation: XjtuRulLifecyclePositionEvaluation,
    *,
    code_revision: str,
    source_acquisition_count: int,
    benchmark_source_acquisition_count: int,
) -> XjtuRulLstmBenchmarkResult:
    """Build immutable benchmark evidence from one frozen execution."""
    if not isinstance(fitted, XjtuRulLstmFit):
        raise XjtuRulLstmBenchmarkResultError("fitted must be an XjtuRulLstmFit")
    config = fitted.config
    state = fitted.preprocessing_state
    sequence = fitted.train_sequence
    training = fitted.model.training
    return XjtuRulLstmBenchmarkResult(
        code_revision=code_revision,
        source_acquisition_count=source_acquisition_count,
        dataset_id=config.dataset_id,
        split_id=config.split_id,
        fold_id=config.fold_id,
        train_source_acquisition_count=sequence.source_observation_count,
        benchmark_source_acquisition_count=benchmark_source_acquisition_count,
        feature_set_id=config.feature_set_id,
        selected_features=tuple(config.selected_features),
        preprocessing_fit_partition=config.fit_partition.value,
        scaling_strategy=config.scaling_strategy.value,
        preprocessing_fit_observation_count=state.observation_count,
        fitted_center=tuple(state.fitted_center),
        fitted_scale=tuple(state.fitted_scale),
        zero_iqr_features=tuple(state.zero_iqr_features),
        sequence_length=sequence.spec.length,
        sequence_stride=sequence.spec.stride,
        sequence_alignment=sequence.spec.alignment.value,
        train_window_count=sequence.window_count,
        model_family=config.model_family.value,
        model_parameters=tuple(sorted(config.model_parameters.items())),
        random_seed=config.random_seed,
        sampling_policy_id=config.sampling_policy_id,
        runtime=training.runtime,
        runtime_version=training.runtime_version,
        device=training.device,
        numeric_precision=training.numeric_precision,
        deterministic_algorithms=training.deterministic_algorithms,
        parameter_count=training.parameter_count,
        batch_size=training.batch_size,
        epochs=training.epochs,
        epoch_losses=tuple(training.epoch_losses),
        predictions=tuple(predictions),
        point_evaluation=point_evaluation,
        lifecycle_evaluation=lifecycle_evaluation,
    )


def write_xjtu_rul_lstm_benchmark_result(
    result: XjtuRulLstmBenchmarkResult,
    output_path: Path,
) -> None:
    """Write deterministic JSON for the frozen held-out benchmark."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            xjtu_rul_lstm_benchmark_document(result),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def xjtu_rul_lstm_benchmark_document(result: XjtuRulLstmBenchmarkResult) -> dict[str, Any]:
    """Return the benchmark artifact without changing any recorded numerical evidence."""
    fold = get_xjtu_reference_split().folds[0]
    return {
        "schema_id": XJTU_RUL_LSTM_BENCHMARK_RESULT_SCHEMA_ID,
        "provenance": {
            "code_revision": result.code_revision,
            "protocol_id": XJTU_RUL_PROTOCOL_ID,
            "dataset_id": result.dataset_id,
            "split_id": result.split_id,
            "fold_id": result.fold_id,
            "evidence_class": XJTU_RUL_LSTM_BENCHMARK_EVIDENCE_CLASS,
        },
        "source_scope": {
            "verified_source_acquisition_count": result.source_acquisition_count,
            "train_bearings": list(fold.train),
            "benchmark_bearings": list(fold.test),
            "train_source_acquisition_count": result.train_source_acquisition_count,
            "benchmark_source_acquisition_count": result.benchmark_source_acquisition_count,
            "project_history_limitation": (
                "fold-1 test bearings were previously observed by project anomaly/robustness work; "
                "this is not a pristine external holdout"
            ),
        },
        "selection": {
            "validation_selected_method_id": XJTU_RUL_LSTM_METHOD_ID,
            "operational_primary_method_id": None,
            "selection_rule": "fold-1-validation-equal-bearing-mean-mae",
        },
        "target": {
            "definition_id": XJTU_RUL_TARGET_DEFINITION_ID,
            "unit": XJTU_RUL_TARGET_UNIT,
            "endpoint_semantics": "last-recorded-acquisition",
            "formula": "N-k",
            "prediction_alignment": "right-edge-acquisition",
            "target_clipping": False,
            "target_normalization": False,
        },
        "method": {
            "method_id": XJTU_RUL_LSTM_METHOD_ID,
            "kind": "temporal-sequence-lstm-regression",
            "feature_schema": {
                "feature_set_id": result.feature_set_id,
                "selected_features": list(result.selected_features),
                "selected_feature_count": len(result.selected_features),
            },
            "preprocessing": {
                "fit_partition": result.preprocessing_fit_partition,
                "scaling_strategy": result.scaling_strategy,
                "fit_observation_count": result.preprocessing_fit_observation_count,
                "fitted_center": list(result.fitted_center),
                "fitted_scale": list(result.fitted_scale),
                "zero_iqr_features": list(result.zero_iqr_features),
            },
            "sequence": {
                "length": result.sequence_length,
                "stride": result.sequence_stride,
                "alignment": result.sequence_alignment,
                "train_window_count": result.train_window_count,
                "benchmark_dropped_prefix_per_bearing": result.sequence_length - 1,
            },
            "model": {
                "family": result.model_family,
                "parameters": dict(result.model_parameters),
                "random_seed": result.random_seed,
                "sampling_policy_id": result.sampling_policy_id,
                "runtime": result.runtime,
                "runtime_version": result.runtime_version,
                "device": result.device,
                "numeric_precision": result.numeric_precision,
                "deterministic_algorithms": result.deterministic_algorithms,
                "parameter_count": result.parameter_count,
                "batch_size": result.batch_size,
                "epochs": result.epochs,
                "epoch_losses": list(result.epoch_losses),
            },
            "predictions": _prediction_documents(result.predictions),
        },
        "evaluation": {
            "point": _point_evaluation_document(result.point_evaluation),
            "lifecycle_position": _lifecycle_evaluation_document(result.lifecycle_evaluation),
        },
        "capability_scope": {
            "available": list(XJTU_RUL_LSTM_BENCHMARK_AVAILABLE_CAPABILITIES),
            "unsupported_or_not_validated": list(
                XJTU_RUL_LSTM_BENCHMARK_UNSUPPORTED_CAPABILITIES
            ),
        },
        "interpretation": (
            "Protocol-frozen retrospective benchmark evidence for the validation-selected "
            "temporal LSTM. The target remains acquisition intervals until the last recorded "
            "acquisition, not validated physical failure time. Prediction intervals remain "
            "unsupported in RUL v1, and no operational primary method or maintenance decision "
            "is created by this benchmark."
        ),
    }


def _point_evaluation_document(evaluation: RulPointEvaluation) -> dict[str, Any]:
    return {
        "aggregation": "equal-bearing-mean",
        "prediction_method_id": evaluation.prediction_method_id,
        "target_definition_id": evaluation.target_definition_id,
        "unit": evaluation.unit,
        "mean_asset_mean_absolute_error": evaluation.mean_asset_mean_absolute_error,
        "mean_asset_root_mean_squared_error": evaluation.mean_asset_root_mean_squared_error,
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


def _lifecycle_evaluation_document(
    evaluation: XjtuRulLifecyclePositionEvaluation,
) -> dict[str, Any]:
    return {
        "boundary": {
            "early": "1..ceil(N/3)",
            "middle": "ceil(N/3)+1..ceil(2N/3)",
            "late": "ceil(2N/3)+1..N",
            "semantics": "retrospective-evaluation-only",
        },
        "prediction_method_id": evaluation.prediction_method_id,
        "target_definition_id": evaluation.target_definition_id,
        "unit": evaluation.unit,
        "aggregation": "equal-bearing-mean-within-lifecycle-position",
        "bearing_positions": [
            {
                "asset_id": item.asset_id,
                "partition_id": item.partition_id,
                "position": item.position,
                "prediction_count": item.prediction_count,
                "mean_absolute_error": item.mean_absolute_error,
                "root_mean_squared_error": item.root_mean_squared_error,
                "mean_signed_error": item.mean_signed_error,
                "normalized_mean_absolute_error": item.normalized_mean_absolute_error,
            }
            for item in evaluation.asset_results
        ],
        "position_summaries": [
            {
                "position": item.position,
                "bearing_count": item.bearing_count,
                "mean_asset_mean_absolute_error": item.mean_asset_mean_absolute_error,
                "mean_asset_root_mean_squared_error": item.mean_asset_root_mean_squared_error,
                "mean_asset_mean_signed_error": item.mean_asset_mean_signed_error,
                "mean_asset_normalized_mean_absolute_error": (
                    item.mean_asset_normalized_mean_absolute_error
                ),
            }
            for item in evaluation.position_summaries
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


def _acquisition_index(asset_id: str, source_observation_id: str) -> int:
    prefix = f"{asset_id}:acquisition-"
    if not source_observation_id.startswith(prefix):
        raise XjtuRulLstmBenchmarkResultError(
            "prediction source identity does not match its bearing"
        )
    suffix = source_observation_id.removeprefix(prefix)
    if not suffix.isdigit() or int(suffix) <= 0:
        raise XjtuRulLstmBenchmarkResultError(
            "prediction source identity must end in a positive acquisition index"
        )
    return int(suffix)


def _validate_code_revision(value: str) -> None:
    if not _FULL_GIT_REVISION.fullmatch(value):
        raise XjtuRulLstmBenchmarkResultError(
            "code_revision must be a full 40-character lowercase Git commit SHA"
        )
