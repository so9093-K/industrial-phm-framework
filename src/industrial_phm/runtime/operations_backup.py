"""Offline, integrity-checked backup and restore for one Operations workspace."""

from __future__ import annotations

import fcntl
import hashlib
import importlib
import json
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from industrial_phm.runtime.operations_config import load_operations_runtime_config
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

OPERATIONS_BACKUP_SCHEMA = "industrial-phm-operations-backup-v1"
_MANIFEST_NAME = "manifest.json"
_PAYLOAD_DIR = "payload"


class OperationsBackupFormatError(ValueError):
    """Raised when backup metadata or payload integrity is invalid."""


@dataclass(frozen=True, slots=True)
class OperationsBackupFile:
    """One workspace-owned file captured in a backup."""

    relative_path: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        _validate_relative_path(self.relative_path)
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int):
            raise ValueError("size_bytes must be an integer")
        if self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
        if (
            not isinstance(self.sha256, str)
            or len(self.sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.sha256)
        ):
            raise ValueError("sha256 must be a lowercase SHA-256 hex digest")


@dataclass(frozen=True, slots=True)
class OperationsBackupManifest:
    """Versioned integrity manifest for an offline workspace backup."""

    schema: str
    created_at: datetime
    files: tuple[OperationsBackupFile, ...]

    def __post_init__(self) -> None:
        if self.schema != OPERATIONS_BACKUP_SCHEMA:
            raise ValueError(f"unsupported Operations backup schema: {self.schema!r}")
        if not isinstance(self.created_at, datetime) or self.created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        paths = tuple(item.relative_path for item in self.files)
        if tuple(sorted(paths)) != paths:
            raise ValueError("backup files must be sorted by relative_path")
        if len(paths) != len(set(paths)):
            raise ValueError("backup files must not contain duplicate relative paths")

    @property
    def total_bytes(self) -> int:
        return sum(item.size_bytes for item in self.files)


@dataclass(frozen=True, slots=True)
class OperationsBackupResult:
    """Completed backup directory and its verified manifest."""

    backup_path: Path
    manifest: OperationsBackupManifest


def create_operations_backup(
    workspace: OperationsWorkspace,
    backup_path: Path,
    *,
    created_at: datetime | None = None,
) -> OperationsBackupResult:
    """Capture one stopped workspace into a new integrity-checked backup directory."""
    if not isinstance(workspace, OperationsWorkspace):
        raise ValueError("workspace must be OperationsWorkspace")
    if not isinstance(backup_path, Path):
        raise ValueError("backup_path must be Path")
    timestamp = datetime.now(UTC) if created_at is None else created_at
    if timestamp.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")
    _validate_backup_destination(workspace.root, backup_path)
    load_operations_runtime_config(workspace.config_path)

    backup_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = Path(
        tempfile.mkdtemp(prefix=f".{backup_path.name}.", suffix=".tmp", dir=backup_path.parent)
    )
    try:
        with _offline_workspace_guard(workspace):
            files = _capture_workspace_payload(workspace, temporary_path / _PAYLOAD_DIR)
            manifest = OperationsBackupManifest(
                schema=OPERATIONS_BACKUP_SCHEMA,
                created_at=timestamp,
                files=files,
            )
            _write_manifest(temporary_path / _MANIFEST_NAME, manifest)
            _verify_backup_payload(temporary_path, manifest)
        os.replace(temporary_path, backup_path)
    except BaseException:
        shutil.rmtree(temporary_path, ignore_errors=True)
        raise

    return OperationsBackupResult(backup_path=backup_path, manifest=manifest)


def validate_operations_backup(backup_path: Path) -> OperationsBackupManifest:
    """Load and verify one backup directory without mutating it."""
    if not isinstance(backup_path, Path):
        raise ValueError("backup_path must be Path")
    if not backup_path.is_dir():
        raise OSError(f"Operations backup directory does not exist: {backup_path}")
    manifest = _read_manifest(backup_path / _MANIFEST_NAME)
    _verify_backup_payload(backup_path, manifest)
    return manifest


