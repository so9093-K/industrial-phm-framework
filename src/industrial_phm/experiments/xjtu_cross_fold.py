"""Post-holdout cross-fold robustness evidence for the finalized XJTU configuration.

This is not a fresh holdout and not an independent cross-validation estimate: every fold-2..5
test bearing was already observed during fold-1 development, and fold-1 test bearings appear in
later folds' train partitions. The four folds run in one pass and produce one artifact so that
no fold result can be inspected before the next one is executed.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import fmean
from typing import Any, Literal

from industrial_phm.adapters import XjtuSyAdapter, validate_xjtu_source
from industrial_phm.experiments.config import ExperimentConfig
from industrial_phm.experiments.xjtu import XjtuSplitFold, get_xjtu_reference_split
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

XJTU_CROSS_FOLD_RESULT_SCHEMA_ID = "xjtu-cross-fold-robustness-result-v1"

_HOLDOUT_FOLD_ID = "fold-1"
_ROBUSTNESS_FOLD_IDS = ("fold-2", "fold-3", "fold-4", "fold-5")
_PARTITION: Literal["test"] = "test"
_FULL_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")


class XjtuCrossFoldRobustnessError(ValueError):
    """Raised when cross-fold robustness execution violates its frozen protocol."""


@dataclass(frozen=True, slots=True)
class XjtuBearingRobustnessEvidence:
    """One robustness-fold test bearing's descriptive anomaly-score evidence."""

    asset_id: str
    operating_condition: str
    full_run_observation_count: int
    middle_third_observation_count: int
    late_third_observation_count: int
    acquisition_order_spearman_rho: float
    late_vs_middle_rank_probability: float


@dataclass(frozen=True, slots=True)
class XjtuFoldRobustnessResult:
    """One robustness fold's provenance, populations and bearing evidence."""

    fold_id: str
    experiment_id: str
    test_bearings: tuple[str, ...]
    complete_train_observation_count: int
    reference_observation_count: int
    model_fit_observation_count: int
    bearing_results: tuple[XjtuBearingRobustnessEvidence, ...]
    mean_bearing_acquisition_order_spearman_rho: float
    mean_bearing_late_vs_middle_rank_probability: float


@dataclass(frozen=True, slots=True)
class XjtuConditionRobustnessSummary:
    """Equal-weight summary of one operating condition across the robustness folds."""

    operating_condition: str
    bearing_count: int
    mean_bearing_acquisition_order_spearman_rho: float
    mean_bearing_late_vs_middle_rank_probability: float


@dataclass(frozen=True, slots=True)
class XjtuCrossFoldRobustnessResult:
    """All robustness folds and the three pre-frozen equal-weight summaries."""

    code_revision: str
    dataset_id: str
    split_id: str
    finalized_experiment_id: str
    source_acquisition_count: int
    folds: tuple[XjtuFoldRobustnessResult, ...]
    condition_summaries: tuple[XjtuConditionRobustnessSummary, ...]
    overall_bearing_count: int
    overall_mean_bearing_acquisition_order_spearman_rho: float
    overall_mean_bearing_late_vs_middle_rank_probability: float


def run_xjtu_cross_fold_robustness(
    source: Path,
    output_path: Path,
    *,
    code_revision: str,
) -> XjtuCrossFoldRobustnessResult:
    """Execute folds 2-5 in one pass and write one deterministic robustness artifact."""
    _validate_code_revision(code_revision)
    source_report = validate_xjtu_source(source)
    if not source_report.profile_matches:
        raise XjtuCrossFoldRobustnessError(
            "XJTU-SY source does not match the observed complete profile: "
            + "; ".join(source_report.profile_issues)
        )

    adapter = XjtuSyAdapter()
    assets = tuple(
        sorted(
            {
                asset_id
                for fold in get_xjtu_reference_split().folds
                for asset_id in (*fold.train, *fold.validation, *fold.test)
            }
        )
    )
    vectors = tuple(iter_vibration_features(adapter.iter_asset_series(source, assets)))
    result = evaluate_xjtu_cross_fold_robustness(
        vectors,
        code_revision=code_revision,
        source_acquisition_count=source_report.acquisition_count,
    )
    write_xjtu_cross_fold_robustness_result(result, output_path)
    return result


