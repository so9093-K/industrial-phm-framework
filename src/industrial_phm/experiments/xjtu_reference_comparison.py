"""Reference-only H0/H1 development comparison for XJTU fold-1."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from statistics import fmean
from typing import Any, Literal

from industrial_phm.adapters import XjtuSyAdapter, validate_xjtu_source
from industrial_phm.experiments.config import ExperimentConfig, ReferenceStrategy
from industrial_phm.experiments.xjtu import (
    get_xjtu_reference_split,
    load_packaged_xjtu_experiment_configs,
)
from industrial_phm.experiments.xjtu_evaluation import (
    XjtuDevelopmentEvaluation,
    evaluate_xjtu_development_scores,
    late_vs_middle_rank_probability,
)
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
from industrial_phm.models import AnomalyScores, fit_isolation_forest

XJTU_REFERENCE_COMPARISON_SCHEMA_ID = "xjtu-fold-1-reference-comparison-result-v1"
XJTU_REFERENCE_DECISION_RULE_ID = "late-vs-middle-rank-probability-strict-improvement-v1"

_FOLD_ID = "fold-1"
_PARTITION: Literal["validation"] = "validation"
_BASELINE_REFERENCE = ReferenceStrategy.ALL_TRAIN_OBSERVATIONS
_ALTERNATIVE_REFERENCE = ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD
_REFERENCE_MANIFEST = "xjtu-sy-isolation-forest-fold-1-reference-v3.toml"
_FULL_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")


class XjtuReferenceComparisonError(ValueError):
    """Raised when the reference comparison violates its frozen protocol."""


@dataclass(frozen=True, slots=True)
class XjtuBearingReferenceEvidence:
    """One validation bearing's retrospective lifecycle-shape evidence.

    Each statistic is recorded next to the population it was computed on:
    ``acquisition_order_spearman_rho`` covers the complete ``1..N`` run, while
    ``late_vs_middle_rank_probability`` compares the two lifecycle-third groups.
    """

    asset_id: str
    operating_condition: str
    full_run_observation_count: int
    middle_third_observation_count: int
    late_third_observation_count: int
    late_vs_middle_rank_probability: float | None
    acquisition_order_spearman_rho: float | None


@dataclass(frozen=True, slots=True)
class XjtuReferenceHypothesisResult:
    """One reference strategy evaluated against the fold-1 validation partition."""

    experiment_id: str
    reference_strategy: str
    complete_train_observation_count: int
    reference_observation_count: int
    model_fit_observation_count: int
    bearing_results: tuple[XjtuBearingReferenceEvidence, ...]
    mean_bearing_late_vs_middle_rank_probability: float | None
    mean_bearing_acquisition_order_spearman_rho: float | None


@dataclass(frozen=True, slots=True)
class XjtuReferenceComparisonResult:
    """Frozen H0/H1 reference comparison and its deterministic decision."""

    code_revision: str
    dataset_id: str
    split_id: str
    fold_id: str
    partition: str
    source_acquisition_count: int
    hypotheses: tuple[XjtuReferenceHypothesisResult, ...]
    selected_experiment_id: str
    selected_reference_strategy: str
    decision_rule_id: str = XJTU_REFERENCE_DECISION_RULE_ID


@lru_cache(maxsize=1)
def get_xjtu_reference_hypotheses() -> tuple[ExperimentConfig, ...]:
    """Load the packaged, frozen H0/H1 reference comparison configurations."""
    configs = load_packaged_xjtu_experiment_configs(_REFERENCE_MANIFEST)
    _validate_hypothesis_scope(configs)
    return configs


def run_xjtu_fold_1_reference_comparison(
    source: Path,
    output_path: Path,
    *,
    code_revision: str,
) -> XjtuReferenceComparisonResult:
    """Execute the frozen H0/H1 comparison on fold-1 and write deterministic JSON evidence."""
    _validate_code_revision(code_revision)
    source_report = validate_xjtu_source(source)
    if not source_report.profile_matches:
        raise XjtuReferenceComparisonError(
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
    result = evaluate_xjtu_reference_hypotheses(
        train_vectors,
        validation_vectors,
        code_revision=code_revision,
        source_acquisition_count=source_report.acquisition_count,
    )
    write_xjtu_reference_comparison_result(result, output_path)
    return result


def evaluate_xjtu_reference_hypotheses(
    train_vectors: Sequence[VibrationFeatureVector],
    validation_vectors: Sequence[VibrationFeatureVector],
    *,
    code_revision: str,
    source_acquisition_count: int,
) -> XjtuReferenceComparisonResult:
    """Run H0 and H1 through one shared execution path and apply the frozen decision rule."""
    _validate_code_revision(code_revision)
    hypotheses = get_xjtu_reference_hypotheses()
    results: list[XjtuReferenceHypothesisResult] = []

    for config in hypotheses:
        preprocessing_state, fit_input = fit_xjtu_preprocessing_and_prepare_model_input(
            config,
            train_vectors,
        )
        model = fit_isolation_forest(config, fit_input)
        scores = model.score(
            prepare_xjtu_model_scoring_input(
                config,
                preprocessing_state,
                validation_vectors,
                partition=_PARTITION,
            )
        )
        evaluation = evaluate_xjtu_development_scores(config, validation_vectors, scores)
        results.append(
            _hypothesis_result(
                config,
                evaluation,
                validation_vectors,
                scores,
                complete_train_observation_count=fit_input.source_observation_count,
                reference_observation_count=fit_input.reference_observation_count,
                model_fit_observation_count=fit_input.fit_observation_count,
            )
        )

    materialized = tuple(results)
    selected = select_xjtu_reference_hypothesis(materialized)
    first = hypotheses[0]
    return XjtuReferenceComparisonResult(
        code_revision=code_revision,
        dataset_id=first.dataset_id,
        split_id=first.split_id,
        fold_id=first.fold_id,
        partition=_PARTITION,
        source_acquisition_count=source_acquisition_count,
        hypotheses=materialized,
        selected_experiment_id=selected.experiment_id,
        selected_reference_strategy=selected.reference_strategy,
    )


def select_xjtu_reference_hypothesis(
    hypotheses: Sequence[XjtuReferenceHypothesisResult],
) -> XjtuReferenceHypothesisResult:
    """Adopt the alternative reference only on a strict mean rank-probability improvement."""
    baseline = _single(hypotheses, _BASELINE_REFERENCE)
    alternative = _single(hypotheses, _ALTERNATIVE_REFERENCE)

    for hypothesis in (baseline, alternative):
        undefined = tuple(
            bearing.asset_id
            for bearing in hypothesis.bearing_results
            if bearing.late_vs_middle_rank_probability is None
        )
        if undefined or hypothesis.mean_bearing_late_vs_middle_rank_probability is None:
            raise XjtuReferenceComparisonError(
                "reference comparison requires a defined late_vs_middle_rank_probability for "
                f"every validation bearing; {hypothesis.reference_strategy} is undefined for "
                f"{sorted(undefined)}"
            )

    baseline_mean = baseline.mean_bearing_late_vs_middle_rank_probability
    alternative_mean = alternative.mean_bearing_late_vs_middle_rank_probability
    assert baseline_mean is not None and alternative_mean is not None
    return alternative if alternative_mean > baseline_mean else baseline


def write_xjtu_reference_comparison_result(
    result: XjtuReferenceComparisonResult,
    output_path: Path,
) -> None:
    """Write deterministic, reviewable JSON evidence for one reference comparison run."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_result_document(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _hypothesis_result(
    config: ExperimentConfig,
    evaluation: XjtuDevelopmentEvaluation,
    validation_vectors: Sequence[VibrationFeatureVector],
    scores: AnomalyScores,
    *,
    complete_train_observation_count: int,
    reference_observation_count: int,
    model_fit_observation_count: int,
) -> XjtuReferenceHypothesisResult:
    rho_by_asset = {
        bearing.asset_id: bearing.acquisition_order_spearman_rho
        for bearing in evaluation.bearing_results
    }
    condition_by_asset = {
        bearing.asset_id: bearing.operating_condition for bearing in evaluation.bearing_results
    }
    full_run_count_by_asset = {
        bearing.asset_id: bearing.observation_count for bearing in evaluation.bearing_results
    }
    segments = _validation_segment_scores(validation_vectors, scores)

    bearing_results = tuple(
        XjtuBearingReferenceEvidence(
            asset_id=asset_id,
            operating_condition=condition_by_asset[asset_id],
            full_run_observation_count=full_run_count_by_asset[asset_id],
            middle_third_observation_count=len(segments[asset_id][MIDDLE_THIRD]),
            late_third_observation_count=len(segments[asset_id][LATE_THIRD]),
            late_vs_middle_rank_probability=late_vs_middle_rank_probability(
                segments[asset_id][MIDDLE_THIRD],
                segments[asset_id][LATE_THIRD],
            ),
            acquisition_order_spearman_rho=rho_by_asset[asset_id],
        )
        for asset_id in sorted(rho_by_asset)
    )
    probabilities = tuple(bearing.late_vs_middle_rank_probability for bearing in bearing_results)
    mean_probability = (
        float(fmean(value for value in probabilities if value is not None))
        if probabilities and all(value is not None for value in probabilities)
        else None
    )

    return XjtuReferenceHypothesisResult(
        experiment_id=config.experiment_id,
        reference_strategy=config.reference_strategy.value,
        complete_train_observation_count=complete_train_observation_count,
        reference_observation_count=reference_observation_count,
        model_fit_observation_count=model_fit_observation_count,
        bearing_results=bearing_results,
        mean_bearing_late_vs_middle_rank_probability=mean_probability,
        mean_bearing_acquisition_order_spearman_rho=(
            evaluation.mean_bearing_acquisition_order_spearman_rho
        ),
    )


