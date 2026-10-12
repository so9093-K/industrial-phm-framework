"""Stateful PHM model analysis over ordered per-asset steps (ADR-0025).

One SQLite store owns bindings, per-binding state, step results, review intervals and a change
sequence. Each step commits its result (or skip reason), the updated state, interval changes and
the cursor in one transaction, so a restart neither duplicates nor loses a step and stateful
outputs (review intervals, RUL trajectories) continue exactly where they stopped.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from industrial_phm.models.package import (
    LoadedModelPackage,
    ModelPackageError,
    ModelTask,
    StepKind,
)

_SCHEMA_VERSION = 2


class PhmAnalysisError(ValueError):
    """Raised when PHM analysis state or a binding violates the contract."""


class StepState(StrEnum):
    ANALYZED = "analyzed"
    SKIPPED = "skipped"


class Applicability(StrEnum):
    INSIDE = "inside"
    OUTSIDE = "outside"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class PhmBinding:
    """Explicit decision to run one package over one (source, asset) stream."""

    binding_id: str
    package_id: str
    source_id: str
    asset_id: str
    step_kind: StepKind
    created_at: datetime
    recorded_replay: bool = False
    measurement_point_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("binding_id", "package_id", "source_id", "asset_id"):
            _identifier(getattr(self, name), name)
        if not isinstance(self.step_kind, StepKind):
            raise PhmAnalysisError("step_kind must be a StepKind")
        if self.measurement_point_id is not None:
            _identifier(self.measurement_point_id, "measurement_point_id")
        _aware(self.created_at, "created_at")


@dataclass(frozen=True, slots=True)
class PreparedStep:
    """One step projected to the package's feature schema, or the reason it cannot be."""

    step_key: str
    position: int
    replay: bool
    input_reference: Mapping[str, Any]
    event_start: datetime | None = None
    event_end: datetime | None = None
    features: Sequence[float] | None = None
    context: Mapping[str, str] = field(default_factory=dict)
    skip_reason: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.step_key, "step_key")
        if isinstance(self.position, bool) or not isinstance(self.position, int):
            raise PhmAnalysisError("position must be an integer")
        for name in ("event_start", "event_end"):
            value = getattr(self, name)
            if value is not None:
                _aware(value, name)
        if (self.features is None) == (self.skip_reason is None):
            raise PhmAnalysisError("a prepared step has either features or a skip reason")
        if self.features is not None:
            values = tuple(float(v) for v in self.features)
            if not values or not all(math.isfinite(v) for v in values):
                raise PhmAnalysisError("step features must be finite")
            object.__setattr__(self, "features", values)
        object.__setattr__(self, "input_reference", MappingProxyType(dict(self.input_reference)))
        object.__setattr__(self, "context", MappingProxyType(dict(self.context)))


@dataclass(frozen=True, slots=True)
class StepResult:
    binding_id: str
    step_key: str
    position: int
    state: StepState
    analysis_run_id: str
    processed_at: datetime
    replay: bool
    input_reference: Mapping[str, Any]
    output: Mapping[str, Any]
    change_seq: int
    event_start: datetime | None = None
    event_end: datetime | None = None
    reason: str | None = None
    features: Mapping[str, float] | None = None


@dataclass(frozen=True, slots=True)
class ReviewInterval:
    binding_id: str
    interval_id: str
    start_position: int
    end_position: int
    start_step_key: str
    end_step_key: str
    step_count: int
    peak_score: float
    peak_step_key: str
    open: bool
    change_seq: int
    start_event_at: datetime | None = None
    end_event_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class BindingProgress:
    binding: PhmBinding
    cursor_position: int | None
    cursor_step_key: str | None
    state: Mapping[str, Any]
    health: str = "pending"
    health_reason: str | None = None
    health_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class IntervalWrite:
    """Create or update one review interval as part of a step transaction."""

    interval_id: str
    start: Mapping[str, Any]
    end: Mapping[str, Any]
    step_count: int
    peak_score: float
    peak_step_key: str
    open: bool


@dataclass(frozen=True, slots=True)
class StepEvaluation:
    """Pure outcome of evaluating one step against the committed binding state."""

    state: StepState
    output: Mapping[str, Any]
    new_state: Mapping[str, Any]
    reason: str | None = None
    interval_writes: Sequence[IntervalWrite] = ()


