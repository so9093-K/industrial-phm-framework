"""One-time IMS Set 2 -> Set 3 cross-test anomaly-scoring evaluation."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any

from industrial_phm.adapters import ImsBearingAdapter, validate_ims_source
from industrial_phm.experiments.config import ExperimentParameter
from industrial_phm.experiments.ims import (
    IMS_BEARING_COUNT,
    IMS_EVALUATION_ACQUISITION_COUNT,
    IMS_EVALUATION_ARCHIVE_SCOPE,
    IMS_EVALUATION_TEST_ID,
    IMS_RADIAL_LOAD_LB,
    IMS_ROTATIONAL_SPEED_RPM,
    IMS_TRAIN_ACQUISITION_COUNT,
    IMS_TRAIN_TEST_ID,
    get_ims_cross_test_configuration,
)
from industrial_phm.experiments.ims_model_input import (
    fit_ims_preprocessing_and_prepare_model_input,
    prepare_ims_model_scoring_input,
)
from industrial_phm.experiments.score_statistics import (
    late_vs_middle_rank_probability,
    spearman_rho,
)
from industrial_phm.features import VibrationFeatureVector, iter_vibration_features
from industrial_phm.models import AnomalyScores, fit_isolation_forest

IMS_CROSS_TEST_RESULT_SCHEMA_ID = "ims-single-channel-cross-test-result-v1"

_FULL_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")


class ImsCrossTestEvaluationError(ValueError):
    """Raised when IMS cross-test execution violates the frozen v1 protocol."""


@dataclass(frozen=True, slots=True)
class ImsBearingCrossTestEvidence:
    """Descriptive score-shape evidence for one Set 3 bearing."""

    asset_id: str
    test_id: str
    full_run_observation_count: int
    middle_stage_observation_count: int
    late_stage_observation_count: int
    acquisition_order_spearman_rho: float
    late_vs_middle_rank_probability: float


@dataclass(frozen=True, slots=True)
class ImsCrossTestResult:
    """Reproducible evidence for the one fixed IMS cross-test configuration."""

    code_revision: str
    experiment_id: str
    dataset_id: str
    split_id: str
    fold_id: str
    source_acquisition_count: int
    train_test_id: str
    evaluation_test_id: str
    evaluation_archive_scope: str
    selected_features: tuple[str, ...]
    reference_strategy: str
    sampling_policy_id: str
    scaling_strategy: str
    model_family: str
    model_parameters: tuple[tuple[str, ExperimentParameter], ...]
    random_seed: int
    complete_train_observation_count: int
    reference_observation_count: int
    model_fit_observation_count: int
    scoring_observation_count: int
    rotational_speed_rpm: float
    radial_load_lb: float
    bearing_results: tuple[ImsBearingCrossTestEvidence, ...]
    mean_bearing_acquisition_order_spearman_rho: float
    mean_bearing_late_vs_middle_rank_probability: float


def run_ims_cross_test_evaluation(
    source: Path,
    output_path: Path,
    *,
    code_revision: str,
) -> ImsCrossTestResult:
    """Run the frozen cross-test path and write one deterministic evidence artifact."""
    _validate_code_revision(code_revision)
    source_report = validate_ims_source(source)
    if not source_report.profile_matches:
        raise ImsCrossTestEvaluationError(
            "IMS source does not match the verified archive profile: "
            + "; ".join(source_report.profile_issues)
        )

    adapter = ImsBearingAdapter()
    train_vectors = tuple(
        iter_vibration_features(
            adapter.iter_test_series(source, IMS_TRAIN_TEST_ID, archive_scope="all")
        )
    )
    evaluation_vectors = tuple(
        iter_vibration_features(
            adapter.iter_test_series(
                source,
                IMS_EVALUATION_TEST_ID,
                archive_scope=IMS_EVALUATION_ARCHIVE_SCOPE,
            )
        )
    )
    result = evaluate_ims_cross_test(
        train_vectors,
        evaluation_vectors,
        code_revision=code_revision,
        source_acquisition_count=source_report.acquisition_count,
    )
    write_ims_cross_test_result(result, output_path)
    return result


def evaluate_ims_cross_test(
    train_vectors: Sequence[VibrationFeatureVector],
    evaluation_vectors: Sequence[VibrationFeatureVector],
    *,
    code_revision: str,
    source_acquisition_count: int,
) -> ImsCrossTestResult:
    """Fit the fixed Set 2 configuration and score only README-documented Set 3."""
    _validate_code_revision(code_revision)
    if isinstance(source_acquisition_count, bool) or source_acquisition_count <= 0:
        raise ImsCrossTestEvaluationError("source_acquisition_count must be positive")

    config = get_ims_cross_test_configuration()
    preprocessing_state, fit_input = fit_ims_preprocessing_and_prepare_model_input(
        config,
        train_vectors,
    )
    model = fit_isolation_forest(config, fit_input)
    scoring_input = prepare_ims_model_scoring_input(
        config,
        preprocessing_state,
        evaluation_vectors,
    )
    scores = model.score(scoring_input)
    bearing_results = _bearing_evidence(evaluation_vectors, scores)

    if len(bearing_results) != IMS_BEARING_COUNT:
        raise ImsCrossTestEvaluationError(
            f"IMS cross-test must produce {IMS_BEARING_COUNT} bearing results"
        )

    return ImsCrossTestResult(
        code_revision=code_revision,
        experiment_id=config.experiment_id,
        dataset_id=config.dataset_id,
        split_id=config.split_id,
        fold_id=config.fold_id,
        source_acquisition_count=source_acquisition_count,
        train_test_id=IMS_TRAIN_TEST_ID,
        evaluation_test_id=IMS_EVALUATION_TEST_ID,
        evaluation_archive_scope=IMS_EVALUATION_ARCHIVE_SCOPE,
        selected_features=tuple(config.selected_features),
        reference_strategy=config.reference_strategy.value,
        sampling_policy_id=config.sampling_policy_id,
        scaling_strategy=config.scaling_strategy.value,
        model_family=config.model_family.value,
        model_parameters=tuple(sorted(config.model_parameters.items())),
        random_seed=config.random_seed,
        complete_train_observation_count=fit_input.source_observation_count,
        reference_observation_count=fit_input.reference_observation_count,
        model_fit_observation_count=fit_input.fit_observation_count,
        scoring_observation_count=scoring_input.observation_count,
        rotational_speed_rpm=IMS_ROTATIONAL_SPEED_RPM,
        radial_load_lb=IMS_RADIAL_LOAD_LB,
        bearing_results=bearing_results,
        mean_bearing_acquisition_order_spearman_rho=float(
            fmean(item.acquisition_order_spearman_rho for item in bearing_results)
        ),
        mean_bearing_late_vs_middle_rank_probability=float(
            fmean(item.late_vs_middle_rank_probability for item in bearing_results)
        ),
    )


def write_ims_cross_test_result(result: ImsCrossTestResult, output_path: Path) -> None:
    """Write deterministic JSON whose sections mirror the developer transparency view."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_result_document(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _bearing_evidence(
    vectors: Sequence[VibrationFeatureVector],
    anomaly_scores: AnomalyScores,
) -> tuple[ImsBearingCrossTestEvidence, ...]:
    score_by_id = dict(
        zip(anomaly_scores.source_observation_ids, anomaly_scores.scores, strict=True)
    )
    grouped: dict[str, list[tuple[int, float]]] = defaultdict(list)
    seen: set[str] = set()

    for vector_index, vector in enumerate(vectors):
        acquisition_index = _acquisition_index(vector, vector_index=vector_index)
        observation_id = f"{vector.asset_id}:acquisition-{acquisition_index}"
        if observation_id in seen:
            raise ImsCrossTestEvaluationError(
                f"IMS evaluation observation identity repeats: {observation_id!r}"
            )
        seen.add(observation_id)
        try:
            score = score_by_id[observation_id]
        except KeyError as error:
            raise ImsCrossTestEvaluationError(
                f"IMS anomaly scores are missing {observation_id!r}"
            ) from error
        grouped[vector.asset_id].append((acquisition_index, score))

    if seen != set(score_by_id):
        raise ImsCrossTestEvaluationError(
            "IMS anomaly scores must align exactly with evaluation feature vectors"
        )

    results: list[ImsBearingCrossTestEvidence] = []
    for asset_id in sorted(grouped):
        ordered = sorted(grouped[asset_id])
        indices = tuple(index for index, _ in ordered)
        scores = tuple(score for _, score in ordered)
        if len(scores) != IMS_EVALUATION_ACQUISITION_COUNT:
            raise ImsCrossTestEvaluationError(
                f"IMS evaluation bearing {asset_id} must contain "
                f"{IMS_EVALUATION_ACQUISITION_COUNT} observations"
            )
        early_end = _ceil_div(len(scores), 3)
        middle_end = _ceil_div(2 * len(scores), 3)
        middle_scores = scores[early_end:middle_end]
        late_scores = scores[middle_end:]

        rho = spearman_rho(indices, scores)
        rank_probability = late_vs_middle_rank_probability(middle_scores, late_scores)
        if rho is None or rank_probability is None:
            raise ImsCrossTestEvaluationError(
                f"IMS evaluation statistic is undefined for {asset_id}"
            )
        results.append(
            ImsBearingCrossTestEvidence(
                asset_id=asset_id,
                test_id=IMS_EVALUATION_TEST_ID,
                full_run_observation_count=len(scores),
                middle_stage_observation_count=len(middle_scores),
                late_stage_observation_count=len(late_scores),
                acquisition_order_spearman_rho=rho,
                late_vs_middle_rank_probability=rank_probability,
            )
        )
    return tuple(results)


