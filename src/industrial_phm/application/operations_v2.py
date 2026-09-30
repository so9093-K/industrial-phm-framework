"""User-question-oriented Operations V2 monitor read models.

The V2 monitor translates existing operational evidence into a small operator-facing
vocabulary. It does not create asset-health, fault, severity, alarm, or maintenance
verdicts.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from industrial_phm.application.acquisition_telemetry import (
    AcquisitionFailureComponent,
    AcquisitionFailureTelemetry,
    AcquisitionTelemetrySurface,
)
from industrial_phm.application.maintenance_review import FindingReviewStatus
from industrial_phm.application.opcua_persistent import OpcUaPersistentSessionState
from industrial_phm.application.operational import AnalysisRun
from industrial_phm.application.operations_attention import (
    AttentionHandlingState,
    AttentionItem,
    AttentionKind,
    OperationsAttentionQueue,
)
from industrial_phm.application.operations_overview import OperationsOverview
from industrial_phm.application.source_health import (
    SourceDataFlowState,
    SourceHealthAssessment,
)
from industrial_phm.application.source_registration import RegisteredSource
from industrial_phm.application.window_analysis_runtime import (
    WindowAnalysisRunnerState,
    WindowAnalysisRunnerTelemetry,
)


class OperationsMonitorStatus(StrEnum):
    """Small operator-facing state vocabulary used across the V2 shell."""

    RUNNING = "running"
    WAITING = "waiting"
    DELAYED = "delayed"
    STOPPED = "stopped"
    NEEDS_ATTENTION = "needs-attention"
    ERROR = "error"
    UNAVAILABLE = "unavailable"


class OperationsMonitorStageKind(StrEnum):
    SOURCE = "source"
    COLLECTION = "collection"
    STORAGE = "storage"
    ANALYSIS = "analysis"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class OperationsMonitorStage:
    kind: OperationsMonitorStageKind
    status: OperationsMonitorStatus
    title: str
    summary: str
    updated_at: datetime | None = None
    count: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, OperationsMonitorStageKind):
            raise ValueError("kind must be an OperationsMonitorStageKind")
        if not isinstance(self.status, OperationsMonitorStatus):
            raise ValueError("status must be an OperationsMonitorStatus")
        _require_text(self.title, "title")
        _require_text(self.summary, "summary")
        if self.updated_at is not None:
            _require_aware(self.updated_at, "updated_at")
        if self.count is not None:
            _require_non_negative_int(self.count, "count")


@dataclass(frozen=True, slots=True)
class OperationsMonitorAttention:
    """One operator-facing reason to inspect a current operational fact."""

    attention_id: str
    status: OperationsMonitorStatus
    title: str
    detail: str
    occurred_at: datetime | None = None
    asset_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.attention_id, "attention_id")
        if self.status not in {
            OperationsMonitorStatus.DELAYED,
            OperationsMonitorStatus.NEEDS_ATTENTION,
            OperationsMonitorStatus.ERROR,
        }:
            raise ValueError("attention status must require inspection")
        _require_text(self.title, "title")
        _require_text(self.detail, "detail")
        if self.occurred_at is not None:
            _require_aware(self.occurred_at, "occurred_at")
        if self.asset_id is not None:
            _require_text(self.asset_id, "asset_id")


@dataclass(frozen=True, slots=True)
class OperationsMonitorAsset:
    asset_id: str
    status: OperationsMonitorStatus
    source_count: int
    last_data_at: datetime | None
    latest_analysis_at: datetime | None
    pending_review_count: int
    attention_count: int

    def __post_init__(self) -> None:
        _require_text(self.asset_id, "asset_id")
        if not isinstance(self.status, OperationsMonitorStatus):
            raise ValueError("status must be an OperationsMonitorStatus")
        for field_name in (
            "source_count",
            "pending_review_count",
            "attention_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        for field_name in ("last_data_at", "latest_analysis_at"):
            value = getattr(self, field_name)
            if value is not None:
                _require_aware(value, field_name)


class OperationsActivityKind(StrEnum):
    ANALYSIS_COMPLETED = "analysis-completed"
    ATTENTION = "attention"


@dataclass(frozen=True, slots=True)
class OperationsActivityItem:
    activity_id: str
    kind: OperationsActivityKind
    occurred_at: datetime
    title: str
    asset_id: str | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.activity_id, "activity_id")
        if not isinstance(self.kind, OperationsActivityKind):
            raise ValueError("kind must be an OperationsActivityKind")
        _require_aware(self.occurred_at, "occurred_at")
        _require_text(self.title, "title")
        if self.asset_id is not None:
            _require_text(self.asset_id, "asset_id")
        if self.detail is not None:
            _require_text(self.detail, "detail")


@dataclass(frozen=True, slots=True)
class OperationsMonitorView:
    assessed_at: datetime
    stages: Sequence[OperationsMonitorStage]
    assets: Sequence[OperationsMonitorAsset]
    attention: Sequence[OperationsMonitorAttention]
    activities: Sequence[OperationsActivityItem]

    def __post_init__(self) -> None:
        _require_aware(self.assessed_at, "assessed_at")
        stages = tuple(self.stages)
        assets = tuple(self.assets)
        attention = tuple(self.attention)
        activities = tuple(self.activities)
        if any(not isinstance(item, OperationsMonitorStage) for item in stages):
            raise ValueError("stages must contain OperationsMonitorStage values")
        if tuple(item.kind for item in stages) != tuple(OperationsMonitorStageKind):
            raise ValueError("stages must follow the complete canonical stage order")
        if any(not isinstance(item, OperationsMonitorAsset) for item in assets):
            raise ValueError("assets must contain OperationsMonitorAsset values")
        if tuple(sorted(item.asset_id for item in assets)) != tuple(
            item.asset_id for item in assets
        ):
            raise ValueError("assets must use deterministic asset-id order")
        if any(not isinstance(item, OperationsMonitorAttention) for item in attention):
            raise ValueError("attention must contain OperationsMonitorAttention values")
        if attention != tuple(sorted(attention, key=_attention_sort_key)):
            raise ValueError("attention must use deterministic operator ordering")
        if any(not isinstance(item, OperationsActivityItem) for item in activities):
            raise ValueError("activities must contain OperationsActivityItem values")
        if activities != tuple(sorted(activities, key=_activity_sort_key)):
            raise ValueError("activities must use newest-first deterministic ordering")
        object.__setattr__(self, "stages", stages)
        object.__setattr__(self, "assets", assets)
        object.__setattr__(self, "attention", attention)
        object.__setattr__(self, "activities", activities)

    @property
    def attention_count(self) -> int:
        return len(self.attention)


def build_operations_monitor_view(
    *,
    sources: Sequence[RegisteredSource],
    overview: OperationsOverview,
    attention: OperationsAttentionQueue,
    acquisition_surfaces: Sequence[AcquisitionTelemetrySurface] = (),
    analysis_runs: Sequence[AnalysisRun] = (),
    analysis_runtime: WindowAnalysisRunnerTelemetry | None = None,
    analysis_heartbeat_timeout: timedelta = timedelta(seconds=20),
    as_of: datetime,
) -> OperationsMonitorView:
    """Build the V2 landing-page model from already-loaded operational evidence."""

    _require_aware(as_of, "as_of")
    if not isinstance(overview, OperationsOverview):
        raise ValueError("overview must be an OperationsOverview")
    if not isinstance(attention, OperationsAttentionQueue):
        raise ValueError("attention must be an OperationsAttentionQueue")
    if overview.assessed_at != as_of:
        raise ValueError("overview and monitor must use the same assessment time")
    if (
        not isinstance(analysis_heartbeat_timeout, timedelta)
        or analysis_heartbeat_timeout <= timedelta()
    ):
        raise ValueError("analysis_heartbeat_timeout must be positive")

    source_values = tuple(sources)
    if any(not isinstance(item, RegisteredSource) for item in source_values):
        raise ValueError("sources must contain only RegisteredSource values")
    source_ids = tuple(item.source_id for item in source_values)
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("sources must contain unique source ids")
    overview_source_ids = tuple(item.source_id for item in overview.source_health_assessments)
    if set(source_ids) != set(overview_source_ids):
        raise ValueError("sources and overview must describe the same source population")

    surface_values = tuple(acquisition_surfaces)
    if any(not isinstance(item, AcquisitionTelemetrySurface) for item in surface_values):
        raise ValueError("acquisition_surfaces contains an unsupported value")
    surface_ids = tuple(item.source.source_id for item in surface_values)
    if len(set(surface_ids)) != len(surface_ids):
        raise ValueError("acquisition_surfaces must contain unique source ids")
    if not set(surface_ids).issubset(set(source_ids)):
        raise ValueError("acquisition_surfaces must reference registered sources")
    _validate_global_spool_snapshot(surface_values)

    runs = tuple(analysis_runs)
    if any(not isinstance(item, AnalysisRun) for item in runs):
        raise ValueError("analysis_runs must contain only AnalysisRun values")
    run_ids = tuple(item.analysis_run_id for item in runs)
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("analysis_runs must contain unique analysis ids")

    surface_by_source = {item.source.source_id: item for item in surface_values}
    source_by_id = {item.source_id: item for item in source_values}
    health_by_source = {
        item.source_id: item for item in overview.source_health_assessments
    }

    monitor_attention = _monitor_attention(
        attention,
        source_by_id,
        health_by_source,
        surface_by_source,
        analysis_runtime,
        analysis_heartbeat_timeout,
        as_of,
    )
    stages = (
        _source_stage(overview, surface_by_source),
        _collection_stage(overview, surface_values),
        _storage_stage(surface_values),
        _analysis_stage(
            surface_values,
            analysis_runtime,
            analysis_heartbeat_timeout,
            as_of,
        ),
        _review_stage(overview),
    )
    assets = _asset_rows(
        source_values,
        overview,
        monitor_attention,
        runs,
        surface_by_source,
    )
    activities = _activities(monitor_attention, runs, limit=12)
    return OperationsMonitorView(
        assessed_at=as_of,
        stages=stages,
        assets=assets,
        attention=monitor_attention,
        activities=activities,
    )


def _source_stage(
    overview: OperationsOverview,
    surfaces: dict[str, AcquisitionTelemetrySurface],
) -> OperationsMonitorStage:
    total = overview.registered_source_count
    if total == 0:
        return OperationsMonitorStage(
            OperationsMonitorStageKind.SOURCE,
            OperationsMonitorStatus.WAITING,
            "Sources",
            "No source configured",
            count=0,
        )
    statuses = tuple(
        _source_status(item, surfaces.get(item.source_id))
        for item in overview.source_health_assessments
    )
    errors = statuses.count(OperationsMonitorStatus.ERROR)
    delayed = statuses.count(OperationsMonitorStatus.DELAYED)
    running = statuses.count(OperationsMonitorStatus.RUNNING)
    waiting = statuses.count(OperationsMonitorStatus.WAITING)
    if errors:
        status = OperationsMonitorStatus.ERROR
        summary = f"{errors} source(s) have a current data-flow failure"
    elif delayed:
        status = OperationsMonitorStatus.DELAYED
        summary = f"{delayed} source(s) delayed"
    elif running:
        status = OperationsMonitorStatus.RUNNING
        summary = f"{running} of {total} source(s) receiving data"
        if waiting:
            summary += f" · {waiting} waiting"
    elif waiting:
        status = OperationsMonitorStatus.WAITING
        summary = f"{waiting} source(s) waiting for data"
    elif overview.active_source_count == 0:
        status = OperationsMonitorStatus.STOPPED
        summary = "No source is enabled"
    else:
        status = OperationsMonitorStatus.UNAVAILABLE
        summary = "Current source timing is unavailable"
    latest = max(
        (_latest_source_data_at(item, surfaces.get(item.source_id))
         for item in overview.source_health_assessments),
        default=None,
    )
    return OperationsMonitorStage(
        OperationsMonitorStageKind.SOURCE,
        status,
        "Sources",
        summary,
        updated_at=latest,
        count=total,
    )


def _collection_stage(
    overview: OperationsOverview,
    surfaces: Sequence[AcquisitionTelemetrySurface],
) -> OperationsMonitorStage:
    if overview.registered_source_count == 0:
        return OperationsMonitorStage(
            OperationsMonitorStageKind.COLLECTION,
            OperationsMonitorStatus.WAITING,
            "Collect",
            "Waiting for a configured source",
        )
    worker_failures = sum(
        _current_failure(surface, AcquisitionFailureComponent.OPCUA_WORKER) is not None
        for surface in surfaces
    )
    connected = sum(
        surface.source.session is not None
        and surface.source.session.state == OpcUaPersistentSessionState.CONNECTED
        for surface in surfaces
    )
    if worker_failures:
        status = OperationsMonitorStatus.ERROR
        summary = f"{worker_failures} collection worker failure(s)"
    elif connected:
        status = OperationsMonitorStatus.RUNNING
        summary = f"{connected} live source session(s) connected"
    elif overview.active_source_count:
        status = OperationsMonitorStatus.WAITING
        summary = "Collection enabled; waiting for live session evidence"
    else:
        status = OperationsMonitorStatus.STOPPED
        summary = "Collection is not enabled"
    updated = max(
        (
            surface.source.session.state_changed_at
            for surface in surfaces
            if surface.source.session is not None
        ),
        default=None,
    )
    return OperationsMonitorStage(
        OperationsMonitorStageKind.COLLECTION,
        status,
        "Collect",
        summary,
        updated_at=updated,
        count=connected,
    )


def _storage_stage(
    surfaces: Sequence[AcquisitionTelemetrySurface],
) -> OperationsMonitorStage:
    if not surfaces:
        return OperationsMonitorStage(
            OperationsMonitorStageKind.STORAGE,
            OperationsMonitorStatus.UNAVAILABLE,
            "Store",
            "No live storage telemetry available",
        )
    failures = sum(
        _current_failure(surface, AcquisitionFailureComponent.HISTORY_WRITER) is not None
        for surface in surfaces
    )
    pending = surfaces[0].spool.pending_event_count
    history = tuple(
        surface.source.history
        for surface in surfaces
        if surface.source.history is not None
    )
    if failures:
        status = OperationsMonitorStatus.ERROR
        summary = f"{failures} history writer failure(s)"
    elif history:
        status = OperationsMonitorStatus.RUNNING
        summary = "History current" if pending == 0 else f"{pending} event(s) waiting to store"
    elif pending:
        status = OperationsMonitorStatus.WAITING
        summary = f"{pending} event(s) waiting for first history commit"
    else:
        status = OperationsMonitorStatus.WAITING
        summary = "Waiting for collected data"
    updated = max((item.committed_at for item in history), default=None)
    return OperationsMonitorStage(
        OperationsMonitorStageKind.STORAGE,
        status,
        "Store",
        summary,
        updated_at=updated,
        count=pending,
    )


def _analysis_stage(
    surfaces: Sequence[AcquisitionTelemetrySurface],
    runtime: WindowAnalysisRunnerTelemetry | None,
    timeout: timedelta,
    as_of: datetime,
) -> OperationsMonitorStage:
    window_failures = sum(
        _current_failure(surface, AcquisitionFailureComponent.WINDOW_COORDINATOR)
        is not None
        for surface in surfaces
    )
    if window_failures:
        return OperationsMonitorStage(
            OperationsMonitorStageKind.ANALYSIS,
            OperationsMonitorStatus.ERROR,
            "Analyze",
            f"{window_failures} analysis-input preparation failure(s)",
        )
    if runtime is None:
        return OperationsMonitorStage(
            OperationsMonitorStageKind.ANALYSIS,
            OperationsMonitorStatus.UNAVAILABLE,
            "Analyze",
            "Analysis service status unavailable",
        )
    age = as_of - runtime.heartbeat_at
    if runtime.state == WindowAnalysisRunnerState.FAILED:
        status = OperationsMonitorStatus.ERROR
        summary = runtime.last_failure or "Analysis service failed"
    elif runtime.state == WindowAnalysisRunnerState.STOPPED:
        status = OperationsMonitorStatus.STOPPED
        summary = "Analysis service stopped"
    elif age > timeout:
        status = OperationsMonitorStatus.DELAYED
        summary = f"Analysis service heartbeat is {int(age.total_seconds())}s old"
    else:
        status = OperationsMonitorStatus.RUNNING
        if runtime.last_analysis_at is None:
            summary = "Analysis service running; waiting for analyzable data"
        else:
            summary = f"{runtime.analyzed_count} analysis result(s) recorded"
    return OperationsMonitorStage(
        OperationsMonitorStageKind.ANALYSIS,
        status,
        "Analyze",
        summary,
        updated_at=runtime.heartbeat_at,
        count=runtime.analyzed_count,
    )


def _review_stage(overview: OperationsOverview) -> OperationsMonitorStage:
    pending = overview.pending_review_count
    return OperationsMonitorStage(
        OperationsMonitorStageKind.REVIEW,
        (
            OperationsMonitorStatus.NEEDS_ATTENTION
            if pending
            else OperationsMonitorStatus.WAITING
        ),
        "Review",
        f"{pending} review(s) waiting" if pending else "No review waiting",
        count=pending,
    )


def _asset_rows(
    sources: Sequence[RegisteredSource],
    overview: OperationsOverview,
    attention: Sequence[OperationsMonitorAttention],
    runs: Sequence[AnalysisRun],
    surfaces: dict[str, AcquisitionTelemetrySurface],
) -> tuple[OperationsMonitorAsset, ...]:
    asset_ids = {source.asset_id for source in sources}
    asset_ids.update(run.asset_id for run in runs)
    asset_ids.update(item.asset_id for item in attention if item.asset_id is not None)

    reviews_by_asset: dict[str, int] = {}
    for review in overview.review_summaries:
        if review.status != FindingReviewStatus.CLOSED:
            asset_id = review.finding.asset_id
            reviews_by_asset[asset_id] = reviews_by_asset.get(asset_id, 0) + 1

    health_by_source = {item.source_id: item for item in overview.source_health_assessments}
    rows = []
    for asset_id in sorted(asset_ids):
        asset_sources = tuple(source for source in sources if source.asset_id == asset_id)
        asset_health = tuple(
            health_by_source[source.source_id]
            for source in asset_sources
            if source.source_id in health_by_source
        )
        source_statuses = tuple(
            _source_status(item, surfaces.get(item.source_id)) for item in asset_health
        )
        status = _aggregate_asset_status(source_statuses, bool(asset_sources))
        source_ids = {source.source_id for source in asset_sources}
        last_data = max(
            (
                _latest_source_data_at(item, surfaces.get(item.source_id))
                for item in asset_health
            ),
            default=None,
        )
        latest_analysis = max(
            (run.completed_at for run in runs if run.asset_id == asset_id),
            default=None,
        )
        rows.append(
            OperationsMonitorAsset(
                asset_id=asset_id,
                status=status,
                source_count=len(asset_sources),
                last_data_at=last_data,
                latest_analysis_at=latest_analysis,
                pending_review_count=reviews_by_asset.get(asset_id, 0),
                attention_count=sum(item.asset_id == asset_id for item in attention),
            )
        )
        del source_ids
    return tuple(rows)


def _monitor_attention(
    queue: OperationsAttentionQueue,
    sources: dict[str, RegisteredSource],
    health: dict[str, SourceHealthAssessment],
    surfaces: dict[str, AcquisitionTelemetrySurface],
    runtime: WindowAnalysisRunnerTelemetry | None,
    timeout: timedelta,
    as_of: datetime,
) -> tuple[OperationsMonitorAttention, ...]:
    values: list[OperationsMonitorAttention] = []
    source_kinds = {
        AttentionKind.SOURCE_ERROR,
        AttentionKind.NO_RECEIPT,
        AttentionKind.STALE,
    }
    for item in queue.items:
        if item.kind in source_kinds and item.source_id is not None:
            source_health = health.get(item.source_id)
            surface = surfaces.get(item.source_id)
            if (
                source_health is not None
                and surface is not None
                and _source_status(source_health, surface) == OperationsMonitorStatus.RUNNING
            ):
                continue
        values.append(_project_existing_attention(item, sources))

    for source_id, surface in surfaces.items():
        source = sources[source_id]
        for component, title in (
            (AcquisitionFailureComponent.OPCUA_WORKER, "Collection needs attention"),
            (AcquisitionFailureComponent.HISTORY_WRITER, "History storage needs attention"),
            (
                AcquisitionFailureComponent.WINDOW_COORDINATOR,
                "Analysis input preparation needs attention",
            ),
        ):
            failure = _current_failure(surface, component)
            if failure is None:
                continue
            values.append(
                OperationsMonitorAttention(
                    attention_id=f"runtime:{component.value}:{source_id}",
                    status=OperationsMonitorStatus.ERROR,
                    title=title,
                    detail=failure.detail,
                    occurred_at=failure.occurred_at,
                    asset_id=source.asset_id,
                )
            )

    if runtime is not None:
        if runtime.state == WindowAnalysisRunnerState.FAILED:
            values.append(
                OperationsMonitorAttention(
                    attention_id="analysis-service:failed",
                    status=OperationsMonitorStatus.ERROR,
                    title="Analysis service stopped on an error",
                    detail=runtime.last_failure or "Analysis service failed",
                    occurred_at=runtime.last_failure_at,
                )
            )
        elif (
            runtime.state == WindowAnalysisRunnerState.RUNNING
            and as_of - runtime.heartbeat_at > timeout
        ):
            values.append(
                OperationsMonitorAttention(
                    attention_id="analysis-service:delayed",
                    status=OperationsMonitorStatus.DELAYED,
                    title="Analysis service is not updating",
                    detail="The latest analysis-service heartbeat is delayed.",
                    occurred_at=runtime.heartbeat_at,
                )
            )

    deduplicated = {item.attention_id: item for item in values}
    return tuple(sorted(deduplicated.values(), key=_attention_sort_key))


def _project_existing_attention(
    item: AttentionItem,
    sources: dict[str, RegisteredSource],
) -> OperationsMonitorAttention:
    asset_id = None if item.asset_identity is None else item.asset_identity.asset_id
    if asset_id is None and item.source_id in sources:
        asset_id = sources[item.source_id].asset_id
    if item.kind == AttentionKind.STALE:
        status = OperationsMonitorStatus.DELAYED
        title = "Data is delayed"
    elif item.kind == AttentionKind.REVIEW_REQUIRED:
        status = OperationsMonitorStatus.NEEDS_ATTENTION
        title = (
            "Review waiting"
            if item.handling_state == AttentionHandlingState.UNHANDLED
            else "Review in progress"
        )
    elif item.kind == AttentionKind.DATA_QUALITY_ISSUE:
        status = OperationsMonitorStatus.NEEDS_ATTENTION
        title = "Data quality needs review"
    elif item.kind == AttentionKind.SYSTEM_STATE_ERROR:
        status = OperationsMonitorStatus.ERROR
        title = "System state is unavailable"
    elif item.kind == AttentionKind.SOURCE_ERROR:
        status = OperationsMonitorStatus.ERROR
        title = "Source data flow failed"
    else:
        status = OperationsMonitorStatus.NEEDS_ATTENTION
        title = "Source is waiting for data"
    detail = item.detail or item.kind.value.replace("_", " ").lower()
    return OperationsMonitorAttention(
        attention_id=f"existing:{item.attention_id}",
        status=status,
        title=title,
        detail=detail,
        occurred_at=item.occurred_at,
        asset_id=asset_id,
    )


def _source_status(
    health: SourceHealthAssessment,
    surface: AcquisitionTelemetrySurface | None,
) -> OperationsMonitorStatus:
    if surface is not None:
        if _current_failure(surface, AcquisitionFailureComponent.OPCUA_WORKER) is not None:
            return OperationsMonitorStatus.ERROR
        session = surface.source.session
        flow = surface.source.flow
        if session is not None and session.state == OpcUaPersistentSessionState.CONNECTED:
            if flow is not None and flow.accepted_event_count > 0:
                return OperationsMonitorStatus.RUNNING
            return OperationsMonitorStatus.WAITING
    if health.data_flow_state == SourceDataFlowState.SOURCE_ERROR:
        return OperationsMonitorStatus.ERROR
    if health.data_flow_state == SourceDataFlowState.STALE:
        return OperationsMonitorStatus.DELAYED
    if health.data_flow_state == SourceDataFlowState.NO_RECEIPT:
        return OperationsMonitorStatus.WAITING
    if health.data_flow_state == SourceDataFlowState.FRESH:
        return OperationsMonitorStatus.RUNNING
    if health.data_flow_state == SourceDataFlowState.INACTIVE:
        return OperationsMonitorStatus.STOPPED
    if health.data_flow_state == SourceDataFlowState.FRESHNESS_NOT_CONFIGURED:
        return OperationsMonitorStatus.RUNNING
    return OperationsMonitorStatus.UNAVAILABLE


def _latest_source_data_at(
    health: SourceHealthAssessment,
    surface: AcquisitionTelemetrySurface | None,
) -> datetime | None:
    values = []
    if health.latest_received_at is not None:
        values.append(health.latest_received_at)
    if (
        surface is not None
        and surface.source.flow is not None
        and surface.source.flow.last_received_at is not None
    ):
        values.append(surface.source.flow.last_received_at)
    return max(values, default=None)


def _current_failure(
    surface: AcquisitionTelemetrySurface,
    component: AcquisitionFailureComponent,
) -> AcquisitionFailureTelemetry | None:
    failure = surface.source.failure
    if failure is None or failure.component != component:
        return None
    if component == AcquisitionFailureComponent.OPCUA_WORKER:
        session = surface.source.session
        if (
            session is not None
            and session.state == OpcUaPersistentSessionState.CONNECTED
            and session.state_changed_at > failure.occurred_at
        ):
            return None
    elif component == AcquisitionFailureComponent.HISTORY_WRITER:
        history = surface.source.history
        if history is not None and history.acknowledged_at > failure.occurred_at:
            return None
    else:
        window = surface.source.window
        if window is not None and window.updated_at > failure.occurred_at:
            return None
    return failure


def _aggregate_asset_status(
    statuses: Sequence[OperationsMonitorStatus],
    has_source: bool,
) -> OperationsMonitorStatus:
    if OperationsMonitorStatus.ERROR in statuses:
        return OperationsMonitorStatus.ERROR
    if OperationsMonitorStatus.DELAYED in statuses:
        return OperationsMonitorStatus.DELAYED
    if OperationsMonitorStatus.RUNNING in statuses:
        return OperationsMonitorStatus.RUNNING
    if OperationsMonitorStatus.WAITING in statuses:
        return OperationsMonitorStatus.WAITING
    if has_source:
        return OperationsMonitorStatus.STOPPED
    return OperationsMonitorStatus.UNAVAILABLE


def _activities(
    attention: Sequence[OperationsMonitorAttention],
    runs: Sequence[AnalysisRun],
    *,
    limit: int,
) -> tuple[OperationsActivityItem, ...]:
    values = [
        OperationsActivityItem(
            activity_id=f"analysis:{run.analysis_run_id}",
            kind=OperationsActivityKind.ANALYSIS_COMPLETED,
            occurred_at=run.completed_at,
            title="Analysis completed",
            asset_id=run.asset_id,
            detail=", ".join(run.capability_ids) or "analysis result recorded",
        )
        for run in runs
    ]
    for item in attention:
        if item.occurred_at is None:
            continue
        values.append(
            OperationsActivityItem(
                activity_id=f"attention:{item.attention_id}",
                kind=OperationsActivityKind.ATTENTION,
                occurred_at=item.occurred_at,
                title=item.title,
                asset_id=item.asset_id,
                detail=item.detail,
            )
        )
    return tuple(sorted(values, key=_activity_sort_key)[:limit])


def _validate_global_spool_snapshot(
    surfaces: Sequence[AcquisitionTelemetrySurface],
) -> None:
    if not surfaces:
        return
    expected = surfaces[0].spool
    if any(surface.spool != expected for surface in surfaces[1:]):
        raise ValueError("acquisition surfaces must share one global spool snapshot")


def _attention_sort_key(
    item: OperationsMonitorAttention,
) -> tuple[int, float, str]:
    status_rank = {
        OperationsMonitorStatus.ERROR: 0,
        OperationsMonitorStatus.NEEDS_ATTENTION: 1,
        OperationsMonitorStatus.DELAYED: 2,
    }[item.status]
    occurred_rank = float("inf") if item.occurred_at is None else -item.occurred_at.timestamp()
    return status_rank, occurred_rank, item.attention_id


def _activity_sort_key(item: OperationsActivityItem) -> tuple[float, str]:
    return -item.occurred_at.timestamp(), item.activity_id


def _require_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _require_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