StepEvaluator = Callable[[Mapping[str, Any], PreparedStep], StepEvaluation]


def analysis_run_id(binding_id: str, step_key: str, package_id: str) -> str:
    digest = hashlib.sha256(f"{binding_id}\n{step_key}\n{package_id}".encode()).hexdigest()
    return f"phm-run-{digest[:24]}"


class SqlitePhmAnalysisStore:
    """WAL-backed authority for PHM bindings, state, results and review intervals."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise PhmAnalysisError("path must be pathlib.Path")
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    # Bindings -----------------------------------------------------------------

    def create_binding(self, binding: PhmBinding) -> bool:
        connection = self._connect()
        try:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT package_id, source_id, asset_id, step_kind, recorded_replay, "
                    "measurement_point_id "
                    "FROM binding WHERE binding_id = ?",
                    (binding.binding_id,),
                ).fetchone()
                if existing is not None:
                    if tuple(existing) != (
                        binding.package_id,
                        binding.source_id,
                        binding.asset_id,
                        binding.step_kind.value,
                        int(binding.recorded_replay),
                        binding.measurement_point_id,
                    ):
                        raise PhmAnalysisError("binding ID already exists with different content")
                    return False
                connection.execute(
                    "INSERT INTO binding(binding_id, package_id, source_id, asset_id, step_kind, "
                    "created_at, recorded_replay, measurement_point_id, state) "
                    "VALUES (?,?,?,?,?,?,?,?,'{}')",
                    (
                        binding.binding_id,
                        binding.package_id,
                        binding.source_id,
                        binding.asset_id,
                        binding.step_kind.value,
                        binding.created_at.isoformat(),
                        int(binding.recorded_replay),
                        binding.measurement_point_id,
                    ),
                )
                _log_change(connection, binding.binding_id, "binding", binding.binding_id)
            return True
        finally:
            connection.close()

    def list_bindings(self) -> tuple[PhmBinding, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT binding_id, package_id, source_id, asset_id, step_kind, created_at, "
                "recorded_replay, measurement_point_id FROM binding ORDER BY binding_id"
            ).fetchall()
        finally:
            connection.close()
        return tuple(_binding(row) for row in rows)

    def progress(self, binding_id: str) -> BindingProgress:
        connection = self._connect()
        try:
            return _progress(connection, binding_id)
        finally:
            connection.close()

    def set_binding_health(
        self, binding_id: str, *, healthy: bool, reason: str | None, at: datetime
    ) -> None:
        """Record whether the runner could load and run the bound package; log only changes."""
        _aware(at, "at")
        health = "ok" if healthy else "unavailable"
        connection = self._connect()
        try:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT health, health_reason FROM binding WHERE binding_id = ?",
                    (binding_id,),
                ).fetchone()
                if row is None:
                    raise PhmAnalysisError(f"unknown binding: {binding_id}")
                if tuple(row) == (health, reason):
                    return
                connection.execute(
                    "UPDATE binding SET health = ?, health_reason = ?, health_at = ? "
                    "WHERE binding_id = ?",
                    (health, reason, at.isoformat(), binding_id),
                )
                _log_change(connection, binding_id, "health", health)
        finally:
            connection.close()

    # Step processing ----------------------------------------------------------

    def commit_step(
        self,
        binding_id: str,
        step: PreparedStep,
        *,
        evaluate: StepEvaluator,
        package_id: str,
        processed_at: datetime,
        feature_names: Sequence[str],
    ) -> StepResult | None:
        """Atomically evaluate and record one step; return None if it was already recorded.

        ``evaluate`` receives the committed state and must be pure. It runs inside the write
        transaction so the state it reads is exactly the state its result is committed against.
        """
        _aware(processed_at, "processed_at")
        if step.features is not None and len(step.features) != len(feature_names):
            raise PhmAnalysisError("step features must align with the package feature names")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                done = connection.execute(
                    "SELECT 1 FROM step_result WHERE binding_id = ? AND step_key = ?",
                    (binding_id, step.step_key),
                ).fetchone()
                if done is not None:
                    connection.execute("ROLLBACK")
                    return None
                progress = _progress(connection, binding_id)
                late = (
                    progress.cursor_position is not None
                    and step.position <= progress.cursor_position
                )
                if late:
                    outcome = StepEvaluation(
                        StepState.SKIPPED,
                        {},
                        progress.state,
                        "late-step: an equal or later position was already analyzed",
                    )
                else:
                    outcome = evaluate(progress.state, step)
                state, output, reason = outcome.state, outcome.output, outcome.reason
                change_seq = _log_change(connection, binding_id, "step", step.step_key)
                run_id = analysis_run_id(binding_id, step.step_key, package_id)
                connection.execute(
                    "INSERT INTO step_result VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        binding_id,
                        step.step_key,
                        step.position,
                        state.value,
                        run_id,
                        processed_at.isoformat(),
                        int(step.replay),
                        _json(step.input_reference),
                        _json(output),
                        change_seq,
                        _iso(step.event_start),
                        _iso(step.event_end),
                        reason,
                        None
                        if step.features is None
                        else _json(dict(zip(feature_names, step.features, strict=True))),
                    ),
                )
                if not late:
                    for write in outcome.interval_writes:
                        _write_interval(connection, binding_id, write, change_seq)
                    connection.execute(
                        "UPDATE binding SET cursor_position = ?, cursor_step_key = ?, state = ? "
                        "WHERE binding_id = ?",
                        (step.position, step.step_key, _json(outcome.new_state), binding_id),
                    )
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        finally:
            connection.close()
        return StepResult(
            binding_id=binding_id,
            step_key=step.step_key,
            position=step.position,
            state=state,
            analysis_run_id=run_id,
            processed_at=processed_at,
            replay=step.replay,
            input_reference=step.input_reference,
            output=MappingProxyType(dict(output)),
            change_seq=change_seq,
            event_start=step.event_start,
            event_end=step.event_end,
            reason=reason,
            features=None
            if step.features is None
            else dict(zip(feature_names, step.features, strict=True)),
        )

    # Reads --------------------------------------------------------------------

    def list_results(
        self, binding_id: str, *, after_change_seq: int = 0, limit: int = 5000
    ) -> tuple[StepResult, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM step_result WHERE binding_id = ? AND change_seq > ? "
                "ORDER BY change_seq LIMIT ?",
                (binding_id, after_change_seq, limit),
            ).fetchall()
        finally:
            connection.close()
        return tuple(_result(row) for row in rows)

    def get_result(self, binding_id: str, position: int) -> StepResult | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM step_result WHERE binding_id = ? AND position = ?",
                (binding_id, position),
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else _result(row)

    def latest_result(
        self, binding_id: str, *, state: StepState | None = None
    ) -> StepResult | None:
        connection = self._connect()
        try:
            clause = "" if state is None else "AND state = ? "
            params = (binding_id,) if state is None else (binding_id, state.value)
            row = connection.execute(
                "SELECT * FROM step_result WHERE binding_id = ? "
                + clause
                + "ORDER BY position DESC, change_seq DESC LIMIT 1",
                params,
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else _result(row)

    def list_intervals(self, binding_id: str) -> tuple[ReviewInterval, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM review_interval WHERE binding_id = ? ORDER BY start_position",
                (binding_id,),
            ).fetchall()
        finally:
            connection.close()
        return tuple(_interval(row) for row in rows)

    def latest_change_seq(self) -> int:
        connection = self._connect()
        try:
            row = connection.execute("SELECT MAX(change_seq) FROM change_log").fetchone()
        finally:
            connection.close()
        return int(row[0] or 0)

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path, timeout=30.0, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS phm_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        current = connection.execute(
            "SELECT value FROM phm_meta WHERE key = 'schema_version'"
        ).fetchone()
        if current is None:
            connection.execute(
                "INSERT OR IGNORE INTO phm_meta VALUES ('schema_version', ?)",
                (str(_SCHEMA_VERSION),),
            )
        elif current[0] == "1":
            # Older M1 stores have neither field; unmerged M3 stores may have replay only.
            # Serialize migration and re-read under the write lock for concurrent readers.
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                columns = {row[1] for row in connection.execute("PRAGMA table_info(binding)")}
                if "recorded_replay" not in columns:
                    connection.execute(
                        "ALTER TABLE binding ADD COLUMN recorded_replay INTEGER NOT NULL DEFAULT 0"
                    )
                if "measurement_point_id" not in columns:
                    connection.execute("ALTER TABLE binding ADD COLUMN measurement_point_id TEXT")
                connection.execute(
                    "UPDATE phm_meta SET value = ? WHERE key = 'schema_version'",
                    (str(_SCHEMA_VERSION),),
                )
        elif current[0] != str(_SCHEMA_VERSION):
            connection.close()
            raise PhmAnalysisError(f"unsupported PHM analysis schema: {current[0]!r}")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS binding(
                binding_id TEXT PRIMARY KEY,
                package_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                asset_id TEXT NOT NULL,
                step_kind TEXT NOT NULL,
                created_at TEXT NOT NULL,
                recorded_replay INTEGER NOT NULL DEFAULT 0,
                measurement_point_id TEXT,
                cursor_position INTEGER,
                cursor_step_key TEXT,
                state TEXT NOT NULL,
                health TEXT NOT NULL DEFAULT 'pending',
                health_reason TEXT,
                health_at TEXT
            );
            CREATE TABLE IF NOT EXISTS step_result(
                binding_id TEXT NOT NULL,
                step_key TEXT NOT NULL,
                position INTEGER NOT NULL,
                state TEXT NOT NULL,
                analysis_run_id TEXT NOT NULL,
                processed_at TEXT NOT NULL,
                replay INTEGER NOT NULL,
                input_reference TEXT NOT NULL,
                output TEXT NOT NULL,
                change_seq INTEGER NOT NULL,
                event_start TEXT,
                event_end TEXT,
                reason TEXT,
                features TEXT,
                PRIMARY KEY(binding_id, step_key)
            );
            CREATE INDEX IF NOT EXISTS step_result_position ON step_result(binding_id, position);
            CREATE TABLE IF NOT EXISTS review_interval(
                binding_id TEXT NOT NULL,
                interval_id TEXT NOT NULL,
                start_position INTEGER NOT NULL,
                end_position INTEGER NOT NULL,
                start_step_key TEXT NOT NULL,
                end_step_key TEXT NOT NULL,
                step_count INTEGER NOT NULL,
                peak_score REAL NOT NULL,
                peak_step_key TEXT NOT NULL,
                open INTEGER NOT NULL,
                change_seq INTEGER NOT NULL,
                start_event_at TEXT,
                end_event_at TEXT,
                PRIMARY KEY(binding_id, interval_id)
            );
            CREATE TABLE IF NOT EXISTS change_log(
                change_seq INTEGER PRIMARY KEY AUTOINCREMENT,
                binding_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                ref TEXT NOT NULL
            );
            """
        )
        return connection


