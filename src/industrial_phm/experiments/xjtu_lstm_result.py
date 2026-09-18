"""One-shot XJTU LSTM retrospective development result and execution contract."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from industrial_phm.adapters import XjtuSyAdapter, validate_xjtu_source
from industrial_phm.experiments.config import ExperimentParameter
from industrial_phm.experiments.xjtu import get_xjtu_reference_split
from industrial_phm.experiments.xjtu_lstm import (
    XjtuLstmDevelopmentFit,
    fit_xjtu_lstm_development_model,
    score_xjtu_lstm_development_validation,
)
from industrial_phm.experiments.xjtu_lstm_evaluation import (
    XjtuLstmDevelopmentEvaluation,
    evaluate_xjtu_lstm_development_scores,
)
from industrial_phm.features import iter_vibration_features
from industrial_phm.models import (
    LstmAutoencoderTrainingProvenance,
    ReconstructionScores,
)
from industrial_phm.preprocessing import PreprocessingState

XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID = "xjtu-lstm-development-result-v1"
XJTU_LSTM_DEVELOPMENT_EVIDENCE_CLASS = "retrospective-development-evidence"

_FULL_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")
_SCORE_DIRECTION = "higher-is-more-anomalous"
_AVAILABLE_CAPABILITIES = (
    "anomaly-scoring",
    "descriptive-score-trajectory-evaluation",
    "reconstruction-residual-evidence",
)
_UNSUPPORTED_CAPABILITIES = (
    "thresholded-state-detection",
    "health-assessment",
    "fault-diagnostics",
    "prognostics-rul",
)


class XjtuLstmDevelopmentResultError(ValueError):
    """Raised when the frozen LSTM development result contract is violated."""


@dataclass(frozen=True, slots=True)
class XjtuLstmDevelopmentResult:
    """Serializable retrospective evidence for the frozen fold-1 LSTM protocol."""

    code_revision: str
    source_acquisition_count: int
    experiment_id: str
    dataset_id: str
    split_id: str
    fold_id: str
    feature_set_id: str
    selected_features: tuple[str, ...]
    fit_partition: str
    scaling_strategy: str
    preprocessing_fit_observation_count: int
    fitted_center: tuple[float, ...]
    fitted_scale: tuple[float, ...]
    zero_iqr_features: tuple[str, ...]
    reference_strategy: str
    sampling_policy_id: str
    reference_source_acquisition_count: int
    reference_window_count: int
    reference_dropped_prefix_count: int
    validation_source_acquisition_count: int
    validation_window_count: int
    validation_dropped_prefix_count: int
    sequence_length: int
    sequence_stride: int
    sequence_alignment: str
    model_family: str
    model_parameters: tuple[tuple[str, ExperimentParameter], ...]
    random_seed: int
    training: LstmAutoencoderTrainingProvenance
    score_semantics_id: str
    evaluation: XjtuLstmDevelopmentEvaluation

    def __post_init__(self) -> None:
        _validate_code_revision(self.code_revision)
        for field_name in (
            "source_acquisition_count",
            "preprocessing_fit_observation_count",
            "reference_source_acquisition_count",
            "reference_window_count",
            "validation_source_acquisition_count",
            "validation_window_count",
            "sequence_length",
            "sequence_stride",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise XjtuLstmDevelopmentResultError(f"{field_name} must be a positive integer")
        for field_name in (
            "reference_dropped_prefix_count",
            "validation_dropped_prefix_count",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise XjtuLstmDevelopmentResultError(f"{field_name} must be a non-negative integer")
        if not isinstance(self.training, LstmAutoencoderTrainingProvenance):
            raise XjtuLstmDevelopmentResultError(
                "training must be LstmAutoencoderTrainingProvenance"
            )
        if not isinstance(self.evaluation, XjtuLstmDevelopmentEvaluation):
            raise XjtuLstmDevelopmentResultError("evaluation must be XjtuLstmDevelopmentEvaluation")


def run_xjtu_lstm_development_evaluation(
    source: Path,
    output_path: Path,
    *,
    code_revision: str,
) -> XjtuLstmDevelopmentResult:
    """Run the frozen fold-1 train/validation LSTM path and write one evidence artifact."""
    _validate_code_revision(code_revision)
    source_report = validate_xjtu_source(source)
    if not source_report.profile_matches:
        raise XjtuLstmDevelopmentResultError(
            "XJTU-SY source does not match the observed complete profile: "
            + "; ".join(source_report.profile_issues)
        )

    fold = get_xjtu_reference_split().folds[0]
    adapter = XjtuSyAdapter()
    train_vectors = tuple(iter_vibration_features(adapter.iter_asset_series(source, fold.train)))
    validation_vectors = tuple(
        iter_vibration_features(adapter.iter_asset_series(source, fold.validation))
    )
    fitted = fit_xjtu_lstm_development_model(train_vectors, validation_vectors)
    scores = score_xjtu_lstm_development_validation(fitted)
    evaluation = evaluate_xjtu_lstm_development_scores(scores)
    result = build_xjtu_lstm_development_result(
        fitted,
        scores,
        evaluation,
        code_revision=code_revision,
        source_acquisition_count=source_report.acquisition_count,
    )
    write_xjtu_lstm_development_result(result, output_path)
    return result


def build_xjtu_lstm_development_result(
    fitted: XjtuLstmDevelopmentFit,
    scores: ReconstructionScores,
    evaluation: XjtuLstmDevelopmentEvaluation,
    *,
    code_revision: str,
    source_acquisition_count: int,
) -> XjtuLstmDevelopmentResult:
    """Resolve one immutable result from already completed fit, scoring, and evaluation."""
    _validate_code_revision(code_revision)
    if not isinstance(fitted, XjtuLstmDevelopmentFit):
        raise XjtuLstmDevelopmentResultError("fitted must be an XjtuLstmDevelopmentFit")
    if not isinstance(scores, ReconstructionScores):
        raise XjtuLstmDevelopmentResultError("scores must be ReconstructionScores")
    if not isinstance(evaluation, XjtuLstmDevelopmentEvaluation):
        raise XjtuLstmDevelopmentResultError("evaluation must be XjtuLstmDevelopmentEvaluation")
    if isinstance(source_acquisition_count, bool) or source_acquisition_count <= 0:
        raise XjtuLstmDevelopmentResultError("source_acquisition_count must be positive")

    config = fitted.config
    state: PreprocessingState = fitted.preprocessing_state
    reference = fitted.sequence_inputs.reference
    validation = fitted.sequence_inputs.validation
    training = fitted.model.training

    experiment_ids = {
        config.experiment_id,
        state.experiment_id,
        fitted.model.experiment_id,
        scores.experiment_id,
        evaluation.experiment_id,
    }
    if experiment_ids != {config.experiment_id}:
        raise XjtuLstmDevelopmentResultError(
            "fit, scores, and evaluation must share one experiment identity"
        )
    if scores.window_count != validation.window_count:
        raise XjtuLstmDevelopmentResultError(
            "validation score population must match sequence construction"
        )
    if training.fit_window_count != reference.window_count:
        raise XjtuLstmDevelopmentResultError(
            "training fit population must match reference sequence windows"
        )

    return XjtuLstmDevelopmentResult(
        code_revision=code_revision,
        source_acquisition_count=source_acquisition_count,
        experiment_id=config.experiment_id,
        dataset_id=config.dataset_id,
        split_id=config.split_id,
        fold_id=config.fold_id,
        feature_set_id=config.feature_set_id,
        selected_features=tuple(config.selected_features),
        fit_partition=config.fit_partition.value,
        scaling_strategy=config.scaling_strategy.value,
        preprocessing_fit_observation_count=state.observation_count,
        fitted_center=tuple(state.fitted_center),
        fitted_scale=tuple(state.fitted_scale),
        zero_iqr_features=tuple(state.zero_iqr_features),
        reference_strategy=config.reference_strategy.value,
        sampling_policy_id=config.sampling_policy_id,
        reference_source_acquisition_count=reference.source_observation_count,
        reference_window_count=reference.window_count,
        reference_dropped_prefix_count=reference.dropped_prefix_observation_count,
        validation_source_acquisition_count=validation.source_observation_count,
        validation_window_count=validation.window_count,
        validation_dropped_prefix_count=validation.dropped_prefix_observation_count,
        sequence_length=reference.spec.length,
        sequence_stride=reference.spec.stride,
        sequence_alignment=reference.spec.alignment.value,
        model_family=config.model_family.value,
        model_parameters=tuple(sorted(config.model_parameters.items())),
        random_seed=config.random_seed,
        training=training,
        score_semantics_id=scores.score_semantics_id,
        evaluation=evaluation,
    )


def write_xjtu_lstm_development_result(
    result: XjtuLstmDevelopmentResult,
    output_path: Path,
) -> None:
    """Write deterministic JSON for the preregistered retrospective development evidence."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_result_document(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _result_document(result: XjtuLstmDevelopmentResult) -> dict[str, Any]:
    training = result.training
    evaluation = result.evaluation
    fold = get_xjtu_reference_split().folds[0]
    return {
        "schema_id": XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID,
        "provenance": {
            "code_revision": result.code_revision,
            "experiment_id": result.experiment_id,
            "dataset_id": result.dataset_id,
            "split_id": result.split_id,
            "fold_id": result.fold_id,
            "evidence_class": XJTU_LSTM_DEVELOPMENT_EVIDENCE_CLASS,
        },
        "source_scope": {
            "verified_source_acquisition_count": result.source_acquisition_count,
            "train_bearings": list(fold.train),
            "validation_bearings": list(fold.validation),
            "excluded": [f"test:{asset_id}" for asset_id in fold.test],
        },
        "feature_schema": {
            "feature_set_id": result.feature_set_id,
            "selected_features": list(result.selected_features),
            "selected_feature_count": len(result.selected_features),
        },
        "preprocessing": {
            "fit_partition": result.fit_partition,
            "scaling_strategy": result.scaling_strategy,
            "fit_observation_count": result.preprocessing_fit_observation_count,
            "fitted_center": list(result.fitted_center),
            "fitted_scale": list(result.fitted_scale),
            "zero_iqr_features": list(result.zero_iqr_features),
        },
        "reference": {
            "strategy": result.reference_strategy,
            "sampling_policy_id": result.sampling_policy_id,
            "source_acquisition_count": result.reference_source_acquisition_count,
            "window_count": result.reference_window_count,
        },
        "sequence_construction": {
            "length": result.sequence_length,
            "stride": result.sequence_stride,
            "alignment": result.sequence_alignment,
            "feature_width": len(result.selected_features),
            "reference": {
                "source_acquisition_count": result.reference_source_acquisition_count,
                "window_count": result.reference_window_count,
                "dropped_prefix_acquisition_count": result.reference_dropped_prefix_count,
            },
            "validation": {
                "source_acquisition_count": result.validation_source_acquisition_count,
                "window_count": result.validation_window_count,
                "dropped_prefix_acquisition_count": result.validation_dropped_prefix_count,
            },
        },
        "model": {
            "family": result.model_family,
            "parameters": dict(result.model_parameters),
            "random_seed": result.random_seed,
            "training": {
                "framework": training.runtime,
                "framework_version": training.runtime_version,
                "device": training.device,
                "numeric_precision": training.numeric_precision,
                "deterministic_algorithms": training.deterministic_algorithms,
                "sampling_policy_id": training.sampling_policy_id,
                "fit_window_count": training.fit_window_count,
                "parameter_count": training.parameter_count,
                "batch_size": training.batch_size,
                "epochs": training.epochs,
                "epoch_losses": list(training.epoch_losses),
                "final_epoch_mean_training_loss": training.final_loss,
            },
        },
        "scoring": {
            "score_semantics_id": result.score_semantics_id,
            "direction": _SCORE_DIRECTION,
            "alignment": result.sequence_alignment,
            "input_numeric_precision": training.numeric_precision,
            "window_count": result.validation_window_count,
        },
        "evaluation": {
            "partition_semantics": XJTU_LSTM_DEVELOPMENT_EVIDENCE_CLASS,
            "lifecycle_segmentation": "original-full-run-thirds",
            "statistics": [
                "acquisition-order-spearman-rho",
                "lifecycle-late-vs-middle-rank-probability",
                "feature-mean-reconstruction-residual",
            ],
            "aggregation": "three-bearing-equal-weight-mean",
            "mean_bearing_acquisition_order_spearman_rho": (
                evaluation.mean_bearing_acquisition_order_spearman_rho
            ),
            "mean_bearing_late_vs_middle_rank_probability": (
                evaluation.mean_bearing_late_vs_middle_rank_probability
            ),
            "feature_residual_summary": [
                {
                    "feature_name": feature_name,
                    "mean_residual": residual,
                }
                for feature_name, residual in zip(
                    evaluation.feature_names,
                    evaluation.mean_bearing_feature_residuals,
                    strict=True,
                )
            ],
            "bearings": [
                {
                    "asset_id": bearing.asset_id,
                    "source_acquisition_count": bearing.source_acquisition_count,
                    "score_window_count": bearing.score_window_count,
                    "dropped_prefix_count": bearing.dropped_prefix_count,
                    "acquisition_order_spearman_rho": (bearing.acquisition_order_spearman_rho),
                    "late_vs_middle_rank_probability": (bearing.late_vs_middle_rank_probability),
                    "mean_feature_residuals": list(bearing.mean_feature_residuals),
                }
                for bearing in evaluation.bearing_results
            ],
        },
        "capability_scope": {
            "available": list(_AVAILABLE_CAPABILITIES),
            "unsupported_or_not_validated": list(_UNSUPPORTED_CAPABILITIES),
        },
        "interpretation": (
            "Retrospective development evidence on the preregistered fold-1 validation scope. "
            "This artifact records continuous reconstruction anomaly scores and descriptive "
            "lifecycle statistics without threshold calibration, state classification, health "
            "assessment, fault diagnosis, prognostics, or RUL claims."
        ),
    }


def _validate_code_revision(value: str) -> None:
    if not _FULL_GIT_REVISION.fullmatch(value):
        raise XjtuLstmDevelopmentResultError(
            "code_revision must be a full 40-character lowercase Git commit SHA"
        )
