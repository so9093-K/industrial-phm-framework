import signal
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from industrial_phm.runtime import (
    OperationsRuntimeConfig,
    OperationsWorkspace,
    build_operations_runtime_plan,
)
from industrial_phm.runtime.operations_runtime import (
    OPERATIONS_WORKSPACE_ENV,
    OperationsComponentKind,
    OperationsComponentLaunch,
)
from industrial_phm.runtime.operations_supervisor import (
    OperationsChildProcessState,
    OperationsSupervisorState,
    OperationsSupervisorStateKind,
    OperationsSupervisorStateRepository,
    request_operations_supervisor_stop,
    run_operations_supervisor,
)


class _FakeProcess:
    def __init__(self, pid: int, *, return_code: int | None = None) -> None:
        self.pid = pid
        self.return_code = return_code
        self.signals: list[int] = []
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.return_code

    def send_signal(self, sig: int) -> None:
        self.signals.append(sig)
        self.return_code = 0

    def terminate(self) -> None:
        self.terminated = True
        self.return_code = -15

    def kill(self) -> None:
        self.killed = True
        self.return_code = -9

    def wait(self, timeout: float | None = None) -> int:
        if self.return_code is None:
            raise subprocess.TimeoutExpired("fake", timeout)
        return self.return_code


def _plan(root: Path):
    workspace = OperationsWorkspace(root)
    return build_operations_runtime_plan(workspace, OperationsRuntimeConfig())


def test_supervisor_state_repository_round_trips_process_identity(tmp_path: Path) -> None:
    path = tmp_path / "runtime" / "supervisor.json"
    at = datetime(2026, 10, 2, 6, 0, tzinfo=UTC)
    state = OperationsSupervisorState(
        state=OperationsSupervisorStateKind.FAILED,
        supervisor_pid=100,
        started_at=at,
        updated_at=at + timedelta(seconds=3),
        components=(
            OperationsChildProcessState(
                OperationsComponentKind.COLLECTION,
                101,
                tmp_path / "logs" / "collection.log",
                return_code=0,
            ),
            OperationsChildProcessState(
                OperationsComponentKind.ANALYSIS,
                102,
                tmp_path / "logs" / "analysis.log",
                return_code=3,
            ),
        ),
        failure="analysis exited with code 3",
    )
    repository = OperationsSupervisorStateRepository(path)

    repository.write(state)

    assert repository.load() == state


def test_supervisor_starts_collection_analysis_ui_and_stops_as_one_set(
    tmp_path: Path,
) -> None:
    plan = _plan(tmp_path / "plant-a")
    repository = OperationsSupervisorStateRepository(plan.workspace.supervisor_state_path)
    launched: list[OperationsComponentKind] = []
    processes: dict[OperationsComponentKind, _FakeProcess] = {}

    def launch(component: OperationsComponentLaunch) -> _FakeProcess:
        launched.append(component.kind)
        process = _FakeProcess(200 + len(launched))
        processes[component.kind] = process
        return process

    start = datetime(2026, 10, 2, 6, 0, tzinfo=UTC)
    times = iter((start, start + timedelta(seconds=1)))

    result = run_operations_supervisor(
        plan,
        repository=repository,
        process_launcher=launch,
        stop_requested=lambda: True,
        now=lambda: next(times),
        sleep=lambda _: None,
    )

    assert launched == [
        OperationsComponentKind.COLLECTION,
        OperationsComponentKind.ANALYSIS,
        OperationsComponentKind.UI,
    ]
    assert result.exit_code == 0
    assert result.state.state == OperationsSupervisorStateKind.STOPPED
    assert repository.load() == result.state
    assert tuple(item.return_code for item in result.state.components) == (0, 0, 0)
    assert processes[OperationsComponentKind.COLLECTION].signals == [signal.SIGINT]
    assert processes[OperationsComponentKind.ANALYSIS].signals == [signal.SIGINT]
    assert processes[OperationsComponentKind.UI].signals == [signal.SIGINT]


def test_supervisor_fails_whole_set_when_one_component_exits(tmp_path: Path) -> None:
    plan = _plan(tmp_path / "plant-a")
    repository = OperationsSupervisorStateRepository(plan.workspace.supervisor_state_path)
    processes: dict[OperationsComponentKind, _FakeProcess] = {}

    def launch(component: OperationsComponentLaunch) -> _FakeProcess:
        process = _FakeProcess(
            300 + len(processes),
            return_code=3 if component.kind == OperationsComponentKind.ANALYSIS else None,
        )
        processes[component.kind] = process
        return process

    start = datetime(2026, 10, 2, 6, 0, tzinfo=UTC)
    times = iter((start, start + timedelta(seconds=1)))

    result = run_operations_supervisor(
        plan,
        repository=repository,
        process_launcher=launch,
        now=lambda: next(times),
        sleep=lambda _: None,
    )

    assert result.exit_code == 1
    assert result.state.state == OperationsSupervisorStateKind.FAILED
    assert result.state.failure == "analysis exited with code 3"
    assert tuple(item.return_code for item in result.state.components) == (0, 3, 0)
    assert processes[OperationsComponentKind.COLLECTION].signals == [signal.SIGINT]
    assert processes[OperationsComponentKind.UI].signals == [signal.SIGINT]


