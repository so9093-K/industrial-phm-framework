import pytest

from industrial_phm.experiments.binary_ranking import (
    BinaryRankingEvaluationError,
    evaluate_binary_anomaly_ranking,
    harmonic_mean_unit_interval,
)
from industrial_phm.models import AnomalyScores


def test_binary_ranking_evaluation_late_binds_labels_by_source_identity() -> None:
    scores = AnomalyScores(
        experiment_id="mimii-fixture",
        source_observation_ids=("a.wav", "b.wav", "c.wav", "d.wav"),
        scores=(0.1, 0.4, 0.35, 0.8),
    )

    evaluation = evaluate_binary_anomaly_ranking(
        scores,
        {
            "d.wav": 1,
            "b.wav": 0,
            "a.wav": 0,
            "c.wav": 1,
        },
        max_false_positive_rate=0.1,
    )

    assert evaluation.observation_count == 4
    assert evaluation.normal_count == 2
    assert evaluation.anomaly_count == 2
    assert evaluation.roc_auc == pytest.approx(0.75)
    assert evaluation.partial_roc_auc == pytest.approx(0.7368421052631579)
    assert evaluation.max_false_positive_rate == pytest.approx(0.1)


def test_binary_ranking_evaluation_requires_exact_identity_coverage() -> None:
    scores = AnomalyScores(
        experiment_id="mimii-fixture",
        source_observation_ids=("a.wav", "b.wav"),
        scores=(0.1, 0.9),
    )

    with pytest.raises(BinaryRankingEvaluationError, match="exactly match"):
        evaluate_binary_anomaly_ranking(scores, {"a.wav": 0, "other.wav": 1})


def test_binary_ranking_evaluation_rejects_single_class_labels() -> None:
    scores = AnomalyScores(
        experiment_id="mimii-fixture",
        source_observation_ids=("a.wav", "b.wav"),
        scores=(0.1, 0.9),
    )

    with pytest.raises(BinaryRankingEvaluationError, match="both normal and anomaly"):
        evaluate_binary_anomaly_ranking(scores, {"a.wav": 0, "b.wav": 0})


def test_harmonic_mean_preserves_zero_without_epsilon_replacement() -> None:
    assert harmonic_mean_unit_interval((0.5, 1.0)) == pytest.approx(2.0 / 3.0)
    assert harmonic_mean_unit_interval((0.5, 0.0, 1.0)) == 0.0

    with pytest.raises(BinaryRankingEvaluationError, match=r"\[0, 1\]"):
        harmonic_mean_unit_interval((0.5, 1.1))