def _validation_segment_scores(
    vectors: Sequence[VibrationFeatureVector],
    scores: AnomalyScores,
) -> dict[str, dict[str, tuple[float, ...]]]:
    score_by_observation_id = dict(zip(scores.source_observation_ids, scores.scores, strict=True))
    ordered_by_asset: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for vector in vectors:
        acquisition_index = vector.metadata.get("acquisition_index")
        if not isinstance(acquisition_index, int) or isinstance(acquisition_index, bool):
            raise XjtuReferenceComparisonError(
                "XJTU validation feature vectors require a positive integer acquisition_index"
            )
        observation_id = f"{vector.asset_id}:acquisition-{acquisition_index}"
        if observation_id not in score_by_observation_id:
            raise XjtuReferenceComparisonError(
                f"validation anomaly scores are missing observation {observation_id!r}"
            )
        ordered_by_asset[vector.asset_id].append(
            (acquisition_index, score_by_observation_id[observation_id])
        )

    segments: dict[str, dict[str, tuple[float, ...]]] = {}
    for asset_id, observations in ordered_by_asset.items():
        run = sorted(observations, key=lambda item: item[0])
        buckets: dict[str, list[float]] = defaultdict(list)
        for position, (_, score) in enumerate(run):
            buckets[lifecycle_segment(position, len(run))].append(score)
        segments[asset_id] = {
            MIDDLE_THIRD: tuple(buckets[MIDDLE_THIRD]),
            LATE_THIRD: tuple(buckets[LATE_THIRD]),
        }
    return segments


