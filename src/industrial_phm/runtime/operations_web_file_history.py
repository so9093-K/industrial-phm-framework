"""Supervisor-owned background FILE history jobs for the Operations Web.

One history write of a realistic CSV takes longer than a bounded Web command can wait, so
the supervisor runs it on its own thread and records only its status. The status file is
ephemeral runtime state, not evidence: committed history stays the DuckLake batch itself,
and a retry of the same FILE batch reuses that commit instead of writing it twice.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from industrial_phm.runtime.operations_web_setup import (
    MAX_WEB_BACKGROUND_HISTORY_BYTES,
    SourceControlConflict,
    check_file_history_backfill,
    run_file_history_backfill,
)
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

_SCHEMA = "web-file-history-jobs-v1"
_TERMINAL = frozenset({"succeeded", "failed", "interrupted"})


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def read_file_history_jobs(workspace: OperationsWorkspace) -> dict[str, dict[str, object]]:
    """Return the last job per FILE source; an absent or unreadable file means no status."""
    try:
        data = json.loads(workspace.file_history_job_path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    jobs = data.get("jobs") if isinstance(data, dict) and data.get("schema") == _SCHEMA else None
    if not isinstance(jobs, dict):
        return {}
    return {
        str(source_id): dict(job)
        for source_id, job in jobs.items()
        if isinstance(job, dict) and job.get("state") in _TERMINAL | {"running"}
    }


def _failure(error: Exception) -> str:
    if isinstance(error, SourceControlConflict):
        return "source_control_conflict"
    if isinstance(error, ValueError | TypeError | UnicodeError):
        return "invalid_source_action"
    return "source_state_unavailable"


class FileHistoryJobs:
    """At most one history write at a time; DuckLake has a single local writer."""

    def __init__(
        self,
        workspace: Path,
        *,
        run: Callable[..., dict[str, object]] = run_file_history_backfill,
    ) -> None:
        self._workspace = OperationsWorkspace(workspace)
        self._root = workspace
        self._run = run
        self._lock = threading.Lock()
        self._closed = False
        self._thread: threading.Thread | None = None
        # A new supervisor generation cannot be continuing an earlier thread.
        self._jobs = {
            source_id: (
                {**job, "state": "interrupted", "finished_at": _now()}
                if job.get("state") == "running"
                else job
            )
            for source_id, job in read_file_history_jobs(self._workspace).items()
        }
        if self._jobs:
            self._write()

    def start(self, payload: dict[str, object]) -> dict[str, object]:
        """Check synchronously, then write history on a supervisor thread."""
        with self._lock:
            if self._closed:
                raise SourceControlConflict("FILE history owner is shutting down")
            paths, registry, source_id = check_file_history_backfill(
                self._root, payload, max_bytes=MAX_WEB_BACKGROUND_HISTORY_BYTES
            )
            running = next(
                (key for key, job in self._jobs.items() if job.get("state") == "running"), None
            )
            if running == source_id:
                return self._view(source_id)
            if running is not None:
                raise SourceControlConflict("another FILE history job is running")
            self._jobs[source_id] = {"state": "running", "started_at": _now()}
            self._write()
            self._thread = threading.Thread(
                target=self._execute,
                args=(paths, registry, source_id),
                name=f"web-file-history-{source_id}",
            )
            self._thread.start()
            return self._view(source_id)

    def _execute(self, paths: object, registry: object, source_id: str) -> None:
        try:
            result = self._run(paths, registry, source_id)
            update: dict[str, object] = {
                "state": "succeeded",
                "event_count": result["event_count"],
                "history_snapshot_id": result["history_snapshot_id"],
                "recovered_segment_count": result["recovered_segment_count"],
            }
        except Exception as error:  # A job records a bounded failure code only.
            update = {"state": "failed", "failure": _failure(error)}
        with self._lock:
            self._jobs[source_id] = {
                **self._jobs[source_id],
                **update,
                "finished_at": _now(),
            }
            self._write()

    def _view(self, source_id: str) -> dict[str, object]:
        return {
            "schema_version": 1,
            "source_id": source_id,
            **self._jobs[source_id],
            "meaning": "background-file-history-job-status-not-history-evidence",
        }

    def _write(self) -> None:
        target = self._workspace.file_history_job_path
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(
            json.dumps({"schema": _SCHEMA, "jobs": self._jobs}, sort_keys=True), encoding="utf-8"
        )
        os.replace(temporary, target)

    def close(self) -> None:
        """Let an in-flight history write finish before the supervisor lease is released."""
        with self._lock:
            self._closed = True
            thread = self._thread
        if thread is not None:
            thread.join()


def file_history_job_fields(job: Mapping[str, object] | None) -> dict[str, object] | None:
    """Browser-safe status projection; bounded fields only, never raw exceptions or paths."""
    if job is None:
        return None
    return {
        key: job.get(key)
        for key in (
            "state",
            "started_at",
            "finished_at",
            "event_count",
            "history_snapshot_id",
            "recovered_segment_count",
            "failure",
        )
    }
