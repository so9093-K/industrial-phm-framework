"""Delivered waveforms that no model reads yet still list their asset and lead to a model."""

from __future__ import annotations

from pathlib import Path

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.phm_read import project_phm_monitor
from tests.support.phm import analyze, deliver, phm_workspace


def test_the_monitor_read_names_streams_no_model_reads(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    for ordinal in range(1, 4):
        deliver(workspace, tmp_path / "waves", ordinal, 0.5)
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    (stream,) = project_phm_monitor(store, workspace.models_path, snapshots)["unbound_streams"]
    assert (stream["asset_id"], stream["source_id"], stream["last_ordinal"]) == (
        "bearing-a",
        "bench",
        3,
    )
    assert stream["recorded_replay"] is True

    bound = phm_workspace(tmp_path / "bound")
    deliver(bound, tmp_path / "waves-b", 1, 0.5)
    analyze(bound)
    read = project_phm_monitor(
        SqlitePhmAnalysisStore(bound.phm_analysis_path),
        bound.models_path,
        SqliteAcquisitionSnapshotRepository(bound.acquisition_snapshot_path),
    )
    assert read["unbound_streams"] == []
