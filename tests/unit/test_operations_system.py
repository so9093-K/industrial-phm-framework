from datetime import UTC, datetime, timedelta

from industrial_phm.application.operations_attention import SystemStateErrorEvidence
from industrial_phm.application.operations_monitor import (
    OperationsMonitorStage,
    OperationsMonitorStageKind,
    OperationsMonitorStatus,
    OperationsMonitorView,
)
from industrial_phm.application.operations_system import (
    SystemRuntimeKind,
    build_system_runtime_view,
)
from industrial_phm.application.window_analysis_runtime import (
    WindowAnalysisRunnerState,
    WindowAnalysisRunnerTelemetry,
)

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def _monitor() -> OperationsMonitorView:
    stages = (
        OperationsMonitorStage(
            OperationsMonitorStageKind.SOURCE,
            OperationsMonitorStatus.WAITING,
            "Sources",
            "No source configured",
        ),
        OperationsMonitorStage(
            OperationsMonitorStageKind.COLLECTION,
            OperationsMonitorStatus.WAITING,
            "Collect",
            "Waiting for a configured source",
        ),
        OperationsMonitorStage(
            OperationsMonitorStageKind.STORAGE,
            OperationsMonitorStatus.UNAVAILABLE,
            "Store",
            "No live storage telemetry available",
        ),
        OperationsMonitorStage(
            OperationsMonitorStageKind.ANALYSIS,
            OperationsMonitorStatus.RUNNING,
            "Analyze",
            "Analysis service running",
            updated_at=NOW,
        ),
        OperationsMonitorStage(
            OperationsMonitorStageKind.REVIEW,
            OperationsMonitorStatus.WAITING,
            "Review",
            "No review waiting",
        ),
    )
    return OperationsMonitorView(
        assessed_at=NOW,
        stages=stages,
        assets=(),
        attention=(),
        activities=(),
    )


def _runtime() -> WindowAnalysisRunnerTelemetry:
    return WindowAnalysisRunnerTelemetry(
        state=WindowAnalysisRunnerState.RUNNING,
        started_at=NOW - timedelta(hours=1),
        heartbeat_at=NOW,
        cycle_count=5,
        analyzed_count=3,
        skipped_count=2,
        last_cycle_completed_at=NOW,
        last_analysis_at=NOW - timedelta(seconds=5),
        last_analysis_run_id="run-3",
        last_skip_at=NOW - timedelta(seconds=20),
        last_skip_reason="missing phase T",
    )


def test_system_view_uses_instrumented_runtime_without_inventing_collection_process() -> None:
    view = build_system_runtime_view(
        monitor=_monitor(),
        sources=(),
        acquisition_surfaces=(),
        analysis_runtime=_runtime(),
        system_errors=(),
        as_of=NOW,
    )

    assert tuple(item.kind for item in view.services) == tuple(SystemRuntimeKind)
    acquisition = view.services[0]
    assert acquisition.status == OperationsMonitorStatus.UNAVAILABLE
    assert acquisition.summary == "No live OPC UA source is configured"

    analysis = view.services[2]
    assert analysis.status == OperationsMonitorStatus.RUNNING
    assert {fact.label: fact.value for fact in analysis.facts}["Completed analyses"] == "3"
    facts = {fact.label: fact.value for fact in analysis.facts}
    assert facts["Skipped inputs"] == "2"
    assert facts["Last skip reason"] == "missing phase T"
    assert facts["Heartbeat"] == "2026-09-30 12:00:00 UTC"

    application = view.services[3]
    assert application.status == OperationsMonitorStatus.RUNNING
    assert application.title == "Operations state read"
    assert application.summary == "Current Operations state read succeeded"
    assert {fact.label: fact.value for fact in application.facts}["Process heartbeat"] == (
        "Not instrumented"
    )


def test_system_view_surfaces_read_failure_as_application_error() -> None:
    error = SystemStateErrorEvidence(
        "asset-history",
        "catalog unreadable",
        NOW - timedelta(seconds=1),
    )
    view = build_system_runtime_view(
        monitor=_monitor(),
        sources=(),
        acquisition_surfaces=(),
        analysis_runtime=None,
        system_errors=(error,),
        as_of=NOW,
    )

    application = view.services[3]
    assert application.status == OperationsMonitorStatus.ERROR
    assert application.summary == "1 current state-read error(s)"
    assert view.errors[0].title == "Asset History"
    assert view.errors[0].detail == "catalog unreadable"