def _result_document(result: ImsCrossTestResult) -> dict[str, Any]:
    return {
        "schema_id": IMS_CROSS_TEST_RESULT_SCHEMA_ID,
        "provenance": {
            "code_revision": result.code_revision,
            "experiment_id": result.experiment_id,
            "dataset_id": result.dataset_id,
            "split_id": result.split_id,
            "fold_id": result.fold_id,
        },
        "source_scope": {
            "verified_source_acquisition_count": result.source_acquisition_count,
            "train": {
                "test_id": result.train_test_id,
                "acquisition_count": IMS_TRAIN_ACQUISITION_COUNT,
                "bearing_count": IMS_BEARING_COUNT,
                "scope": "complete-archive-set",
            },
            "evaluation": {
                "test_id": result.evaluation_test_id,
                "archive_scope": result.evaluation_archive_scope,
                "acquisition_count": IMS_EVALUATION_ACQUISITION_COUNT,
                "bearing_count": IMS_BEARING_COUNT,
            },
            "excluded": [
                "set-1",
                "set-3:archive-extension",
            ],
        },
        "feature_schema": {
            "feature_set_id": "vibration-statistical-v1",
            "selected_features": list(result.selected_features),
            "selected_feature_count": len(result.selected_features),
        },
        "preprocessing": {
            "fit_partition": "train",
            "scaling_strategy": result.scaling_strategy,
        },
        "population_flow": {
            "complete_train_observation_count": result.complete_train_observation_count,
            "reference_observation_count": result.reference_observation_count,
            "model_fit_observation_count": result.model_fit_observation_count,
            "scoring_observation_count": result.scoring_observation_count,
        },
        "model": {
            "model_family": result.model_family,
            "parameters": dict(result.model_parameters),
            "random_seed": result.random_seed,
            "reference_strategy": result.reference_strategy,
            "sampling_policy_id": result.sampling_policy_id,
            "score_semantics": "higher-is-more-anomalous",
        },
        "operating_context": {
            "rotational_speed_rpm": result.rotational_speed_rpm,
            "radial_load_lb": result.radial_load_lb,
        },
        "evaluation": {
            "partition_semantics": "one-time-cross-test-evaluation",
            "statistics": [
                "acquisition-order-spearman-rho",
                "test-stage-late-vs-middle-rank-probability",
            ],
            "aggregation": "four-bearing-equal-weight-mean",
            "test_stage_segmentation": {
                "definition": "early=p<ceil(N/3); middle=ceil(N/3)..ceil(2N/3)-1; late=rest",
                "N": IMS_EVALUATION_ACQUISITION_COUNT,
                "early_count": _ceil_div(IMS_EVALUATION_ACQUISITION_COUNT, 3),
                "middle_count": (
                    _ceil_div(2 * IMS_EVALUATION_ACQUISITION_COUNT, 3)
                    - _ceil_div(IMS_EVALUATION_ACQUISITION_COUNT, 3)
                ),
                "late_count": (
                    IMS_EVALUATION_ACQUISITION_COUNT
                    - _ceil_div(2 * IMS_EVALUATION_ACQUISITION_COUNT, 3)
                ),
            },
            "mean_bearing_acquisition_order_spearman_rho": (
                result.mean_bearing_acquisition_order_spearman_rho
            ),
            "mean_bearing_late_vs_middle_rank_probability": (
                result.mean_bearing_late_vs_middle_rank_probability
            ),
            "bearings": [
                {
                    "asset_id": item.asset_id,
                    "test_id": item.test_id,
                    "full_run_observation_count": item.full_run_observation_count,
                    "middle_stage_observation_count": item.middle_stage_observation_count,
                    "late_stage_observation_count": item.late_stage_observation_count,
                    "acquisition_order_spearman_rho": (item.acquisition_order_spearman_rho),
                    "late_vs_middle_rank_probability": (item.late_vs_middle_rank_probability),
                }
                for item in result.bearing_results
            ],
        },
        "capability_scope": {
            "available": [
                "anomaly-scoring",
                "descriptive-score-trajectory-evaluation",
            ],
            "unsupported_or_not_validated": [
                "thresholded-state-detection",
                "health-assessment",
                "fault-diagnostics",
                "prognostics-rul",
            ],
        },
        "interpretation": (
            "Cross-test portability evidence for a fixed unsupervised anomaly-scoring "
            "configuration. Set 2 is the complete train/reference distribution; Set 3 "
            "README-documented scope is scored once without IMS-specific model tuning. "
            "The statistics describe anomaly-score shape over observed acquisition order "
            "and are not fault-onset accuracy, Health Indicator quality, diagnostics, or "
            "prognostic performance."
        ),
    }


def _validate_code_revision(value: str) -> None:
    if not _FULL_GIT_REVISION.fullmatch(value):
        raise ImsCrossTestEvaluationError(
            "code_revision must be a full 40-character lowercase Git commit SHA"
        )


def _acquisition_index(
    vector: VibrationFeatureVector,
    *,
    vector_index: int,
) -> int:
    value = vector.metadata.get("acquisition_index")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ImsCrossTestEvaluationError(
            f"IMS evaluation vector {vector_index} requires acquisition_index"
        )
    return value


def _ceil_div(numerator: int, denominator: int) -> int:
    return -(-numerator // denominator)
