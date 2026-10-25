"""A binding whose package declares a task this product does not run is never run; it is
listed as unable to run, with the reason, instead of being hidden."""

from __future__ import annotations

from pathlib import Path

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.phm_read import project_phm_monitor
from industrial_phm.runtime.operations_web_phm_models import project_phm_models
from tests.support.phm import analyze, deliver, phm_workspace, unsupported_into


def test_a_package_of_an_unsupported_task_is_refused_and_said(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    package_id = unsupported_into(workspace)
    for ordinal in range(1, 4):
        deliver(workspace, tmp_path / "waves", ordinal, 0.5)
    analyze(workspace)
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)

    assert not store.list_results("odd-task")
    assert store.progress("odd-task").health_reason
    monitor = project_phm_monitor(
        store,
        workspace.models_path,
        SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
    )
    states = {item["binding_id"]: item["processing_state"] for item in monitor["items"]}
    assert states["odd-task"] == "unavailable"
    assert {states["anomaly-a"], states["anomaly-b"]} == {"processed"}
    # It is not offered for connection either.
    packages = project_phm_models(workspace, "bearing-a")["packages"]
    assert package_id not in {item["package_id"] for item in packages}
