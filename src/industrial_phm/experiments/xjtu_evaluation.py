"""XJTU-specific development evaluation for observation-level anomaly scores."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import StatisticsError, correlation, fmean
from typing import Literal

from industrial_phm.experiments.config import ExperimentConfig
from industrial_phm.experiments.xjtu import get_xjtu_reference_split
from industrial_phm.features import VibrationFeatureVector
from industrial_phm.models.output import AnomalyScores

_DATASET_ID = "xjtu-sy"


class XjtuDevelopmentEvaluationError(ValueError):
    """Raised when XJTU development-evaluation inputs violate the fold protocol."""


@dataclass(frozen=True, slots=True)
class XjtuBearingScoreEvaluation:
    """Acquisition-order association for one validation bearing run."""

    asset_id: str
    operating_condition: str
    observation_count: int
    acquisition_order_spearman_rho: float | None


@dataclass(frozen=True, slots=True)
class XjtuDevelopmentEvaluation:
    """Bearing-balanced descriptive evidence for one XJTU validation candidate."""

    experiment_id: str
    split_id: str
    fold_id: str
    bearing_results: tuple[XjtuBearingScoreEvaluation, ...]
    mean_bearing_acquisition_order_spearman_rho: float | None
    partition: Literal["validation"] = field(default="validation", init=False)


def evaluate_xjtu_development_scores(
    config: ExperimentConfig,
    vectors: Sequence[VibrationFeatureVector],
    anomaly_scores: AnomalyScores,
) -> XjtuDevelopmentEvaluation:
    """Summarize validation anomaly-score trajectories with equal bearing weight."""
    if config.dataset_id != _DATASET_ID:
        raise XjtuDevelopmentEvaluationError(
            f"XJTU development evaluation requires dataset_id {_DATASET_ID!r}"
        )
    if anomaly_scores.experiment_id != config.experiment_id:
        raise XjtuDevelopmentEvaluationError(
            "anomaly score experiment_id does not match experiment config"
        )
    if not vectors:
        raise XjtuDevelopmentEvaluationError(
            "XJTU development evaluation requires validation feature vectors"
        )

    split = get_xjtu_reference_split()
    if config.split_id != split.split_id:
        raise XjtuDevelopmentEvaluationError(
            "XJTU development evaluation config references an unknown split"
        )
    fold = next(
        (candidate for candidate in split.folds if candidate.fold_id == config.fold_id),
        None,
    )
    if fold is None:
        raise XjtuDevelopmentEvaluationError(
            f"XJTU development evaluation config references an unknown fold: {config.fold_id!r}"
        )

    expected_assets = set(fold.validation)
    observed_assets = {vector.asset_id for vector in vectors}
    if observed_assets != expected_assets:
        raise XjtuDevelopmentEvaluationError(
            "XJTU development evaluation requires exactly the configured validation bearings; "
            f"missing={sorted(expected_assets - observed_assets)}, "
            f"unexpected={sorted(observed_assets - expected_assets)}"
        )

    score_by_observation_id = dict(
        zip(anomaly_scores.source_observation_ids, anomaly_scores.scores, strict=True)
    )
    vector_ids: list[str] = []
    observations_by_asset: dict[str, list[tuple[int, str, float]]] = defaultdict(list)

    for vector_index, vector in enumerate(vectors):
        if vector.feature_set_id != config.feature_set_id:
            raise XjtuDevelopmentEvaluationError(
                f"XJTU validation feature vector {vector_index} feature_set_id "
                "does not match experiment config"
            )
        if vector.metadata.get("dataset_id") != _DATASET_ID:
            raise XjtuDevelopmentEvaluationError(
                f"XJTU validation feature vector {vector_index} must preserve dataset_id"
            )

        acquisition_index = _positive_acquisition_index(vector, vector_index=vector_index)
        operating_condition = _operating_condition(vector, vector_index=vector_index)
        observation_id = f"{vector.asset_id}:acquisition-{acquisition_index}"
        vector_ids.append(observation_id)

        if observation_id in score_by_observation_id:
            observations_by_asset[vector.asset_id].append(
                (
                    acquisition_index,
                    operating_condition,
                    score_by_observation_id[observation_id],
                )
            )

    if len(vector_ids) != len(set(vector_ids)):
        raise XjtuDevelopmentEvaluationError(
            "XJTU validation feature vectors must have unique source observation identities"
        )

    vector_id_set = set(vector_ids)
    score_id_set = set(score_by_observation_id)
    if vector_id_set != score_id_set:
        raise XjtuDevelopmentEvaluationError(
            "anomaly scores must align exactly with XJTU validation feature vectors; "
            f"missing={sorted(vector_id_set - score_id_set)[:10]}, "
            f"unexpected={sorted(score_id_set - vector_id_set)[:10]}"
        )

    bearing_results = tuple(
        _evaluate_bearing(asset_id, observations_by_asset[asset_id])
        for asset_id in sorted(expected_assets)
    )
    correlations = tuple(result.acquisition_order_spearman_rho for result in bearing_results)
    mean_rho = (
        float(fmean(correlation for correlation in correlations if correlation is not None))
        if all(correlation is not None for correlation in correlations)
        else None
    )

    return XjtuDevelopmentEvaluation(
        experiment_id=config.experiment_id,
        split_id=config.split_id,
        fold_id=config.fold_id,
        bearing_results=bearing_results,
        mean_bearing_acquisition_order_spearman_rho=mean_rho,
    )


def _evaluate_bearing(
    asset_id: str,
    observations: Sequence[tuple[int, str, float]],
) -> XjtuBearingScoreEvaluation:
    conditions = {condition for _, condition, _ in observations}
    if len(conditions) != 1:
        raise XjtuDevelopmentEvaluationError(
            f"validation bearing {asset_id} must have one operating_condition"
        )

    ordered = sorted(observations, key=lambda item: item[0])
    acquisition_indices = tuple(index for index, _, _ in ordered)
    scores = tuple(score for _, _, score in ordered)
    return XjtuBearingScoreEvaluation(
        asset_id=asset_id,
        operating_condition=next(iter(conditions)),
        observation_count=len(ordered),
        acquisition_order_spearman_rho=spearman_rho(acquisition_indices, scores),
    )


@dataclass(frozen=True, slots=True)
class XjtuBearingScoreSeries:
    """One bearing run's anomaly scores in ``1..N`` acquisition order."""

    asset_id: str
    operating_condition: str
    acquisition_indices: tuple[int, ...]
    scores: tuple[float, ...]

    @property
    def observation_count(self) -> int:
        """Return how many acquisitions this run contributes."""
        return len(self.scores)


