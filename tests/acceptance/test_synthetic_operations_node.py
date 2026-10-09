import json
import socket
import subprocess
import sys
import threading
import time
from dataclasses import replace
from http.client import HTTPConnection
from pathlib import Path
from typing import BinaryIO

import pytest

pytest.importorskip("asyncua")
pytest.importorskip("duckdb")
pytest.importorskip("marimo")

from industrial_phm.application import (
    JsonFindingReviewRepository,
    JsonOperationalFindingRepository,
    JsonSourceRepository,
    SqliteObservationWindowRepository,
    SqlitePhaseUnbalanceRepository,
)
from industrial_phm.demo import SYNTHETIC_DEMO_SOURCE_ID
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime import (
    OperationsUiConfig,
    OperationsWorkspace,
    initialize_operations_workspace,
)
from industrial_phm.runtime.operations_config import write_operations_runtime_config
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from industrial_phm.runtime.operations_web_review import (
    record_web_review_action,
    request_web_analysis_review,
)
from tests.support.window_analysis import phase_unbalance_analysis

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
    return _tail_log(path)


def _tail_log(path: Path, *, limit_bytes: int = 8192) -> str:
    """Capture bounded child evidence when CI fails, without reading whole logs."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            skipped = max(0, size - limit_bytes)
            handle.seek(skipped)
            body = handle.read(limit_bytes).decode("utf-8", errors="replace")
    except FileNotFoundError:
        return "<log not created>"
    return (f"<earlier {skipped} bytes omitted>\n" if skipped else "") + body


def _pipeline_failure_evidence(
    workspace: OperationsWorkspace,
    *,
    process: subprocess.Popen[bytes],
    process_log_path: Path,
) -> str:
    """Surface the exact pipeline boundary that failed instead of just a timeout."""
    lines = [f"demo process returncode: {process.poll()}"]
    try:
        status = _run_cli("operations", "status", str(workspace.root), timeout=10.0)
        lines.append(
            f"operations status exit={status.returncode}\n"
            f"stdout:\n{status.stdout[-8192:]}\nstderr:\n{status.stderr[-4096:]}"
        )
    except subprocess.TimeoutExpired:
        lines.append("operations status command timed out after 10s")

    lines.append(f"demo launcher:\n{_process_log(process_log_path)}")
    for filename in ("synthetic-opcua.log", "collection.log", "analysis.log", "ui.log"):
        lines.append(f"{filename}:\n{_tail_log(workspace.logs_path / filename)}")
    for label, path in (
        ("history catalog", workspace.history_catalog_path),
        ("spool", workspace.acquisition_spool_path),
        ("window SQLite", workspace.window_state_path),
        ("analysis SQLite", workspace.phase_unbalance_state_path),
    ):
        lines.append(f"{label} exists={path.is_file()}")
    return "\n".join(lines)


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
    process: subprocess.Popen[bytes],
    process_log_path: Path,
    timeout: float = 60.0,
) -> tuple[int, int]:
    """Require persisted results after a real 10s event window + 2s lateness.

    CI workers run several heavyweight Python/OPC UA/DuckLake jobs in parallel:
    the prior blind 35s deadline sometimes expired even though a retry passed.
    Keep an absolute bound; distinguish early child death and emit bounded
    per-component evidence if the data pipeline never completes.
    """
    windows = SqliteObservationWindowRepository(workspace.window_state_path)
    analysis = SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path)
    deadline = time.monotonic() + timeout
    latest = (0, 0)
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise AssertionError(
                "synthetic demo process exited before finalized-window/analysis evidence\n"
                + _pipeline_failure_evidence(
                    workspace, process=process, process_log_path=process_log_path
                )
            )
        latest = (len(windows.list_windows()), analysis.count_results())
        if latest[0] > 0 and latest[1] > 0:
            return latest
        time.sleep(0.25)
    raise AssertionError(
        "synthetic demo produced no finalized-window/analysis evidence "
        f"within {timeout:g}s: windows={latest[0]} results={latest[1]}\n"
        + _pipeline_failure_evidence(workspace, process=process, process_log_path=process_log_path)
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
        first_windows, first_results = _wait_for_analysis_evidence(
            workspace, process=first, process_log_path=first_log
        )
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
        original_windows, original_results = _wait_for_analysis_evidence(
            workspace, process=original, process_log_path=original_log
        )
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
    backup_result = _run_cli("maintenance", "backup", str(root), str(backup))
    assert backup_result.returncode == 0, (
        f"stdout={backup_result.stdout}\nstderr={backup_result.stderr}"
    )
    assert "schema=industrial-phm-operations-backup-v1" in backup_result.stdout

    restored_root = tmp_path / "plant-restored"
    restore_result = _run_cli("maintenance", "restore", str(backup), str(restored_root))
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


def test_synthetic_ci_log_tail_is_bounded(tmp_path: Path) -> None:
    log = tmp_path / "collector.log"
    assert _tail_log(log) == "<log not created>"
    log.write_bytes(b"x" * 10000 + b"\nSOURCE_CONNECTION_FAILED\n")
    tail = _tail_log(log, limit_bytes=1024)
    assert tail.startswith("<earlier 9002 bytes omitted>\n")
    assert "SOURCE_CONNECTION_FAILED" in tail
    assert len(tail) < 1150


def test_supervised_web_preview_is_readable_but_cannot_write(
    tmp_path: Path,
) -> None:
    """Real supervised UI process must keep the owner's lifetime writer lease."""
    root = tmp_path / "web-readonly-supervisor"
    workspace = OperationsWorkspace(root)
    initialization = initialize_operations_workspace(workspace)
    port = _free_loopback_port()
    write_operations_runtime_config(
        workspace.config_path,
        replace(initialization.config, ui=OperationsUiConfig(port=port)),
    )
    logfile = tmp_path / "readonly-supervisor.log"
    handle = logfile.open("ab", buffering=0)
    process = subprocess.Popen(
        _cli_argv("operations", "start", str(root), "--ui", "web-preview"),
        stdin=subprocess.DEVNULL,
        stdout=handle,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + 45
        while True:
            if process.poll() is not None:
                pytest.fail("supervised Web preview exited before ready:\n" + _process_log(logfile))
            try:
                connection = HTTPConnection("127.0.0.1", port, timeout=3)
                connection.request("GET", "/web/")
                response = connection.getresponse()
                html = response.read()
                connection.close()
                if response.status == 200 and b"Operations" in html:
                    break
            except OSError:
                pass
            if time.monotonic() >= deadline:
                pytest.fail("supervised Web preview not ready:\n" + _process_log(logfile))
            time.sleep(0.3)

        deadline = time.monotonic() + 30
        while True:
            status = _run_cli("operations", "status", str(root))
            if status.returncode == 0 and "ready=yes" in status.stdout:
                break
            if process.poll() is not None or time.monotonic() >= deadline:
                pytest.fail(
                    "supervisor did not report all components ready:\n"
                    + status.stdout
                    + status.stderr
                    + "\n"
                    + _process_log(logfile)
                )
            time.sleep(0.3)

        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        connection.request("GET", "/api/v1/session")
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        assert response.status == 200
        token = payload["csrf_token"]
        assert isinstance(token, str)

        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        body = b"{}"
        connection.request(
            "POST",
            "/api/v1/sources/file",
            body=body,
            headers={
                "Host": f"127.0.0.1:{port}",
                "Origin": f"http://127.0.0.1:{port}",
                "Sec-Fetch-Site": "same-origin",
                "X-CSRF-Token": token,
                "Content-Type": "application/json",
            },
        )
        result = connection.getresponse()
        rejection = json.loads(result.read())
        connection.close()
        assert result.status == 409
        assert rejection["error"]["code"] == "workspace_writer_busy"
        assert JsonSourceRepository(workspace.source_registry_path).list_sources() == ()

        stopped = _run_cli("operations", "stop", str(root))
        assert stopped.returncode == 0, stopped.stderr
        assert process.wait(timeout=20) == 0, _process_log(logfile)
    finally:
        if process.poll() is None:
            _run_cli("operations", "stop", str(root), timeout=10)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        handle.close()


def test_supervised_web_controlled_mode_persists_but_external_preview_cannot_write(
    tmp_path: Path,
) -> None:
    """Real HTTP mutation must execute in supervisor; a separate preview stays read-only."""
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux peer credentials required for supervised actions")
    root = tmp_path / "web-controlled"
    workspace = OperationsWorkspace(root)
    initialization = initialize_operations_workspace(workspace)
    input_dir = root / "inputs"
    input_dir.mkdir()
    (input_dir / "phases.csv").write_text(
        "timestamp,phase-R,phase-S,phase-T\n"
        "2026-10-08T12:00:00+00:00,220.5,219.0,221.0\n"
        "2026-10-08T12:00:01+00:00,220.6,219.1,221.1\n",
        encoding="utf-8",
    )
    port = _free_loopback_port()
    write_operations_runtime_config(
        workspace.config_path,
        replace(initialization.config, ui=OperationsUiConfig(port=port)),
    )
    logfile = tmp_path / "controlled-supervisor.log"
    handle = logfile.open("ab", buffering=0)
    process = subprocess.Popen(
        _cli_argv("operations", "start", str(root), "--ui", "web-controlled"),
        stdin=subprocess.DEVNULL,
        stdout=handle,
        stderr=subprocess.STDOUT,
    )

    def request(
        on_port: int,
        method: str,
        route: str,
        *,
        body: dict[str, object] | None = None,
        token: str | None = None,
    ) -> tuple[int, dict[str, object]]:
        conn = HTTPConnection("127.0.0.1", on_port, timeout=7)
        headers = {"Host": f"127.0.0.1:{on_port}"}
        raw = None
        if body is not None:
            raw = json.dumps(body).encode()
            headers.update(
                {
                    "Origin": f"http://127.0.0.1:{on_port}",
                    "Sec-Fetch-Site": "same-origin",
                    "X-CSRF-Token": token or "",
                    "Content-Type": "application/json",
                }
            )
        try:
            conn.request(method, route, body=raw, headers=headers)
            response = conn.getresponse()
            parsed = json.loads(response.read())
            assert isinstance(parsed, dict)
            return response.status, parsed
        finally:
            conn.close()

    try:
        deadline = time.monotonic() + 50
        while True:
            if process.poll() is not None:
                pytest.fail("controlled Web exited before ready:\n" + _process_log(logfile))
            try:
                status, session = request(port, "GET", "/api/v1/session")
                if status == 200:
                    break
            except OSError:
                pass
            if time.monotonic() >= deadline:
                pytest.fail("controlled Web not ready:\n" + _process_log(logfile))
            time.sleep(0.2)
        assert session["write_scope"] == "supervisor-owned-source-control"
        csrf = session["csrf_token"]
        assert isinstance(csrf, str)
        source: dict[str, object] = {
            "source_id": "supervised-file",
            "name": "Prepared three phase CSV",
            "asset_id": "pump-01",
            "file_path": "inputs/phases.csv",
            "channel_columns": ["phase-R", "phase-S", "phase-T"],
            "measurement_point_id": "panel",
            "timestamp_column": "timestamp",
        }
        assert request(port, "POST", "/api/v1/sources/file", body=source, token="bad")[0] == 403
        assert request(port, "POST", "/api/v1/sources/file", body=source, token=csrf)[0] == 201
        assert JsonSourceRepository(workspace.source_registry_path).get("supervised-file")
        assert request(port, "POST", "/api/v1/sources/file", body=source, token=csrf)[0] == 409
        assert request(port, "GET", "/api/v1/sources")[1]["sources"]["total"] == 1

        external = create_operations_web_read_server(workspace.root)
        external_thread = threading.Thread(target=external.serve_forever, daemon=True)
        external_thread.start()
        try:
            outside_port = external.server_port
            csrf_outside = request(outside_port, "GET", "/api/v1/session")[1]["csrf_token"]
            assert isinstance(csrf_outside, str)
            result = request(
                outside_port, "POST", "/api/v1/sources/file", body=source, token=csrf_outside
            )
            assert result[0] == 409
            assert result[1]["error"]["code"] == "workspace_writer_busy"
        finally:
            external.shutdown()
            external.server_close()
            external_thread.join(timeout=5)

        stopped = _run_cli("operations", "stop", str(root))
        assert stopped.returncode == 0, stopped.stderr
        assert process.wait(timeout=20) == 0, _process_log(logfile)
    finally:
        if process.poll() is None:
            _run_cli("operations", "stop", str(root), timeout=10)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        handle.close()


def test_web_human_review_survives_backup_restore_and_two_supervised_starts(
    tmp_path: Path,
) -> None:
    """Restored Web retains exact evidence and a human review disposition."""
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux peer credentials required for supervised commands")
    workspace = OperationsWorkspace(tmp_path / "original")
    initialized = initialize_operations_workspace(workspace)
    port = _free_loopback_port()
    write_operations_runtime_config(
        workspace.config_path,
        replace(initialized.config, ui=OperationsUiConfig(port=port)),
    )
    phase = phase_unbalance_analysis()
    SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path).record(phase)
    request = request_web_analysis_review(
        workspace.root,
        {
            "analysis_run_id": phase.run.analysis_run_id,
            "evidence_id": phase.evidence.evidence_id,
        },
    )
    finding_id = request["finding_id"]
    assert isinstance(finding_id, str)
    assert record_web_review_action(
        workspace.root,
        {"finding_id": finding_id, "action": "acknowledge", "note": ""},
    )["status"] == "acknowledged"
    assert not workspace.supervisor_state_path.exists()

    backup_path = tmp_path / "backup"
    backup = _run_cli("maintenance", "backup", str(workspace.root), str(backup_path))
    assert backup.returncode == 0, backup.stderr
    restored_root = tmp_path / "restored"
    restored = _run_cli("maintenance", "restore", str(backup_path), str(restored_root))
    assert restored.returncode == 0, restored.stderr
    restored_workspace = OperationsWorkspace(restored_root)
    assert not restored_workspace.supervisor_state_path.exists()
    assert len(
        JsonOperationalFindingRepository(restored_workspace.finding_state_path).list_findings()
    ) == 1
    assert (
        JsonFindingReviewRepository(restored_workspace.maintenance_review_state_path)
        .status_for(finding_id)
        .value
        == "acknowledged"
    )
    results = SqlitePhaseUnbalanceRepository(
        restored_workspace.phase_unbalance_state_path
    ).find_results({phase.run.analysis_run_id})
    assert len(results) == 1
    assert results[0].evidence.evidence_id == phase.evidence.evidence_id

    def get(path: str) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", port, timeout=12)
        try:
            connection.request("GET", path, headers={"Host": f"127.0.0.1:{port}"})
            response = connection.getresponse()
            payload = json.loads(response.read())
            assert isinstance(payload, dict)
            return response.status, payload
        finally:
            connection.close()

    # A new supervisor generation must not rewrite or lose stored review state.
    for generation in range(2):
        log_path = tmp_path / f"restored-supervisor-{generation}.log"
        handle = log_path.open("ab", buffering=0)
        process = subprocess.Popen(
            _cli_argv("operations", "start", str(restored_root), "--ui", "web-controlled"),
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 50
            while True:
                if process.poll() is not None:
                    pytest.fail("restored Web exited before ready:\n" + _process_log(log_path))
                try:
                    status, session = get("/api/v1/session")
                    if status == 200:
                        break
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    pytest.fail("restored Web not ready:\n" + _process_log(log_path))
                time.sleep(0.2)
            assert session["write_scope"] == "supervisor-owned-source-control"
            status, monitor = get("/api/v1/monitor")
            assert status == 200
            reviews = monitor["review_requests"]
            assert isinstance(reviews, dict)
            items = reviews["items"]
            assert isinstance(items, list)
            matched = [entry for entry in items if entry["finding_id"] == finding_id]
            assert len(matched) == 1
            assert matched[0]["analysis_run_id"] == phase.run.analysis_run_id
            assert matched[0]["evidence_ids"] == [phase.evidence.evidence_id]
            assert matched[0]["status"] == "acknowledged"
            stopped = _run_cli("operations", "stop", str(restored_root))
            assert stopped.returncode == 0, stopped.stderr
            assert process.wait(timeout=20) == 0, _process_log(log_path)
        finally:
            if process.poll() is None:
                _run_cli("operations", "stop", str(restored_root), timeout=10)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            handle.close()
    events = JsonFindingReviewRepository(
        restored_workspace.maintenance_review_state_path
    ).list_events()
    assert len(events) == 1
    assert (
        JsonFindingReviewRepository(workspace.maintenance_review_state_path)
        .status_for(finding_id)
        .value
        == "acknowledged"
    )