# Task evaluation ------------------------------------------------------------


def evaluate_with_package(package: LoadedModelPackage) -> StepEvaluator:
    """Return the pure in-transaction evaluator for one verified package."""
    manifest = package.manifest
    spec = manifest.output
    rule = spec.review_interval

    def evaluate(state: Mapping[str, Any], step: PreparedStep) -> StepEvaluation:
        if step.skip_reason is not None:
            return StepEvaluation(StepState.SKIPPED, {}, state, step.skip_reason)
        assert step.features is not None
        try:
            (value,) = package.evaluate([step.features])
        except ModelPackageError as error:
            return StepEvaluation(
                StepState.SKIPPED, {}, state, f"package evaluation failed: {error}"
            )
        applicability = _applicability(manifest.applicability, step.context).value
        if spec.task is ModelTask.ANOMALY_SCORE:
            assert spec.threshold is not None and rule is not None
            exceeds = value > spec.threshold
            tracker, writes = advance_review_interval(
                state.get("interval") or {},
                step,
                score=value,
                exceeds=exceeds,
                min_consecutive_steps=rule.min_consecutive_steps,
                max_gap_steps=rule.max_gap_steps,
            )
            output: dict[str, Any] = {
                "task": spec.task.value,
                "score": value,
                "threshold": spec.threshold,
                "exceeds_threshold": exceeds,
                "applicability": applicability,
            }
            contributions = package.feature_contributions([step.features])
            if contributions is not None:
                output["feature_contributions"] = dict(contributions[0])
            return StepEvaluation(
                StepState.ANALYZED, output, {**state, "interval": tracker}, None, writes
            )
        previous = state.get("last_estimate")
        output = {
            "task": spec.task.value,
            "estimate": value,
            "unit": spec.unit,
            "endpoint_semantics": spec.endpoint_semantics,
            "change_from_previous": None if previous is None else value - float(previous),
            "applicability": applicability,
        }
        return StepEvaluation(StepState.ANALYZED, output, {**state, "last_estimate": value})

    return evaluate


