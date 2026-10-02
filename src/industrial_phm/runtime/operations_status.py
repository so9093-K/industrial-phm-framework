"""Local Operations runtime status from process identity and component telemetry."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from industrial_phm.application.acquisition_telemetry import (
    CollectionServiceRuntimeState,
    CollectionServiceRuntimeTelemetry,
)
from industrial_phm.application.window_analysis_runtime import (
    JsonWindowAnalysisRuntimeRepository,
    WindowAnalysisRunnerState,
    WindowAnalysisRunnerTelemetry,
)
from industrial_phm.runtime.acquisition_telemetry import SqliteAcquisitionTelemetryRepository
from industrial_phm.runtime.operations_config import load_operations_runtime_config
from industrial_phm.runtime.operations_runtime import OperationsComponentKind
from industrial_phm.runtime.operations_supervisor import (
    OperationsChildProcessState,
    OperationsSupervisorState,
    OperationsSupervisorStateKind,
    OperationsSupervisorStateRepository,
)
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

DEFAULT_RUNTIME_HEARTBEAT_TIMEOUT = timedelta(seconds=20)


class OperationsRuntimeCondition(StrEnum):
    """Small local-runtime vocabulary without inventing asset/source health."""

    RUNNING = "running"
    STALE = "stale"
    STOPPED = "stopped"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class OperationsProcessEvidence:
    """Last supervisor-owned process identity plus current local PID existence."""

    pid: int
    alive: bool
    return_code: int | None

    def __post_init__(self) -> None:
        if isinstance(self.pid, bool) or not isinstance(self.pid, int) or self.pid <= 0:
            raise ValueError("pid must be a positive integer")
        if not isinstance(self.alive, bool):
            raise ValueError("alive must be bool")
        if self.return_code is not None and (
            isinstance(self.return_code, bool) or not isinstance(self.return_code, int)
        ):
            raise ValueError("return_code must be an integer or None")


@dataclass(frozen=True, slots=True)
class OperationsSupervisorStatus:
    """Supervisor liveness, separate from child component health/readiness."""

    condition: OperationsRuntimeCondition
    process: OperationsProcessEvidence | None
    heartbeat_at: datetime | None
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.condition, OperationsRuntimeCondition):
            raise ValueError("condition must be OperationsRuntimeCondition")
        if self.process is not None and not isinstance(self.process, OperationsProcessEvidence):
            raise ValueError("process must be OperationsProcessEvidence or None")
        if self.heartbeat_at is not None:
            _require_aware(self.heartbeat_at, "heartbeat_at")
        _require_text(self.detail, "detail")

    @property
    def running(self) -> bool:
        return self.condition == OperationsRuntimeCondition.RUNNING


@dataclass(frozen=True, slots=True)
class OperationsComponentStatus:
    """One managed service's process identity and authoritative runtime evidence."""

    kind: OperationsComponentKind
    condition: OperationsRuntimeCondition
    process: OperationsProcessEvidence | None
    runtime_state: str | None
    heartbeat_at: datetime | None
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, OperationsComponentKind):
            raise ValueError("kind must be OperationsComponentKind")
        if not isinstance(self.condition, OperationsRuntimeCondition):
            raise ValueError("condition must be OperationsRuntimeCondition")
        if self.process is not None and not isinstance(self.process, OperationsProcessEvidence):
            raise ValueError("process must be OperationsProcessEvidence or None")
        if self.runtime_state is not None:
            _require_text(self.runtime_state, "runtime_state")
        if self.heartbeat_at is not None:
            _require_aware(self.heartbeat_at, "heartbeat_at")
        _require_text(self.detail, "detail")

    @property
    def ready(self) -> bool:
        return self.condition == OperationsRuntimeCondition.RUNNING


@dataclass(frozen=True, slots=True)
class OperationsRuntimeStatus:
    """Local node process/readiness snapshot for CLI and later Operations projection."""

    workspace: OperationsWorkspace
    assessed_at: datetime
    supervisor: OperationsSupervisorStatus
    components: tuple[OperationsComponentStatus, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.workspace, OperationsWorkspace):
            raise ValueError("workspace must be OperationsWorkspace")
        _require_aware(self.assessed_at, "assessed_at")
        if not isinstance(self.supervisor, OperationsSupervisorStatus):
            raise ValueError("supervisor must be OperationsSupervisorStatus")
        expected = tuple(OperationsComponentKind)
        actual = tuple(component.kind for component in self.components)
        if actual != expected:
            raise ValueError("components must follow the canonical Operations component order")

    @property
    def ready(self) -> bool:
        return self.supervisor.running and all(component.ready for component in self.components)