def restore_operations_backup(
    backup_path: Path,
    workspace: OperationsWorkspace,
) -> OperationsBackupResult:
    """Restore a verified backup atomically into a new workspace root."""
    if not isinstance(workspace, OperationsWorkspace):
        raise ValueError("workspace must be OperationsWorkspace")
    manifest = validate_operations_backup(backup_path)
    root = workspace.root
    if root.exists():
        raise ValueError(f"restore destination must not already exist: {root}")
    _validate_separate_paths(root, backup_path)

    root.parent.mkdir(parents=True, exist_ok=True)
    temporary_root = Path(
        tempfile.mkdtemp(prefix=f".{root.name}.restore.", suffix=".tmp", dir=root.parent)
    )
    try:
        payload = backup_path / _PAYLOAD_DIR
        for item in manifest.files:
            source = payload / PurePosixPath(item.relative_path)
            destination = temporary_root / PurePosixPath(item.relative_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
        restored = OperationsWorkspace(temporary_root)
        load_operations_runtime_config(restored.config_path)
        restored.logs_path.mkdir(parents=True, exist_ok=True)
        os.replace(temporary_root, root)
    except BaseException:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise

    return OperationsBackupResult(backup_path=backup_path, manifest=manifest)


def _capture_workspace_payload(
    workspace: OperationsWorkspace,
    payload_root: Path,
) -> tuple[OperationsBackupFile, ...]:
    payload_root.mkdir(parents=True, exist_ok=True)
    sources = _workspace_owned_backup_files(workspace)
    captured: list[OperationsBackupFile] = []
    for relative_path, source in sources:
        destination = payload_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == ".sqlite":
            _backup_sqlite(source, destination)
        else:
            shutil.copy2(source, destination)
        captured.append(
            OperationsBackupFile(
                relative_path=relative_path.as_posix(),
                size_bytes=destination.stat().st_size,
                sha256=_sha256_file(destination),
            )
        )
    return tuple(sorted(captured, key=lambda item: item.relative_path))


def _workspace_owned_backup_files(
    workspace: OperationsWorkspace,
) -> tuple[tuple[Path, Path], ...]:
    root = workspace.root
    candidates = (workspace.config_path, *workspace.runtime_state_files)
    selected: dict[str, tuple[Path, Path]] = {}

    for source in candidates:
        if not source.exists():
            continue
        _require_regular_non_symlink_file(source)
        relative = source.relative_to(root)
        selected[relative.as_posix()] = (relative, source)

    if workspace.history_data_path.exists():
        if workspace.history_data_path.is_symlink() or not workspace.history_data_path.is_dir():
            raise ValueError(
                f"history data path must be a non-symlink directory: {workspace.history_data_path}"
            )
        for source in workspace.history_data_path.rglob("*"):
            if source.is_symlink():
                raise ValueError(f"backup does not follow symlinks: {source}")
            if source.is_dir():
                continue
            _require_regular_non_symlink_file(source)
            relative = source.relative_to(root)
            selected[relative.as_posix()] = (relative, source)

    if workspace.config_path.relative_to(root).as_posix() not in selected:
        raise OSError(f"Operations workspace config is unavailable: {workspace.config_path}")
    return tuple(selected[key] for key in sorted(selected))


def _backup_sqlite(source: Path, destination: Path) -> None:
    source_uri = f"file:{source.resolve()}?mode=ro"
    try:
        source_connection = sqlite3.connect(source_uri, uri=True)
        destination_connection = sqlite3.connect(destination)
        try:
            source_connection.backup(destination_connection)
        finally:
            destination_connection.close()
            source_connection.close()
    except sqlite3.Error as error:
        raise OperationsBackupFormatError(f"failed to snapshot SQLite file: {source}") from error


@contextmanager
def _offline_workspace_guard(workspace: OperationsWorkspace) -> Iterator[None]:
    """Prevent product supervisor/history access while an offline backup is captured."""
    if os.name != "posix":
        raise RuntimeError("Operations backup currently requires the POSIX local runtime")

    workspace.supervisor_lock_path.parent.mkdir(parents=True, exist_ok=True)
    with workspace.supervisor_lock_path.open("a+") as supervisor_lock:
        try:
            fcntl.flock(supervisor_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                f"Operations workspace is running; stop it before backup: {workspace.root}"
            ) from error

        history_lock: Any | None = None
        try:
            if workspace.history_catalog_path.exists():
                filelock = importlib.import_module("filelock")
                history_lock = filelock.FileLock(str(workspace.history_catalog_path) + ".phm.lock")
                try:
                    history_lock.acquire(timeout=0)
                except filelock.Timeout as error:
                    raise RuntimeError(
                        "Operations history is in use; stop history writers before backup"
                    ) from error
            yield
        finally:
            if history_lock is not None:
                history_lock.release()
            fcntl.flock(supervisor_lock.fileno(), fcntl.LOCK_UN)


def _write_manifest(path: Path, manifest: OperationsBackupManifest) -> None:
    payload = {
        "schema": manifest.schema,
        "created_at": manifest.created_at.isoformat(),
        "files": [
            {
                "relative_path": item.relative_path,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
            }
            for item in manifest.files
        ],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_manifest(path: Path) -> OperationsBackupManifest:
    if not path.is_file():
        raise OperationsBackupFormatError(f"backup manifest is unavailable: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise OperationsBackupFormatError("backup manifest must contain valid JSON") from error
    if not isinstance(raw, dict) or set(raw) != {"schema", "created_at", "files"}:
        raise OperationsBackupFormatError("backup manifest has unsupported root keys")
    schema = raw["schema"]
    created_at_raw = raw["created_at"]
    files_raw = raw["files"]
    if not isinstance(schema, str) or not isinstance(created_at_raw, str):
        raise OperationsBackupFormatError("backup manifest schema/created_at is invalid")
    if not isinstance(files_raw, list):
        raise OperationsBackupFormatError("backup manifest files must be a list")
    try:
        created_at = datetime.fromisoformat(created_at_raw)
        files = tuple(_parse_manifest_file(value) for value in files_raw)
        return OperationsBackupManifest(schema=schema, created_at=created_at, files=files)
    except (TypeError, ValueError) as error:
        raise OperationsBackupFormatError(f"invalid backup manifest: {error}") from error


def _parse_manifest_file(value: object) -> OperationsBackupFile:
    if not isinstance(value, dict) or set(value) != {"relative_path", "size_bytes", "sha256"}:
        raise OperationsBackupFormatError("backup manifest file entry has unsupported keys")
    relative_path = value["relative_path"]
    size_bytes = value["size_bytes"]
    sha256 = value["sha256"]
    if not isinstance(relative_path, str) or not isinstance(size_bytes, int) or not isinstance(sha256, str):
        raise OperationsBackupFormatError("backup manifest file entry has invalid types")
    return OperationsBackupFile(relative_path, size_bytes, sha256)


def _verify_backup_payload(
    backup_path: Path,
    manifest: OperationsBackupManifest,
) -> None:
    payload_root = backup_path / _PAYLOAD_DIR
    if not payload_root.is_dir():
        raise OperationsBackupFormatError("backup payload directory is unavailable")
    expected = {item.relative_path for item in manifest.files}
    actual: set[str] = set()
    for path in payload_root.rglob("*"):
        if path.is_symlink():
            raise OperationsBackupFormatError(f"backup payload contains a symlink: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise OperationsBackupFormatError(f"backup payload contains a non-file: {path}")
        actual.add(path.relative_to(payload_root).as_posix())
    if actual != expected:
        raise OperationsBackupFormatError(
            f"backup payload file set mismatch: missing={sorted(expected - actual)!r} "
            f"extra={sorted(actual - expected)!r}"
        )

    for item in manifest.files:
        path = payload_root / PurePosixPath(item.relative_path)
        if path.stat().st_size != item.size_bytes:
            raise OperationsBackupFormatError(f"backup size mismatch: {item.relative_path}")
        if _sha256_file(path) != item.sha256:
            raise OperationsBackupFormatError(f"backup checksum mismatch: {item.relative_path}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_backup_destination(workspace_root: Path, backup_path: Path) -> None:
    if backup_path.exists():
        raise ValueError(f"backup destination must not already exist: {backup_path}")
    _validate_separate_paths(workspace_root, backup_path)
    workspace_resolved = workspace_root.expanduser().resolve(strict=False)
    backup_resolved = backup_path.expanduser().resolve(strict=False)
    if backup_resolved.is_relative_to(workspace_resolved):
        raise ValueError("backup destination must not be inside the Operations workspace")


def _validate_separate_paths(first: Path, second: Path) -> None:
    first_resolved = first.expanduser().resolve(strict=False)
    second_resolved = second.expanduser().resolve(strict=False)
    if first_resolved == second_resolved:
        raise ValueError("backup and workspace paths must be distinct")


def _require_regular_non_symlink_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"backup source must be a regular non-symlink file: {path}")


def _validate_relative_path(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("relative_path must not be empty")
    path = PurePosixPath(value)
    if path.is_absolute() or "." in path.parts or ".." in path.parts:
        raise ValueError(f"relative_path must stay inside the backup payload: {value!r}")
