import sqlite3
from pathlib import Path

import pytest

from industrial_phm.cli import main
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace


def test_operations_backup_restore_cli_round_trip_with_history_payload(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pytest.importorskip("filelock")

    workspace = OperationsWorkspace(tmp_path / "plant-a")
    initialize_operations_workspace(workspace)
    workspace.source_registry_path.write_text('{"source": "demo"}\n', encoding="utf-8")

    catalog = sqlite3.connect(workspace.history_catalog_path)
    try:
        catalog.execute("CREATE TABLE evidence(id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
        catalog.execute("INSERT INTO evidence(value) VALUES ('history-kept')")
        catalog.execute(
            'CREATE TABLE ducklake_metadata("key" TEXT NOT NULL, "value" TEXT NOT NULL, '
            '"scope" TEXT, scope_id INTEGER)'
        )
        catalog.execute(
            "INSERT INTO ducklake_metadata(key, value, scope, scope_id) VALUES (?, ?, NULL, NULL)",
            ["data_path", str(workspace.history_data_path.resolve()) + "/"],
        )
        catalog.execute(
            "CREATE TABLE ducklake_schema(path TEXT, path_is_relative BOOLEAN)"
        )
        catalog.execute(
            "INSERT INTO ducklake_schema(path, path_is_relative) VALUES ('raw/', 1)"
        )
        catalog.commit()
    finally:
        catalog.close()
    workspace.history_data_path.joinpath("part-1.parquet").write_bytes(b"history-data")
    workspace.logs_path.joinpath("collection.log").write_text("do-not-back-up\n", encoding="utf-8")

    backup = tmp_path / "backup-a"
    assert main(["operations", "backup", str(workspace.root), str(backup)]) == 0
    backup_output = capsys.readouterr().out
    assert f"workspace={workspace.root}" in backup_output
    assert f"backup={backup}" in backup_output
    assert "schema=industrial-phm-operations-backup-v1" in backup_output

    restored = OperationsWorkspace(tmp_path / "plant-restored")
    assert main(["operations", "restore", str(backup), str(restored.root)]) == 0
    restore_output = capsys.readouterr().out
    assert "state=restored" in restore_output

    restored_catalog = sqlite3.connect(restored.history_catalog_path)
    try:
        assert restored_catalog.execute("SELECT value FROM evidence").fetchone() == (
            "history-kept",
        )
    finally:
        restored_catalog.close()
    assert restored.history_data_path.joinpath("part-1.parquet").read_bytes() == b"history-data"
    restored_catalog = sqlite3.connect(restored.history_catalog_path)
    try:
        restored_data_path = restored_catalog.execute(
            "SELECT value FROM ducklake_metadata WHERE key = 'data_path'"
        ).fetchone()
        assert restored_data_path == (str(restored.history_data_path.resolve()) + "/",)
    finally:
        restored_catalog.close()
    assert tuple(restored.logs_path.iterdir()) == ()



def test_operations_restore_refuses_ducklake_absolute_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pytest.importorskip("filelock")

    workspace = OperationsWorkspace(tmp_path / "plant-a")
    initialize_operations_workspace(workspace)
    catalog = sqlite3.connect(workspace.history_catalog_path)
    try:
        catalog.execute(
            'CREATE TABLE ducklake_metadata("key" TEXT NOT NULL, "value" TEXT NOT NULL, '
            '"scope" TEXT, scope_id INTEGER)'
        )
        catalog.execute(
            "INSERT INTO ducklake_metadata(key, value, scope, scope_id) VALUES (?, ?, NULL, NULL)",
            ["data_path", str(workspace.history_data_path.resolve()) + "/"],
        )
        catalog.execute(
            "CREATE TABLE ducklake_schema(path TEXT, path_is_relative BOOLEAN)"
        )
        catalog.execute(
            "INSERT INTO ducklake_schema(path, path_is_relative) VALUES (?, 0)",
            [str(workspace.history_data_path.resolve() / "absolute-schema")],
        )
        catalog.commit()
    finally:
        catalog.close()

    backup = tmp_path / "backup-a"
    assert main(["operations", "backup", str(workspace.root), str(backup)]) == 0
    capsys.readouterr()

    restored = OperationsWorkspace(tmp_path / "plant-restored")
    exit_code = main(["operations", "restore", str(backup), str(restored.root)])

    assert exit_code == 1
    assert "absolute/custom paths" in capsys.readouterr().err
    assert not restored.root.exists()