def inspect_operations_runtime_status(
    workspace: OperationsWorkspace,
    *,
    as_of: datetime | None = None,
    process_checker: Callable[[int], bool] | None = None,
    heartbeat_timeout: timedelta = DEFAULT_RUNTIME_HEARTBEAT_TIMEOUT,
) -> OperationsRuntimeStatus:
    """Read one initialized workspace without turning PID existence into health."""
    if not isinstance(workspace, OperationsWorkspace):
        raise ValueError("workspace must be OperationsWorkspace")
    if not isinstance(heartbeat_timeout, timedelta) or heartbeat_timeout <= timedelta():
        raise ValueError("heartbeat_timeout must be positive")

    load_operations_runtime_config(workspace.config_path)
    effective_as_of = datetime.now(UTC) if as_of is None else as_of
    _require_aware(effective_as_of, "as_of")
    effective_checker = _pid_is_alive if process_checker is None else process_checker

    supervisor = OperationsSupervisorStateRepository(workspace.supervisor_state_path).load()
    collection_runtime = _load_collection_runtime(workspace)
    analysis_runtime = _load_analysis_runtime(workspace)

    return build_operations_runtime_status(
        workspace,
        supervisor=supervisor,
        collection_runtime=collection_runtime,
        analysis_runtime=analysis_runtime,
        as_of=effective_as_of,
        process_checker=effective_checker,
        heartbeat_timeout=heartbeat_timeout,
    )


def build_operations_runtime_status(
    workspace: OperationsWorkspace,
    *,
    supervisor: OperationsSupervisorState | None,
    collection_runtime: CollectionServiceRuntimeTelemetry | None,
    analysis_runtime: WindowAnalysisRunnerTelemetry | None,
    as_of: datetime,
    process_checker: Callable[[int], bool],
    heartbeat_timeout: timedelta = DEFAULT_RUNTIME_HEARTBEAT_TIMEOUT,
) -> OperationsRuntimeStatus:
    """Combine process identity and component-owned heartbeat evidence."""
    if not isinstance(workspace, OperationsWorkspace):
        raise ValueError("workspace must be OperationsWorkspace")
    _require_aware(as_of, "as_of")
    if not isinstance(heartbeat_timeout, timedelta) or heartbeat_timeout <= timedelta():
        raise ValueError("heartbeat_timeout must be positive")

    supervisor_status = _supervisor_status(
        supervisor,
        as_of=as_of,
        process_checker=process_checker,
        timeout=heartbeat_timeout,
    )
    child_by_kind = (
        {}
        if supervisor is None
        else {component.kind: component for component in supervisor.components}
    )
    components = (
        _collection_status(
            child_by_kind.get(OperationsComponentKind.COLLECTION),
            collection_runtime,
            as_of=as_of,
            process_checker=process_checker,
            timeout=heartbeat_timeout,
        ),
        _analysis_status(
            child_by_kind.get(OperationsComponentKind.ANALYSIS),
            analysis_runtime,
            as_of=as_of,
            process_checker=process_checker,
            timeout=heartbeat_timeout,
        ),
    )
    return OperationsRuntimeStatus(
        workspace=workspace,
        assessed_at=as_of,
        supervisor=supervisor_status,
        components=components,
    )


def _supervisor_status(
    state: OperationsSupervisorState | None,
    *,
    as_of: datetime,
    process_checker: Callable[[int], bool],
    timeout: timedelta,
) -> OperationsSupervisorStatus:
    if state is None:
        return OperationsSupervisorStatus(
            OperationsRuntimeCondition.UNAVAILABLE,
            None,
            None,
            "supervisor state unavailable",
        )

    process = OperationsProcessEvidence(
        pid=state.supervisor_pid,
        alive=process_checker(state.supervisor_pid)
        if state.state == OperationsSupervisorStateKind.RUNNING
        else False,
        return_code=None,
    )
    if state.state == OperationsSupervisorStateKind.FAILED:
        return OperationsSupervisorStatus(
            OperationsRuntimeCondition.FAILED,
            process,
            state.updated_at,
            state.failure or "supervisor failed",
        )
    if state.state == OperationsSupervisorStateKind.STOPPED:
        return OperationsSupervisorStatus(
            OperationsRuntimeCondition.STOPPED,
            process,
            state.updated_at,
            "supervisor stopped",
        )
    if not process.alive:
        return OperationsSupervisorStatus(
            OperationsRuntimeCondition.FAILED,
            process,
            state.updated_at,
            "supervisor process is not running",
        )
    if _stale(state.updated_at, as_of=as_of, timeout=timeout):
        return OperationsSupervisorStatus(
            OperationsRuntimeCondition.STALE,
            process,
            state.updated_at,
            "supervisor heartbeat is stale",
        )
    return OperationsSupervisorStatus(
        OperationsRuntimeCondition.RUNNING,
        process,
        state.updated_at,
        "supervisor process is running",
    )


