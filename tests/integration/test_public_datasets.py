"""Public datasets in the data folder are offered on the Web and imported by the supervisor."""

import json
import os
from datetime import UTC, datetime, timedelta
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
from industrial_phm.runtime.public_datasets import (
    PublicDataset,
    PublicDatasetJobs,
    list_public_datasets,
)

pytest.importorskip("ijson")
pytest.importorskip("duckdb")

MEMBERS = {"3.공기압축기/SourceData_16.json": 1338, "3.공기압축기/SourceData_9.json": 902}


def _aihub(root: Path, split: str = "training", members: dict[str, int] = MEMBERS) -> None:
    archive = root / f"raw/aihub/239/archives/{split}/raw/3.공기압축기.zip"
    archive.parent.mkdir(parents=True)
    with ZipFile(archive, "w") as opened:
        for member, device in members.items():
            records = [
                {"ITEM_NAME": "R상전류", "ITEM_VALUE": value, "TIMESTAMP": stamp}
                for value, stamp in ((68.0, "2020-10-22 00:00:22"), (0.0, "2020-10-22 00:01:22"))
            ]
            body = {"DEVICE_ID": device, "DEVICE_BD_ID": 1, "data": records}
            opened.writestr(member, json.dumps(body, ensure_ascii=False))


def test_an_aihub_member_becomes_one_assets_history_read_as_kst(tmp_path: Path) -> None:
    root = tmp_path / "data"
    _aihub(root)
    # The same device is in the validation archive too; it stays a member of its own.
    _aihub(root, "validation", {"3.공기압축기/SourceData_70.json": 1338})
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    found = list_public_datasets(workspace, root)["items"]
    assert [(item["asset_id"], item["split"]) for item in found if item["device_id"] == "1338"] == [
        ("공기압축기 1338", "학습용"),
        ("공기압축기 1338", "검증용"),
    ]
    items = {item["asset_id"]: item for item in found if item["split"] == "학습용"}
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
    stored = {(item["asset_id"], item["split"]): item["stored"] for item in listing["items"]}
    # Importing the training member does not mark the validation member of the same device.
    assert stored == {
        ("공기압축기 1338", "학습용"): True,
        ("공기압축기 902", "학습용"): False,
        ("공기압축기 1338", "검증용"): False,
    }
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


def test_a_restarted_web_lists_archives_from_the_index_without_rereading_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from industrial_phm.adapters import aihub_power
    from industrial_phm.runtime import public_datasets

    root = tmp_path / "data"
    _aihub(root)
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    public_datasets.write_public_dataset_index(workspace, root)
    # A new Web process starts with an empty memory cache and must not decompress members.
    monkeypatch.setattr(public_datasets, "_IDENTITY_CACHE", {})

    def unread(_path: Path) -> dict[str, tuple[str, str]]:
        raise AssertionError("archive members were reread")

    monkeypatch.setattr(aihub_power, "read_power_member_identities", unread)
    assets = {item["asset_id"] for item in list_public_datasets(workspace, root)["items"]}
    assert assets == {"공기압축기 1338", "공기압축기 902"}


def test_interrupted_aihub_import_can_retry_committed_batches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from collections.abc import Callable

    from industrial_phm.runtime import public_datasets

    root = tmp_path / "data"
    archive = root / "raw/aihub/239/archives/training/raw/3.공기압축기.zip"
    archive.parent.mkdir(parents=True)
    start = datetime(2020, 10, 22)
    body = {
        "DEVICE_ID": 1338,
        "DEVICE_BD_ID": 1,
        "data": [
            {
                "ITEM_NAME": "R상전류",
                "ITEM_VALUE": 68.0,
                "TIMESTAMP": (start + timedelta(seconds=i)).strftime("%Y-%m-%d %H:%M:%S"),
            }
            for i in range(2001)
        ],
    }
    with ZipFile(archive, "w") as opened:
        opened.writestr("3.공기압축기/SourceData_16.json", json.dumps(body, ensure_ascii=False))
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    target = list_public_datasets(workspace, root)["items"][0]
    real_import = public_datasets._import_aihub

    def stop_after_first_commit(
        destination: OperationsWorkspace, item: PublicDataset, progress: Callable[[int], None]
    ) -> None:
        def interrupted(done: int) -> None:
            progress(done)
            if done == 2000:
                raise RuntimeError("simulated interruption after committed batch")

        real_import(destination, item, interrupted)

    monkeypatch.setattr(public_datasets, "_import_aihub", stop_after_first_commit)
    jobs = PublicDatasetJobs(workspace.root, root=root)
    jobs.start({"dataset_id": target["dataset_id"]})
    jobs.close()
    partial = list_public_datasets(workspace, root)
    assert partial["jobs"][target["dataset_id"]]["state"] == "failed"
    assert (partial["items"][0]["stored"], partial["items"][0]["partial"]) == (False, True)

    monkeypatch.setattr(public_datasets, "_import_aihub", real_import)
    jobs = PublicDatasetJobs(workspace.root, root=root)
    jobs.start({"dataset_id": target["dataset_id"]})
    jobs.close()
    completed = list_public_datasets(workspace, root)
    assert completed["jobs"][target["dataset_id"]]["state"] == "succeeded"
    assert completed["jobs"][target["dataset_id"]]["done"] == 2001
    assert (completed["items"][0]["stored"], completed["items"][0]["partial"]) == (True, False)


