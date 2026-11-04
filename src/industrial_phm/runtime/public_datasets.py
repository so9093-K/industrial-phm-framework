"""Real public datasets prepared next to the workspace, imported from the Web in one step.

The Web lists the AI-Hub 239 power records and XJTU-SY bearing runs found in the datasets
folder (the repository's ``data/``, mounted read-only into the container) and imports one in
the supervisor's background:

- an AI-Hub member becomes the stored history of one asset, its source time read as KST;
- an XJTU-SY bearing the packaged models were not trained on is replayed with both anomaly
  models connected. The models are fitted once from the training bearings when the workspace
  has none.

A dataset that is missing or incomplete is never replaced by another one.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from industrial_phm.runtime.operations_web_setup import SourceControlConflict
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

AIHUB_ARCHIVES = Path("raw/aihub/239/archives")
XJTU_SOURCE = Path("interim/xjtu-sy/XJTU-SY_Bearing_Datasets")
_SCHEMA = "industrial-phm-public-dataset-jobs-v1"
# Local source time of a whole member; selection bounds, not claimed record times.
_WHOLE_MEMBER = (datetime(1900, 1, 1), datetime(2200, 1, 1))
_SPLITS = {"training": "학습용", "validation": "검증용"}
_PROGRESS_WRITE_SECONDS = 1.0


class DatasetImportError(RuntimeError):
    """An import that cannot proceed; ``code`` is the bounded reason shown on screen."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class PublicDataset:
    dataset_id: str
    kind: str
    asset_id: str
    path: Path
    member: str | None = None
    description: Mapping[str, object] = field(default_factory=dict)


def datasets_root() -> Path:
    """The folder that holds prepared public datasets; ``data/`` unless configured."""
    return Path(os.environ.get("INDUSTRIAL_PHM_DATASETS_DIR", "data"))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _equipment(stem: str) -> str:
    """``3.공기압축기`` → ``공기압축기``; ``1.펌프_일반모터`` → ``펌프·일반모터``."""
    return re.sub(r"^\d+\.", "", stem).replace("_", "·")


_IDENTITY_CACHE: dict[tuple[str, int, int], dict[str, tuple[str, str]]] = {}
_CACHE_LOCK = threading.Lock()


def _identities(archive: Path, index: Mapping[str, Any]) -> dict[str, tuple[str, str]]:
    """Device identifiers per member, reread only when the archive file changes.

    Reading every member's head of a few hundred members took about 5 s on a container's
    mounted folder, so the supervisor keeps an index in the workspace across restarts.
    """
    from industrial_phm.adapters.aihub_power import read_power_member_identities

    stat = archive.stat()
    key = (str(archive.resolve()), stat.st_size, stat.st_mtime_ns)
    with _CACHE_LOCK:
        held = _IDENTITY_CACHE.get(key)
    if held is None:
        entry = index.get(key[0])
        if (
            isinstance(entry, dict)
            and (entry.get("size"), entry.get("mtime_ns")) == key[1:]
            and isinstance(entry.get("members"), dict)
        ):
            held = {member: (str(ids[0]), str(ids[1])) for member, ids in entry["members"].items()}
        else:
            held = read_power_member_identities(archive)
        with _CACHE_LOCK:
            _IDENTITY_CACHE[key] = held
    return held


def _archives(root: Path) -> list[Path]:
    return sorted((root / AIHUB_ARCHIVES).glob("*/raw/*.zip"))


def _read_index(workspace: OperationsWorkspace | None) -> dict[str, Any]:
    if workspace is None:
        return {}
    try:
        data = json.loads(workspace.public_dataset_index_path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def write_public_dataset_index(workspace: OperationsWorkspace, root: Path | None = None) -> None:
    """Record each archive's member devices, so a restarted Web lists them at once."""
    root = root or datasets_root()
    index: dict[str, object] = {}
    for archive in _archives(root):
        try:
            identities = _identities(archive, {})
            stat = archive.stat()
        except OSError, ValueError, RuntimeError:
            continue
        index[str(archive.resolve())] = {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "members": {member: list(ids) for member, ids in identities.items()},
        }
    target = workspace.public_dataset_index_path
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, target)


