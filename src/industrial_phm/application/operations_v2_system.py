"""Operator-facing System runtime projection for Operations V2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from industrial_phm.application.acquisition_telemetry import (
    AcquisitionTelemetrySurface,
    CollectionServiceRuntimeTelemetry,
)
from industrial_phm.application.opcua_persistent import OpcUaPersistentSessionState
from industrial_phm.application.operations_attention import SystemStateErrorEvidence
from industrial_phm.application.operations_v2 import (
    COLLECTION_SERVICE_TIMEOUT,
    OperationsMonitorStage,
    OperationsMonitorStageKind,
    OperationsMonitorStatus,
    OperationsMonitorView,
    collection_service_issue,
    last_live_data_at,
)
from industrial_phm.application.source_registration import RegisteredSource, SourceType
from industrial_phm.application.window_analysis_runtime import WindowAnalysisRunnerTelemetry


class SystemRuntimeKind(StrEnum):
    ACQUISITION = "acquisition"
    HISTORY = "history"
    ANALYSIS = "analysis"
    APPLICATION = "application"


@dataclass(frozen=True, slots=True)
class SystemRuntimeFact:
    label: str
    value: str

    def __post_init__(self) -> None:
        _require_text(self.label, "label")
        _require_text(self.value, "value")


@dataclass(frozen=True, slots=True)
class SystemRuntimeService:
    kind: SystemRuntimeKind
    title: str
    status: OperationsMonitorStatus
    summary: str
    updated_at: datetime | None
    facts: Sequence[SystemRuntimeFact] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SystemRuntimeKind):
            raise ValueError("kind must be a SystemRuntimeKind")
        _require_text(self.title, "title")
        if not isinstance(self.status, OperationsMonitorStatus):
            raise ValueError("status must be an OperationsMonitorStatus")
        _require_text(self.summary, "summary")
        if self.updated_at is not None:
            _require_aware(self.updated_at, "updated_at")
        facts = tuple(self.facts)
        if any(not isinstance(item, SystemRuntimeFact) for item in facts):
            raise ValueError("facts must contain SystemRuntimeFact values")
        if len({item.label for item in facts}) != len(facts):
            raise ValueError("fact labels must be unique")
        object.__setattr__(self, "facts", facts)


@dataclass(frozen=True, slots=True)
class SystemRuntimeError:
    scope: str
    title: str
    detail: str
    detected_at: datetime

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.scope, "scope"),
            (self.title, "title"),
            (self.detail, "detail"),
        ):
            _require_text(value, field_name)
        _require_aware(self.detected_at, "detected_at")


@dataclass(frozen=True, slots=True)
class SystemRuntimeView:
    assessed_at: datetime
    services: Sequence[SystemRuntimeService]
    errors: Sequence[SystemRuntimeError]

    def __post_init__(self) -> None:
        _require_aware(self.assessed_at, "assessed_at")
        services = tuple(self.services)
        errors = tuple(self.errors)
        if any(not isinstance(item, SystemRuntimeService) for item in services):
            raise ValueError("services must contain SystemRuntimeService values")
        if tuple(item.kind for item in services) != tuple(SystemRuntimeKind):
            raise ValueError("services must use the complete canonical system order")
        if any(not isinstance(item, SystemRuntimeError) for item in errors):
            raise ValueError("errors must contain SystemRuntimeError values")
        if errors != tuple(
            sorted(errors, key=lambda item: (-item.detected_at.timestamp(), item.scope))
        ):
            raise ValueError("errors must use newest-first deterministic order")
        object.__setattr__(self, "services", services)
        object.__setattr__(self, "errors", errors)


def build_system_runtime_view(
    *,
    monitor: OperationsMonitorView,
    sources: Sequence[RegisteredSource],
    acquisition_surfaces: Sequence[AcquisitionTelemetrySurface],
    analysis_runtime: WindowAnalysisRunnerTelemetry | None,
    system_errors: Sequence[SystemStateErrorEvidence],
    as_of: datetime,
    collection_service: CollectionServiceRuntimeTelemetry | None = None,
) -> SystemRuntimeView:
    """Build service/runtime facts without inventing uninstrumented process heartbeats."""

    _require_aware(as_of, "as_of")
    if not isinstance(monitor, OperationsMonitorView):
        raise ValueError("monitor must be an OperationsMonitorView")
    if monitor.assessed_at != as_of:
        raise ValueError("monitor and system view must use the same assessment time")

    source_values = tuple(sources)
    surfaces = tuple(acquisition_surfaces)
    errors = tuple(system_errors)
    if any(not isinstance(item, RegisteredSource) for item in source_values):
        raise ValueError("sources contains unsupported values")
    if any(not isinstance(item, AcquisitionTelemetrySurface) for item in surfaces):
        raise ValueError("acquisition_surfaces contains unsupported values")
    if any(not isinstance(item, SystemStateErrorEvidence) for item in errors):
        raise ValueError("system_errors contains unsupported values")

    surface_ids = tuple(item.source.source_id for item in surfaces)
    if len(set(surface_ids)) != len(surface_ids):
        raise ValueError("acquisition_surfaces must contain unique source ids")
    source_ids = {item.source_id for item in source_values}
    if not set(surface_ids).issubset(source_ids):
        raise ValueError("acquisition_surfaces must reference registered sources")

    collection_stage = _stage(monitor, OperationsMonitorStageKind.COLLECTION)
    storage_stage = _stage(monitor, OperationsMonitorStageKind.STORAGE)
    analysis_stage = _stage(monitor, OperationsMonitorStageKind.ANALYSIS)

    services = (
        _acquisition_service(collection_stage, source_values, surfaces, collection_service, as_of),
        _history_service(storage_stage, surfaces),
        _analysis_service(analysis_stage, surfaces, analysis_runtime),
        _application_service(errors, as_of),
    )
    projected_errors = tuple(
        sorted(
            (
                SystemRuntimeError(
                    scope=item.scope,
                    title=_error_title(item.scope),
                    detail=item.detail,
                    detected_at=item.detected_at,
                )
                for item in errors
            ),
            key=lambda item: (-item.detected_at.timestamp(), item.scope),
        )
    )
    return SystemRuntimeView(
        assessed_at=as_of,
        services=services,
        errors=projected_errors,
    )


def _acquisition_service(
    stage: OperationsMonitorStage,
    sources: Sequence[RegisteredSource],
    surfaces: Sequence[AcquisitionTelemetrySurface],
    collection_service: CollectionServiceRuntimeTelemetry | None = None,
    as_of: datetime | None = None,
) -> SystemRuntimeService:
    # Session facts come from the collector's own reports; when it is not running
    # they are its last report, not current connections.
    service_down = (
        as_of is not None
        and collection_service_issue(
            collection_service, as_of=as_of, timeout=COLLECTION_SERVICE_TIMEOUT
        )
        is not None
    )
    live_sources = tuple(item for item in sources if item.source_type == SourceType.OPCUA)
    sessions = tuple(item.source.session for item in surfaces if item.source.session is not None)
    connected = sum(item.state == OpcUaPersistentSessionState.CONNECTED for item in sessions)
    reconnecting = sum(
        item.state
        in {
            OpcUaPersistentSessionState.CONNECTING,
            OpcUaPersistentSessionState.RECONNECT_WAIT,
        }
        for item in sessions
    )
    stopped = sum(
        item.state
        in {
            OpcUaPersistentSessionState.DISCONNECTED,
            OpcUaPersistentSessionState.STOPPED,
        }
        for item in sessions
    )
    last_received = max(
        (value for item in surfaces if (value := last_live_data_at(item)) is not None),
        default=None,
    )

    if not live_sources:
        status = OperationsMonitorStatus.UNAVAILABLE
        summary = "No live OPC UA source is configured"
    elif not surfaces:
        status = OperationsMonitorStatus.UNAVAILABLE
        summary = "Live acquisition telemetry is unavailable"
    else:
        status = stage.status
        summary = stage.summary

    return SystemRuntimeService(
        kind=SystemRuntimeKind.ACQUISITION,
        title="Live acquisition",
        status=status,
        summary=summary,
        updated_at=max(
            (item.state_changed_at for item in sessions),
            default=None,
        ),
        facts=(
            SystemRuntimeFact(
                "Collection service",
                "Not instrumented"
                if collection_service is None
                else (
                    f"Not responding (last reported {collection_service.state.value})"
                    if service_down
                    else collection_service.state.value.capitalize()
                ),
            ),
            SystemRuntimeFact(
                "Service heartbeat",
                _time_value(
                    None if collection_service is None else collection_service.heartbeat_at
                ),
            ),
            SystemRuntimeFact("Configured live sources", str(len(live_sources))),
            SystemRuntimeFact(
                "Connected sessions",
                (
                    f"Unknown (last report {connected} / {len(live_sources)})"
                    if service_down
                    else f"{connected} / {len(live_sources)}"
                ),
            ),
            SystemRuntimeFact("Connecting / reconnecting", str(reconnecting)),
            SystemRuntimeFact("Stopped / disconnected", str(stopped)),
            SystemRuntimeFact("Last received data", _time_value(last_received)),
        ),
    )


def _history_service(
    stage: OperationsMonitorStage,
    surfaces: Sequence[AcquisitionTelemetrySurface],
) -> SystemRuntimeService:
    latest_commit = max(
        (item.source.history.committed_at for item in surfaces if item.source.history is not None),
        default=None,
    )
    pending = None if not surfaces else surfaces[0].spool.pending_event_count
    oldest_age = None if not surfaces else surfaces[0].spool.oldest_pending_age_seconds
    return SystemRuntimeService(
        kind=SystemRuntimeKind.HISTORY,
        title="History storage",
        status=stage.status,
        summary=stage.summary,
        updated_at=latest_commit,
        facts=(
            SystemRuntimeFact(
                "Waiting to store",
                "Unavailable" if pending is None else str(pending),
            ),
            SystemRuntimeFact(
                "Oldest waiting age",
                _oldest_waiting_value(pending, oldest_age),
            ),
            SystemRuntimeFact("Latest commit", _time_value(latest_commit)),
        ),
    )


def _analysis_service(
    stage: OperationsMonitorStage,
    surfaces: Sequence[AcquisitionTelemetrySurface],
    runtime: WindowAnalysisRunnerTelemetry | None,
) -> SystemRuntimeService:
    latest_finalized = max(
        (
            item.source.window.last_finalized_window_end
            for item in surfaces
            if item.source.window is not None
            and item.source.window.last_finalized_window_end is not None
        ),
        default=None,
    )
    finalized_count = sum(
        item.source.window.finalized_window_count
        for item in surfaces
        if item.source.window is not None
    )
    facts = [
        SystemRuntimeFact("Latest finalized input", _time_value(latest_finalized)),
        SystemRuntimeFact("Finalized windows", str(finalized_count)),
    ]
    if runtime is None:
        facts.extend(
            (
                SystemRuntimeFact("Heartbeat", "Unavailable"),
                SystemRuntimeFact("Completed analyses", "Unavailable"),
                SystemRuntimeFact("Skipped inputs", "Unavailable"),
                SystemRuntimeFact("Last failure", "Unavailable"),
            )
        )
    else:
        facts.extend(
            (
                SystemRuntimeFact("Heartbeat", _time_value(runtime.heartbeat_at)),
                SystemRuntimeFact("Completed analyses", str(runtime.analyzed_count)),
                SystemRuntimeFact("Skipped inputs", str(runtime.skipped_count)),
                SystemRuntimeFact("Last result", _time_value(runtime.last_analysis_at)),
                SystemRuntimeFact("Last skip", _time_value(runtime.last_skip_at)),
                SystemRuntimeFact("Last skip reason", runtime.last_skip_reason or "None"),
                SystemRuntimeFact("Last failure", runtime.last_failure or "None"),
            )
        )
    return SystemRuntimeService(
        kind=SystemRuntimeKind.ANALYSIS,
        title="Analysis service",
        status=stage.status,
        summary=stage.summary,
        updated_at=None if runtime is None else runtime.heartbeat_at,
        facts=tuple(facts),
    )


def _application_service(
    errors: Sequence[SystemStateErrorEvidence],
    as_of: datetime,
) -> SystemRuntimeService:
    status = OperationsMonitorStatus.ERROR if errors else OperationsMonitorStatus.RUNNING
    summary = (
        f"{len(errors)} current state-read error(s)"
        if errors
        else "Current Operations state read succeeded"
    )
    return SystemRuntimeService(
        kind=SystemRuntimeKind.APPLICATION,
        title="Operations state read",
        status=status,
        summary=summary,
        updated_at=as_of,
        facts=(
            SystemRuntimeFact("Current read errors", str(len(errors))),
            SystemRuntimeFact("Last refresh", _time_value(as_of)),
            SystemRuntimeFact("Process heartbeat", "Not instrumented"),
        ),
    )


def _stage(
    monitor: OperationsMonitorView,
    kind: OperationsMonitorStageKind,
) -> OperationsMonitorStage:
    return next(item for item in monitor.stages if item.kind == kind)


def _error_title(scope: str) -> str:
    if scope.startswith("live-data:"):
        return "Live data"
    return {
        "source-settings": "Source settings",
        "source-runtime": "Source runtime",
        "field-analysis-results": "Vibration analysis results",
        "phase-analysis-results": "Three-phase analysis results",
        "review-requests": "Review requests",
        "maintenance-review": "Maintenance review",
        "live-data": "Live data",
        "analysis-service": "Analysis service",
        "analysis-attempts": "Analysis attempts",
        "asset-history": "Asset History",
    }.get(scope, "Application state")


def _oldest_waiting_value(
    pending: int | None,
    oldest_age: float | None,
) -> str:
    if pending is None:
        return "Unavailable"
    if pending == 0:
        return "None"
    if oldest_age is None:
        return "Unavailable"
    return f"{oldest_age:.1f} s"


def _time_value(value: datetime | None) -> str:
    if value is None:
        return "Unavailable"
    if value.utcoffset() is None:
        return "Time not comparable"
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _require_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
