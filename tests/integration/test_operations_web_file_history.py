"""Supervisor background FILE history jobs: real history, status, concurrency and restart."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime import operations_web_file_history as jobs_module
from industrial_phm.runtime.operations_web_file_history import (
    FileHistoryJobs,
    read_file_history_jobs,
)
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from industrial_phm.runtime.operations_web_setup import (
    SourceControlConflict,
    change_web_source_control,
    receive_workspace_file_source,
    register_workspace_csv_source,
)


def _file_source(workspace: OperationsWorkspace, source_id: str) -> None:
    inputs = workspace.root / "inputs"
    inputs.mkdir(exist_ok=True)
    observed = datetime.now(UTC) - timedelta(minutes=2)
    (inputs / f"{source_id}.csv").write_text(
        "timestamp,phase-R,phase-S\n"
        f"{observed.isoformat()},220.5,219.0\n"
        f"{(observed + timedelta(seconds=1)).isoformat()},220.7,219.2\n"
        f"{(observed + timedelta(seconds=2)).isoformat()},220.9,219.4\n",
        encoding="utf-8",
    )
    register_workspace_csv_source(
        workspace.root,
        {
            "source_id": source_id,
            "name": source_id,
            "asset_id": "pump-01",
            "measurement_point_id": "",
            "file_path": f"inputs/{source_id}.csv",
            "channel_columns": ["phase-R", "phase-S"],
            "timestamp_column": "timestamp",
        },
    )
    change_web_source_control(
        workspace.root, "lifecycle", {"source_id": source_id, "target_state": "active"}
    )


def _sources(port: int) -> dict[str, dict[str, object]]:
    connection = HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        connection.request("GET", "/api/v1/sources", headers={"Host": f"127.0.0.1:{port}"})
        payload = json.loads(connection.getresponse().read())
    finally:
        connection.close()
    return {item["source_id"]: item for item in payload["sources"]["items"]}


def test_background_job_writes_real_history_and_reports_it_through_sources(
    tmp_path: Path,
) -> None:
    pytest.importorskip("duckdb")
    pytest.importorskip("filelock")
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    root = workspace.root.resolve()
    _file_source(workspace, "file-a")
    jobs = FileHistoryJobs(root)
    identity = {"source_id": "file-a"}
    # No receipt yet: refused before any job status or history exists.
    with pytest.raises(SourceControlConflict, match="receipt"):
        jobs.start(identity)
    assert read_file_history_jobs(workspace) == {}
    assert receive_workspace_file_source(root, identity)["accepted_new_receipt"] is True

    started = jobs.start(identity)
    assert started["state"] == "running"
    assert started["meaning"] == "background-file-history-job-status-not-history-evidence"
    jobs.close()
    first = read_file_history_jobs(workspace)["file-a"]
    assert first["state"] == "succeeded"
    assert first["event_count"] == 6
    assert isinstance(first["history_snapshot_id"], int)
    # A retry of the same batch reuses its commit rather than writing it twice.
    jobs.start(identity)
    jobs.close()
    again = read_file_history_jobs(workspace)["file-a"]
    assert again["recovered_segment_count"] == 1
    assert again["history_snapshot_id"] == first["history_snapshot_id"]

    server = create_operations_web_read_server(root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status = _sources(server.server_port)["file-a"]["file_history_job"]
        assert status == {
            "state": "succeeded",
            "started_at": again["started_at"],
            "finished_at": again["finished_at"],
            "event_count": 6,
            "history_snapshot_id": first["history_snapshot_id"],
            "recovered_segment_count": 1,
            "failure": None,
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def test_one_writer_at_a_time_restart_marks_interrupted_and_failures_stay_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    monkeypatch.setattr(
        jobs_module,
        "check_file_history_backfill",
        lambda root, payload, *, max_bytes: (None, None, payload["source_id"]),
    )
    release = threading.Event()

    def blocked(paths: object, registry: object, source_id: str) -> dict[str, object]:
        release.wait(timeout=30)
        if source_id == "broken":
            raise OSError("/private/path must not leak")
        return {"event_count": 4, "history_snapshot_id": 7, "recovered_segment_count": 0}

    jobs = FileHistoryJobs(workspace.root, run=blocked)
    assert jobs.start({"source_id": "a"})["state"] == "running"
    # The same source reports the running job instead of starting a second writer.
    assert jobs.start({"source_id": "a"})["state"] == "running"
    with pytest.raises(SourceControlConflict, match="another"):
        jobs.start({"source_id": "b"})
    # A new supervisor generation cannot be continuing the earlier thread.
    restarted = FileHistoryJobs(workspace.root, run=blocked)
    assert read_file_history_jobs(workspace)["a"]["state"] == "interrupted"
    release.set()
    jobs.close()
    assert jobs.start({"source_id": "broken"})["state"] == "running"
    jobs.close()
    broken = read_file_history_jobs(workspace)["broken"]
    assert broken["state"] == "failed"
    assert broken["failure"] == "source_state_unavailable"
    assert "private" not in workspace.file_history_job_path.read_text(encoding="utf-8")
    restarted.close()
