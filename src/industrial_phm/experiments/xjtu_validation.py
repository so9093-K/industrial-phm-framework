"""Reproducible XJTU fold-1 candidate validation execution and evidence."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from industrial_phm.adapters import XjtuSyAdapter, validate_xjtu_source
from industrial_phm.experiments.config import ExperimentConfig
from industrial_phm.experiments.xjtu import (
    get_xjtu_isolation_forest_candidates,
    get_xjtu_reference_split,
)
from industrial_phm.experiments.xjtu_evaluation import (
    XjtuBearingScoreEvaluation,
    XjtuDevelopmentEvaluation,
    evaluate_xjtu_development_scores,
)
from industrial_phm.experiments.xjtu_model_input import (
    fit_xjtu_preprocessing_and_prepare_model_input,
    prepare_xjtu_model_scoring_input,
)
from industrial_phm.experiments.xjtu_score_trajectory import (
    XjtuCandidateScoreTrajectory,
    XjtuScoreTrajectoryReport,
    build_xjtu_candidate_score_trajectory,
    write_xjtu_score_trajectory_summary,
    write_xjtu_score_trajectory_table,
)
from industrial_phm.features import VibrationFeatureVector, iter_vibration_features
from industrial_phm.models import FittedIsolationForest, fit_isolation_forest

XJTU_FOLD_1_VALIDATION_SCHEMA_ID = "xjtu-fold-1-validation-result-v1"
XJTU_CANDIDATE_SELECTION_RULE_ID = "max-mean-rho-parsimony-acquisition-uniform-v1"
_FOLD_ID = "fold-1"
_PARTITION: Literal["validation"] = "validation"
_FIT_PARTITION: Literal["train"] = "train"
_ACQUISITION_UNIFORM = "acquisition-uniform-v1"
_SCORE_TRAJECTORY_TABLE = "xjtu-sy-iforest-fold-1-score-trajectory-v1.csv"
_SCORE_TRAJECTORY_SUMMARY = "xjtu-sy-iforest-fold-1-score-trajectory-summary-v1.json"
_FULL_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")


class XjtuFoldValidationError(ValueError):
    """Raised when fold-1 validation execution or evidence violates its contract."""


@dataclass(frozen=True, slots=True)
class XjtuCandidateValidationResult:
    """One candidate configuration and its validation evidence."""

    experiment_id: str
    feature_set_id: str
    selected_features: tuple[str, ...]
    sampling_policy_id: str
    scaling_strategy: str
    model_family: str
    model_parameters: tuple[tuple[str, str | int | float | bool], ...]
    random_seed: int
    source_observation_count: int
    fit_observation_count: int
    evaluation: XjtuDevelopmentEvaluation

    @property
    def mean_bearing_acquisition_order_spearman_rho(self) -> float | None:
        return self.evaluation.mean_bearing_acquisition_order_spearman_rho


@dataclass(frozen=True, slots=True)
class XjtuFoldValidationResult:
    """All candidate evidence and the deterministic fold-1 selection."""

    code_revision: str
    dataset_id: str
    split_id: str
    fold_id: str
    partition: str
    source_acquisition_count: int
    candidates: tuple[XjtuCandidateValidationResult, ...]
    selected_experiment_id: str
    selection_rule_id: str = XJTU_CANDIDATE_SELECTION_RULE_ID
    score_trajectories: tuple[XjtuCandidateScoreTrajectory, ...] = ()


def run_xjtu_fold_1_validation(
    source: Path,
    output_path: Path,
    *,
    code_revision: str,
    score_trajectory_dir: Path | None = None,
) -> XjtuFoldValidationResult:
    """Execute the four frozen candidates against fold-1 validation and write JSON evidence.

    ``score_trajectory_dir`` additionally writes development-only per-observation score
    trajectories. It never changes the fit, the scores, or the selection artifact.
    """
    _validate_code_revision(code_revision)
    source_report = validate_xjtu_source(source)
    if not source_report.profile_matches:
        raise XjtuFoldValidationError(
            "XJTU-SY source does not match the observed complete profile: "
            + "; ".join(source_report.profile_issues)
        )

    split = get_xjtu_reference_split()
    fold = next(item for item in split.folds if item.fold_id == _FOLD_ID)
    adapter = XjtuSyAdapter()
    train_vectors = tuple(iter_vibration_features(adapter.iter_asset_series(source, fold.train)))
    validation_vectors = tuple(
        iter_vibration_features(adapter.iter_asset_series(source, fold.validation))
    )
    result = evaluate_xjtu_fold_1_candidates(
        train_vectors,
        validation_vectors,
        code_revision=code_revision,
        source_acquisition_count=source_report.acquisition_count,
    )
    write_xjtu_fold_1_validation_result(result, output_path)
    if score_trajectory_dir is not None:
        write_xjtu_score_trajectory_artifacts(result, score_trajectory_dir)
    return result


def evaluate_xjtu_fold_1_candidates(
    train_vectors: Sequence[VibrationFeatureVector],
    validation_vectors: Sequence[VibrationFeatureVector],
    *,
    code_revision: str,
    source_acquisition_count: int,
) -> XjtuFoldValidationResult:
    """Run the packaged candidates through one shared train/validation execution path."""
    _validate_code_revision(code_revision)
    candidates = get_xjtu_isolation_forest_candidates()
    candidate_results: list[XjtuCandidateValidationResult] = []
    trajectories: list[XjtuCandidateScoreTrajectory] = []

    for config in candidates:
        _validate_candidate_scope(config)
        preprocessing_state, fit_input = fit_xjtu_preprocessing_and_prepare_model_input(
            config,
            train_vectors,
        )
        model = fit_isolation_forest(config, fit_input)
        validation_scores = model.score(
            prepare_xjtu_model_scoring_input(
                config,
                preprocessing_state,
                validation_vectors,
                partition=_PARTITION,
            )
        )
        evaluation = evaluate_xjtu_development_scores(
            config,
            validation_vectors,
            validation_scores,
        )
        train_scores = model.score(
            prepare_xjtu_model_scoring_input(
                config,
                preprocessing_state,
                train_vectors,
                partition=_FIT_PARTITION,
            )
        )
        trajectories.append(
            build_xjtu_candidate_score_trajectory(
                config.experiment_id,
                (
                    (_FIT_PARTITION, train_vectors, train_scores),
                    (_PARTITION, validation_vectors, validation_scores),
                ),
            )
        )
        candidate_results.append(
            _candidate_result(config, evaluation, fit_input.source_observation_count, model)
        )

    materialized = tuple(candidate_results)
    selected = select_xjtu_validation_candidate(materialized)
    first = candidates[0]
    return XjtuFoldValidationResult(
        code_revision=code_revision,
        dataset_id=first.dataset_id,
        split_id=first.split_id,
        fold_id=first.fold_id,
        partition=_PARTITION,
        source_acquisition_count=source_acquisition_count,
        candidates=materialized,
        selected_experiment_id=selected.experiment_id,
        score_trajectories=tuple(trajectories),
    )


def select_xjtu_validation_candidate(
    candidates: Sequence[XjtuCandidateValidationResult],
) -> XjtuCandidateValidationResult:
    """Apply the frozen mean-rho rule and deterministic simplicity tie-breakers."""
    eligible = tuple(
        candidate
        for candidate in candidates
        if candidate.mean_bearing_acquisition_order_spearman_rho is not None
    )
    if not eligible:
        raise XjtuFoldValidationError(
            "candidate selection requires at least one defined mean bearing Spearman rho"
        )

    return min(
        eligible,
        key=lambda candidate: (
            -_defined_mean(candidate),
            len(candidate.selected_features),
            candidate.sampling_policy_id != _ACQUISITION_UNIFORM,
            candidate.experiment_id,
        ),
    )


def write_xjtu_fold_1_validation_result(
    result: XjtuFoldValidationResult,
    output_path: Path,
) -> None:
    """Write deterministic, reviewable JSON evidence for one fold-1 validation run."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_result_document(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_xjtu_score_trajectory_artifacts(
    result: XjtuFoldValidationResult,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Write the development-only score-trajectory table and bearing summary."""
    if not result.score_trajectories:
        raise XjtuFoldValidationError(
            "fold-1 validation result carries no score trajectories to write"
        )
    report = XjtuScoreTrajectoryReport(
        code_revision=result.code_revision,
        dataset_id=result.dataset_id,
        split_id=result.split_id,
        fold_id=result.fold_id,
        candidates=result.score_trajectories,
    )
    table_path = output_dir / _SCORE_TRAJECTORY_TABLE
    summary_path = output_dir / _SCORE_TRAJECTORY_SUMMARY
    write_xjtu_score_trajectory_table(report, table_path)
    write_xjtu_score_trajectory_summary(report, summary_path)
    return table_path, summary_path


def _candidate_result(
    config: ExperimentConfig,
    evaluation: XjtuDevelopmentEvaluation,
    source_observation_count: int,
    model: FittedIsolationForest,
) -> XjtuCandidateValidationResult:
    return XjtuCandidateValidationResult(
        experiment_id=config.experiment_id,
        feature_set_id=config.feature_set_id,
        selected_features=tuple(config.selected_features),
        sampling_policy_id=config.sampling_policy_id,
        scaling_strategy=config.scaling_strategy.value,
        model_family=config.model_family.value,
        model_parameters=tuple(sorted(config.model_parameters.items())),
        random_seed=config.random_seed,
        source_observation_count=source_observation_count,
        fit_observation_count=model.fit_observation_count,
        evaluation=evaluation,
    )


def _validate_candidate_scope(config: ExperimentConfig) -> None:
    if config.fold_id != _FOLD_ID:
        raise XjtuFoldValidationError(
            f"fold-1 validation received candidate for {config.fold_id!r}"
        )


def _validate_code_revision(value: str) -> None:
    if not _FULL_GIT_REVISION.fullmatch(value):
        raise XjtuFoldValidationError(
            "code_revision must be a full 40-character lowercase Git commit SHA"
        )


def _defined_mean(candidate: XjtuCandidateValidationResult) -> float:
    value = candidate.mean_bearing_acquisition_order_spearman_rho
    if value is None:
        raise XjtuFoldValidationError("candidate mean bearing Spearman rho is undefined")
    return value


def _result_document(result: XjtuFoldValidationResult) -> dict[str, Any]:
    return {
        "schema_id": XJTU_FOLD_1_VALIDATION_SCHEMA_ID,
        "code_revision": result.code_revision,
        "dataset_id": result.dataset_id,
        "split_id": result.split_id,
        "fold_id": result.fold_id,
        "partition": result.partition,
        "source_acquisition_count": result.source_acquisition_count,
        "selection_rule": {
            "id": result.selection_rule_id,
            "primary": "maximize mean_bearing_acquisition_order_spearman_rho",
            "undefined_mean": "ineligible",
            "tie_breakers": [
                "fewer selected features",
                "acquisition-uniform-v1",
                "lexicographically smaller experiment_id",
            ],
        },
        "selected_experiment_id": result.selected_experiment_id,
        "candidates": [_candidate_document(candidate) for candidate in result.candidates],
    }


def _candidate_document(candidate: XjtuCandidateValidationResult) -> dict[str, Any]:
    return {
        "experiment_id": candidate.experiment_id,
        "feature_set_id": candidate.feature_set_id,
        "selected_features": list(candidate.selected_features),
        "sampling_policy_id": candidate.sampling_policy_id,
        "scaling_strategy": candidate.scaling_strategy,
        "model_family": candidate.model_family,
        "model_parameters": dict(candidate.model_parameters),
        "random_seed": candidate.random_seed,
        "source_observation_count": candidate.source_observation_count,
        "fit_observation_count": candidate.fit_observation_count,
        "validation_bearings": [
            _bearing_document(bearing) for bearing in candidate.evaluation.bearing_results
        ],
        "mean_bearing_acquisition_order_spearman_rho": (
            candidate.mean_bearing_acquisition_order_spearman_rho
        ),
    }


def _bearing_document(bearing: XjtuBearingScoreEvaluation) -> dict[str, Any]:
    return {
        "asset_id": bearing.asset_id,
        "operating_condition": bearing.operating_condition,
        "observation_count": bearing.observation_count,
        "acquisition_order_spearman_rho": bearing.acquisition_order_spearman_rho,
    }