def _aihub_datasets(root: Path, index: Mapping[str, Any]) -> list[PublicDataset]:
    found = []
    for archive in _archives(root):
        split = archive.parent.parent.name
        equipment = _equipment(archive.stem)
        try:
            identities = _identities(archive, index)
            with ZipFile(archive) as opened:
                sizes = {info.filename: info.file_size for info in opened.infolist()}
        except OSError, ValueError, RuntimeError:
            # An unreadable archive is left out rather than listed with guessed devices.
            continue
        for member, (device, board) in sorted(
            identities.items(), key=lambda item: (len(item[1][0]), item[1])
        ):
            found.append(
                PublicDataset(
                    dataset_id=f"aihub239:{split}:{archive.name}:{member}",
                    kind="aihub-239",
                    asset_id=f"{equipment} {device}" + ("" if board == "1" else f"-{board}"),
                    path=archive,
                    member=member,
                    description={
                        "equipment": equipment,
                        "split": _SPLITS.get(split, split),
                        "device_id": device,
                        "device_board_id": board,
                        "bytes": sizes.get(member),
                    },
                )
            )
    return found


def _xjtu_datasets(root: Path) -> list[PublicDataset]:
    from industrial_phm.adapters import list_xjtu_acquisition_files
    from industrial_phm.demo.xjtu_models import held_out_bearings

    source = root / XJTU_SOURCE
    if not source.is_dir():
        return []
    found = []
    for bearing in held_out_bearings():
        try:
            files = list_xjtu_acquisition_files(source, bearing)
        except OSError, ValueError:
            continue
        if not files:
            continue
        first = files[0]
        found.append(
            PublicDataset(
                dataset_id=f"xjtu-sy:{bearing}",
                kind="xjtu-sy",
                asset_id=bearing,
                path=source,
                description={
                    "bearing": bearing,
                    "rotational_speed_hz": first.rotational_speed_hz,
                    "radial_load_kn": first.radial_load_kn,
                    "acquisitions": len(files),
                },
            )
        )
    return found


def find_public_datasets(
    root: Path | None = None, workspace: OperationsWorkspace | None = None
) -> list[PublicDataset]:
    """Every importable dataset under the datasets folder, AI-Hub first."""
    root = root or datasets_root()
    if not root.is_dir():
        return []
    return [*_aihub_datasets(root, _read_index(workspace)), *_xjtu_datasets(root)]