def evaluate_xjtu_cross_fold_robustness(
    vectors: Sequence[VibrationFeatureVector],
    *,
    code_revision: str,
    source_acquisition_count: int,
) -> XjtuCrossFoldRobustnessResult:
    """Run every robustness fold before summarizing, so no fold can be inspected mid-run."""
    _validate_code_revision(code_revision)
    finalized = get_xjtu_finalized_configuration()
    by_asset: dict[str, list[VibrationFeatureVector]] = defaultdict(list)
    for vector in vectors:
        by_asset[vector.asset_id].append(vector)

    split = get_xjtu_reference_split()
    folds = {fold.fold_id: fold for fold in split.folds}
    _validate_fold_scope(folds)

    results = tuple(
        _evaluate_fold(finalized, folds[fold_id], by_asset) for fold_id in _ROBUSTNESS_FOLD_IDS
    )
    bearings = tuple(bearing for fold_result in results for bearing in fold_result.bearing_results)
    if len(bearings) != 12:
        raise XjtuCrossFoldRobustnessError(
            f"robustness evidence requires 12 test bearings, got {len(bearings)}"
        )

    return XjtuCrossFoldRobustnessResult(
        code_revision=code_revision,
        dataset_id=finalized.dataset_id,
        split_id=finalized.split_id,
        finalized_experiment_id=finalized.experiment_id,
        source_acquisition_count=source_acquisition_count,
        folds=results,
        condition_summaries=_condition_summaries(bearings),
        overall_bearing_count=len(bearings),
        overall_mean_bearing_acquisition_order_spearman_rho=float(
            fmean(bearing.acquisition_order_spearman_rho for bearing in bearings)
        ),
        overall_mean_bearing_late_vs_middle_rank_probability=float(
            fmean(bearing.late_vs_middle_rank_probability for bearing in bearings)
        ),
    )


