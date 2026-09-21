import pytest

from industrial_phm.analysis import (
    AnalysisAssetEvidence,
    AnalysisObservation,
    ScoreIntervalError,
    derive_early_scored_window_review_threshold,
    score_exceedance_intervals,
)


def _asset(scores: tuple[float, ...], *, positions: tuple[int, ...] | None = None) -> AnalysisAssetEvidence:
    observed_positions = positions or tuple(range(1, len(scores) + 1))
    observations = tuple(
        AnalysisObservation(
            source_observation_id=f"bearing:acquisition-{position}",
            acquisition_index=position,
            score=score,
            feature_residuals=(score, score / 2.0),
        )
        for position, score in zip(observed_positions, scores, strict=True)
    )
    return AnalysisAssetEvidence(
        asset_id="BearingX",
        score_window_count=len(observations),
        acquisition_order_spearman_rho=0.5,
        late_vs_middle_rank_probability=0.7,
        mean_feature_residuals=(1.0, 0.5),
        observations=observations,
    )


def test_review_threshold_uses_only_earliest_third_of_scored_windows() -> None:
    asset = _asset((1.0, 2.0, 3.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0))

    threshold = derive_early_scored_window_review_threshold(asset, quantile=0.95)

    assert threshold.policy_id == "early-scored-windows-nearest-rank-quantile-v1"
    assert threshold.value == pytest.approx(3.0)
    assert threshold.reference_observation_count == 3
    assert threshold.reference_scope == "earliest-third-of-recorded-scored-windows"
    assert "not a validated normal/fault state threshold" in threshold.semantics


def test_score_exceedance_intervals_group_contiguous_observations() -> None:
    asset = _asset((1.0, 2.0, 3.0, 5.0, 6.0, 2.0, 7.0, 8.0, 1.0))
    threshold = derive_early_scored_window_review_threshold(asset, quantile=0.95)

    intervals = score_exceedance_intervals(asset, threshold)

    assert len(intervals) == 2
    assert (
        intervals[0].start_acquisition_index,
        intervals[0].end_acquisition_index,
        intervals[0].observation_count,
    ) == (4, 5, 2)
    assert intervals[0].peak_score == pytest.approx(6.0)
    assert intervals[0].mean_score == pytest.approx(5.5)
    assert (
        intervals[1].start_acquisition_index,
        intervals[1].end_acquisition_index,
        intervals[1].observation_count,
    ) == (7, 8, 2)


def test_score_exceedance_interval_preserves_source_lineage() -> None:
    asset = _asset((1.0, 2.0, 3.0, 5.0, 6.0, 1.0))
    threshold = derive_early_scored_window_review_threshold(asset, quantile=0.95)

    interval = score_exceedance_intervals(asset, threshold)[0]

    assert interval.source_observation_ids == (
        "bearing:acquisition-4",
        "bearing:acquisition-5",
    )


def test_exceeding_scores_with_acquisition_gap_are_separate_intervals() -> None:
    asset = _asset(
        (1.0, 2.0, 3.0, 5.0, 6.0),
        positions=(1, 2, 3, 5, 6),
    )
    threshold = derive_early_scored_window_review_threshold(asset, quantile=0.95)

    intervals = score_exceedance_intervals(asset, threshold)

    assert len(intervals) == 1
    assert intervals[0].start_acquisition_index == 5
    assert intervals[0].end_acquisition_index == 6


@pytest.mark.parametrize("quantile", (0.0, 1.0, -0.1, 1.1))
def test_review_threshold_rejects_invalid_quantile(quantile: float) -> None:
    with pytest.raises(ScoreIntervalError, match="quantile"):
        derive_early_scored_window_review_threshold(_asset((1.0, 2.0, 3.0)), quantile=quantile)