def test_supervisor_cleans_started_child_when_later_spawn_fails(tmp_path: Path) -> None:
    plan = _plan(tmp_path / "plant-a")
    repository = OperationsSupervisorStateRepository(plan.workspace.supervisor_state_path)
    collection = _FakeProcess(401)

    def launch(component: OperationsComponentLaunch) -> _FakeProcess:
        if component.kind == OperationsComponentKind.ANALYSIS:
            raise OSError("cannot spawn analysis")
        return collection

    start = datetime(2026, 10, 2, 6, 0, tzinfo=UTC)
    times = iter((start, start + timedelta(seconds=1)))

    result = run_operations_supervisor(
        plan,
        repository=repository,
        process_launcher=launch,
        now=lambda: next(times),
        sleep=lambda _: None,
    )

    assert result.exit_code == 1
    assert result.state.state == OperationsSupervisorStateKind.FAILED
    assert result.state.failure == "failed to start local component: cannot spawn analysis"
    assert tuple(item.kind for item in result.state.components) == (
        OperationsComponentKind.COLLECTION,
    )
    assert collection.signals == [signal.SIGINT]


def test_stop_request_requires_live_workspace_lock(tmp_path: Path, monkeypatch) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    at = datetime(2026, 10, 2, 6, 0, tzinfo=UTC)
    repository = OperationsSupervisorStateRepository(workspace.supervisor_state_path)
    repository.write(
        OperationsSupervisorState(
            state=OperationsSupervisorStateKind.RUNNING,
            supervisor_pid=501,
            started_at=at,
            updated_at=at,
            components=(),
        )
    )
    workspace.supervisor_lock_path.parent.mkdir(parents=True, exist_ok=True)
    workspace.supervisor_lock_path.touch()

    signals: list[tuple[int, int]] = []

    with pytest.raises(RuntimeError, match="lock is not owned"):
        request_operations_supervisor_stop(
            workspace,
            signal_sender=lambda pid, sig: signals.append((pid, sig)),
        )

    assert signals == []


def test_stop_request_signals_recorded_supervisor_only_when_lock_is_owned(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    at = datetime(2026, 10, 2, 6, 0, tzinfo=UTC)
    repository = OperationsSupervisorStateRepository(workspace.supervisor_state_path)
    repository.write(
        OperationsSupervisorState(
            state=OperationsSupervisorStateKind.RUNNING,
            supervisor_pid=502,
            started_at=at,
            updated_at=at,
            components=(),
        )
    )
    workspace.supervisor_lock_path.parent.mkdir(parents=True, exist_ok=True)
    workspace.supervisor_lock_path.write_text("502\n", encoding="utf-8")

    import industrial_phm.runtime.operations_supervisor as supervisor_module

    real_flock = supervisor_module.fcntl.flock

    def owned_lock(file_descriptor: int, operation: int) -> None:
        if operation == supervisor_module.fcntl.LOCK_EX | supervisor_module.fcntl.LOCK_NB:
            raise BlockingIOError
        real_flock(file_descriptor, operation)

    monkeypatch.setattr(supervisor_module.fcntl, "flock", owned_lock)
    signals: list[tuple[int, int]] = []

    pid = request_operations_supervisor_stop(
        workspace,
        signal_sender=lambda value, sig: signals.append((value, sig)),
    )

    assert pid == 502
    assert signals == [(502, signal.SIGINT)]


def test_stop_request_rejects_state_and_lock_owner_pid_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    at = datetime(2026, 10, 2, 6, 0, tzinfo=UTC)
    repository = OperationsSupervisorStateRepository(workspace.supervisor_state_path)
    repository.write(
        OperationsSupervisorState(
            state=OperationsSupervisorStateKind.RUNNING,
            supervisor_pid=601,
            started_at=at,
            updated_at=at,
            components=(),
        )
    )
    workspace.supervisor_lock_path.parent.mkdir(parents=True, exist_ok=True)
    workspace.supervisor_lock_path.write_text("602\n", encoding="utf-8")

    import industrial_phm.runtime.operations_supervisor as supervisor_module

    def owned_lock(file_descriptor: int, operation: int) -> None:
        if operation == supervisor_module.fcntl.LOCK_EX | supervisor_module.fcntl.LOCK_NB:
            raise BlockingIOError

    monkeypatch.setattr(supervisor_module.fcntl, "flock", owned_lock)
    signals: list[tuple[int, int]] = []

    with pytest.raises(RuntimeError, match="state/lock owner mismatch"):
        request_operations_supervisor_stop(
            workspace,
            signal_sender=lambda value, sig: signals.append((value, sig)),
        )

    assert signals == []



def test_ui_child_environment_uses_workspace_and_clears_granular_path_overrides(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import industrial_phm.runtime.operations_supervisor as supervisor_module

    plan = _plan(tmp_path / "plant-a")
    ui = plan.components[2]
    monkeypatch.setenv("INDUSTRIAL_PHM_HISTORY_DATA", "/tmp/wrong-history")
    monkeypatch.setenv("INDUSTRIAL_PHM_OPERATIONS_SOURCE_REGISTRY", "/tmp/wrong-registry")

    environment = supervisor_module._component_environment(ui)

    assert environment[OPERATIONS_WORKSPACE_ENV] == str(plan.workspace.root)
    assert "INDUSTRIAL_PHM_HISTORY_DATA" not in environment
    assert "INDUSTRIAL_PHM_OPERATIONS_SOURCE_REGISTRY" not in environment
