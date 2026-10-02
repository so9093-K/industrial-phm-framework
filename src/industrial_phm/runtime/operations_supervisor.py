"""Foreground supervisor for the local Operations service process set."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback uses runtime-state preflight only
    fcntl = None  # type: ignore[assignment]

from industrial_phm.runtime.operations_runtime import (
    OperationsComponentKind,
    OperationsComponentLaunch,
    OperationsRuntimePlan,
)

_SUPERVISOR_SCHEMA = "industrial-phm-operations-supervisor-v1"


class OperationsSupervisorStateKind(StrEnum):
    """Lifecycle state owned only by the local process supervisor."""

    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class OperationsChildProcessState:
    """Process identity owned by the supervisor, not component health."""

    kind: OperationsComponentKind
    pid: int
    log_path: Path
    return_code: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, OperationsComponentKind):
            raise ValueError("kind must be OperationsComponentKind")
        if isinstance(self.pid, bool) or not isinstance(self.pid, int) or self.pid <= 0:
            raise ValueError("pid must be a positive integer")
        if not isinstance(self.log_path, Path):
            raise ValueError("log_path must be Path")
        if self.return_code is not None and (
            isinstance(self.return_code, bool) or not isinstance(self.return_code, int)
        ):
            raise ValueError("return_code must be an integer or None")


@dataclass(frozen=True, slots=True)
class OperationsSupervisorState:
    """Latest process-lifecycle evidence for one local Operations workspace."""

    state: OperationsSupervisorStateKind
    supervisor_pid: int
    started_at: datetime
    updated_at: datetime
    components: tuple[OperationsChildProcessState, ...]
    failure: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, OperationsSupervisorStateKind):
            raise ValueError("state must be OperationsSupervisorStateKind")
        if (
            isinstance(self.supervisor_pid, bool)
            or not isinstance(self.supervisor_pid, int)
            or self.supervisor_pid <= 0
        ):
            raise ValueError("supervisor_pid must be a positive integer")
        _require_aware(self.started_at, "started_at")
        _require_aware(self.updated_at, "updated_at")
        if self.updated_at < self.started_at:
            raise ValueError("updated_at must not be before started_at")
        kinds = tuple(component.kind for component in self.components)
        if len(kinds) != len(set(kinds)):
            raise ValueError("components must not contain duplicate kinds")
        if self.state == OperationsSupervisorStateKind.FAILED:
            if not isinstance(self.failure, str) or not self.failure.strip():
                raise ValueError("FAILED supervisor state requires failure detail")
        elif self.failure is not None:
            raise ValueError("non-FAILED supervisor state must not carry failure")


class OperationsSupervisorStateRepository:
    """Atomic latest-state repository for supervisor process identity."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise ValueError("path must be Path")
        self._path = path

    def load(self) -> OperationsSupervisorState | None:
        if not self._path.exists():
            return None
        try:
            root = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"invalid Operations supervisor state in {self._path}") from error
        if not isinstance(root, dict) or root.get("schema") != _SUPERVISOR_SCHEMA:
            raise ValueError(f"unsupported Operations supervisor state in {self._path}")
        value = root.get("supervisor")
        if not isinstance(value, dict):
            raise ValueError(f"Operations supervisor object is missing in {self._path}")
        try:
            components_value = value["components"]
            if not isinstance(components_value, list):
                raise TypeError("components must be a list")
            components = tuple(_parse_component(item) for item in components_value)
            return OperationsSupervisorState(
                state=OperationsSupervisorStateKind(value["state"]),
                supervisor_pid=value["supervisor_pid"],
                started_at=datetime.fromisoformat(value["started_at"]),
                updated_at=datetime.fromisoformat(value["updated_at"]),
                components=components,
                failure=value.get("failure"),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"invalid Operations supervisor state in {self._path}") from error

    def write(self, state: OperationsSupervisorState) -> None:
        if not isinstance(state, OperationsSupervisorState):
            raise ValueError("state must be OperationsSupervisorState")
        payload = {
            "schema": _SUPERVISOR_SCHEMA,
            "supervisor": {
                "state": state.state.value,
                "supervisor_pid": state.supervisor_pid,
                "started_at": state.started_at.isoformat(),
                "updated_at": state.updated_at.isoformat(),
                "failure": state.failure,
                "components": [
                    {
                        "kind": component.kind.value,
                        "pid": component.pid,
                        "log_path": str(component.log_path),
                        "return_code": component.return_code,
                    }
                    for component in state.components
                ],
            },
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


class ManagedOperationsProcess(Protocol):
    """Small child-process surface used by the supervisor and unit-test fakes."""

    pid: int

    def poll(self) -> int | None: ...

    def send_signal(self, sig: int) -> None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


ProcessLauncher = Callable[[OperationsComponentLaunch], ManagedOperationsProcess]


@dataclass(frozen=True, slots=True)
class OperationsSupervisorResult:
    """Final supervisor state and a process-style exit code."""

    state: OperationsSupervisorState
    exit_code: int

    def __post_init__(self) -> None:
        if not isinstance(self.state, OperationsSupervisorState):
            raise ValueError("state must be OperationsSupervisorState")
        if isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int):
            raise ValueError("exit_code must be an integer")


