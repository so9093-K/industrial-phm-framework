import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import BinaryIO

import pytest

pytest.importorskip("asyncua")
pytest.importorskip("duckdb")
pytest.importorskip("marimo")

from industrial_phm.application import (
    SqliteObservationWindowRepository,
    SqlitePhaseUnbalanceRepository,
)
from industrial_phm.demo import SYNTHETIC_DEMO_SOURCE_ID
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime import OperationsWorkspace

_CLI_BOOTSTRAP = "from industrial_phm.cli import main; raise SystemExit(main())"


def _cli_argv(*args: str) -> list[str]:
    return [sys.executable, "-c", _CLI_BOOTSTRAP, *args]


def _free_loopback_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _run_cli(*args: str, timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _cli_argv(*args),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _start_demo(
    workspace: Path,
    *,
    opcua_port: int,
    ui_port: int,
    process_log_path: Path,
) -> tuple[subprocess.Popen[bytes], BinaryIO]:
    process_log = process_log_path.open("ab", buffering=0)
    process = subprocess.Popen(
        _cli_argv(
            "demo",
            "synthetic",
            "--workspace",
            str(workspace),
            "--opcua-port",
            str(opcua_port),
            "--ui-port",
            str(ui_port),
            "--publish-interval-seconds",
            "0.2",
            "--startup-timeout-seconds",
            "10",
        ),
        stdin=subprocess.DEVNULL,
        stdout=process_log,
        stderr=subprocess.STDOUT,
    )
    return process, process_log


def _process_log(path: Path) -> str:
    if not path.is_file():
        return "<process log unavailable>"
    return path.read_text(encoding="utf-8", errors="replace")


def _wait_until_ready(
    process: subprocess.Popen[bytes],
    workspace: Path,
    *,
    process_log_path: Path,
    timeout: float = 30.0,
) -> None:
    deadline = time.monotonic() + timeout
    last_status = ""
    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            raise AssertionError(
                f"synthetic demo exited before ready: code={return_code}\n"
                f"{_process_log(process_log_path)}"
            )
        status = _run_cli("operations", "status", str(workspace))
        last_status = f"stdout:\n{status.stdout}\nstderr:\n{status.stderr}"
        if status.returncode == 0:
            assert "ready=yes" in status.stdout
            assert "collection condition=running" in status.stdout
            assert "analysis condition=running" in status.stdout
            assert "ui condition=running" in status.stdout
            return
        time.sleep(0.25)
    raise AssertionError(
        f"Operations node did not become ready within {timeout:g}s\n"
        f"{last_status}\n{_process_log(process_log_path)}"
    )


def _wait_for_analysis_evidence(
    workspace: OperationsWorkspace,
    *,
    timeout: float = 35.0,
) -> tuple[int, int]:
    windows = SqliteObservationWindowRepository(workspace.window_state_path)
    analysis = SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path)
    deadline = time.monotonic() + timeout
    latest = (0, 0)
    while time.monotonic() < deadline:
        latest = (len(windows.list_windows()), analysis.count_results())
        if latest[0] > 0 and latest[1] > 0:
            return latest
        time.sleep(0.25)
    raise AssertionError(
        "synthetic demo produced no finalized-window/analysis evidence "
        f"within {timeout:g}s: windows={latest[0]} results={latest[1]}"
    )


def _stop_demo(
    process: subprocess.Popen[bytes],
    workspace: Path,
    *,
    process_log_path: Path,
    assert_success: bool,
) -> None:
    if process.poll() is not None:
        if assert_success:
            assert process.returncode == 0, _process_log(process_log_path)
        return

    stop = _run_cli("operations", "stop", str(workspace))
    if assert_success:
        assert stop.returncode == 0, f"stdout={stop.stdout}\nstderr={stop.stderr}"
        assert "stop=requested" in stop.stdout
    try:
        return_code = process.wait(timeout=20.0)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            return_code = process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()
            return_code = process.wait(timeout=5.0)
    if assert_success:
        assert return_code == 0, _process_log(process_log_path)