def write_xjtu_cross_fold_robustness_result(
    result: XjtuCrossFoldRobustnessResult,
    output_path: Path,
) -> None:
    """Write one deterministic, reviewable cross-fold robustness artifact."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_result_document(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def fold_scoped_configuration(
    finalized: ExperimentConfig,
    fold_id: str,
) -> ExperimentConfig:
    """Re-target the finalized configuration at one fold without changing any other axis."""
    if fold_id not in _ROBUSTNESS_FOLD_IDS:
        raise XjtuCrossFoldRobustnessError(
            f"cross-fold robustness covers {_ROBUSTNESS_FOLD_IDS}, got {fold_id!r}"
        )
    suffix = finalized.experiment_id.removeprefix(f"xjtu-sy-iforest-{_HOLDOUT_FOLD_ID}-")
    if suffix == finalized.experiment_id:
        raise XjtuCrossFoldRobustnessError(
            f"unexpected finalized experiment_id shape: {finalized.experiment_id!r}"
        )
    return replace(
        finalized,
        experiment_id=f"xjtu-sy-iforest-{fold_id}-{suffix}",
        fold_id=fold_id,
    )


def _evaluate_fold(
    finalized: ExperimentConfig,
    fold: XjtuSplitFold,
    by_asset: dict[str, list[VibrationFeatureVector]],
) -> XjtuFoldRobustnessResult:
    config = fold_scoped_configuration(finalized, fold.fold_id)
    train_vectors = _partition_vectors(by_asset, fold.train, fold_id=fold.fold_id)
    test_vectors = _partition_vectors(by_asset, fold.test, fold_id=fold.fold_id)

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
        _bearing_evidence(series, fold_id=fold.fold_id)
        for series in align_xjtu_bearing_scores(test_vectors, scores)
    )

    return XjtuFoldRobustnessResult(
        fold_id=fold.fold_id,
        experiment_id=config.experiment_id,
        test_bearings=tuple(sorted(fold.test)),
        complete_train_observation_count=fit_input.source_observation_count,
        reference_observation_count=fit_input.reference_observation_count,
        model_fit_observation_count=fit_input.fit_observation_count,
        bearing_results=bearing_results,
        mean_bearing_acquisition_order_spearman_rho=float(
            fmean(bearing.acquisition_order_spearman_rho for bearing in bearing_results)
        ),
        mean_bearing_late_vs_middle_rank_probability=float(
            fmean(bearing.late_vs_middle_rank_probability for bearing in bearing_results)
        ),
    )


def _partition_vectors(
    by_asset: dict[str, list[VibrationFeatureVector]],
    assets: Sequence[str],
    *,
    fold_id: str,
) -> tuple[VibrationFeatureVector, ...]:
    missing = sorted(set(assets) - set(by_asset))
    if missing:
        raise XjtuCrossFoldRobustnessError(f"{fold_id} requires feature vectors for {missing}")
    return tuple(vector for asset_id in sorted(assets) for vector in by_asset[asset_id])


def _bearing_evidence(
    series: XjtuBearingScoreSeries,
    *,
    fold_id: str,
) -> XjtuBearingRobustnessEvidence:
    buckets: dict[str, list[float]] = defaultdict(list)
    for position, score in enumerate(series.scores):
        buckets[lifecycle_segment(position, series.observation_count)].append(score)

    rho = (
        spearman_rho(series.acquisition_indices, series.scores)
        if series.observation_count >= 2
        else None
    )
    probability = late_vs_middle_rank_probability(
        tuple(buckets[MIDDLE_THIRD]),
        tuple(buckets[LATE_THIRD]),
    )
    if rho is None or probability is None:
        raise XjtuCrossFoldRobustnessError(
            f"{fold_id} bearing {series.asset_id} has an undefined statistic; a partial "
            "cross-fold run is not recorded as canonical evidence"
        )

    return XjtuBearingRobustnessEvidence(
        asset_id=series.asset_id,
        operating_condition=series.operating_condition,
        full_run_observation_count=series.observation_count,
        middle_third_observation_count=len(buckets[MIDDLE_THIRD]),
        late_third_observation_count=len(buckets[LATE_THIRD]),
        acquisition_order_spearman_rho=rho,
        late_vs_middle_rank_probability=probability,
    )


def _condition_summaries(
    bearings: Sequence[XjtuBearingRobustnessEvidence],
) -> tuple[XjtuConditionRobustnessSummary, ...]:
    grouped: dict[str, list[XjtuBearingRobustnessEvidence]] = defaultdict(list)
    for bearing in bearings:
        grouped[bearing.operating_condition].append(bearing)

    return tuple(
        XjtuConditionRobustnessSummary(
            operating_condition=condition,
            bearing_count=len(members),
            mean_bearing_acquisition_order_spearman_rho=float(
                fmean(member.acquisition_order_spearman_rho for member in members)
            ),
            mean_bearing_late_vs_middle_rank_probability=float(
                fmean(member.late_vs_middle_rank_probability for member in members)
            ),
        )
        for condition, members in sorted(grouped.items())
    )


def _validate_fold_scope(folds: dict[str, XjtuSplitFold]) -> None:
    missing = tuple(fold_id for fold_id in _ROBUSTNESS_FOLD_IDS if fold_id not in folds)
    if missing:
        raise XjtuCrossFoldRobustnessError(
            f"the reference split is missing robustness folds {missing}"
        )
    if _HOLDOUT_FOLD_ID in _ROBUSTNESS_FOLD_IDS:
        raise XjtuCrossFoldRobustnessError(
            "the consumed fold-1 holdout must never be re-scored here"
        )


def _validate_code_revision(value: str) -> None:
    if not _FULL_GIT_REVISION.fullmatch(value):
        raise XjtuCrossFoldRobustnessError(
            "code_revision must be a full 40-character lowercase Git commit SHA"
        )


def _result_document(result: XjtuCrossFoldRobustnessResult) -> dict[str, Any]:
    return {
        "schema_id": XJTU_CROSS_FOLD_RESULT_SCHEMA_ID,
        "code_revision": result.code_revision,
        "dataset_id": result.dataset_id,
        "split_id": result.split_id,
        "finalized_experiment_id": result.finalized_experiment_id,
        "evaluated_folds": list(_ROBUSTNESS_FOLD_IDS),
        "scored_partition": _PARTITION,
        "source_acquisition_count": result.source_acquisition_count,
        "interpretation": (
            "Post-holdout robustness evidence for the finalized configuration. Not a fresh "
            "holdout and not an independent cross-validation estimate: every fold-2..5 test "
            "bearing was already observed during fold-1 development, and fold-1 test bearings "
            "appear in later folds' train partitions. The consumed fold-1 holdout is not "
            "re-scored here and its numbers are not merged into these aggregates. Both "
            "statistics are recorded descriptively with no primary/secondary ranking."
        ),
        "folds": [_fold_document(fold) for fold in result.folds],
        "operating_condition_summary": [
            {
                "operating_condition": summary.operating_condition,
                "bearing_count": summary.bearing_count,
                "mean_bearing_acquisition_order_spearman_rho": (
                    summary.mean_bearing_acquisition_order_spearman_rho
                ),
                "mean_bearing_late_vs_middle_rank_probability": (
                    summary.mean_bearing_late_vs_middle_rank_probability
                ),
            }
            for summary in result.condition_summaries
        ],
        "overall_summary": {
            "bearing_count": result.overall_bearing_count,
            "mean_bearing_acquisition_order_spearman_rho": (
                result.overall_mean_bearing_acquisition_order_spearman_rho
            ),
            "mean_bearing_late_vs_middle_rank_probability": (
                result.overall_mean_bearing_late_vs_middle_rank_probability
            ),
        },
    }


def _fold_document(fold: XjtuFoldRobustnessResult) -> dict[str, Any]:
    return {
        "fold_id": fold.fold_id,
        "experiment_id": fold.experiment_id,
        "test_bearings": list(fold.test_bearings),
        "complete_train_observation_count": fold.complete_train_observation_count,
        "reference_observation_count": fold.reference_observation_count,
        "model_fit_observation_count": fold.model_fit_observation_count,
        "mean_bearing_acquisition_order_spearman_rho": (
            fold.mean_bearing_acquisition_order_spearman_rho
        ),
        "mean_bearing_late_vs_middle_rank_probability": (
            fold.mean_bearing_late_vs_middle_rank_probability
        ),
        "test_bearing_results": [
            {
                "asset_id": bearing.asset_id,
                "operating_condition": bearing.operating_condition,
                "full_run_observation_count": bearing.full_run_observation_count,
                "middle_third_observation_count": bearing.middle_third_observation_count,
                "late_third_observation_count": bearing.late_third_observation_count,
                "acquisition_order_spearman_rho": bearing.acquisition_order_spearman_rho,
                "late_vs_middle_rank_probability": bearing.late_vs_middle_rank_probability,
            }
            for bearing in fold.bearing_results
        ],
    }