def advance_review_interval(
    tracker: Mapping[str, Any],
    step: PreparedStep,
    *,
    score: float,
    exceeds: bool,
    min_consecutive_steps: int,
    max_gap_steps: int,
) -> tuple[dict[str, Any], tuple[IntervalWrite, ...]]:
    """Open an interval after N consecutive crossings; close it after more than G quiet steps.

    The interval end only moves on crossing steps, so trailing quiet steps never widen it.
    """
    point = {
        "position": step.position,
        "key": step.step_key,
        "start_at": _iso(step.event_start),
        "end_at": _iso(step.event_end),
        "score": score,
    }
    current = dict(tracker)
    interrupted: tuple[IntervalWrite, ...] = ()
    last = current.get("end") or (current.get("run") or [None])[-1]
    if last is not None:
        allowed_gap = max_gap_steps if current.get("open_id") else 0
        if step.event_start is not None and step.event_end is not None and last.get("end_at"):
            missing_duration = (
                step.event_start - datetime.fromisoformat(last["end_at"])
            ).total_seconds()
            width = (step.event_end - step.event_start).total_seconds()
            disconnected = missing_duration < 0 or missing_duration > allowed_gap * width
        else:
            distance = step.position - last["position"]
            disconnected = distance <= 0 or distance > allowed_gap + 1
        if disconnected:
            if current.get("open_id"):
                interrupted = (_interval_write(current, open_=False),)
            current = {}
    if exceeds:
        if current.get("open_id"):
            current["end"] = point
            current["count"] = int(current["count"]) + 1
            current["gap"] = 0
            if score > float(current["peak"]):
                current["peak"], current["peak_key"] = score, step.step_key
            return current, (*interrupted, _interval_write(current, open_=True))
        run = [*current.get("run", []), point]
        if len(run) < min_consecutive_steps:
            return {"run": run}, interrupted
        peak = max(run, key=lambda item: float(item["score"]))
        opened = {
            "open_id": f"interval-{run[0]['position']}",
            "start": run[0],
            "end": run[-1],
            "count": len(run),
            "peak": float(peak["score"]),
            "peak_key": peak["key"],
            "gap": 0,
        }
        return opened, (*interrupted, _interval_write(opened, open_=True))
    if current.get("open_id"):
        current["gap"] = int(current.get("gap", 0)) + 1
        if current["gap"] > max_gap_steps:
            return {}, (*interrupted, _interval_write(current, open_=False))
        return current, interrupted
    return {}, interrupted


