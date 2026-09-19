"""Dataset-neutral binary ranking evaluation for higher-is-more-anomalous scores."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sklearn.metrics import roc_auc_score  # type: ignore[import-untyped]

from industrial_phm.models.output import AnomalyScores


class BinaryRankingEvaluationError(ValueError):
    """Raised when anomaly scores and binary labels cannot be evaluated safely."""


@dataclass(frozen=True, slots=True)
class BinaryRankingEvaluation:
    """ROC evidence for one identity-aligned binary anomaly-ranking population."""

    observation_count: int
    normal_count: int
    anomaly_count: int
    roc_auc: float
    partial_roc_auc: float
    max_false_positive_rate: float

    def __post_init__(self) -> None:
        if self.observation_count <= 0:
            raise BinaryRankingEvaluationError("observation_count must be positive")
        if self.normal_count <= 0 or self.anomaly_count <= 0:
            raise BinaryRankingEvaluationError(
                "binary ranking evaluation requires both normal and anomaly observations"
            )
        if self.normal_count + self.anomaly_count != self.observation_count:
            raise BinaryRankingEvaluationError(
                "normal_count and anomaly_count must sum to observation_count"
            )
        for field_name in ("roc_auc", "partial_roc_auc"):
            value = getattr(self, field_name)
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise BinaryRankingEvaluationError(
                    f"{field_name} must be a finite unit-interval metric"
                )
        if (
            not math.isfinite(self.max_false_positive_rate)
            or not 0.0 < self.max_false_positive_rate <= 1.0
        ):
            raise BinaryRankingEvaluationError(
                "max_false_positive_rate must be finite and in (0, 1]"
            )


def evaluate_binary_anomaly_ranking(
    scores: AnomalyScores,
    labels_by_observation_id: Mapping[str, bool | int],
    *,
    max_false_positive_rate: float = 0.1,
) -> BinaryRankingEvaluation:
    """Join binary labels by source identity and compute full and standardized partial ROC AUC."""
    if (
        isinstance(max_false_positive_rate, bool)
        or not isinstance(max_false_positive_rate, int | float)
        or not math.isfinite(float(max_false_positive_rate))
        or not 0.0 < float(max_false_positive_rate) <= 1.0
    ):
        raise BinaryRankingEvaluationError(
            "max_false_positive_rate must be a finite number in (0, 1]"
        )
    max_fpr = float(max_false_positive_rate)

    score_ids = tuple(scores.source_observation_ids)
    label_ids = set(labels_by_observation_id)
    expected_ids = set(score_ids)
    missing = sorted(expected_ids - label_ids)
    unexpected = sorted(label_ids - expected_ids)
    if missing or unexpected:
        raise BinaryRankingEvaluationError(
            "label identities must exactly match scored observations; "
            f"missing={missing}, unexpected={unexpected}"
        )

    labels = tuple(
        _binary_label(labels_by_observation_id[observation_id])
        for observation_id in score_ids
    )
    anomaly_count = sum(labels)
    normal_count = len(labels) - anomaly_count
    if normal_count == 0 or anomaly_count == 0:
        raise BinaryRankingEvaluationError(
            "binary ranking evaluation requires both normal and anomaly observations"
        )

    roc_auc = float(roc_auc_score(labels, scores.scores))
    partial_roc_auc = float(roc_auc_score(labels, scores.scores, max_fpr=max_fpr))
    return BinaryRankingEvaluation(
        observation_count=len(labels),
        normal_count=normal_count,
        anomaly_count=anomaly_count,
        roc_auc=roc_auc,
        partial_roc_auc=partial_roc_auc,
        max_false_positive_rate=max_fpr,
    )


def harmonic_mean_unit_interval(values: Sequence[float]) -> float:
    """Return the protocol-safe harmonic mean without epsilon replacement for zero values."""
    metrics = tuple(float(value) for value in values)
    if not metrics:
        raise BinaryRankingEvaluationError("harmonic mean requires at least one metric")
    for value in metrics:
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise BinaryRankingEvaluationError(
                "harmonic mean metrics must be finite values in [0, 1]"
            )
    if any(value == 0.0 for value in metrics):
        return 0.0
    return float(len(metrics) / math.fsum(1.0 / value for value in metrics))


def _binary_label(value: bool | int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int) and value in (0, 1):
        return value
    raise BinaryRankingEvaluationError("binary labels must be bool or integer 0/1")
