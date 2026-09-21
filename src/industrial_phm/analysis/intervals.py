"""Transparent review thresholds and score-exceedance intervals."""

from __future__ import annotations

import math
from dataclasses import dataclass

from industrial_phm.analysis.view import AnalysisAssetEvidence, AnalysisObservation


class ScoreIntervalError(ValueError):
    """Raised when a review-threshold or interval contract is invalid."""


@dataclass(frozen=True, slots=True)
class ReviewScoreThreshold:
    """Descriptive score threshold for retrospective review, not PHM state detection."""

    policy_id: str
    value: float
    quantile: float
    reference_observation_count: int
    reference_scope: str
    semantics: str

    def __post_init__(self) -> None:
        if not self.policy_id.strip() or self.policy_id != self.policy_id.strip():
            raise ScoreIntervalError("policy_id must be a trimmed non-empty string")
        if not math.isfinite(self.value):
            raise ScoreIntervalError("threshold value must be finite")
        if not 0.0 < self.quantile < 1.0:
            raise ScoreIntervalError("quantile must be in (0, 1)")
        if self.reference_observation_count <= 0:
            raise ScoreIntervalError("reference_observation_count must be positive")
        if not self.reference_scope.strip() or self.reference_scope != self.reference_scope.strip():
            raise ScoreIntervalError("reference_scope must be a trimmed non-empty string")
        if not self.semantics.strip() or self.semantics != self.semantics.strip():
            raise ScoreIntervalError("semantics must be a trimmed non-empty string")


@dataclass(frozen=True, slots=True)
class ScoreExceedanceInterval:
    """One contiguous run of observations above a descriptive review threshold."""

    asset_id: str
    start_acquisition_index: int
    end_acquisition_index: int
    observation_count: int
    peak_score: float
    mean_score: float
    source_observation_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.asset_id.strip() or self.asset_id != self.asset_id.strip():
            raise ScoreIntervalError("asset_id must be a trimmed non-empty string")
        if self.start_acquisition_index <= 0 or self.end_acquisition_index <= 0:
            raise ScoreIntervalError("acquisition indices must be positive")
        if self.end_acquisition_index < self.start_acquisition_index:
            raise ScoreIntervalError("end_acquisition_index must not precede start")
        if self.observation_count <= 0:
            raise ScoreIntervalError("observation_count must be positive")
        if self.observation_count != len(self.source_observation_ids):
            raise ScoreIntervalError(
                "observation_count must match source_observation_ids population"
            )
        if not math.isfinite(self.peak_score) or not math.isfinite(self.mean_score):
            raise ScoreIntervalError("interval scores must be finite")
        if self.peak_score < self.mean_score:
            raise ScoreIntervalError("peak_score must be greater than or equal to mean_score")


_EARLY_THIRD_QUANTILE_POLICY_ID = "early-scored-windows-nearest-rank-quantile-v1"
_REVIEW_THRESHOLD_SEMANTICS = (
    "retrospective review threshold derived from early scored windows; "
    "not a validated normal/fault state threshold"
)


def derive_early_scored_window_review_threshold(
    asset: AnalysisAssetEvidence,
    *,
    quantile: float = 0.95,
) -> ReviewScoreThreshold:
    """Derive a deterministic review threshold from the earliest third of scored windows."""
    if not 0.0 < quantile < 1.0:
        raise ScoreIntervalError("quantile must be in (0, 1)")
    observations = tuple(asset.observations)
    if len(observations) < 3:
        raise ScoreIntervalError("at least three scored observations are required")

    reference_count = max(1, len(observations) // 3)
    reference = observations[:reference_count]
    ordered_scores = sorted(observation.score for observation in reference)
    rank = max(1, math.ceil(quantile * len(ordered_scores)))
    value = ordered_scores[rank - 1]

    return ReviewScoreThreshold(
        policy_id=_EARLY_THIRD_QUANTILE_POLICY_ID,
        value=value,
        quantile=quantile,
        reference_observation_count=reference_count,
        reference_scope="earliest-third-of-recorded-scored-windows",
        semantics=_REVIEW_THRESHOLD_SEMANTICS,
    )


def score_exceedance_intervals(
    asset: AnalysisAssetEvidence,
    threshold: ReviewScoreThreshold,
) -> tuple[ScoreExceedanceInterval, ...]:
    """Group contiguous acquisition-aligned observations whose score exceeds the threshold."""
    if threshold.reference_observation_count >= len(asset.observations):
        raise ScoreIntervalError(
            "review threshold reference scope must leave observations for interval review"
        )

    runs: list[list[AnalysisObservation]] = []
    current: list[AnalysisObservation] = []
    review_observations = asset.observations[threshold.reference_observation_count :]

    for observation in review_observations:
        exceeds = observation.score > threshold.value
        contiguous = (
            not current or observation.acquisition_index == current[-1].acquisition_index + 1
        )
        if exceeds and contiguous:
            current.append(observation)
        elif exceeds:
            runs.append(current)
            current = [observation]
        elif current:
            runs.append(current)
            current = []

    if current:
        runs.append(current)

    return tuple(_interval(asset.asset_id, run) for run in runs if run)


def _interval(
    asset_id: str,
    observations: list[AnalysisObservation],
) -> ScoreExceedanceInterval:
    scores = tuple(observation.score for observation in observations)
    return ScoreExceedanceInterval(
        asset_id=asset_id,
        start_acquisition_index=observations[0].acquisition_index,
        end_acquisition_index=observations[-1].acquisition_index,
        observation_count=len(observations),
        peak_score=max(scores),
        mean_score=sum(scores) / len(scores),
        source_observation_ids=tuple(
            observation.source_observation_id for observation in observations
        ),
    )
