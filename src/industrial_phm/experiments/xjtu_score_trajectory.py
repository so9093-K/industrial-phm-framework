"""Per-observation anomaly-score trajectories for fold-1 development diagnosis."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Literal

from industrial_phm.experiments.xjtu_evaluation import spearman_rho
from industrial_phm.features import VibrationFeatureVector
from industrial_phm.models.output import AnomalyScores

XJTU_SCORE_TRAJECTORY_SCHEMA_ID = "xjtu-fold-1-score-trajectory-v1"
LIFECYCLE_SEGMENTS = ("early_third", "middle_third", "late_third")

ScoredPartition = Literal["train", "validation"]
_SCORED_PARTITIONS: tuple[ScoredPartition, ...] = ("train", "validation")
_DATASET_ID = "xjtu-sy"
_TABLE_COLUMNS = (
    "experiment_id",
    "partition",
    "asset_id",
    "operating_condition",
    "acquisition_index",
    "anomaly_score",
)


class XjtuScoreTrajectoryError(ValueError):
    """Raised when score-trajectory inputs or artifacts violate their contract."""


@dataclass(frozen=True, slots=True)
class XjtuScoreObservation:
    """One scored acquisition in bearing-run lifecycle order."""

    partition: ScoredPartition
    asset_id: str
    operating_condition: str
    acquisition_index: int
    anomaly_score: float


@dataclass(frozen=True, slots=True)
class XjtuLifecycleSegmentScores:
    """Retrospective lifecycle-third summary of one bearing run's scores."""

    segment: str
    observation_count: int
    median_anomaly_score: float | None
    acquisition_order_spearman_rho: float | None


@dataclass(frozen=True, slots=True)
class XjtuBearingScoreTrajectory:
    """Score-trajectory shape for one scored bearing run."""

    partition: ScoredPartition
    asset_id: str
    operating_condition: str
    observation_count: int
    median_anomaly_score: float
    min_anomaly_score: float
    max_anomaly_score: float
    acquisition_order_spearman_rho: float | None
    segments: tuple[XjtuLifecycleSegmentScores, ...]


@dataclass(frozen=True, slots=True)
class XjtuCandidateScoreTrajectory:
    """Every scored observation and bearing summary for one candidate."""

    experiment_id: str
    observations: tuple[XjtuScoreObservation, ...]
    bearings: tuple[XjtuBearingScoreTrajectory, ...]


@dataclass(frozen=True, slots=True)
class XjtuScoreTrajectoryReport:
    """Development-only score trajectories behind one fold-1 validation run."""

    code_revision: str
    dataset_id: str
    split_id: str
    fold_id: str
    candidates: tuple[XjtuCandidateScoreTrajectory, ...]


def build_xjtu_candidate_score_trajectory(
    experiment_id: str,
    scored_partitions: Sequence[
        tuple[ScoredPartition, Sequence[VibrationFeatureVector], AnomalyScores]
    ],
) -> XjtuCandidateScoreTrajectory:
    """Align scores back to lifecycle order and summarize each scored bearing run."""
    observations: list[XjtuScoreObservation] = []
    for partition, vectors, anomaly_scores in scored_partitions:
        observations.extend(_partition_observations(partition, vectors, anomaly_scores))

    ordered = tuple(
        sorted(
            observations,
            key=lambda item: (item.partition, item.asset_id, item.acquisition_index),
        )
    )
    return XjtuCandidateScoreTrajectory(
        experiment_id=experiment_id,
        observations=ordered,
        bearings=summarize_xjtu_bearing_score_trajectories(ordered),
    )


def summarize_xjtu_bearing_score_trajectories(
    observations: Sequence[XjtuScoreObservation],
) -> tuple[XjtuBearingScoreTrajectory, ...]:
    """Describe each bearing run's score trajectory over its full lifecycle and thirds."""
    grouped: dict[tuple[ScoredPartition, str], list[XjtuScoreObservation]] = defaultdict(list)
    for observation in observations:
        grouped[(observation.partition, observation.asset_id)].append(observation)

    summaries: list[XjtuBearingScoreTrajectory] = []
    for partition, asset_id in sorted(grouped, key=lambda key: (key[0], key[1])):
        run = sorted(grouped[(partition, asset_id)], key=lambda item: item.acquisition_index)
        conditions = {observation.operating_condition for observation in run}
        if len(conditions) != 1:
            raise XjtuScoreTrajectoryError(
                f"bearing run {asset_id} must have exactly one operating_condition"
            )
        scores = [observation.anomaly_score for observation in run]
        summaries.append(
            XjtuBearingScoreTrajectory(
                partition=partition,
                asset_id=asset_id,
                operating_condition=next(iter(conditions)),
                observation_count=len(run),
                median_anomaly_score=float(median(scores)),
                min_anomaly_score=min(scores),
                max_anomaly_score=max(scores),
                acquisition_order_spearman_rho=_ordered_rho(run),
                segments=_lifecycle_segments(run),
            )
        )
    return tuple(summaries)


