"""XJTU-specific retrospective evaluation for LSTM reconstruction scores."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import fmean
from typing import Literal

from industrial_phm.adapters import get_xjtu_expected_acquisition_count
from industrial_phm.experiments.score_statistics import (
    ScoreStatisticsError,
    late_vs_middle_rank_probability,
    spearman_rho,
)
from industrial_phm.experiments.xjtu import get_xjtu_reference_split
from industrial_phm.experiments.xjtu_lifecycle import (
    LATE_THIRD,
    MIDDLE_THIRD,
    lifecycle_segment,
)
from industrial_phm.experiments.xjtu_lstm import get_xjtu_lstm_development_configuration
from industrial_phm.experiments.xjtu_sequence import (
    XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID,
    XJTU_LSTM_SEQUENCE_SPEC,
)
from industrial_phm.models.reconstruction_scoring import ReconstructionScores


class XjtuLstmDevelopmentEvaluationError(ValueError):
    """Raised when LSTM reconstruction scores violate the frozen XJTU evaluation scope."""


@dataclass(frozen=True, slots=True)
class XjtuLstmBearingEvaluation:
    """Retrospective reconstruction-score evidence for one validation bearing."""

    asset_id: str
    source_acquisition_count: int
    score_window_count: int
    dropped_prefix_count: int
    acquisition_order_spearman_rho: float
    late_vs_middle_rank_probability: float
    mean_feature_residuals: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class XjtuLstmDevelopmentEvaluation:
    """Bearing-first descriptive evidence for the frozen XJTU LSTM development protocol."""

    experiment_id: str
    split_id: str
    fold_id: str
    feature_names: tuple[str, ...]
    bearing_results: tuple[XjtuLstmBearingEvaluation, ...]
    mean_bearing_acquisition_order_spearman_rho: float
    mean_bearing_late_vs_middle_rank_probability: float
    mean_bearing_feature_residuals: tuple[float, ...]
    partition: Literal["validation"] = field(default="validation", init=False)


def evaluate_xjtu_lstm_development_scores(
    scores: ReconstructionScores,
) -> XjtuLstmDevelopmentEvaluation:
    """Evaluate aligned LSTM scores without redefining the original XJTU lifecycle."""
    if not isinstance(scores, ReconstructionScores):
        raise XjtuLstmDevelopmentEvaluationError(
            "XJTU LSTM development evaluation requires ReconstructionScores"
        )

    config = get_xjtu_lstm_development_configuration()
    split = get_xjtu_reference_split()
    fold = next(candidate for candidate in split.folds if candidate.fold_id == config.fold_id)

    if scores.experiment_id != XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID:
        raise XjtuLstmDevelopmentEvaluationError(
            "reconstruction scores must match the frozen XJTU LSTM protocol identity"
        )
    if scores.feature_set_id != config.feature_set_id:
        raise XjtuLstmDevelopmentEvaluationError(
            "reconstruction score feature_set_id must match the XJTU LSTM configuration"
        )
    if tuple(scores.feature_names) != tuple(config.selected_features):
        raise XjtuLstmDevelopmentEvaluationError(
            "reconstruction score feature schema must match the XJTU LSTM configuration"
        )
    if scores.spec != XJTU_LSTM_SEQUENCE_SPEC:
        raise XjtuLstmDevelopmentEvaluationError(
            "reconstruction score window spec must match the frozen XJTU LSTM protocol"
        )
    if any(partition != "validation" for partition in scores.partition_ids):
        raise XjtuLstmDevelopmentEvaluationError(
            "XJTU LSTM development evaluation requires validation scores only"
        )

    expected_assets = tuple(fold.validation)
    observed_assets = set(scores.asset_ids)
    if observed_assets != set(expected_assets):
        raise XjtuLstmDevelopmentEvaluationError(
            "XJTU LSTM development evaluation requires exactly the configured validation "
            f"bearings; missing={sorted(set(expected_assets) - observed_assets)}, "
            f"unexpected={sorted(observed_assets - set(expected_assets))}"
        )

    grouped: dict[
        str,
        list[tuple[int, float, tuple[float, ...], str]],
    ] = defaultdict(list)
    for (
        sequence_id,
        asset_id,
        source_observation_id,
        position,
        score,
        feature_residuals,
    ) in zip(
        scores.sequence_ids,
        scores.asset_ids,
        scores.aligned_source_observation_ids,
        scores.aligned_source_positions,
        scores.scores,
        scores.feature_residuals,
        strict=True,
    ):
        if sequence_id != asset_id:
            raise XjtuLstmDevelopmentEvaluationError(
                "XJTU LSTM score sequence_id must equal its bearing asset_id"
            )
        expected_source_id = f"{asset_id}:acquisition-{position}"
        if source_observation_id != expected_source_id:
            raise XjtuLstmDevelopmentEvaluationError(
                "XJTU LSTM score source identity must match its aligned acquisition position"
            )
        grouped[asset_id].append((position, score, tuple(feature_residuals), source_observation_id))

    bearing_results = tuple(
        _evaluate_bearing(
            asset_id,
            grouped[asset_id],
            feature_count=len(scores.feature_names),
        )
        for asset_id in expected_assets
    )

    correlations = tuple(result.acquisition_order_spearman_rho for result in bearing_results)
    rank_probabilities = tuple(result.late_vs_middle_rank_probability for result in bearing_results)
    feature_count = len(scores.feature_names)
    mean_feature_residuals = tuple(
        float(fmean(result.mean_feature_residuals[index] for result in bearing_results))
        for index in range(feature_count)
    )

    return XjtuLstmDevelopmentEvaluation(
        experiment_id=scores.experiment_id,
        split_id=config.split_id,
        fold_id=config.fold_id,
        feature_names=tuple(scores.feature_names),
        bearing_results=bearing_results,
        mean_bearing_acquisition_order_spearman_rho=float(fmean(correlations)),
        mean_bearing_late_vs_middle_rank_probability=float(fmean(rank_probabilities)),
        mean_bearing_feature_residuals=mean_feature_residuals,
    )


def _evaluate_bearing(
    asset_id: str,
    rows: Sequence[tuple[int, float, tuple[float, ...], str]],
    *,
    feature_count: int,
) -> XjtuLstmBearingEvaluation:
    source_count = get_xjtu_expected_acquisition_count(asset_id)
    expected_positions = tuple(
        range(
            XJTU_LSTM_SEQUENCE_SPEC.length,
            source_count + 1,
            XJTU_LSTM_SEQUENCE_SPEC.stride,
        )
    )
    ordered = sorted(rows, key=lambda item: item[0])
    positions = tuple(position for position, _, _, _ in ordered)
    if positions != expected_positions:
        raise XjtuLstmDevelopmentEvaluationError(
            f"{asset_id} requires exact right-edge score coverage from "
            f"{expected_positions[0]} through {expected_positions[-1]}"
        )

    bearing_scores = tuple(score for _, score, _, _ in ordered)
    middle_scores = tuple(
        score
        for position, score, _, _ in ordered
        if lifecycle_segment(position - 1, source_count) == MIDDLE_THIRD
    )
    late_scores = tuple(
        score
        for position, score, _, _ in ordered
        if lifecycle_segment(position - 1, source_count) == LATE_THIRD
    )
    try:
        correlation = spearman_rho(positions, bearing_scores)
    except ScoreStatisticsError as error:
        raise XjtuLstmDevelopmentEvaluationError(str(error)) from error
    rank_probability = late_vs_middle_rank_probability(middle_scores, late_scores)
    if correlation is None or rank_probability is None:
        raise XjtuLstmDevelopmentEvaluationError(
            f"XJTU LSTM development statistic is undefined for {asset_id}"
        )

    feature_residuals = tuple(
        float(fmean(row[index] for _, _, row, _ in ordered)) for index in range(feature_count)
    )
    return XjtuLstmBearingEvaluation(
        asset_id=asset_id,
        source_acquisition_count=source_count,
        score_window_count=len(ordered),
        dropped_prefix_count=expected_positions[0] - 1,
        acquisition_order_spearman_rho=correlation,
        late_vs_middle_rank_probability=rank_probability,
        mean_feature_residuals=feature_residuals,
    )

