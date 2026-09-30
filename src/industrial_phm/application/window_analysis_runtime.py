"""Persistent runtime telemetry for the independent live-window analysis runner."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platforms use atomic replace only
    fcntl = None  # type: ignore[assignment]

from industrial_phm.application.live_window_analysis import (
    WindowAnalysisOutcome,
    WindowAnalysisState,
)

_SCHEMA = "industrial-phm-window-analysis-runtime-v1"


class WindowAnalysisRunnerState(StrEnum):
    """Last state explicitly recorded by the independent analysis runner."""

    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WindowAnalysisRunnerTelemetry:
    """Latest runner evidence plus cumulative work counters across restarts."""

    state: WindowAnalysisRunnerState
    started_at: datetime
    heartbeat_at: datetime
    cycle_count: int = 0
    analyzed_count: int = 0
    skipped_count: int = 0
    last_cycle_completed_at: datetime | None = None
    last_analysis_at: datetime | None = None
    last_analysis_run_id: str | None = None
    last_skip_at: datetime | None = None
    last_skip_reason: str | None = None
    last_failure_at: datetime | None = None
    last_failure: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, WindowAnalysisRunnerState):
            raise ValueError("state must be a WindowAnalysisRunnerState")
        _require_aware(self.started_at, "started_at")
        _require_aware(self.heartbeat_at, "heartbeat_at")
        if self.heartbeat_at < self.started_at:
            raise ValueError("heartbeat_at must not be before started_at")
        for field_name in ("cycle_count", "analyzed_count", "skipped_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.analyzed_count + self.skipped_count > self.cycle_count and self.cycle_count == 0:
            raise ValueError("non-zero work counters require at least one completed cycle")
        for field_name in (
            "last_cycle_completed_at",
            "last_analysis_at",
            "last_skip_at",
            "last_failure_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_aware(value, field_name)
                if value > self.heartbeat_at:
                    raise ValueError(f"{field_name} must not be after heartbeat_at")
        if (self.last_analysis_at is None) != (self.last_analysis_run_id is None):
            raise ValueError("last analysis time and run id must be recorded together")
        if (self.last_skip_at is None) != (self.last_skip_reason is None):
            raise ValueError("last skip time and reason must be recorded together")
        if (self.last_failure_at is None) != (self.last_failure is None):
            raise ValueError("last failure time and detail must be recorded together")
        for field_name in ("last_analysis_run_id", "last_skip_reason", "last_failure"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} must not be empty")


class JsonWindowAnalysisRuntimeRepository:
    """Atomic latest-state repository read by Operations without owning runner lifecycle."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise ValueError("path must be a pathlib.Path")
        self._path = path

    def load(self) -> WindowAnalysisRunnerTelemetry | None:
        if not self._path.exists():
            return None
        root = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(root, dict) or root.get("schema") != _SCHEMA:
            raise ValueError(f"unsupported window analysis runtime schema in {self._path}")
        value = root.get("runner")
        if not isinstance(value, dict):
            raise ValueError(f"window analysis runtime runner object is missing in {self._path}")
        try:
            return WindowAnalysisRunnerTelemetry(
                state=WindowAnalysisRunnerState(value["state"]),
                started_at=datetime.fromisoformat(value["started_at"]),
                heartbeat_at=datetime.fromisoformat(value["heartbeat_at"]),
                cycle_count=value["cycle_count"],
                analyzed_count=value["analyzed_count"],
                skipped_count=value["skipped_count"],
                last_cycle_completed_at=_optional_time(value.get("last_cycle_completed_at")),
                last_analysis_at=_optional_time(value.get("last_analysis_at")),
                last_analysis_run_id=value.get("last_analysis_run_id"),
                last_skip_at=_optional_time(value.get("last_skip_at")),
                last_skip_reason=value.get("last_skip_reason"),
                last_failure_at=_optional_time(value.get("last_failure_at")),
                last_failure=value.get("last_failure"),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"invalid window analysis runtime state in {self._path}") from error

    def record_start(self, at: datetime) -> WindowAnalysisRunnerTelemetry:
        _require_aware(at, "at")
        with _exclusive(self._path):
            previous = self.load()
            status = WindowAnalysisRunnerTelemetry(
                state=WindowAnalysisRunnerState.RUNNING,
                started_at=at,
                heartbeat_at=at,
                cycle_count=0 if previous is None else previous.cycle_count,
                analyzed_count=0 if previous is None else previous.analyzed_count,
                skipped_count=0 if previous is None else previous.skipped_count,
                last_cycle_completed_at=(
                    None if previous is None else previous.last_cycle_completed_at
                ),
                last_analysis_at=None if previous is None else previous.last_analysis_at,
                last_analysis_run_id=(
                    None if previous is None else previous.last_analysis_run_id
                ),
                last_skip_at=None if previous is None else previous.last_skip_at,
                last_skip_reason=None if previous is None else previous.last_skip_reason,
                last_failure_at=None if previous is None else previous.last_failure_at,
                last_failure=None if previous is None else previous.last_failure,
            )
            self._write(status)
            return status

    def record_cycle(
        self,
        outcomes: Sequence[WindowAnalysisOutcome],
        *,
        completed_at: datetime,
    ) -> WindowAnalysisRunnerTelemetry:
        _require_aware(completed_at, "completed_at")
        with _exclusive(self._path):
            current = self._require_current()
            return self._record_cycle_locked(
                current,
                tuple(outcomes),
                completed_at=completed_at,
            )

    def _record_cycle_locked(
        self,
        current: WindowAnalysisRunnerTelemetry,
        outcomes: tuple[WindowAnalysisOutcome, ...],
        *,
        completed_at: datetime,
    ) -> WindowAnalysisRunnerTelemetry:
        if completed_at < current.heartbeat_at:
            raise ValueError("completed_at must not move backwards")
        values = outcomes
        if any(not isinstance(item, WindowAnalysisOutcome) for item in values):
            raise ValueError("outcomes must contain only WindowAnalysisOutcome values")

        analyzed = tuple(item for item in values if item.state == WindowAnalysisState.ANALYZED)
        skipped = tuple(item for item in values if item.state == WindowAnalysisState.SKIPPED)
        latest_analysis = (
            None if not analyzed else max(analyzed, key=lambda item: item.recorded_at)
        )
        latest_skip = None if not skipped else max(skipped, key=lambda item: item.recorded_at)

        status = replace(
            current,
            state=WindowAnalysisRunnerState.RUNNING,
            heartbeat_at=completed_at,
            cycle_count=current.cycle_count + 1,
            analyzed_count=current.analyzed_count + len(analyzed),
            skipped_count=current.skipped_count + len(skipped),
            last_cycle_completed_at=completed_at,
            last_analysis_at=(
                current.last_analysis_at
                if latest_analysis is None
                else latest_analysis.recorded_at
            ),
            last_analysis_run_id=(
                current.last_analysis_run_id
                if latest_analysis is None
                else latest_analysis.analysis_run_id
            ),
            last_skip_at=(
                current.last_skip_at if latest_skip is None else latest_skip.recorded_at
            ),
            last_skip_reason=(
                current.last_skip_reason if latest_skip is None else latest_skip.reason
            ),
        )
        self._write(status)
        return status

    def record_failure(
        self,
        detail: str,
        *,
        occurred_at: datetime,
    ) -> WindowAnalysisRunnerTelemetry:
        _require_aware(occurred_at, "occurred_at")
        if not isinstance(detail, str) or not detail.strip():
            raise ValueError("detail must not be empty")
        with _exclusive(self._path):
            current = self._require_current()
            if occurred_at < current.heartbeat_at:
                raise ValueError("occurred_at must not move backwards")
            status = replace(
                current,
                state=WindowAnalysisRunnerState.FAILED,
                heartbeat_at=occurred_at,
                last_failure_at=occurred_at,
                last_failure=detail,
            )
            self._write(status)
            return status

    def record_stop(self, at: datetime) -> WindowAnalysisRunnerTelemetry:
        _require_aware(at, "at")
        with _exclusive(self._path):
            current = self._require_current()
            if at < current.heartbeat_at:
                raise ValueError("at must not move backwards")
            status = replace(
                current,
                state=WindowAnalysisRunnerState.STOPPED,
                heartbeat_at=at,
            )
            self._write(status)
            return status

    def _require_current(self) -> WindowAnalysisRunnerTelemetry:
        current = self.load()
        if current is None:
            raise ValueError("window analysis runner runtime has not been started")
        return current

    def _write(self, status: WindowAnalysisRunnerTelemetry) -> None:
        payload = {
            "schema": _SCHEMA,
            "runner": {
                "state": status.state.value,
                "started_at": status.started_at.isoformat(),
                "heartbeat_at": status.heartbeat_at.isoformat(),
                "cycle_count": status.cycle_count,
                "analyzed_count": status.analyzed_count,
                "skipped_count": status.skipped_count,
                "last_cycle_completed_at": _format_time(status.last_cycle_completed_at),
                "last_analysis_at": _format_time(status.last_analysis_at),
                "last_analysis_run_id": status.last_analysis_run_id,
                "last_skip_at": _format_time(status.last_skip_at),
                "last_skip_reason": status.last_skip_reason,
                "last_failure_at": _format_time(status.last_failure_at),
                "last_failure": status.last_failure,
            },
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self._path.parent,
            prefix=f".{self._path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.replace(handle.name, self._path)
        finally:
            Path(handle.name).unlink(missing_ok=True)


@contextmanager
def _exclusive(path: Path) -> Iterator[None]:
    """Serialize runner runtime read-modify-write between cooperating local processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path) + ".lock", "a+") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _require_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")


def _optional_time(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("stored datetime must be a string")
    return datetime.fromisoformat(value)


def _format_time(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()