def _collection_status(
    child: OperationsChildProcessState | None,
    runtime: CollectionServiceRuntimeTelemetry | None,
    *,
    as_of: datetime,
    process_checker: Callable[[int], bool],
    timeout: timedelta,
) -> OperationsComponentStatus:
    process = _child_process_evidence(child, process_checker)
    if runtime is None:
        return OperationsComponentStatus(
            OperationsComponentKind.COLLECTION,
            OperationsRuntimeCondition.UNAVAILABLE,
            process,
            None,
            None,
            "collection runtime telemetry unavailable",
        )
    if runtime.state == CollectionServiceRuntimeState.FAILED:
        return OperationsComponentStatus(
            OperationsComponentKind.COLLECTION,
            OperationsRuntimeCondition.FAILED,
            process,
            runtime.state.value,
            runtime.heartbeat_at,
            runtime.last_failure or "collection service failed",
        )
    if runtime.state == CollectionServiceRuntimeState.STOPPED:
        return OperationsComponentStatus(
            OperationsComponentKind.COLLECTION,
            OperationsRuntimeCondition.STOPPED,
            process,
            runtime.state.value,
            runtime.heartbeat_at,
            "collection service stopped",
        )
    return _running_component_status(
        OperationsComponentKind.COLLECTION,
        process,
        runtime.state.value,
        runtime.heartbeat_at,
        as_of=as_of,
        timeout=timeout,
    )


def _analysis_status(
    child: OperationsChildProcessState | None,
    runtime: WindowAnalysisRunnerTelemetry | None,
    *,
    as_of: datetime,
    process_checker: Callable[[int], bool],
    timeout: timedelta,
) -> OperationsComponentStatus:
    process = _child_process_evidence(child, process_checker)
    if runtime is None:
        return OperationsComponentStatus(
            OperationsComponentKind.ANALYSIS,
            OperationsRuntimeCondition.UNAVAILABLE,
            process,
            None,
            None,
            "analysis runtime telemetry unavailable",
        )
    if runtime.state == WindowAnalysisRunnerState.FAILED:
        return OperationsComponentStatus(
            OperationsComponentKind.ANALYSIS,
            OperationsRuntimeCondition.FAILED,
            process,
            runtime.state.value,
            runtime.heartbeat_at,
            runtime.last_failure or "analysis runner failed",
        )
    if runtime.state == WindowAnalysisRunnerState.STOPPED:
        return OperationsComponentStatus(
            OperationsComponentKind.ANALYSIS,
            OperationsRuntimeCondition.STOPPED,
            process,
            runtime.state.value,
            runtime.heartbeat_at,
            "analysis runner stopped",
        )
    return _running_component_status(
        OperationsComponentKind.ANALYSIS,
        process,
        runtime.state.value,
        runtime.heartbeat_at,
        as_of=as_of,
        timeout=timeout,
    )


def _running_component_status(
    kind: OperationsComponentKind,
    process: OperationsProcessEvidence | None,
    runtime_state: str,
    heartbeat_at: datetime,
    *,
    as_of: datetime,
    timeout: timedelta,
) -> OperationsComponentStatus:
    if process is None:
        return OperationsComponentStatus(
            kind,
            OperationsRuntimeCondition.UNAVAILABLE,
            None,
            runtime_state,
            heartbeat_at,
            f"{kind.value} runtime is reporting but supervisor process identity is unavailable",
        )
    if process.return_code is not None or not process.alive:
        return OperationsComponentStatus(
            kind,
            OperationsRuntimeCondition.FAILED,
            process,
            runtime_state,
            heartbeat_at,
            f"{kind.value} process is not running",
        )
    if _stale(heartbeat_at, as_of=as_of, timeout=timeout):
        return OperationsComponentStatus(
            kind,
            OperationsRuntimeCondition.STALE,
            process,
            runtime_state,
            heartbeat_at,
            f"{kind.value} runtime heartbeat is stale",
        )
    return OperationsComponentStatus(
        kind,
        OperationsRuntimeCondition.RUNNING,
        process,
        runtime_state,
        heartbeat_at,
        f"{kind.value} runtime is ready",
    )


def _child_process_evidence(
    child: OperationsChildProcessState | None,
    process_checker: Callable[[int], bool],
) -> OperationsProcessEvidence | None:
    if child is None:
        return None
    if child.return_code is not None:
        return OperationsProcessEvidence(child.pid, False, child.return_code)
    return OperationsProcessEvidence(child.pid, process_checker(child.pid), None)


def _load_collection_runtime(
    workspace: OperationsWorkspace,
) -> CollectionServiceRuntimeTelemetry | None:
    if not workspace.acquisition_telemetry_path.is_file():
        return None
    return SqliteAcquisitionTelemetryRepository(
        workspace.acquisition_telemetry_path
    ).get_collection_service_runtime()


def _load_analysis_runtime(
    workspace: OperationsWorkspace,
) -> WindowAnalysisRunnerTelemetry | None:
    if not workspace.analysis_runtime_path.is_file():
        return None
    return JsonWindowAnalysisRuntimeRepository(workspace.analysis_runtime_path).load()


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _stale(heartbeat_at: datetime, *, as_of: datetime, timeout: timedelta) -> bool:
    return as_of - heartbeat_at > timeout


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