def _interval_write(tracker: Mapping[str, Any], *, open_: bool) -> IntervalWrite:
    return IntervalWrite(
        interval_id=tracker["open_id"],
        start=tracker["start"],
        end=tracker["end"],
        step_count=int(tracker["count"]),
        peak_score=float(tracker["peak"]),
        peak_step_key=tracker["peak_key"],
        open=open_,
    )


def _applicability(rules: Mapping[str, Sequence[str]], context: Mapping[str, str]) -> Applicability:
    if not rules:
        return Applicability.UNKNOWN
    for key, allowed in rules.items():
        observed = context.get(key)
        if observed is None:
            return Applicability.UNKNOWN
        if observed not in allowed:
            return Applicability.OUTSIDE
    return Applicability.INSIDE


def _write_interval(
    connection: sqlite3.Connection, binding_id: str, write: IntervalWrite, change_seq: int
) -> None:
    connection.execute(
        "INSERT INTO review_interval VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(binding_id, interval_id) DO UPDATE SET end_position=excluded.end_position, "
        "end_step_key=excluded.end_step_key, step_count=excluded.step_count, "
        "peak_score=excluded.peak_score, peak_step_key=excluded.peak_step_key, open=excluded.open, "
        "change_seq=excluded.change_seq, end_event_at=excluded.end_event_at",
        (
            binding_id,
            write.interval_id,
            write.start["position"],
            write.end["position"],
            write.start["key"],
            write.end["key"],
            write.step_count,
            write.peak_score,
            write.peak_step_key,
            int(write.open),
            change_seq,
            write.start["start_at"],
            write.end["end_at"],
        ),
    )


