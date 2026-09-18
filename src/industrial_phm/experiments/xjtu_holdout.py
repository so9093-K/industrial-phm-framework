"""One-shot XJTU fold-1 holdout test evaluation of the finalized configuration.

This path deliberately has no candidate comparison, no reference comparison, no threshold
calibration and no tunable parameter. It consumes exactly the one configuration fold-1
development finalized and reports descriptive statistics on the holdout partition. Anything that
would let a holdout result change the configuration belongs in a new protocol version, not here.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean
from typing import Any, Literal

from industrial_phm.adapters import XjtuSyAdapter, validate_xjtu_source
from industrial_phm.experiments.config import ExperimentConfig
from industrial_phm.experiments.xjtu import get_xjtu_reference_split
from industrial_phm.experiments.xjtu_evaluation import (
    XjtuBearingScoreSeries,
    align_xjtu_bearing_scores,
    late_vs_middle_rank_probability,
    spearman_rho,
)
from industrial_phm.experiments.xjtu_finalized import get_xjtu_finalized_configuration
from industrial_phm.experiments.xjtu_lifecycle import (
    LATE_THIRD,
    MIDDLE_THIRD,
    lifecycle_segment,
)
from industrial_phm.experiments.xjtu_model_input import (
    fit_xjtu_preprocessing_and_prepare_model_input,
    prepare_xjtu_model_scoring_input,
)
from industrial_phm.features import VibrationFeatureVector, iter_vibration_features
from industrial_phm.models import fit_isolation_forest

XJTU_HOLDOUT_RESULT_SCHEMA_ID = "xjtu-fold-1-holdout-result-v1"

_FOLD_ID = "fold-1"
_PARTITION: Literal["test"] = "test"
_FULL_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")


class XjtuHoldoutEvaluationError(ValueError):
    """Raised when holdout evaluation violates its one-shot protocol."""


@dataclass(frozen=True, slots=True)
class XjtuBearingHoldoutEvidence:
    """One holdout bearing run's descriptive anomaly-score evidence."""

    asset_id: str
    operating_condition: str
    full_run_observation_count: int
    middle_third_observation_count: int
    late_third_observation_count: int
    acquisition_order_spearman_rho: float | None
    late_vs_middle_rank_probability: float | None


@dataclass(frozen=True, slots=True)
class XjtuHoldoutResult:
    """Holdout evidence for the one finalized fold-1 configuration."""

    code_revision: str
    experiment_id: str
    dataset_id: str
    split_id: str
    fold_id: str
    partition: str
    reference_strategy: str
    sampling_policy_id: str
    scaling_strategy: str
    model_family: str
    random_seed: int
    source_acquisition_count: int
    complete_train_observation_count: int
    reference_observation_count: int
    model_fit_observation_count: int
    bearing_results: tuple[XjtuBearingHoldoutEvidence, ...]
    mean_bearing_acquisition_order_spearman_rho: float | None
    mean_bearing_late_vs_middle_rank_probability: float | None


def run_xjtu_fold_1_holdout_evaluation(
    source: Path,
    output_path: Path,
    *,
    code_revision: str,
) -> XjtuHoldoutResult:
    """Evaluate the finalized configuration on the fold-1 holdout partition exactly once."""
    _validate_code_revision(code_revision)
    source_report = validate_xjtu_source(source)
    if not source_report.profile_matches:
        raise XjtuHoldoutEvaluationError(
            "XJTU-SY source does not match the observed complete profile: "
            + "; ".join(source_report.profile_issues)
        )

    fold = next(item for item in get_xjtu_reference_split().folds if item.fold_id == _FOLD_ID)
    adapter = XjtuSyAdapter()
    train_vectors = tuple(iter_vibration_features(adapter.iter_asset_series(source, fold.train)))
    test_vectors = tuple(iter_vibration_features(adapter.iter_asset_series(source, fold.test)))
    result = evaluate_xjtu_fold_1_holdout(
        train_vectors,
        test_vectors,
        code_revision=code_revision,
        source_acquisition_count=source_report.acquisition_count,
    )
    write_xjtu_holdout_result(result, output_path)
    return result