def run_operations_supervisor(
    plan: OperationsRuntimePlan,
    *,
    repository: OperationsSupervisorStateRepository | None = None,
    process_launcher: ProcessLauncher | None = None,
    stop_requested: Callable[[], bool] | None = None,
    now: Callable[[], datetime] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    poll_interval_seconds: float = 0.25,
    heartbeat_interval_seconds: float = 5.0,
    graceful_timeout_seconds: float = 10.0,
    terminate_timeout_seconds: float = 5.0,
) -> OperationsSupervisorResult:
    """Run collection and analysis as one foreground local service lifecycle.

    Child telemetry remains the authoritative health/readiness evidence. This function
    owns process identity, coordinated shutdown and unexpected-process-exit handling only.
    """
    if not isinstance(plan, OperationsRuntimePlan):
        raise ValueError("plan must be OperationsRuntimePlan")
    _require_positive_seconds(poll_interval_seconds, "poll_interval_seconds")
    _require_positive_seconds(heartbeat_interval_seconds, "heartbeat_interval_seconds")
    _require_positive_seconds(graceful_timeout_seconds, "graceful_timeout_seconds")
    _require_positive_seconds(terminate_timeout_seconds, "terminate_timeout_seconds")

    effective_repository = (
        OperationsSupervisorStateRepository(plan.workspace.supervisor_state_path)
        if repository is None
        else repository
    )
    effective_launcher: ProcessLauncher = (
        _spawn_component if process_launcher is None else process_launcher
    )
    effective_stop_requested: Callable[[], bool] = (
        (lambda: False) if stop_requested is None else stop_requested
    )
    effective_now: Callable[[], datetime] = (
        (lambda: datetime.now(UTC)) if now is None else now
    )

    with _supervisor_lock(plan):
        started_at = effective_now()
        _require_aware(started_at, "started_at")
        children: list[tuple[OperationsComponentLaunch, ManagedOperationsProcess]] = []
        try:
            for launch in plan.components:
                children.append((launch, effective_launcher(launch)))
        except OSError as error:
            _stop_children(
                children,
                graceful_timeout_seconds=graceful_timeout_seconds,
                terminate_timeout_seconds=terminate_timeout_seconds,
            )
            state = _build_final_state(
                plan,
                children,
                state=OperationsSupervisorStateKind.FAILED,
                supervisor_pid=os.getpid(),
                started_at=started_at,
                updated_at=effective_now(),
                failure=f"failed to start local component: {error}",
            )
            effective_repository.write(state)
            return OperationsSupervisorResult(state, 1)

        running_state = OperationsSupervisorState(
            state=OperationsSupervisorStateKind.RUNNING,
            supervisor_pid=os.getpid(),
            started_at=started_at,
            updated_at=started_at,
            components=tuple(
                OperationsChildProcessState(launch.kind, child.pid, launch.log_path)
                for launch, child in children
            ),
        )
        last_heartbeat_at = started_at
        try:
            effective_repository.write(running_state)
            while True:
                exited = tuple(
                    (launch, child, return_code)
                    for launch, child in children
                    if (return_code := child.poll()) is not None
                )
                if exited:
                    detail = ", ".join(
                        f"{launch.kind.value} exited with code {return_code}"
                        for launch, _, return_code in exited
                    )
                    _stop_children(
                        children,
                        graceful_timeout_seconds=graceful_timeout_seconds,
                        terminate_timeout_seconds=terminate_timeout_seconds,
                    )
                    state = _build_final_state(
                        plan,
                        children,
                        state=OperationsSupervisorStateKind.FAILED,
                        supervisor_pid=running_state.supervisor_pid,
                        started_at=started_at,
                        updated_at=effective_now(),
                        failure=detail,
                    )
                    effective_repository.write(state)
                    return OperationsSupervisorResult(state, 1)

                if effective_stop_requested():
                    _stop_children(
                        children,
                        graceful_timeout_seconds=graceful_timeout_seconds,
                        terminate_timeout_seconds=terminate_timeout_seconds,
                    )
                    state = _build_final_state(
                        plan,
                        children,
                        state=OperationsSupervisorStateKind.STOPPED,
                        supervisor_pid=running_state.supervisor_pid,
                        started_at=started_at,
                        updated_at=effective_now(),
                    )
                    effective_repository.write(state)
                    return OperationsSupervisorResult(state, 0)

                updated_at = effective_now()
                _require_aware(updated_at, "updated_at")
                if (updated_at - last_heartbeat_at).total_seconds() >= heartbeat_interval_seconds:
                    running_state = replace(running_state, updated_at=updated_at)
                    effective_repository.write(running_state)
                    last_heartbeat_at = updated_at
                sleep(poll_interval_seconds)
        except KeyboardInterrupt:
            _stop_children(
                children,
                graceful_timeout_seconds=graceful_timeout_seconds,
                terminate_timeout_seconds=terminate_timeout_seconds,
            )
            state = _build_final_state(
                plan,
                children,
                state=OperationsSupervisorStateKind.STOPPED,
                supervisor_pid=running_state.supervisor_pid,
                started_at=started_at,
                updated_at=effective_now(),
            )
            effective_repository.write(state)
            return OperationsSupervisorResult(state, 130)
        except Exception:
            _stop_children(
                children,
                graceful_timeout_seconds=graceful_timeout_seconds,
                terminate_timeout_seconds=terminate_timeout_seconds,
            )
            raise