def run_binding(
    store: SqlitePhmAnalysisStore,
    binding: PhmBinding,
    package: LoadedModelPackage,
    steps: Iterable[PreparedStep],
    *,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[StepResult, ...]:
    """Process prepared steps in order for one binding; already-recorded steps are skipped."""
    if binding.package_id != package.package_id:
        raise PhmAnalysisError("binding and loaded package differ")
    evaluate = evaluate_with_package(package)
    results = []
    for step in steps:
        result = store.commit_step(
            binding.binding_id,
            step,
            evaluate=evaluate,
            package_id=package.package_id,
            processed_at=now(),
            feature_names=package.manifest.input.feature_names,
        )
        if result is not None:
            results.append(result)
    return tuple(results)


# Row mapping -----------------------------------------------------------------


def _progress(connection: sqlite3.Connection, binding_id: str) -> BindingProgress:
    row = connection.execute(
        "SELECT binding_id, package_id, source_id, asset_id, step_kind, created_at, "
        "recorded_replay, cursor_position, cursor_step_key, state, health, health_reason, "
        "health_at, measurement_point_id FROM binding WHERE binding_id = ?",
        (binding_id,),
    ).fetchone()
    if row is None:
        raise PhmAnalysisError(f"unknown binding: {binding_id}")
    return BindingProgress(
        binding=_binding((*row[:7], row[13])),
        cursor_position=None if row[7] is None else int(row[7]),
        cursor_step_key=row[8],
        state=json.loads(row[9]),
        health=row[10],
        health_reason=row[11],
        health_at=_dt(row[12]),
    )


def _binding(row: Sequence[Any]) -> PhmBinding:
    return PhmBinding(
        binding_id=row[0],
        package_id=row[1],
        source_id=row[2],
        asset_id=row[3],
        step_kind=StepKind(row[4]),
        created_at=datetime.fromisoformat(row[5]),
        recorded_replay=bool(row[6]),
        measurement_point_id=row[7],
    )


def _result(row: Sequence[Any]) -> StepResult:
    return StepResult(
        binding_id=row[0],
        step_key=row[1],
        position=int(row[2]),
        state=StepState(row[3]),
        analysis_run_id=row[4],
        processed_at=datetime.fromisoformat(row[5]),
        replay=bool(row[6]),
        input_reference=json.loads(row[7]),
        output=json.loads(row[8]),
        change_seq=int(row[9]),
        event_start=_dt(row[10]),
        event_end=_dt(row[11]),
        reason=row[12],
        features=None if row[13] is None else json.loads(row[13]),
    )


def _interval(row: Sequence[Any]) -> ReviewInterval:
    return ReviewInterval(
        binding_id=row[0],
        interval_id=row[1],
        start_position=int(row[2]),
        end_position=int(row[3]),
        start_step_key=row[4],
        end_step_key=row[5],
        step_count=int(row[6]),
        peak_score=float(row[7]),
        peak_step_key=row[8],
        open=bool(row[9]),
        change_seq=int(row[10]),
        start_event_at=_dt(row[11]),
        end_event_at=_dt(row[12]),
    )


def _log_change(connection: sqlite3.Connection, binding_id: str, kind: str, ref: str) -> int:
    cursor = connection.execute(
        "INSERT INTO change_log(binding_id, kind, ref) VALUES (?,?,?)", (binding_id, kind, ref)
    )
    assert cursor.lastrowid is not None
    return int(cursor.lastrowid)


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, allow_nan=False, default=str)


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _dt(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise PhmAnalysisError(f"{name} must be timezone-aware")


def _identifier(value: object, name: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > 512
    ):
        raise PhmAnalysisError(f"{name} must be a trimmed non-empty identifier")
