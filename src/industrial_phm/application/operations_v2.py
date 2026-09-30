"""User-question-oriented Operations V2 monitor read models.

The V2 monitor deliberately translates existing operational evidence into a small
operator-facing vocabulary. It does not create asset-health, fault, severity, alarm,
or maintenance verdicts.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from industrial_phm.application.acquisition_telemetry import (
    AcquisitionFailureComponent,
    AcquisitionTelemetrySurface,
)
from industrial_phm.application.maintenance_review import FindingReviewStatus
from industrial_phm.application.opcua_persistent import OpcUaPersistentSessionState
from industrial_phm.application.operational import AnalysisRun
from industrial_phm.application.operations_attention import OperationsAttentionQueue
from industrial_phm.application.operations_overview import OperationsOverview
from industrial_phm.application.source_health import SourceDataFlowState
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
            if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count < 0:
                raise ValueError("count must be a non-negative integer")


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
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        for field_name in ("last_data_at", "latest_analysis_at"):
            value = getattr(self, field_name)
            if value is not None:
                _require_aware(value, field_name)


class OperationsActivityKind(StrEnum):
    ANALYSIS_COMPLETED = "analysis-completed"
    ATTENTION = "attention"
    REVIEW = "review"


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
    attention_count: int
    unhandled_attention_count: int
    activities: Sequence[OperationsActivityItem]

    def __post_init__(self) -> None:
        _require_aware(self.assessed_at, "assessed_at")
        stages = tuple(self.stages)
        assets = tuple(self.assets)
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
        if any(not isinstance(item, OperationsActivityItem) for item in activities):
            raise ValueError("activities must contain OperationsActivityItem values")
        expected_activities = tuple(
            sorted(
                activities,
                key=lambda item: (-item.occurred_at.timestamp(), item.activity_id),
            )
        )
        if activities != expected_activities:
            raise ValueError("activities must use newest-first deterministic ordering")
        for field_name in ("attention_count", "unhandled_attention_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.unhandled_attention_count > self.attention_count:
            raise ValueError("unhandled attention must not exceed total attention")
        object.__setattr__(self, "stages", stages)
        object.__setattr__(self, "assets", assets)
        object.__setattr__(self, "activities", activities)


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
    if not isinstance(analysis_heartbeat_timeout, timedelta) or analysis_heartbeat_timeout <= timedelta():
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

    runs = tuple(analysis_runs)
    if any(not isinstance(item, AnalysisRun) for item in runs):
        raise ValueError("analysis_runs must contain only AnalysisRun values")
    run_ids = tuple(item.analysis_run_id for item in runs)
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("analysis_runs must contain unique analysis ids")

    stages = (
        _source_stage(overview),
        _collection_stage(overview, surface_values),
        _storage_stage(surface_values),
        _analysis_stage(surface_values, analysis_runtime, analysis_heartbeat_timeout, as_of),
        _review_stage(overview),
    )
    assets = _asset_rows(source_values, overview, attention, runs)
    activities = _activities(attention, runs, limit=12)
    return OperationsMonitorView(
        assessed_at=as_of,
        stages=stages,
        assets=assets,
        attention_count=len(attention.items),
        unhandled_attention_count=attention.unhandled_count,
        activities=activities,
    )


def _source_stage(overview: OperationsOverview) -> OperationsMonitorStage:
    total = overview.registered_source_count
    if total == 0:
        return OperationsMonitorStage(
            OperationsMonitorStageKind.SOURCE,
            OperationsMonitorStatus.WAITING,
            "Sources",
            "No source configured",
            count=0,
        )
    error_count = overview.source_data_flow_count(SourceDataFlowState.SOURCE_ERROR)
    stale_count = overview.source_data_flow_count(SourceDataFlowState.STALE)
    no_receipt = overview.source_data_flow_count(SourceDataFlowState.NO_RECEIPT)
    fresh = overview.source_data_flow_count(SourceDataFlowState.FRESH)
    if error_count:
        status = OperationsMonitorStatus.NEEDS_ATTENTION
        summary = f"{error_count} source(s) need attention"
    elif stale_count:
        status = OperationsMonitorStatus.DELAYED
        summary = f"{stale_count} source(s) delayed"
    elif fresh:
        status = OperationsMonitorStatus.RUNNING
        summary = f"{fresh} of {total} source(s) receiving recent data"
    elif no_receipt:
        status = OperationsMonitorStatus.WAITING
        summary = f"{no_receipt} active source(s) waiting for data"
    elif overview.active_source_count == 0:
        status = OperationsMonitorStatus.STOPPED
        summary = "No source is enabled"
    else:
        status = OperationsMonitorStatus.UNAVAILABLE
        summary = "Current source timing is unavailable"
    latest = max(
        (
            item.latest_received_at
            for item in overview.source_health_assessments
            if item.latest_received_at is not None
        ),
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
        surface.source.failure is not None
        and surface.source.failure.component == AcquisitionFailureComponent.OPCUA_WORKER
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
        surface.source.failure is not None
        and surface.source.failure.component == AcquisitionFailureComponent.HISTORY_WRITER
        for surface in surfaces
    )
    pending = sum(surface.spool.pending_event_count for surface in surfaces)
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
        surface.source.failure is not None
        and surface.source.failure.component == AcquisitionFailureComponent.WINDOW_COORDINATOR
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
    attention: OperationsAttentionQueue,
    runs: Sequence[AnalysisRun],
) -> tuple[OperationsMonitorAsset, ...]:
    asset_ids = {source.config.asset_id for source in sources}
    asset_ids.update(run.asset_id for run in runs)
    asset_ids.update(
        item.asset_identity.asset_id
        for item in attention.items
        if item.asset_identity is not None
    )
    reviews_by_asset: dict[str, int] = {}
    for review in overview.review_summaries:
        if review.status != FindingReviewStatus.CLOSED:
            asset_id = review.finding.asset_id
            reviews_by_asset[asset_id] = reviews_by_asset.get(asset_id, 0) + 1

    health_by_source = {item.source_id: item for item in overview.source_health_assessments}
    rows = []
    for asset_id in sorted(asset_ids):
        asset_sources = tuple(
            source for source in sources if source.config.asset_id == asset_id
        )
        asset_health = tuple(
            health_by_source[source.source_id]
            for source in asset_sources
            if source.source_id in health_by_source
        )
        statuses = tuple(item.data_flow_state for item in asset_health)
        if SourceDataFlowState.SOURCE_ERROR in statuses:
            status = OperationsMonitorStatus.ERROR
        elif SourceDataFlowState.STALE in statuses:
            status = OperationsMonitorStatus.DELAYED
        elif SourceDataFlowState.NO_RECEIPT in statuses:
            status = OperationsMonitorStatus.WAITING
        elif SourceDataFlowState.FRESH in statuses:
            status = OperationsMonitorStatus.RUNNING
        elif asset_sources:
            status = OperationsMonitorStatus.STOPPED
        else:
            status = OperationsMonitorStatus.UNAVAILABLE

        source_ids = {source.source_id for source in asset_sources}
        attention_count = sum(
            (
                item.asset_identity is not None
                and item.asset_identity.asset_id == asset_id
            )
            or (item.source_id is not None and item.source_id in source_ids)
            for item in attention.items
        )
        last_data = max(
            (
                item.latest_received_at
                for item in asset_health
                if item.latest_received_at is not None
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
                attention_count=attention_count,
            )
        )
    return tuple(rows)


def _activities(
    attention: OperationsAttentionQueue,
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
    for item in attention.items:
        if item.occurred_at is None:
            continue
        asset_id = None if item.asset_identity is None else item.asset_identity.asset_id
        values.append(
            OperationsActivityItem(
                activity_id=f"attention:{item.attention_id}",
                kind=OperationsActivityKind.ATTENTION,
                occurred_at=item.occurred_at,
                title="Needs attention",
                asset_id=asset_id,
                detail=item.kind.value,
            )
        )
    ordered = sorted(
        values,
        key=lambda item: (-item.occurred_at.timestamp(), item.activity_id),
    )
    return tuple(ordered[:limit])


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _require_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