def _single(
    hypotheses: Sequence[XjtuReferenceHypothesisResult],
    reference_strategy: ReferenceStrategy,
) -> XjtuReferenceHypothesisResult:
    matches = tuple(
        hypothesis
        for hypothesis in hypotheses
        if hypothesis.reference_strategy == reference_strategy.value
    )
    if len(matches) != 1:
        raise XjtuReferenceComparisonError(
            f"reference comparison requires exactly one {reference_strategy.value!r} hypothesis, "
            f"got {len(matches)}"
        )
    return matches[0]


def _validate_hypothesis_scope(configs: Sequence[ExperimentConfig]) -> None:
    if len(configs) != 2:
        raise XjtuReferenceComparisonError(
            f"reference comparison is frozen to exactly two hypotheses, got {len(configs)}"
        )
    observed = {config.reference_strategy for config in configs}
    if observed != {_BASELINE_REFERENCE, _ALTERNATIVE_REFERENCE}:
        raise XjtuReferenceComparisonError(
            "reference comparison must contain exactly the frozen H0 and H1 strategies"
        )

    baseline = next(
        config for config in configs if config.reference_strategy is _BASELINE_REFERENCE
    )
    for config in configs:
        if config.fold_id != _FOLD_ID:
            raise XjtuReferenceComparisonError(
                f"reference comparison received a candidate for {config.fold_id!r}"
            )
        fixed = (
            (
                "selected_features",
                tuple(config.selected_features),
                tuple(baseline.selected_features),
            ),
            ("sampling_policy_id", config.sampling_policy_id, baseline.sampling_policy_id),
            ("scaling_strategy", config.scaling_strategy, baseline.scaling_strategy),
            ("model_family", config.model_family, baseline.model_family),
            ("model_parameters", dict(config.model_parameters), dict(baseline.model_parameters)),
            ("random_seed", config.random_seed, baseline.random_seed),
        )
        for field_name, observed_value, expected in fixed:
            if observed_value != expected:
                raise XjtuReferenceComparisonError(
                    "reference comparison may only vary reference_strategy; "
                    f"{field_name} differs between hypotheses"
                )


