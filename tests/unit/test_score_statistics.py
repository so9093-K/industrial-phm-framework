import pytest

from industrial_phm.experiments.score_statistics import (
    ScoreStatisticsError,
    late_vs_middle_rank_probability,
    spearman_rho,
)


def test_dataset_neutral_score_statistics_preserve_rank_semantics() -> None:
    assert spearman_rho((1, 2, 3, 4), (10.0, 20.0, 30.0, 40.0)) == pytest.approx(1.0)
    assert late_vs_middle_rank_probability((1.0, 2.0), (3.0, 4.0)) == pytest.approx(1.0)
    assert late_vs_middle_rank_probability((1.0, 2.0), (1.0, 2.0)) == pytest.approx(0.5)


def test_spearman_reports_undefined_constant_sequence_without_imputation() -> None:
    assert spearman_rho((1, 2, 3), (5.0, 5.0, 5.0)) is None


def test_spearman_rejects_misaligned_input() -> None:
    with pytest.raises(ScoreStatisticsError, match="equal sequences"):
        spearman_rho((1, 2), (1.0,))
