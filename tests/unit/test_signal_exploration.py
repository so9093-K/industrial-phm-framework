from __future__ import annotations

from pathlib import Path

import pytest

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.signal_exploration import (
    acquisition_binding,
    acquisition_series,
    comparison,
)
from tests.support.phm import analyze, deliver, phm_workspace

RMS = "feature.Horizontal_vibration_signals.rms"
SKEW = "feature.Horizontal_vibration_signals.skewness"


def test_a_long_range_is_sampled_over_its_whole_length_and_counted_exactly(
    tmp_path: Path,
) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    # Only the last two acquisitions change; a sample of the range's start would miss them.
    for ordinal, scale in enumerate((0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    binding = acquisition_binding(store, "bearing-a")
    assert binding is not None
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    (series,) = acquisition_series(
        store, snapshots, binding, [RMS], [("a", 1, 1), ("b", 1, 8)], max_points=4
    )
    b = series["periods"]["b"]
    assert b["sampled"] is True and b["longest_constant"] is None
    assert (b["observation_count"], b["analyzed_count"], b["usable_count"]) == (8, 8, 5)
    assert (b["first_position"], b["last_position"]) == (1, 8)
    assert b["maximum"] > 3 * b["minimum"]
    (full,) = acquisition_series(store, snapshots, binding, [RMS], [("a", 1, 1), ("b", 1, 8)])
    assert full["periods"]["b"]["sampled"] is False and full["periods"]["b"]["usable_count"] == 8


@pytest.mark.parametrize(
    ("a_median", "b_median", "signed", "percent"),
    [
        (2.0, 3.0, False, 50.0),
        (-0.1, 0.1, False, None),  # a sign change has no meaningful percent
        (0.2, 0.4, True, None),  # skewness and kurtosis are shape, not magnitude
        (0.0, 1.0, False, None),
    ],
)
def test_percent_change_only_for_positive_magnitudes(
    a_median: float, b_median: float, signed: bool, percent: float | None
) -> None:
    a = {"quantiles": [a_median] * 5, "minimum": a_median, "usable_count": 5}
    b = {"quantiles": [b_median] * 5, "minimum": b_median, "usable_count": 5}
    result = comparison(a, b, 0, signed=signed)
    assert result["median_change"] == pytest.approx(b_median - a_median)
    assert result["median_change_percent"] == (None if percent is None else pytest.approx(percent))


def test_shape_features_report_change_without_percent(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.6, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    binding = acquisition_binding(store, "bearing-a")
    assert binding is not None
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    (series,) = acquisition_series(store, snapshots, binding, [SKEW], [("a", 1, 2), ("b", 3, 4)])
    assert series["comparison"]["median_change_percent"] is None
    assert series["comparison"]["median_change"] is not None