def read_public_dataset_jobs(workspace: OperationsWorkspace) -> dict[str, dict[str, object]]:
    try:
        data = json.loads(workspace.public_dataset_job_path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    jobs = data.get("jobs") if isinstance(data, dict) and data.get("schema") == _SCHEMA else None
    return (
        {key: value for key, value in jobs.items() if isinstance(value, dict)}
        if isinstance(jobs, dict)
        else {}
    )


def _stored(workspace: OperationsWorkspace) -> tuple[set[str], dict[str, int]]:
    """Assets with stored history, and acquisitions replayed per XJTU-SY bearing."""
    from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
    from industrial_phm.demo.xjtu_models import XJTU_DEMO_SOURCE_ID
    from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig

    assets: set[str] = set()
    if workspace.history_catalog_path.is_file():
        history = DuckLakeAssetHistory(
            DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
        )
        assets = {item.asset_id for item in history.list_history_assets()}
    replayed: dict[str, int] = {}
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    for stream in snapshots.list_streams():
        if stream.source_id == XJTU_DEMO_SOURCE_ID:
            replayed[stream.asset_id] = stream.ordinal
    return assets, replayed


def list_public_datasets(
    workspace: OperationsWorkspace, root: Path | None = None
) -> dict[str, object]:
    """What the Web may offer to import, whether each is already stored, and the jobs."""
    root = root or datasets_root()
    datasets = find_public_datasets(root, workspace)
    try:
        assets, replayed = _stored(workspace)
    except OSError, ValueError, RuntimeError:
        assets, replayed = set(), {}
    items = []
    for item in datasets:
        stored = item.asset_id in assets if item.kind == "aihub-239" else item.asset_id in replayed
        items.append(
            {
                "dataset_id": item.dataset_id,
                "kind": item.kind,
                "asset_id": item.asset_id,
                "stored": stored,
                **item.description,
            }
        )
    return {
        "schema_version": 1,
        "available": root.is_dir(),
        "items": items,
        "jobs": read_public_dataset_jobs(workspace),
        "meaning": "public-datasets-found-in-the-datasets-folder-not-imported-evidence",
    }


def _import_aihub(
    workspace: OperationsWorkspace, item: PublicDataset, progress: Callable[[int], None]
) -> None:
    from industrial_phm.adapters.aihub_power_history import PowerHistoryBinding
    from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
    from industrial_phm.runtime.aihub_history_import import import_history
    from industrial_phm.runtime.operations_web_file_history import HISTORY_WRITE_LOCK

    split = item.dataset_id.split(":")[1]
    device, board = str(item.description["device_id"]), str(item.description["device_board_id"])
    binding = PowerHistoryBinding(
        source_id=f"aihub239-{split}-{device}-{board}",
        asset_id=item.asset_id,
        device_id=device,
        device_board_id=board,
        timezone="Asia/Seoul",
        identity_evidence="AI-Hub 239 원천 JSON의 DEVICE_ID·DEVICE_BD_ID; 실제 설비 확인 전",
        timezone_evidence="원본 시각에 시간대 표기가 없어 국내 구축 데이터로 보고 KST로 가정",
        version="research-v1",
    )
    assert item.member is not None
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    with HISTORY_WRITE_LOCK:
        import_history(item.path, item.member, binding, *_WHOLE_MEMBER, history, progress=progress)


def _code_revision() -> str | None:
    configured = os.environ.get("INDUSTRIAL_PHM_CODE_REVISION", "").strip()
    if configured:
        return configured
    from industrial_phm.commands.phm import _checkout_revision

    return _checkout_revision()


def _import_xjtu(
    workspace: OperationsWorkspace,
    item: PublicDataset,
    progress: Callable[[int], None],
    step: Callable[[str], None],
) -> None:
    from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
    from industrial_phm.demo.xjtu_models import (
        IFOREST_RECIPE,
        LSTM_RECIPE,
        XJTU_DEMO_SOURCE_ID,
        XjtuModelDemoConfig,
        existing_packages,
        fit_xjtu_packages,
    )
    from industrial_phm.demo.xjtu_snapshot_replay import replay_xjtu_bearing
    from industrial_phm.runtime.operations_web_phm_models import create_phm_binding

    packages = existing_packages(workspace.models_path)
    missing = [recipe for recipe in (IFOREST_RECIPE, LSTM_RECIPE) if recipe not in packages]
    if missing:
        step("models")
        revision = _code_revision()
        evidence = Path(os.environ.get("INDUSTRIAL_PHM_EVIDENCE_DIR", "docs/research/results"))
        if revision is None or not evidence.is_dir():
            raise DatasetImportError("models-unavailable")
        preset = XjtuModelDemoConfig(
            source=item.path,
            workspace=workspace.root,
            bearing=item.asset_id,
            evidence_root=evidence,
            code_revision=revision,
        )
        try:
            packages.update(fit_xjtu_packages(preset, workspace, missing, revision, lambda _: None))
        except ValueError as error:
            raise DatasetImportError("source-incomplete") from error
    for recipe in (IFOREST_RECIPE, LSTM_RECIPE):
        create_phm_binding(
            workspace,
            package_id=packages[recipe],
            source_id=XJTU_DEMO_SOURCE_ID,
            asset_id=item.asset_id,
            recorded_replay=True,
        )
    step("replay")
    delivered = 0

    def counted(_snapshot: object) -> None:
        nonlocal delivered
        delivered += 1
        progress(delivered)

    replay_xjtu_bearing(
        SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
        item.path,
        asset_id=item.asset_id,
        source_id=XJTU_DEMO_SOURCE_ID,
        interval_seconds=0.0,
        on_delivered=counted,
    )


def _failure(error: Exception) -> str:
    if isinstance(error, DatasetImportError):
        return error.code
    if isinstance(error, RuntimeError) and "extra" in str(error):
        return "reader-unavailable"
    if isinstance(error, (OSError, FileNotFoundError)):
        return "dataset-unavailable"
    return "import-failed"


class PublicDatasetJobs:
    """At most one import at a time, owned by the supervisor like FILE history jobs."""

    def __init__(self, workspace: Path, *, root: Path | None = None) -> None:
        self._workspace = OperationsWorkspace(workspace)
        self._root = root
        self._lock = threading.Lock()
        self._closed = False
        self._thread: threading.Thread | None = None
        self._written = 0.0
        # A new supervisor generation cannot be continuing an earlier thread.
        self._jobs = {
            key: (
                {**job, "state": "interrupted", "finished_at": _now()}
                if job.get("state") == "running"
                else job
            )
            for key, job in read_public_dataset_jobs(self._workspace).items()
        }
        if self._jobs:
            self._write()
        # The Web lists the archives from this index after a restart instead of rereading them.
        threading.Thread(target=self._index, name="public-dataset-index", daemon=True).start()

    def _index(self) -> None:
        # A missing index only makes the next listing slower; it is never required.
        with contextlib.suppress(OSError, ValueError, RuntimeError):
            write_public_dataset_index(self._workspace, self._root)

    def start(self, payload: dict[str, object]) -> dict[str, object]:
        """Check the selection synchronously, then import on a supervisor thread."""
        if set(payload) != {"dataset_id"} or not isinstance(payload["dataset_id"], str):
            raise ValueError("unexpected public dataset fields")
        dataset_id = payload["dataset_id"]
        with self._lock:
            if self._closed:
                raise SourceControlConflict("public dataset owner is shutting down")
            running = next(
                (key for key, job in self._jobs.items() if job.get("state") == "running"), None
            )
            if running == dataset_id:
                return self._view(dataset_id)
            if running is not None:
                raise SourceControlConflict("another public dataset import is running")
            item = next(
                (
                    d
                    for d in find_public_datasets(self._root, self._workspace)
                    if d.dataset_id == dataset_id
                ),
                None,
            )
            if item is None:
                raise ValueError("unknown public dataset")
            self._jobs[dataset_id] = {
                "kind": item.kind,
                "asset_id": item.asset_id,
                "state": "running",
                "step": "history" if item.kind == "aihub-239" else "replay",
                "done": 0,
                "started_at": _now(),
            }
            self._write()
            self._thread = threading.Thread(
                target=self._execute, args=(item,), name="public-dataset-import"
            )
            self._thread.start()
            return self._view(dataset_id)

    def _update(self, dataset_id: str, *, force: bool = False, **fields: object) -> None:
        with self._lock:
            self._jobs[dataset_id] = {**self._jobs[dataset_id], **fields}
            if force or time.monotonic() - self._written >= _PROGRESS_WRITE_SECONDS:
                self._write()

    def _execute(self, item: PublicDataset) -> None:
        key = item.dataset_id

        def progress(done: int) -> None:
            self._update(key, done=done)

        def step(name: str) -> None:
            self._update(key, step=name, force=True)

        try:
            if item.kind == "aihub-239":
                _import_aihub(self._workspace, item, progress)
            else:
                _import_xjtu(self._workspace, item, progress, step)
            update: dict[str, object] = {"state": "succeeded"}
        except Exception as error:  # A job records a bounded failure code only.
            update = {"state": "failed", "failure": _failure(error)}
        self._update(key, force=True, finished_at=_now(), **update)

    def _view(self, dataset_id: str) -> dict[str, object]:
        return {
            "schema_version": 1,
            "dataset_id": dataset_id,
            **self._jobs[dataset_id],
            "meaning": "background-public-dataset-import-status-not-history-evidence",
        }

    def _write(self) -> None:
        target = self._workspace.public_dataset_job_path
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(
            json.dumps({"schema": _SCHEMA, "jobs": self._jobs}, sort_keys=True), encoding="utf-8"
        )
        os.replace(temporary, target)
        self._written = time.monotonic()

    def close(self) -> None:
        """Let an in-flight import finish before the supervisor lease is released."""
        with self._lock:
            self._closed = True
            thread = self._thread
        if thread is not None:
            thread.join()