def test_unreadable_aihub_archive_does_not_hide_valid_datasets(tmp_path: Path) -> None:
    from industrial_phm.runtime.public_datasets import write_public_dataset_index

    root = tmp_path / "data"
    _aihub(root)
    broken = root / "raw/aihub/239/archives/training/raw/8.보일러.zip"
    broken.write_bytes(b"unfinished ZIP download")
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)

    write_public_dataset_index(workspace, root)
    listed = list_public_datasets(workspace, root)["items"]
    assert {item["asset_id"] for item in listed} == {"공기압축기 1338", "공기압축기 902"}


def test_changed_aihub_source_needs_reimport_and_preserves_previous_history(tmp_path: Path) -> None:
    root = tmp_path / "data"
    _aihub(root)
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    target = list_public_datasets(workspace, root)["items"][0]

    def run() -> dict[str, object]:
        jobs = PublicDatasetJobs(workspace.root, root=root)
        jobs.start({"dataset_id": target["dataset_id"]})
        jobs.close()
        listing = list_public_datasets(workspace, root)
        assert listing["items"][0]["stored"] is True
        return listing["jobs"][target["dataset_id"]]

    original = run()
    archive = root / "raw/aihub/239/archives/training/raw/3.공기압축기.zip"
    stat = archive.stat()
    with ZipFile(archive) as opened:
        members = {name: opened.read(name) for name in opened.namelist()}
    with ZipFile(archive, "w") as opened:
        for name, content in members.items():
            opened.writestr(name, content.replace(b"68.0", b"79.0"))
    # Restoring the original mtime and byte size must not hide changed contents.
    assert archive.stat().st_size == stat.st_size
    os.utime(archive, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    changed = list_public_datasets(workspace, root)["items"][0]
    assert (changed["stored"], changed["partial"], changed["source_changed"]) == (False, True, True)

    updated = run()
    assert original["source_digest"] != updated["source_digest"]
    assert original["source_id"] != updated["source_id"]
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    assert [r.value for r in history.query_file_events(original["source_id"])] == [68.0, 0.0]
    assert [r.value for r in history.query_file_events(updated["source_id"])] == [79.0, 0.0]
    assert run()["source_id"] == updated["source_id"]
    assert len(history.query_file_events(updated["source_id"])) == 2
    # A metadata-only change is conservative until retry, then byte identity recovers
    # the same stream instead of inserting a duplicate source version.
    stamp = archive.stat()
    os.utime(archive, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 1_000_000))
    assert list_public_datasets(workspace, root)["items"][0]["stored"] is False
    assert run()["source_id"] == updated["source_id"]
    assert len(history.query_file_events(updated["source_id"])) == 2