def _validate_code_revision(value: str) -> None:
    if not _FULL_GIT_REVISION.fullmatch(value):
        raise XjtuReferenceComparisonError(
            "code_revision must be a full 40-character lowercase Git commit SHA"
        )


def _result_document(result: XjtuReferenceComparisonResult) -> dict[str, Any]:
    return {
        "schema_id": XJTU_REFERENCE_COMPARISON_SCHEMA_ID,
        "code_revision": result.code_revision,
        "dataset_id": result.dataset_id,
        "split_id": result.split_id,
        "fold_id": result.fold_id,
        "partition": result.partition,
        "source_acquisition_count": result.source_acquisition_count,
        "decision_rule": {
            "id": result.decision_rule_id,
            "primary": ("maximize bearing-equal mean late_vs_middle_rank_probability"),
            "adopt_alternative": ("only when strictly greater than all-train-observations"),
            "undefined_probability": "ineligible",
            "secondary_statistics_are_recorded_only": [
                "mean_bearing_acquisition_order_spearman_rho",
            ],
        },
        "selected_experiment_id": result.selected_experiment_id,
        "selected_reference_strategy": result.selected_reference_strategy,
        "hypotheses": [_hypothesis_document(item) for item in result.hypotheses],
    }


def _hypothesis_document(hypothesis: XjtuReferenceHypothesisResult) -> dict[str, Any]:
    return {
        "experiment_id": hypothesis.experiment_id,
        "reference_strategy": hypothesis.reference_strategy,
        "complete_train_observation_count": hypothesis.complete_train_observation_count,
        "reference_observation_count": hypothesis.reference_observation_count,
        "model_fit_observation_count": hypothesis.model_fit_observation_count,
        "mean_bearing_late_vs_middle_rank_probability": (
            hypothesis.mean_bearing_late_vs_middle_rank_probability
        ),
        "mean_bearing_acquisition_order_spearman_rho": (
            hypothesis.mean_bearing_acquisition_order_spearman_rho
        ),
        "validation_bearings": [
            {
                "asset_id": bearing.asset_id,
                "operating_condition": bearing.operating_condition,
                "full_run_observation_count": bearing.full_run_observation_count,
                "middle_third_observation_count": bearing.middle_third_observation_count,
                "late_third_observation_count": bearing.late_third_observation_count,
                "late_vs_middle_rank_probability": bearing.late_vs_middle_rank_probability,
                "acquisition_order_spearman_rho": bearing.acquisition_order_spearman_rho,
            }
            for bearing in hypothesis.bearing_results
        ],
    }