def align_xjtu_bearing_scores(
    vectors: Sequence[VibrationFeatureVector],
    anomaly_scores: AnomalyScores,
) -> tuple[XjtuBearingScoreSeries, ...]:
    """Align scores back to their bearing runs in lifecycle order.

    Pure alignment shared by every partition. It does not decide which bearing runs belong to a
    partition: callers validate partition membership before scoring.
    """
    score_by_observation_id = dict(
        zip(anomaly_scores.source_observation_ids, anomaly_scores.scores, strict=True)
    )
    grouped: dict[str, list[tuple[int, str, float]]] = defaultdict(list)
    seen: set[str] = set()

    for vector_index, vector in enumerate(vectors):
        acquisition_index = _positive_acquisition_index(vector, vector_index=vector_index)
        observation_id = f"{vector.asset_id}:acquisition-{acquisition_index}"
        if observation_id in seen:
            raise XjtuDevelopmentEvaluationError(
                f"XJTU feature vectors must have unique source observation identities; "
                f"{observation_id!r} repeats"
            )
        seen.add(observation_id)
        if observation_id not in score_by_observation_id:
            raise XjtuDevelopmentEvaluationError(
                f"anomaly scores are missing observation {observation_id!r}"
            )
        grouped[vector.asset_id].append(
            (
                acquisition_index,
                _operating_condition(vector, vector_index=vector_index),
                score_by_observation_id[observation_id],
            )
        )

    if seen != set(score_by_observation_id):
        raise XjtuDevelopmentEvaluationError(
            "anomaly scores must align exactly with the supplied XJTU feature vectors"
        )

    series: list[XjtuBearingScoreSeries] = []
    for asset_id in sorted(grouped):
        ordered = sorted(grouped[asset_id], key=lambda item: item[0])
        conditions = {condition for _, condition, _ in ordered}
        if len(conditions) != 1:
            raise XjtuDevelopmentEvaluationError(
                f"bearing {asset_id} must have exactly one operating_condition"
            )
        series.append(
            XjtuBearingScoreSeries(
                asset_id=asset_id,
                operating_condition=next(iter(conditions)),
                acquisition_indices=tuple(index for index, _, _ in ordered),
                scores=tuple(score for _, _, score in ordered),
            )
        )
    return tuple(series)


def spearman_rho(
    left: Sequence[int | float],
    right: Sequence[int | float],
) -> float | None:
    """Return the rank correlation of two aligned sequences, or None when it is undefined."""
    if len(left) != len(right) or len(left) < 2:
        raise XjtuDevelopmentEvaluationError(
            "Spearman correlation requires equal sequences with at least two values"
        )
    try:
        return float(correlation(_average_ranks(left), _average_ranks(right)))
    except StatisticsError:
        return None


def late_vs_middle_rank_probability(
    middle_scores: Sequence[float],
    late_scores: Sequence[float],
) -> float | None:
    """Return P(late > middle) + 0.5 * P(late = middle) over all cross-segment pairs.

    ``0.5`` means the late segment holds no consistent rank advantage over the middle one.
    Returns ``None`` when either segment is empty, so the statistic stays undefined instead of
    being imputed. Computed from mid-ranks of the pooled scores, which is exactly the pairwise
    average of ``1.0`` / ``0.5`` / ``0.0`` without materializing every pair.
    """
    middle_count = len(middle_scores)
    late_count = len(late_scores)
    if middle_count == 0 or late_count == 0:
        return None

    pooled_ranks = _average_ranks(tuple(middle_scores) + tuple(late_scores))
    late_rank_sum = math.fsum(pooled_ranks[middle_count:])
    favourable = late_rank_sum - late_count * (late_count + 1) / 2.0
    return float(favourable / (middle_count * late_count))


def _average_ranks(values: Sequence[int | float]) -> tuple[float, ...]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(indexed)
    position = 0
    while position < len(indexed):
        end = position + 1
        while end < len(indexed) and indexed[end][1] == indexed[position][1]:
            end += 1
        average_rank = ((position + 1) + end) / 2.0
        for ranked_position in range(position, end):
            ranks[indexed[ranked_position][0]] = average_rank
        position = end
    return tuple(ranks)


def _positive_acquisition_index(
    vector: VibrationFeatureVector,
    *,
    vector_index: int,
) -> int:
    value = vector.metadata.get("acquisition_index")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise XjtuDevelopmentEvaluationError(
            f"XJTU validation feature vector {vector_index} requires acquisition_index"
        )
    return value


def _operating_condition(
    vector: VibrationFeatureVector,
    *,
    vector_index: int,
) -> str:
    value = vector.metadata.get("operating_condition")
    if not isinstance(value, str) or not value.strip():
        raise XjtuDevelopmentEvaluationError(
            f"XJTU validation feature vector {vector_index} requires operating_condition"
        )
    return value