def test_xjtu_same_count_edit_and_relocation_get_separate_snapshot_streams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from industrial_phm.adapters import XJTU_SY_CHANNELS
    from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
    from industrial_phm.demo import xjtu_models
    from industrial_phm.runtime import operations_web_phm_models, public_datasets

    root = tmp_path / "data"
    bearing = xjtu_models.held_out_bearings()[0]
    folder = root / public_datasets.XJTU_SOURCE / "35Hz12kN" / bearing
    folder.mkdir(parents=True)
    csv = folder / "1.csv"
    csv.write_text(",".join(XJTU_SY_CHANNELS) + "\n0.1,0.2\n")
    # Model training is unrelated to source version isolation; exercise the real replay/store.
    monkeypatch.setattr(
        xjtu_models,
        "existing_packages",
        lambda _: {
            xjtu_models.IFOREST_RECIPE: "iforest",
            xjtu_models.LSTM_RECIPE: "lstm",
        },
    )
    bindings: list[str] = []
    monkeypatch.setattr(
        operations_web_phm_models,
        "create_phm_binding",
        lambda *_, **kwargs: bindings.append(kwargs["source_id"]),
    )
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    target = list_public_datasets(workspace, root)["items"][0]

    def run(data_root: Path) -> dict[str, object]:
        jobs = PublicDatasetJobs(workspace.root, root=data_root)
        jobs.start({"dataset_id": target["dataset_id"]})
        jobs.close()
        listing = list_public_datasets(workspace, data_root)
        assert listing["items"][0]["stored"] is True
        return listing["jobs"][target["dataset_id"]]

    original = run(root)
    stat = csv.stat()
    csv.write_text(csv.read_text().replace("0.1", "0.9"))
    os.utime(csv, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    changed = list_public_datasets(workspace, root)["items"][0]
    assert (changed["stored"], changed["source_changed"]) == (False, True)
    updated = run(root)
    assert updated["source_id"] != original["source_id"]
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    old = snapshots.get(original["source_id"], bearing, 1)
    new = snapshots.get(updated["source_id"], bearing, 1)
    assert old.sha256 != new.sha256

    moved_root = root.rename(tmp_path / "moved-data")
    changed = list_public_datasets(workspace, moved_root)["items"][0]
    assert (changed["stored"], changed["source_changed"]) == (False, True)
    moved = run(moved_root)
    assert moved["source_id"] != updated["source_id"]
    latest = snapshots.get(moved["source_id"], bearing, 1)
    assert latest.file_path.is_file() and latest.sha256 == new.sha256
    assert snapshots.get(original["source_id"], bearing, 1) == old
    assert bindings == [job["source_id"] for job in (original, updated, moved) for _ in range(2)]


def test_import_without_source_fingerprint_is_not_proof_of_current_completion(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    _aihub(root)
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    target = list_public_datasets(workspace, root)["items"][0]
    jobs = PublicDatasetJobs(workspace.root, root=root)
    jobs.start({"dataset_id": target["dataset_id"]})
    jobs.close()
    saved = json.loads(workspace.public_dataset_job_path.read_text())
    for key in ("source_signature", "source_digest"):
        saved["jobs"][target["dataset_id"]].pop(key)
    workspace.public_dataset_job_path.write_text(json.dumps(saved))
    item = list_public_datasets(workspace, root)["items"][0]
    assert (item["stored"], item["partial"]) == (False, True)


def _legacy_job(workspace: OperationsWorkspace, item: PublicDataset) -> None:
    """The job a Web import left before imports recorded a source digest."""
    from industrial_phm.runtime import public_datasets

    job = {"kind": item.kind, "asset_id": item.asset_id, "state": "succeeded", "done": 2}
    workspace.public_dataset_job_path.parent.mkdir(parents=True, exist_ok=True)
    workspace.public_dataset_job_path.write_text(
        json.dumps({"schema": public_datasets._SCHEMA, "jobs": {item.dataset_id: job}})
    )


@pytest.mark.parametrize("changed", [False, True])
def test_aihub_history_stored_before_source_digests_is_versioned_not_stored_twice(
    tmp_path: Path, changed: bool
) -> None:
    from industrial_phm.runtime import public_datasets

    root = tmp_path / "data"
    _aihub(root)
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    item = public_datasets.find_public_datasets(root, workspace)[0]
    base = public_datasets._base_source(item)
    public_datasets._import_aihub(workspace, item, lambda _: None)
    _legacy_job(workspace, item)
    assert list_public_datasets(workspace, root)["items"][0]["partial"] is True
    if changed:
        with ZipFile(item.path) as opened:
            members = {name: opened.read(name) for name in opened.namelist()}
        with ZipFile(item.path, "w") as opened:
            for name, content in members.items():
                opened.writestr(name, content.replace(b"68.0", b"79.0"))

    jobs = PublicDatasetJobs(workspace.root, root=root)
    jobs.start({"dataset_id": item.dataset_id})
    jobs.close()
    listing = list_public_datasets(workspace, root)
    job = listing["jobs"][item.dataset_id]
    assert (job["state"], listing["items"][0]["stored"]) == ("succeeded", True)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    streams = {stream.source_id for stream in history.list_history_streams(item.asset_id)}
    assert [r.value for r in history.query_file_events(base)] == [68.0, 0.0]
    if changed:
        # Other bytes never join the earlier stream; they become a version of their own.
        assert job["source_id"] == f"{base}-{job['source_digest']}"
        assert streams == {base, job["source_id"]}
        assert [r.value for r in history.query_file_events(job["source_id"])] == [79.0, 0.0]
    else:
        assert (job["source_id"], streams) == (base, {base})
        # Importing the same bytes again keeps to the stream that took their digest.
        jobs = PublicDatasetJobs(workspace.root, root=root)
        jobs.start({"dataset_id": item.dataset_id})
        jobs.close()
        assert list_public_datasets(workspace, root)["jobs"][item.dataset_id]["source_id"] == base
        assert [r.value for r in history.query_file_events(base)] == [68.0, 0.0]


@pytest.mark.parametrize("moved", [False, True])
def test_xjtu_replay_stored_before_source_digests_is_versioned_unless_its_files_moved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, moved: bool
) -> None:
    from industrial_phm.adapters import XJTU_SY_CHANNELS
    from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
    from industrial_phm.demo import xjtu_models
    from industrial_phm.runtime import operations_web_phm_models, public_datasets

    root = tmp_path / "data"
    bearing = xjtu_models.held_out_bearings()[0]
    folder = root / public_datasets.XJTU_SOURCE / "35Hz12kN" / bearing
    folder.mkdir(parents=True)
    (folder / "1.csv").write_text(",".join(XJTU_SY_CHANNELS) + "\n0.1,0.2\n")
    monkeypatch.setattr(
        xjtu_models,
        "existing_packages",
        lambda _: {xjtu_models.IFOREST_RECIPE: "iforest", xjtu_models.LSTM_RECIPE: "lstm"},
    )
    bindings: list[str] = []
    monkeypatch.setattr(
        operations_web_phm_models,
        "create_phm_binding",
        lambda *_, **kwargs: bindings.append(kwargs["source_id"]),
    )
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    item = public_datasets.find_public_datasets(root, workspace)[0]
    public_datasets._import_xjtu(workspace, item, lambda _: None, lambda _: None)
    _legacy_job(workspace, item)
    data = root.rename(tmp_path / "moved-data") if moved else root

    jobs = PublicDatasetJobs(workspace.root, root=data)
    jobs.start({"dataset_id": item.dataset_id})
    jobs.close()
    listing = list_public_datasets(workspace, data)
    job = listing["jobs"][item.dataset_id]
    assert (job["state"], listing["items"][0]["stored"]) == ("succeeded", True)
    legacy = xjtu_models.XJTU_DEMO_SOURCE_ID
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    streams = {stream.source_id for stream in snapshots.list_streams()}
    if moved:
        # The earlier stream keeps the old path, so the moved files get a stream of their own.
        assert job["source_id"] == f"{legacy}-{job['source_digest']}"
        assert streams == {legacy, job["source_id"]}
        assert snapshots.get(job["source_id"], bearing, 1).file_path.is_file()
    else:
        assert (job["source_id"], streams) == (legacy, {legacy})
    assert bindings == [legacy, legacy, job["source_id"], job["source_id"]]


def test_source_change_during_import_cannot_be_recorded_as_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from collections.abc import Callable

    from industrial_phm.runtime import public_datasets

    root = tmp_path / "data"
    _aihub(root)
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    target = list_public_datasets(workspace, root)["items"][0]
    real_import = public_datasets._import_aihub

    def change_after_commit(
        destination: OperationsWorkspace, item: PublicDataset, progress: Callable[[int], None]
    ) -> None:
        real_import(destination, item, progress)
        stat = item.path.stat()
        os.utime(item.path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    monkeypatch.setattr(public_datasets, "_import_aihub", change_after_commit)
    jobs = PublicDatasetJobs(workspace.root, root=root)
    jobs.start({"dataset_id": target["dataset_id"]})
    jobs.close()
    listing = list_public_datasets(workspace, root)
    job = listing["jobs"][target["dataset_id"]]
    assert (job["state"], job["failure"]) == ("failed", "source-changed")
    item = listing["items"][0]
    assert (item["stored"], item["partial"], item["source_changed"]) == (False, True, True)
