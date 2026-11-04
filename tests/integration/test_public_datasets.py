"""Public datasets in the data folder are offered on the Web and imported by the supervisor."""

import json
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

import pytest

from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_actions import (
    WEB_SOURCE_ACTION_ROUTES,
    WEB_SUPERVISOR_ONLY_ACTION_ROUTES,
    execute_web_source_action,
)
from industrial_phm.runtime.public_datasets import PublicDatasetJobs, list_public_datasets

pytest.importorskip("ijson")
pytest.importorskip("duckdb")

MEMBERS = {"3.공기압축기/SourceData_16.json": 1338, "3.공기압축기/SourceData_9.json": 902}


def _aihub(root: Path) -> None:
    archive = root / "raw/aihub/239/archives/training/raw/3.공기압축기.zip"
    archive.parent.mkdir(parents=True)
    with ZipFile(archive, "w") as opened:
        for member, device in MEMBERS.items():
            records = [
                {"ITEM_NAME": "R상전류", "ITEM_VALUE": value, "TIMESTAMP": stamp}
                for value, stamp in ((68.0, "2020-10-22 00:00:22"), (0.0, "2020-10-22 00:01:22"))
            ]
            body = {"DEVICE_ID": device, "DEVICE_BD_ID": 1, "data": records}
            opened.writestr(member, json.dumps(body, ensure_ascii=False))


def test_an_aihub_member_becomes_one_assets_history_read_as_kst(tmp_path: Path) -> None:
    root = tmp_path / "data"
    _aihub(root)
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    items = {item["asset_id"]: item for item in list_public_datasets(workspace, root)["items"]}
    # The asset is named by the equipment group and the record's own DEVICE_ID.
    assert set(items) == {"공기압축기 1338", "공기압축기 902"}
    target = items["공기압축기 1338"]
    assert (target["split"], target["device_id"], target["stored"]) == ("학습용", "1338", False)

    jobs = PublicDatasetJobs(workspace.root, root=root)
    jobs.start({"dataset_id": target["dataset_id"]})
    jobs.close()
    listing = list_public_datasets(workspace, root)
    job = listing["jobs"][target["dataset_id"]]
    assert (job["state"], job["done"]) == ("succeeded", 2)
    stored = {item["asset_id"]: item["stored"] for item in listing["items"]}
    assert stored == {"공기압축기 1338": True, "공기압축기 902": False}
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    summary = next(a for a in history.list_history_assets() if a.asset_id == "공기압축기 1338")
    # The source time has no zone and is stored as KST: 00:00:22 local is 15:00:22 UTC before.
    assert summary.start_at == datetime(2020, 10, 21, 15, 0, 22, tzinfo=UTC)


def test_only_a_dataset_the_server_found_is_imported(tmp_path: Path) -> None:
    root = tmp_path / "data"
    _aihub(root)
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    jobs = PublicDatasetJobs(workspace.root, root=root)
    for payload in ({"dataset_id": "../../etc/passwd"}, {"dataset_id": 1}, {"path": "x"}):
        with pytest.raises(ValueError):
            jobs.start(payload)
    assert list_public_datasets(workspace, root)["jobs"] == {}


def test_an_import_needs_the_supervisor_that_owns_its_background_thread() -> None:
    route = "/api/v1/datasets/import"
    assert route in WEB_SOURCE_ACTION_ROUTES and route in WEB_SUPERVISOR_ONLY_ACTION_ROUTES
    with pytest.raises(ValueError, match="supervisor"):
        execute_web_source_action(Path("."), route, {"dataset_id": "x"})