def evaluate_xjtu_fold_1_holdout(
    train_vectors: Sequence[VibrationFeatureVector],
    test_vectors: Sequence[VibrationFeatureVector],
    *,
    code_revision: str,
    source_acquisition_count: int,
) -> XjtuHoldoutResult:
    """Fit the finalized configuration on train and score the holdout partition once."""
    _validate_code_revision(code_revision)
    config = get_xjtu_finalized_configuration()
    _validate_finalized_scope(config)

    preprocessing_state, fit_input = fit_xjtu_preprocessing_and_prepare_model_input(
        config,
        train_vectors,
    )
    model = fit_isolation_forest(config, fit_input)
    scores = model.score(
        prepare_xjtu_model_scoring_input(
            config,
            preprocessing_state,
            test_vectors,
            partition=_PARTITION,
        )
    )
    bearing_results = tuple(
        _bearing_evidence(series) for series in align_xjtu_bearing_scores(test_vectors, scores)
    )

    return XjtuHoldoutResult(
        code_revision=code_revision,
        experiment_id=config.experiment_id,
        dataset_id=config.dataset_id,
        split_id=config.split_id,
        fold_id=config.fold_id,
        partition=_PARTITION,
        reference_strategy=config.reference_strategy.value,
        sampling_policy_id=config.sampling_policy_id,
        scaling_strategy=config.scaling_strategy.value,
        model_family=config.model_family.value,
        random_seed=config.random_seed,
        source_acquisition_count=source_acquisition_count,
        complete_train_observation_count=fit_input.source_observation_count,
        reference_observation_count=fit_input.reference_observation_count,
        model_fit_observation_count=fit_input.fit_observation_count,
        bearing_results=bearing_results,
        mean_bearing_acquisition_order_spearman_rho=_bearing_equal_mean(
            tuple(bearing.acquisition_order_spearman_rho for bearing in bearing_results)
        ),
        mean_bearing_late_vs_middle_rank_probability=_bearing_equal_mean(
            tuple(bearing.late_vs_middle_rank_probability for bearing in bearing_results)
        ),
    )


def write_xjtu_holdout_result(result: XjtuHoldoutResult, output_path: Path) -> None:
    """Write deterministic, reviewable JSON evidence for the one holdout evaluation."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_result_document(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _bearing_evidence(series: XjtuBearingScoreSeries) -> XjtuBearingHoldoutEvidence:
    buckets: dict[str, list[float]] = defaultdict(list)
    for position, score in enumerate(series.scores):
        buckets[lifecycle_segment(position, series.observation_count)].append(score)

    return XjtuBearingHoldoutEvidence(
        asset_id=series.asset_id,
        operating_condition=series.operating_condition,
        full_run_observation_count=series.observation_count,
        middle_third_observation_count=len(buckets[MIDDLE_THIRD]),
        late_third_observation_count=len(buckets[LATE_THIRD]),
        acquisition_order_spearman_rho=(
            spearman_rho(series.acquisition_indices, series.scores)
            if series.observation_count >= 2
            else None
        ),
        late_vs_middle_rank_probability=late_vs_middle_rank_probability(
            tuple(buckets[MIDDLE_THIRD]),
            tuple(buckets[LATE_THIRD]),
        ),
    )


def _bearing_equal_mean(values: Sequence[float | None]) -> float | None:
    if not values or any(value is None for value in values):
        return None
    return float(fmean(value for value in values if value is not None))


def _validate_finalized_scope(config: ExperimentConfig) -> None:
    if config.fold_id != _FOLD_ID:
        raise XjtuHoldoutEvaluationError(
            f"fold-1 holdout evaluation received a {config.fold_id!r} configuration"
        )


def _validate_code_revision(value: str) -> None:
    if not _FULL_GIT_REVISION.fullmatch(value):
        raise XjtuHoldoutEvaluationError(
            "code_revision must be a full 40-character lowercase Git commit SHA"
        )


def _result_document(result: XjtuHoldoutResult) -> dict[str, Any]:
    return {
        "schema_id": XJTU_HOLDOUT_RESULT_SCHEMA_ID,
        "code_revision": result.code_revision,
        "experiment_id": result.experiment_id,
        "dataset_id": result.dataset_id,
        "split_id": result.split_id,
        "fold_id": result.fold_id,
        "partition": result.partition,
        "configuration": {
            "reference_strategy": result.reference_strategy,
            "sampling_policy_id": result.sampling_policy_id,
            "scaling_strategy": result.scaling_strategy,
            "model_family": result.model_family,
            "random_seed": result.random_seed,
        },
        "source_acquisition_count": result.source_acquisition_count,
        "complete_train_observation_count": result.complete_train_observation_count,
        "reference_observation_count": result.reference_observation_count,
        "model_fit_observation_count": result.model_fit_observation_count,
        "interpretation": (
            "One-shot holdout evidence for the finalized fold-1 configuration. Both statistics "
            "are recorded descriptively; this evaluation performs no candidate selection, no "
            "reference comparison and no threshold calibration. The statistics describe "
            "retrospective lifecycle shape and are not fault-onset accuracy, Health Indicator "
            "monotonicity or prognostic performance."
        ),
        "mean_bearing_acquisition_order_spearman_rho": (
            result.mean_bearing_acquisition_order_spearman_rho
        ),
        "mean_bearing_late_vs_middle_rank_probability": (
            result.mean_bearing_late_vs_middle_rank_probability
        ),
        "holdout_bearings": [
            {
                "asset_id": bearing.asset_id,
                "operating_condition": bearing.operating_condition,
                "full_run_observation_count": bearing.full_run_observation_count,
                "middle_third_observation_count": bearing.middle_third_observation_count,
                "late_third_observation_count": bearing.late_third_observation_count,
                "acquisition_order_spearman_rho": bearing.acquisition_order_spearman_rho,
                "late_vs_middle_rank_probability": bearing.late_vs_middle_rank_probability,
            }
            for bearing in result.bearing_results
        ],
    }