def test_clean_workspace_synthetic_node_reaches_evidence_and_restarts(tmp_path: Path) -> None:
    root = tmp_path / "plant-demo"
    workspace = OperationsWorkspace(root)
    opcua_port = _free_loopback_port()
    ui_port = _free_loopback_port()
    while ui_port == opcua_port:
        ui_port = _free_loopback_port()

    first_log = tmp_path / "demo-first.log"
    first, first_handle = _start_demo(
        root,
        opcua_port=opcua_port,
        ui_port=ui_port,
        process_log_path=first_log,
    )
    try:
        _wait_until_ready(first, root, process_log_path=first_log)
        first_windows, first_results = _wait_for_analysis_evidence(workspace)
        logs = _run_cli(
            "operations",
            "logs",
            str(root),
            "--component",
            "ui",
            "--lines",
            "20",
        )
        assert logs.returncode == 0, f"stdout={logs.stdout}\nstderr={logs.stderr}"
        _stop_demo(
            first,
            root,
            process_log_path=first_log,
            assert_success=True,
        )
    finally:
        _stop_demo(
            first,
            root,
            process_log_path=first_log,
            assert_success=False,
        )
        first_handle.close()

    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(
            catalog_path=workspace.history_catalog_path,
            data_path=workspace.history_data_path,
        )
    )
    first_events = history.query_opcua_events(SYNTHETIC_DEMO_SOURCE_ID)
    assert first_events
    first_event_count = len(first_events)

    second_log = tmp_path / "demo-second.log"
    second, second_handle = _start_demo(
        root,
        opcua_port=opcua_port,
        ui_port=ui_port,
        process_log_path=second_log,
    )
    try:
        _wait_until_ready(second, root, process_log_path=second_log)
        time.sleep(2.0)
        _stop_demo(
            second,
            root,
            process_log_path=second_log,
            assert_success=True,
        )
    finally:
        _stop_demo(
            second,
            root,
            process_log_path=second_log,
            assert_success=False,
        )
        second_handle.close()

    final_events = history.query_opcua_events(SYNTHETIC_DEMO_SOURCE_ID)
    final_windows = SqliteObservationWindowRepository(workspace.window_state_path).list_windows()
    final_results = SqlitePhaseUnbalanceRepository(
        workspace.phase_unbalance_state_path
    ).count_results()

    assert len(final_events) > first_event_count
    assert len(final_windows) >= first_windows
    assert final_results >= first_results


def test_stopped_workspace_backup_restores_and_restarts_as_new_node(tmp_path: Path) -> None:
    root = tmp_path / "plant-original"
    workspace = OperationsWorkspace(root)
    opcua_port = _free_loopback_port()
    ui_port = _free_loopback_port()
    while ui_port == opcua_port:
        ui_port = _free_loopback_port()

    original_log = tmp_path / "demo-original.log"
    original, original_handle = _start_demo(
        root,
        opcua_port=opcua_port,
        ui_port=ui_port,
        process_log_path=original_log,
    )
    try:
        _wait_until_ready(original, root, process_log_path=original_log)
        original_windows, original_results = _wait_for_analysis_evidence(workspace)
        _stop_demo(
            original,
            root,
            process_log_path=original_log,
            assert_success=True,
        )
    finally:
        _stop_demo(
            original,
            root,
            process_log_path=original_log,
            assert_success=False,
        )
        original_handle.close()

    original_history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(
            catalog_path=workspace.history_catalog_path,
            data_path=workspace.history_data_path,
        )
    )
    original_events = original_history.query_opcua_events(SYNTHETIC_DEMO_SOURCE_ID)
    assert original_events
    original_event_count = len(original_events)

    backup = tmp_path / "plant-backup"
    backup_result = _run_cli("operations", "backup", str(root), str(backup))
    assert backup_result.returncode == 0, (
        f"stdout={backup_result.stdout}\nstderr={backup_result.stderr}"
    )
    assert "schema=industrial-phm-operations-backup-v1" in backup_result.stdout

    restored_root = tmp_path / "plant-restored"
    restore_result = _run_cli("operations", "restore", str(backup), str(restored_root))
    assert restore_result.returncode == 0, (
        f"stdout={restore_result.stdout}\nstderr={restore_result.stderr}"
    )
    assert "state=restored" in restore_result.stdout
    restored_workspace = OperationsWorkspace(restored_root)
    assert not restored_workspace.supervisor_state_path.exists()
    assert tuple(restored_workspace.logs_path.iterdir()) == ()

    restored_log = tmp_path / "demo-restored.log"
    restored, restored_handle = _start_demo(
        restored_root,
        opcua_port=opcua_port,
        ui_port=ui_port,
        process_log_path=restored_log,
    )
    try:
        _wait_until_ready(restored, restored_root, process_log_path=restored_log)
        time.sleep(2.0)
        _stop_demo(
            restored,
            restored_root,
            process_log_path=restored_log,
            assert_success=True,
        )
    finally:
        _stop_demo(
            restored,
            restored_root,
            process_log_path=restored_log,
            assert_success=False,
        )
        restored_handle.close()

    restored_history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(
            catalog_path=restored_workspace.history_catalog_path,
            data_path=restored_workspace.history_data_path,
        )
    )
    restored_events = restored_history.query_opcua_events(SYNTHETIC_DEMO_SOURCE_ID)
    restored_windows = SqliteObservationWindowRepository(
        restored_workspace.window_state_path
    ).list_windows()
    restored_results = SqlitePhaseUnbalanceRepository(
        restored_workspace.phase_unbalance_state_path
    ).count_results()

    assert len(restored_events) > original_event_count
    assert len(restored_windows) >= original_windows
    assert restored_results >= original_results
    assert len(original_history.query_opcua_events(SYNTHETIC_DEMO_SOURCE_ID)) == (
        original_event_count
    )
