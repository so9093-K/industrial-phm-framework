"""Presentation-independent anomaly evidence summary for user-facing surfaces."""

from __future__ import annotations

from dataclasses import dataclass

from industrial_phm.analysis.intervals import (
    ReviewScoreThreshold,
    ScoreExceedanceInterval,
    derive_early_scored_window_review_threshold,
    score_exceedance_intervals,
)
from industrial_phm.analysis.view import (
    AnalysisAssetEvidence,
    AnalysisObservation,
    AnalysisView,
)


@dataclass(frozen=True, slots=True)
class RankedFeatureResidual:
    """One feature residual ordered for user-facing evidence review."""

    feature_name: str
    mean_squared_residual: float


@dataclass(frozen=True, slots=True)
class AnomalyAssetSummary:
    """Derived review summary over one validated anomaly evidence scope."""

    asset: AnalysisAssetEvidence
    review_threshold: ReviewScoreThreshold
    review_intervals: tuple[ScoreExceedanceInterval, ...]
    strongest_review_interval: ScoreExceedanceInterval | None
    ranked_observations: tuple[AnalysisObservation, ...]
    ranked_feature_residuals: tuple[RankedFeatureResidual, ...]

    @property
    def review_interval_count(self) -> int:
        """Return the number of descriptive review intervals."""
        return len(self.review_intervals)


def summarize_anomaly_for_asset(
    analysis: AnalysisView,
    asset_id: str,
    *,
    evidence_limit: int = 10,
) -> AnomalyAssetSummary:
    """Summarize validated anomaly evidence without creating new PHM semantics."""
    if (
        isinstance(evidence_limit, bool)
        or not isinstance(evidence_limit, int)
        or evidence_limit <= 0
    ):
        raise ValueError("evidence_limit must be a positive integer")

    anomaly = analysis.require_anomaly_evidence()
    asset = anomaly.asset(asset_id)
    threshold = derive_early_scored_window_review_threshold(asset)
    intervals = score_exceedance_intervals(asset, threshold)
    strongest = max(intervals, key=lambda interval: interval.peak_score, default=None)
    ranked_observations = tuple(
        sorted(
            asset.observations,
            key=lambda observation: observation.score,
            reverse=True,
        )[:evidence_limit]
    )
    ranked_feature_residuals = tuple(
        RankedFeatureResidual(
            feature_name=feature_name,
            mean_squared_residual=residual,
        )
        for feature_name, residual in sorted(
            zip(anomaly.feature_names, asset.mean_feature_residuals, strict=True),
            key=lambda pair: pair[1],
            reverse=True,
        )
    )

    return AnomalyAssetSummary(
        asset=asset,
        review_threshold=threshold,
        review_intervals=intervals,
        strongest_review_interval=strongest,
        ranked_observations=ranked_observations,
        ranked_feature_residuals=ranked_feature_residuals,
    )
