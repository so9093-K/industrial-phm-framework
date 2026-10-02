from datetime import UTC, datetime, timedelta
from pathlib import Path

from industrial_phm.application import (
    CollectionServiceRuntimeState,
    CollectionServiceRuntimeTelemetry,
    WindowAnalysisRunnerState,
    WindowAnalysisRunnerTelemetry,
)
from industrial_phm.runtime import (
    OperationsChildProcessState,
    OperationsComponentKind,
    OperationsRuntimeCondition,
    OperationsSupervisorState,
    OperationsSupervisorStateKind,
    OperationsWorkspace,
    build_operations_runtime_status,
)


def _collection(at: datetime) -> CollectionServiceRuntimeTelemetry:
    return CollectionServiceRuntimeTelemetry(
        state=CollectionServiceRuntimeState.RUNNING,
        started_at=at,
        heartbeat_at=at,
        reconcile_count=1,
        owned_source_count=0,
    )


def _analysis(at: datetime) -> WindowAnalysisRunnerTelemetry:
    return WindowAnalysisRunnerTelemetry(
        state=WindowAnalysisRunnerState.RUNNING,
        started_at=at,
        heartbeat_at=at,
    )


def _supervisor(root: Path, at: datetime, *, stopped: bool = False) -> OperationsSupervisorState:
    return OperationsSupervisorState(
        state=(
            OperationsSupervisorStateKind.STOPPED
            if stopped
            else OperationsSupervisorStateKind.RUNNING
        ),
        supervisor_pid=100,
        started_at=at,
        updated_at=at,
        components=(
            OperationsChildProcessState(
                OperationsComponentKind.COLLECTION,
                101,
                root / "logs" / "collection.log",
                return_code=0 if stopped else None,
            ),
            OperationsChildProcessState(
                OperationsComponentKind.ANALYSIS,
                102,
                root / "logs" / "analysis.log",
                return_code=0 if stopped else None,
            ),
            OperationsChildProcessState(
                OperationsComponentKind.UI,
                103,
                root / "logs" / "ui.log",
                return_code=0 if stopped else None,
            ),
        ),
    )


def test_runtime_status_is_ready_only_when_all_component_evidence_is_ready(
    tmp_path: Path,
) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    heartbeat = datetime(2026, 10, 2, 6, 0, tzinfo=UTC)

    status = build_operations_runtime_status(
        workspace,
        supervisor=_supervisor(workspace.root, heartbeat),
        collection_runtime=_collection(heartbeat),
        analysis_runtime=_analysis(heartbeat),
        as_of=heartbeat + timedelta(seconds=5),
        process_checker=lambda _: True,
        ui_listener_probe=lambda _host, _port: True,
    )

    assert status.ready is True
    assert status.supervisor.condition == OperationsRuntimeCondition.RUNNING
    assert tuple(item.condition for item in status.components) == (
        OperationsRuntimeCondition.RUNNING,
        OperationsRuntimeCondition.RUNNING,
        OperationsRuntimeCondition.RUNNING,
    )
    assert status.components[2].runtime_state == "listener-ready"


def test_runtime_status_keeps_stale_analysis_separate_from_process_identity(
    tmp_path: Path,
) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    heartbeat = datetime(2026, 10, 2, 6, 0, tzinfo=UTC)

    status = build_operations_runtime_status(
        workspace,
        supervisor=_supervisor(workspace.root, heartbeat + timedelta(seconds=25)),
        collection_runtime=_collection(heartbeat + timedelta(seconds=25)),
        analysis_runtime=_analysis(heartbeat),
        as_of=heartbeat + timedelta(seconds=30),
        process_checker=lambda _: True,
        ui_listener_probe=lambda _host, _port: True,
    )

    assert status.ready is False
    analysis = status.components[1]
    assert analysis.process is not None
    assert analysis.process.alive is True
    assert analysis.runtime_state == "running"
    assert analysis.condition == OperationsRuntimeCondition.STALE
    assert analysis.detail == "analysis runtime heartbeat is stale"


def test_runtime_status_does_not_promote_unmanaged_component_evidence_to_ready(
    tmp_path: Path,
) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    heartbeat = datetime(2026, 10, 2, 6, 0, tzinfo=UTC)

    status = build_operations_runtime_status(
        workspace,
        supervisor=None,
        collection_runtime=_collection(heartbeat),
        analysis_runtime=_analysis(heartbeat),
        as_of=heartbeat + timedelta(seconds=1),
        process_checker=lambda _: True,
        ui_listener_probe=lambda _host, _port: True,
    )

    assert status.ready is False
    assert status.supervisor.condition == OperationsRuntimeCondition.UNAVAILABLE
    assert tuple(item.condition for item in status.components) == (
        OperationsRuntimeCondition.UNAVAILABLE,
        OperationsRuntimeCondition.UNAVAILABLE,
        OperationsRuntimeCondition.UNAVAILABLE,
    )
    assert status.components[0].runtime_state == "running"


def test_runtime_status_treats_clean_child_exit_as_stopped_not_failed(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    heartbeat = datetime(2026, 10, 2, 6, 0, tzinfo=UTC)

    status = build_operations_runtime_status(
        workspace,
        supervisor=_supervisor(workspace.root, heartbeat, stopped=True),
        collection_runtime=_collection(heartbeat),
        analysis_runtime=_analysis(heartbeat),
        as_of=heartbeat + timedelta(seconds=1),
        process_checker=lambda _: False,
        ui_listener_probe=lambda _host, _port: False,
    )

    assert status.ready is False
    assert status.supervisor.condition == OperationsRuntimeCondition.STOPPED
    assert tuple(item.condition for item in status.components) == (
        OperationsRuntimeCondition.STOPPED,
        OperationsRuntimeCondition.STOPPED,
        OperationsRuntimeCondition.STOPPED,
    )


def test_ui_pid_without_listener_is_not_ready(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    heartbeat = datetime(2026, 10, 2, 6, 0, tzinfo=UTC)

    status = build_operations_runtime_status(
        workspace,
        supervisor=_supervisor(workspace.root, heartbeat),
        collection_runtime=_collection(heartbeat),
        analysis_runtime=_analysis(heartbeat),
        as_of=heartbeat + timedelta(seconds=1),
        process_checker=lambda _: True,
        ui_listener_probe=lambda _host, _port: False,
    )

    ui = status.components[2]
    assert status.ready is False
    assert ui.condition == OperationsRuntimeCondition.NOT_READY
    assert ui.process is not None
    assert ui.process.alive is True
    assert ui.runtime_state == "listener-not-ready"
