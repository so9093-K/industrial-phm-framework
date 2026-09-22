from pathlib import Path

import pytest

from industrial_phm.analysis import (
    AnalysisViewError,
    summarize_anomaly_for_asset,
)
from industrial_phm.analysis.loader import load_analysis_view

_REPOSITORY_ROOT = Path(__file__).parents[2]
_RESULT = (
    _REPOSITORY_ROOT
    / "docs"
    / "research"
    / "results"
    / "xjtu-sy-lstm-autoencoder-fold-1-development-v1.json"
)


def test_anomaly_summary_orders_review_evidence_without_changing_source_values() -> None:
    analysis = load_analysis_view(_RESULT)

    summary = summarize_anomaly_for_asset(analysis, "Bearing1_2")

    assert summary.asset.asset_id == "Bearing1_2"
    assert summary.review_interval_count == len(summary.review_intervals)
    assert summary.review_threshold.reference_observation_count > 0
    assert summary.strongest_review_interval == max(
        summary.review_intervals,
        key=lambda interval: interval.peak_score,
        default=None,
    )
    assert tuple(item.score for item in summary.ranked_observations) == tuple(
        sorted((item.score for item in summary.ranked_observations), reverse=True)
    )
    assert tuple(item.mean_squared_residual for item in summary.ranked_feature_residuals) == tuple(
        sorted(
            (item.mean_squared_residual for item in summary.ranked_feature_residuals),
            reverse=True,
        )
    )


def test_anomaly_summary_rejects_unknown_asset() -> None:
    analysis = load_analysis_view(_RESULT)

    with pytest.raises(AnalysisViewError, match="Bearing9_9"):
        summarize_anomaly_for_asset(analysis, "Bearing9_9")


@pytest.mark.parametrize("evidence_limit", [0, -1, True])
def test_anomaly_summary_rejects_invalid_evidence_limit(evidence_limit: object) -> None:
    analysis = load_analysis_view(_RESULT)

    with pytest.raises(ValueError, match="positive integer"):
        summarize_anomaly_for_asset(
            analysis,
            "Bearing1_2",
            evidence_limit=evidence_limit,  # type: ignore[arg-type]
        )
