"""Monitor facts are bounded persisted reads, including refusal and exact handoff identity."""

from __future__ import annotations

import json
from pathlib import Path

from industrial_phm.application.phm_analysis import PhmBinding, SqlitePhmAnalysisStore
from industrial_phm.application.phm_read import project_phm_monitor
from industrial_phm.runtime.operations_web_phm import handle_phm_read
from industrial_phm.runtime.operations_workspace import (
    OperationsWorkspace,
    initialize_operations_workspace,
)
from tests.support.phm import T0, analyze, deliver, phm_workspace


def test_empty_monitor_does_not_initialize_an_analysis_store(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    status, body = handle_phm_read(workspace, "/api/v1/phm/monitor", "")
    assert status == 200 and body["items"] == [] and body["total"] == 0
    assert not workspace.phm_analysis_path.exists()


def test_monitor_distinguishes_new_input_refusal_and_an_exact_saved_result(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    deliver(workspace, tmp_path / "waves", 1, 0.5)
    analyze(workspace)
    deliver(workspace, tmp_path / "waves", 2, 3.0)
    status, body = handle_phm_read(workspace, "/api/v1/phm/monitor", "")
    assert status == 200
    item = next(i for i in body["items"] if i["binding_id"] == "anomaly-a")
    assert item["processing_state"] == "pending"
    assert item["latest_delivered"]["position"] == 2
    assert item["latest_analyzed"]["position"] == 1
    (tmp_path / "waves/2.csv").write_text("corrupted after delivery")
    analyze(workspace)
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    before = store.list_results("anomaly-a")
    _, body = handle_phm_read(workspace, "/api/v1/phm/monitor", "")
    item = next(i for i in body["items"] if i["binding_id"] == "anomaly-a")
    assert item["processing_state"] == "rejected"
    assert item["latest_processed"]["position"] == 2
    assert item["latest_analyzed"]["position"] == 1
    status, result = handle_phm_read(
        workspace, "/api/v1/phm/result", "binding_id=anomaly-a&position=1"
    )
    assert status == 200 and result["step"]["analysis_run_id"] == before[0].analysis_run_id
    assert str(workspace.root) not in json.dumps(result)
    assert store.list_results("anomaly-a") == before
    assert (
        handle_phm_read(workspace, "/api/v1/phm/result", "binding_id=anomaly-a&position=99")[0]
        == 400
    )
    # An unavailable review store remains distinct from zero outstanding reviews.
    workspace.finding_state_path.write_text("invalid json")
    _, body = handle_phm_read(workspace, "/api/v1/phm/monitor", "")
    assert body["review_read_error"] is True and body["reviews"] is None
    assert body["items"][0]["latest_analyzed"] is not None


def test_many_bindings_use_a_bounded_summary_without_reading_series(
    tmp_path: Path, monkeypatch
) -> None:
    from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository

    workspace = phm_workspace(tmp_path / "ws")
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    template = store.list_bindings()[0]
    for i in range(101):
        store.create_binding(
            PhmBinding(
                f"binding-{i}",
                template.package_id,
                "bench",
                f"asset-{i:03}",
                template.step_kind,
                T0,
            )
        )

    def no_history(*args, **kwargs):
        raise AssertionError("overview must not load entire model histories")

    monkeypatch.setattr(store, "list_results", no_history)
    body = project_phm_monitor(
        store,
        workspace.models_path,
        SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
    )
    assert body["total"] == 103 and len(body["items"]) == 100 and body["truncated"] is True
    assert all(i["processing_state"] == "waiting" for i in body["items"])
