import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from industrial_phm.runtime import (
    OperationsBackupFormatError,
    OperationsWorkspace,
    create_operations_backup,
    initialize_operations_workspace,
    restore_operations_backup,
    validate_operations_backup,
)


def _seed_workspace(root: Path) -> OperationsWorkspace:
    workspace = OperationsWorkspace(root)
    initialize_operations_workspace(workspace)
    workspace.source_registry_path.write_text('{"demo": true}\n', encoding="utf-8")
    connection = sqlite3.connect(workspace.collection_control_path)
    try:
        connection.execute("CREATE TABLE demo(value TEXT NOT NULL)")
        connection.execute("INSERT INTO demo(value) VALUES ('kept')")
        connection.commit()
    finally:
        connection.close()
    workspace.history_data_path.joinpath("raw").mkdir(parents=True)
    workspace.history_data_path.joinpath("raw", "evidence.parquet").write_bytes(b"parquet-demo")
    workspace.logs_path.joinpath("ui.log").write_text("ephemeral log\n", encoding="utf-8")
    workspace.supervisor_state_path.parent.mkdir(parents=True, exist_ok=True)
    workspace.supervisor_state_path.write_text('{"state": "stale"}\n', encoding="utf-8")
    workspace.history_catalog_path.with_name(
        workspace.history_catalog_path.name + ".phm-batch-index.sqlite"
    ).write_bytes(b"derived")
    return workspace


def test_backup_and_restore_preserve_owned_state_without_ephemeral_files(
    tmp_path: Path,
) -> None:
    workspace = _seed_workspace(tmp_path / "plant-a")
    backup = tmp_path / "backup-a"

    result = create_operations_backup(
        workspace,
        backup,
        created_at=datetime(2026, 10, 2, 9, 0, tzinfo=UTC),
    )

    relative_paths = {item.relative_path for item in result.manifest.files}
    assert "config.toml" in relative_paths
    assert "sources.json" in relative_paths
    assert "control.sqlite" in relative_paths
    assert "data/raw/evidence.parquet" in relative_paths
    assert "logs/ui.log" not in relative_paths
    assert "runtime/supervisor.json" not in relative_paths
    assert "catalog.sqlite.phm-batch-index.sqlite" not in relative_paths
    assert result.manifest.total_bytes > 0
    assert validate_operations_backup(backup) == result.manifest

    backup_db = sqlite3.connect(backup / "payload" / "control.sqlite")
    try:
        assert backup_db.execute("SELECT value FROM demo").fetchone() == ("kept",)
    finally:
        backup_db.close()

    restored = OperationsWorkspace(tmp_path / "plant-b")
    restore_operations_backup(backup, restored)

    assert restored.config_path.is_file()
    assert restored.source_registry_path.read_text(encoding="utf-8") == '{"demo": true}\n'
    assert (
        restored.history_data_path.joinpath("raw", "evidence.parquet").read_bytes()
        == b"parquet-demo"
    )
    assert restored.logs_path.is_dir()
    assert tuple(restored.logs_path.iterdir()) == ()
    assert not restored.supervisor_state_path.exists()
    assert not restored.history_catalog_path.with_name(
        restored.history_catalog_path.name + ".phm-batch-index.sqlite"
    ).exists()
    restored_db = sqlite3.connect(restored.collection_control_path)
    try:
        assert restored_db.execute("SELECT value FROM demo").fetchone() == ("kept",)
    finally:
        restored_db.close()


def test_backup_refuses_live_supervisor_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = _seed_workspace(tmp_path / "plant-a")
    import industrial_phm.runtime.operations_backup as backup_module

    assert backup_module.fcntl is not None
    real_flock = backup_module.fcntl.flock

    def busy_lock(file_descriptor: int, operation: int) -> None:
        if operation == backup_module.fcntl.LOCK_EX | backup_module.fcntl.LOCK_NB:
            raise BlockingIOError
        real_flock(file_descriptor, operation)

    monkeypatch.setattr(backup_module.fcntl, "flock", busy_lock)

    with pytest.raises(RuntimeError, match="stop it before backup"):
        create_operations_backup(workspace, tmp_path / "backup-a")


def test_validate_backup_rejects_payload_tamper(tmp_path: Path) -> None:
    workspace = _seed_workspace(tmp_path / "plant-a")
    backup = tmp_path / "backup-a"
    create_operations_backup(workspace, backup)

    (backup / "payload" / "sources.json").write_text('{"tampered": true}\n', encoding="utf-8")

    with pytest.raises(OperationsBackupFormatError, match=r"backup (size|checksum) mismatch"):
        validate_operations_backup(backup)


def test_validate_backup_rejects_manifest_path_escape(tmp_path: Path) -> None:
    workspace = _seed_workspace(tmp_path / "plant-a")
    backup = tmp_path / "backup-a"
    create_operations_backup(workspace, backup)

    manifest_path = backup / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["relative_path"] = "../escape"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(OperationsBackupFormatError, match="relative_path"):
        validate_operations_backup(backup)


def test_restore_refuses_existing_destination(tmp_path: Path) -> None:
    workspace = _seed_workspace(tmp_path / "plant-a")
    backup = tmp_path / "backup-a"
    create_operations_backup(workspace, backup)
    destination = OperationsWorkspace(tmp_path / "plant-b")
    destination.root.mkdir()

    with pytest.raises(ValueError, match="must not already exist"):
        restore_operations_backup(backup, destination)
