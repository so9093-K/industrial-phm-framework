"""XJTU-specific development evaluation for observation-level anomaly scores."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import fmean
from typing import Literal

from industrial_phm.adapters import get_xjtu_expected_acquisition_count
from industrial_phm.experiments.config import ExperimentConfig
from industrial_phm.experiments.xjtu import get_xjtu_reference_split
from industrial_phm.features import VibrationFeatureVector
from industrial_phm.models.output import AnomalyScores

_DATASET_ID = "xjtu-sy"


class XjtuDevelopmentEvaluationError(ValueError):
    """Raised when XJTU development-evaluation inputs violate the fold protocol."""


@dataclass(frozen=True, slots=True)
class XjtuBearingScoreEvaluation:
    """Lifecycle-order association for one validation bearing run."""

    asset_id: str
    operating_condition: str
    observation_count: int
    acquisition_order_spearman_rho: float | None

    def __post_init__(self) -> None:
        _validate_text(self.asset_id, "asset_id")
        _validate_text(self.operating_condition, "operating_condition")
        if (
            isinstance(self.observation_count, bool)
            or not isinstance(self.observation_count, int)
            or self.observation_count < 2
        ):
            raise XjtuDevelopmentEvaluationError(
                "bearing observation_count must be an integer of at least 2"
            )
        rho = self.acquisition_order_spearman_rho
        if rho is not None and (not math.isfinite(rho) or not -1.0 <= rho <= 1.0):
            raise XjtuDevelopmentEvaluationError(
                "acquisition_order_spearman_rho must be finite and within [-1, 1]"
            )


@dataclass(frozen=True, slots=True)
class XjtuDevelopmentEvaluation:
    """Bearing-balanced descriptive evidence for one XJTU validation candidate."""

    experiment_id: str
    split_id: str
    fold_id: str
    bearing_results: Sequence[XjtuBearingScoreEvaluation]
    partition: Literal["validation"] = field(default="validation", init=False)
    mean_bearing_acquisition_order_spearman_rho: float | None = field(init=False)

    def __post_init__(self) -> None:
        for field_name in ("experiment_id", "split_id", "fold_id"):
            _validate_text(getattr(self, field_name), field_name)

        bearing_results = tuple(self.bearing_results)
        if not bearing_results:
            raise XjtuDevelopmentEvaluationError(
                "development evaluation requires at least one bearing result"
            )
        asset_ids = tuple(result.asset_id for result in bearing_results)
        if len(asset_ids) != len(set(asset_ids)):
            raise XjtuDevelopmentEvaluationError(
                "development evaluation bearing_results must contain unique asset_id values"
            )

        correlations = tuple(
            result.acquisition_order_spearman_rho for result in bearing_results
        )
        mean_rho = (
            float(fmean(correlation for correlation in correlations if correlation is not None))
            if all(correlation is not None for correlation in correlations)
            else None
        )

        object.__setattr__(self, "bearing_results", bearing_results)
        object.__setattr__(
            self,
            "mean_bearing_acquisition_order_spearman_rho",
            mean_rho,
        )


def evaluate_xjtu_development_scores(
    config: ExperimentConfig,
    vectors: Sequence[VibrationFeatureVector],
    anomaly_scores: AnomalyScores,
) -> XjtuDevelopmentEvaluation:
    """Evaluate fold validation scores per bearing without acquisition-count weighting."""
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
        zip(
            anomaly_scores.source_observation_ids,
            anomaly_scores.scores,
            strict=True,
        )
    )
    vector_ids: list[str] = []
    vectors_by_asset: dict[str, list[tuple[int, VibrationFeatureVector]]] = defaultdict(list)
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
        acquisition_index = _acquisition_index(vector, vector_index=vector_index)
        observation_id = f"{vector.asset_id}:acquisition-{acquisition_index}"
        vector_ids.append(observation_id)
        vectors_by_asset[vector.asset_id].append((acquisition_index, vector))

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
        _evaluate_bearing(
            asset_id,
            vectors_by_asset[asset_id],
            score_by_observation_id,
        )
        for asset_id in sorted(expected_assets)
    )
    return XjtuDevelopmentEvaluation(
        experiment_id=config.experiment_id,
        split_id=config.split_id,
        fold_id=config.fold_id,
        bearing_results=bearing_results,
    )


def _evaluate_bearing(
    asset_id: str,
    indexed_vectors: Sequence[tuple[int, VibrationFeatureVector]],
    score_by_observation_id: dict[str, float],
) -> XjtuBearingScoreEvaluation:
    expected_count = get_xjtu_expected_acquisition_count(asset_id)
    observed_indices = {index for index, _ in indexed_vectors}
    expected_indices = set(range(1, expected_count + 1))
    if observed_indices != expected_indices:
        raise XjtuDevelopmentEvaluationError(
            f"validation bearing {asset_id} must contain acquisition sequence 1..{expected_count}"
        )

    conditions = {
        vector.metadata.get("operating_condition")
        for _, vector in indexed_vectors
    }
    if len(conditions) != 1:
        raise XjtuDevelopmentEvaluationError(
            f"validation bearing {asset_id} must have one operating_condition"
        )
    operating_condition = next(iter(conditions))
    if not isinstance(operating_condition, str) or not operating_condition.strip():
        raise XjtuDevelopmentEvaluationError(
            f"validation bearing {asset_id} requires operating_condition metadata"
        )

    ordered = sorted(indexed_vectors, key=lambda item: item[0])
    acquisition_indices = tuple(index for index, _ in ordered)
    scores = tuple(
        score_by_observation_id[f"{asset_id}:acquisition-{index}"]
        for index in acquisition_indices
    )
    return XjtuBearingScoreEvaluation(
        asset_id=asset_id,
        operating_condition=operating_condition,
        observation_count=len(ordered),
        acquisition_order_spearman_rho=_spearman_rho(acquisition_indices, scores),
    )


def _spearman_rho(
    left: Sequence[int | float],
    right: Sequence[int | float],
) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        raise XjtuDevelopmentEvaluationError(
            "Spearman correlation requires equal sequences with at least two values"
        )
    left_ranks = _average_ranks(left)
    right_ranks = _average_ranks(right)
    left_mean = fmean(left_ranks)
    right_mean = fmean(right_ranks)
    left_centered = tuple(value - left_mean for value in left_ranks)
    right_centered = tuple(value - right_mean for value in right_ranks)
    denominator = math.sqrt(
        math.fsum(value * value for value in left_centered)
        * math.fsum(value * value for value in right_centered)
    )
    if denominator == 0.0:
        return None
    correlation = math.fsum(
        left_value * right_value
        for left_value, right_value in zip(left_centered, right_centered, strict=True)
    ) / denominator
    return max(-1.0, min(1.0, float(correlation)))


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
            original_index = indexed[ranked_position][0]
            ranks[original_index] = average_rank
        position = end
    return tuple(ranks)


def _acquisition_index(
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


def _validate_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise XjtuDevelopmentEvaluationError(
            f"{field_name} must be a trimmed non-empty string"
        )
