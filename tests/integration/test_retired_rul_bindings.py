"""Remaining-life models were retired: what an older workspace still holds is left untouched,
never run and never listed."""

from __future__ import annotations

from pathlib import Path

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.phm_read import project_phm_bindings, project_phm_monitor
from industrial_phm.runtime.operations_web_capabilities import project_asset_capabilities
from industrial_phm.runtime.operations_web_phm_models import project_phm_models
from tests.support.phm import analyze, deliver, phm_workspace, retire_into


def test_a_leftover_remaining_life_binding_is_neither_run_nor_listed(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    package_id = retire_into(workspace)
    for ordinal in range(1, 4):
        deliver(workspace, tmp_path / "waves", ordinal, 0.5)
    analyze(workspace)
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)

    assert not store.list_results("rul-old")
    assert store.progress("rul-old").health_reason is None
    listed = project_phm_bindings(store, workspace.models_path, snapshots)["bindings"]
    assert {item["binding_id"] for item in listed} == {"anomaly-a", "anomaly-b"}
    monitor = project_phm_monitor(store, workspace.models_path, snapshots)
    assert {item["binding_id"] for item in monitor["items"]} == {"anomaly-a", "anomaly-b"}
    packages = project_phm_models(workspace, "bearing-a")["packages"]
    assert package_id not in {item["package_id"] for item in packages}
    ids = {
        item["id"]
        for item in project_asset_capabilities(workspace, "bearing-a", can_ask=True)["capabilities"]
    }
    assert "rul" not in ids
    # Nothing was deleted: the binding and its package stay as the workspace had them.
    assert any(binding.binding_id == "rul-old" for binding in store.list_bindings())
    assert (workspace.models_path / package_id / "package.json").is_file()