def write_xjtu_score_trajectory_table(
    report: XjtuScoreTrajectoryReport,
    output_path: Path,
) -> None:
    """Write every scored observation as a deterministic research table."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(_TABLE_COLUMNS)
        for candidate in report.candidates:
            for observation in candidate.observations:
                writer.writerow(
                    (
                        candidate.experiment_id,
                        observation.partition,
                        observation.asset_id,
                        observation.operating_condition,
                        observation.acquisition_index,
                        repr(observation.anomaly_score),
                    )
                )


def write_xjtu_score_trajectory_summary(
    report: XjtuScoreTrajectoryReport,
    output_path: Path,
) -> None:
    """Write deterministic, reviewable bearing-level score-trajectory evidence."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_report_document(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _partition_observations(
    partition: ScoredPartition,
    vectors: Sequence[VibrationFeatureVector],
    anomaly_scores: AnomalyScores,
) -> tuple[XjtuScoreObservation, ...]:
    if partition not in _SCORED_PARTITIONS:
        raise XjtuScoreTrajectoryError(
            f"score trajectories cover {_SCORED_PARTITIONS}, got {partition!r}"
        )
    if not vectors:
        raise XjtuScoreTrajectoryError("score trajectories require feature vectors")

    score_by_observation_id = dict(
        zip(anomaly_scores.source_observation_ids, anomaly_scores.scores, strict=True)
    )
    observations: list[XjtuScoreObservation] = []
    for vector_index, vector in enumerate(vectors):
        if vector.metadata.get("dataset_id") != _DATASET_ID:
            raise XjtuScoreTrajectoryError(
                f"XJTU feature vector {vector_index} must preserve dataset_id {_DATASET_ID!r}"
            )
        acquisition_index = _acquisition_index(vector, vector_index=vector_index)
        observation_id = f"{vector.asset_id}:acquisition-{acquisition_index}"
        if observation_id not in score_by_observation_id:
            raise XjtuScoreTrajectoryError(
                f"{partition} anomaly scores are missing observation {observation_id!r}"
            )
        observations.append(
            XjtuScoreObservation(
                partition=partition,
                asset_id=vector.asset_id,
                operating_condition=_operating_condition(vector, vector_index=vector_index),
                acquisition_index=acquisition_index,
                anomaly_score=score_by_observation_id[observation_id],
            )
        )

    if len(observations) != len(score_by_observation_id):
        raise XjtuScoreTrajectoryError(
            f"{partition} anomaly scores must align exactly with its feature vectors"
        )
    return tuple(observations)


def _lifecycle_segments(
    run: Sequence[XjtuScoreObservation],
) -> tuple[XjtuLifecycleSegmentScores, ...]:
    buckets: dict[str, list[XjtuScoreObservation]] = {name: [] for name in LIFECYCLE_SEGMENTS}
    run_length = len(run)
    for position, observation in enumerate(run):
        buckets[LIFECYCLE_SEGMENTS[min(2, (position * 3) // run_length)]].append(observation)

    return tuple(
        XjtuLifecycleSegmentScores(
            segment=segment,
            observation_count=len(members),
            median_anomaly_score=(
                float(median(observation.anomaly_score for observation in members))
                if members
                else None
            ),
            acquisition_order_spearman_rho=_ordered_rho(members),
        )
        for segment, members in ((name, buckets[name]) for name in LIFECYCLE_SEGMENTS)
    )


def _ordered_rho(run: Sequence[XjtuScoreObservation]) -> float | None:
    if len(run) < 2:
        return None
    return spearman_rho(
        tuple(observation.acquisition_index for observation in run),
        tuple(observation.anomaly_score for observation in run),
    )


def _report_document(report: XjtuScoreTrajectoryReport) -> dict[str, Any]:
    return {
        "schema_id": XJTU_SCORE_TRAJECTORY_SCHEMA_ID,
        "code_revision": report.code_revision,
        "dataset_id": report.dataset_id,
        "split_id": report.split_id,
        "fold_id": report.fold_id,
        "scored_partitions": list(_SCORED_PARTITIONS),
        "interpretation": (
            "Development diagnosis of anomaly-score shape over bearing lifecycle order. "
            "Train scores are in-sample and describe the fitted reference distribution; "
            "they are not candidate-selection evidence. The holdout test partition is "
            "never scored here."
        ),
        "candidates": [
            {
                "experiment_id": candidate.experiment_id,
                "bearings": [_bearing_document(bearing) for bearing in candidate.bearings],
            }
            for candidate in report.candidates
        ],
    }


def _bearing_document(bearing: XjtuBearingScoreTrajectory) -> dict[str, Any]:
    return {
        "partition": bearing.partition,
        "asset_id": bearing.asset_id,
        "operating_condition": bearing.operating_condition,
        "observation_count": bearing.observation_count,
        "median_anomaly_score": bearing.median_anomaly_score,
        "min_anomaly_score": bearing.min_anomaly_score,
        "max_anomaly_score": bearing.max_anomaly_score,
        "acquisition_order_spearman_rho": bearing.acquisition_order_spearman_rho,
        "lifecycle_segments": [
            {
                "segment": segment.segment,
                "observation_count": segment.observation_count,
                "median_anomaly_score": segment.median_anomaly_score,
                "acquisition_order_spearman_rho": segment.acquisition_order_spearman_rho,
            }
            for segment in bearing.segments
        ],
    }


def _acquisition_index(vector: VibrationFeatureVector, *, vector_index: int) -> int:
    value = vector.metadata.get("acquisition_index")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise XjtuScoreTrajectoryError(
            f"XJTU feature vector {vector_index} requires a positive integer acquisition_index"
        )
    return value


def _operating_condition(vector: VibrationFeatureVector, *, vector_index: int) -> str:
    value = vector.metadata.get("operating_condition")
    if not isinstance(value, str) or not value.strip():
        raise XjtuScoreTrajectoryError(
            f"XJTU feature vector {vector_index} requires operating_condition"
        )
    return value
