import json
from pathlib import Path

import pytest

from industrial_phm.experiments import (
    XJTU_SCORE_TRAJECTORY_SCHEMA_ID,
    XjtuFoldValidationError,
    XjtuFoldValidationResult,
    XjtuScoreObservation,
    XjtuScoreTrajectoryError,
    XjtuScoreTrajectoryReport,
    build_xjtu_candidate_score_trajectory,
    summarize_xjtu_bearing_score_trajectories,
    write_xjtu_score_trajectory_artifacts,
    write_xjtu_score_trajectory_summary,
    write_xjtu_score_trajectory_table,
)
from industrial_phm.features import VibrationFeatureVector
from industrial_phm.models import AnomalyScores

_EXPERIMENT_ID = "candidate-under-test"


def _vectors(asset_id: str, count: int) -> tuple[VibrationFeatureVector, ...]:
    return tuple(
        VibrationFeatureVector(
            feature_set_id="vibration-statistical-v1",
            asset_id=asset_id,
            feature_names=("feature.placeholder",),
            values=(float(acquisition_index),),
            metadata={
                "dataset_id": "xjtu-sy",
                "operating_condition": "40Hz10kN",
                "acquisition_index": acquisition_index,
            },
        )
        for acquisition_index in range(1, count + 1)
    )


def _scores(asset_id: str, values: tuple[float, ...]) -> AnomalyScores:
    return AnomalyScores(
        experiment_id=_EXPERIMENT_ID,
        source_observation_ids=tuple(
            f"{asset_id}:acquisition-{index}" for index in range(1, len(values) + 1)
        ),
        scores=values,
    )


def _observations(values: tuple[float, ...]) -> tuple[XjtuScoreObservation, ...]:
    return tuple(
        XjtuScoreObservation(
            partition="validation",
            asset_id="Bearing3_2",
            operating_condition="40Hz10kN",
            acquisition_index=index,
            anomaly_score=score,
        )
        for index, score in enumerate(values, start=1)
    )


def test_score_trajectory_refuses_the_holdout_test_partition() -> None:
    vectors = _vectors("Bearing3_1", 3)

    with pytest.raises(XjtuScoreTrajectoryError, match="score trajectories cover"):
        build_xjtu_candidate_score_trajectory(
            _EXPERIMENT_ID,
            (("test", vectors, _scores("Bearing3_1", (0.1, 0.2, 0.3))),),  # type: ignore[arg-type]
        )


def test_score_trajectory_requires_exact_score_alignment() -> None:
    vectors = _vectors("Bearing3_2", 3)

    with pytest.raises(XjtuScoreTrajectoryError, match="missing observation"):
        build_xjtu_candidate_score_trajectory(
            _EXPERIMENT_ID,
            (("validation", vectors, _scores("Bearing3_2", (0.1, 0.2))),),
        )


def test_score_trajectory_orders_observations_by_acquisition_index() -> None:
    vectors = tuple(reversed(_vectors("Bearing3_2", 4)))

    trajectory = build_xjtu_candidate_score_trajectory(
        _EXPERIMENT_ID,
        (("validation", vectors, _scores("Bearing3_2", (0.9, 0.6, 0.3, 0.1))),),
    )

    assert [item.acquisition_index for item in trajectory.observations] == [1, 2, 3, 4]
    assert [item.anomaly_score for item in trajectory.observations] == [0.9, 0.6, 0.3, 0.1]
    assert trajectory.bearings[0].acquisition_order_spearman_rho == -1.0


def test_lifecycle_segments_cover_every_acquisition_exactly_once() -> None:
    summaries = summarize_xjtu_bearing_score_trajectories(
        _observations(tuple(float(value) for value in range(10)))
    )

    segments = summaries[0].segments
    assert [segment.segment for segment in segments] == [
        "early_third",
        "middle_third",
        "late_third",
    ]
    assert sum(segment.observation_count for segment in segments) == 10


def test_lifecycle_segments_separate_a_declining_run_from_its_late_rise() -> None:
    summaries = summarize_xjtu_bearing_score_trajectories(
        _observations((0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.1, 0.2, 0.3))
    )

    bearing = summaries[0]
    early, _, late = bearing.segments
    assert bearing.acquisition_order_spearman_rho is not None
    assert bearing.acquisition_order_spearman_rho < 0.0
    assert early.acquisition_order_spearman_rho == -1.0
    assert late.acquisition_order_spearman_rho == 1.0


def test_score_trajectory_summary_is_deterministic(tmp_path: Path) -> None:
    report = XjtuScoreTrajectoryReport(
        code_revision="a" * 40,
        dataset_id="xjtu-sy",
        split_id="xjtu-sy-condition-stratified-5fold-v1",
        fold_id="fold-1",
        candidates=(
            build_xjtu_candidate_score_trajectory(
                _EXPERIMENT_ID,
                (
                    (
                        "validation",
                        _vectors("Bearing3_2", 3),
                        _scores("Bearing3_2", (0.3, 0.2, 0.1)),
                    ),
                ),
            ),
        ),
    )
    summary_path = tmp_path / "summary.json"
    table_path = tmp_path / "table.csv"

    write_xjtu_score_trajectory_summary(report, summary_path)
    first_summary = summary_path.read_text(encoding="utf-8")
    write_xjtu_score_trajectory_summary(report, summary_path)
    write_xjtu_score_trajectory_table(report, table_path)
    first_table = table_path.read_text(encoding="utf-8")
    write_xjtu_score_trajectory_table(report, table_path)

    assert summary_path.read_text(encoding="utf-8") == first_summary
    assert table_path.read_text(encoding="utf-8") == first_table
    document = json.loads(first_summary)
    assert document["schema_id"] == XJTU_SCORE_TRAJECTORY_SCHEMA_ID
    assert document["scored_partitions"] == ["train", "validation"]
    assert first_table.splitlines()[1] == (f"{_EXPERIMENT_ID},validation,Bearing3_2,40Hz10kN,1,0.3")


def test_trajectory_artifacts_require_collected_trajectories(tmp_path: Path) -> None:
    result = XjtuFoldValidationResult(
        code_revision="a" * 40,
        dataset_id="xjtu-sy",
        split_id="xjtu-sy-condition-stratified-5fold-v1",
        fold_id="fold-1",
        partition="validation",
        source_acquisition_count=9216,
        candidates=(),
        selected_experiment_id=_EXPERIMENT_ID,
    )

    with pytest.raises(XjtuFoldValidationError, match="no score trajectories"):
        write_xjtu_score_trajectory_artifacts(result, tmp_path)