def _build_final_state(
    plan: OperationsRuntimePlan,
    children: list[tuple[OperationsComponentLaunch, ManagedOperationsProcess]],
    *,
    state: OperationsSupervisorStateKind,
    supervisor_pid: int,
    started_at: datetime,
    updated_at: datetime,
    failure: str | None = None,
) -> OperationsSupervisorState:
    by_kind = {launch.kind: child for launch, child in children}
    component_states = []
    for launch in plan.components:
        child = by_kind.get(launch.kind)
        if child is None:
            continue
        component_states.append(
            OperationsChildProcessState(
                launch.kind,
                child.pid,
                launch.log_path,
                return_code=child.poll(),
            )
        )
    return OperationsSupervisorState(
        state=state,
        supervisor_pid=supervisor_pid,
        started_at=started_at,
        updated_at=updated_at,
        components=tuple(component_states),
        failure=failure,
    )


def _spawn_component(launch: OperationsComponentLaunch) -> ManagedOperationsProcess:
    launch.log_path.parent.mkdir(parents=True, exist_ok=True)
    with launch.log_path.open("ab", buffering=0) as log:
        process = subprocess.Popen(
            launch.argv,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    return cast(ManagedOperationsProcess, process)


def _stop_children(
    children: list[tuple[OperationsComponentLaunch, ManagedOperationsProcess]],
    *,
    graceful_timeout_seconds: float,
    terminate_timeout_seconds: float,
) -> None:
    for _, child in reversed(children):
        if child.poll() is None:
            _request_graceful_stop(child)
    for _, child in reversed(children):
        if child.poll() is not None:
            continue
        if _wait(child, graceful_timeout_seconds) is not None:
            continue
        child.terminate()
        if _wait(child, terminate_timeout_seconds) is not None:
            continue
        child.kill()
        child.wait()


def _request_graceful_stop(child: ManagedOperationsProcess) -> None:
    if os.name == "posix":
        child.send_signal(signal.SIGINT)
    else:  # pragma: no cover - Windows process-group semantics need deployment validation
        child.terminate()


def _wait(child: ManagedOperationsProcess, timeout: float) -> int | None:
    try:
        return child.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return None


@contextmanager
def _supervisor_lock(plan: OperationsRuntimePlan) -> Iterator[None]:
    """Prevent two cooperating POSIX supervisors from owning one workspace."""
    path = plan.workspace.supervisor_lock_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if fcntl is None:  # pragma: no cover - current reference runtime is POSIX
        raise RuntimeError("local Operations supervisor requires POSIX advisory file locking")
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                f"another Operations supervisor already owns workspace {plan.workspace.root}"
            ) from error
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _parse_component(value: object) -> OperationsChildProcessState:
    if not isinstance(value, dict):
        raise TypeError("component must be an object")
    return OperationsChildProcessState(
        kind=OperationsComponentKind(value["kind"]),
        pid=value["pid"],
        log_path=Path(value["log_path"]),
        return_code=value.get("return_code"),
    )


def _require_aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")


def _require_positive_seconds(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{name} must be positive")
