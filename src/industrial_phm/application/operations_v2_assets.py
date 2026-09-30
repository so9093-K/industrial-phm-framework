"""Asset workspace projections for the Operations V2 migration."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from industrial_phm.application.asset_detail import AssetDetail, AssetEvidenceEventKind
from industrial_phm.application.maintenance_review import (
    FindingReviewStatus,
    finding_review_status,
)
from industrial_phm.application.measurement_history import HistoryAssetSummary
from industrial_phm.application.operational import OperationalAnalysisResult
from industrial_phm.application.operations_v2 import (
    OperationsMonitorAsset,
    OperationsMonitorStatus,
)
from industrial_phm.application.source_health import SourceDataFlowState
from industrial_phm.application.source_registration import SourceType


@dataclass(frozen=True, slots=True)
class AssetWorkspaceSource:
    source_id: str
    name: str
    source_type: SourceType
    status: OperationsMonitorStatus
    last_data_at: datetime | None
    measurement_point_id: str | None
    channel_count: int

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id")
        _require_text(self.name, "name")
        if not isinstance(self.source_type, SourceType):
            raise ValueError("source_type must be a SourceType")
        if not isinstance(self.status, OperationsMonitorStatus):
            raise ValueError("status must be an OperationsMonitorStatus")
        if self.last_data_at is not None:
            _require_aware(self.last_data_at, "last_data_at")
        if self.measurement_point_id is not None:
            _require_text(self.measurement_point_id, "measurement_point_id")
        _require_non_negative_int(self.channel_count, "channel_count")


@dataclass(frozen=True, slots=True)
class AssetWorkspaceAnalysis:
    analysis_run_id: str
    capability_id: str
    evidence_id: str
    source_id: str
    measurement_point_id: str | None
    observed_start_at: datetime
    observed_end_at: datetime
    completed_at: datetime
    data_quality: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.analysis_run_id, "analysis_run_id"),
            (self.capability_id, "capability_id"),
            (self.evidence_id, "evidence_id"),
            (self.source_id, "source_id"),
            (self.data_quality, "data_quality"),
        ):
            _require_text(value, field_name)
        if self.measurement_point_id is not None:
            _require_text(self.measurement_point_id, "measurement_point_id")
        for value, field_name in (
            (self.observed_start_at, "observed_start_at"),
            (self.observed_end_at, "observed_end_at"),
            (self.completed_at, "completed_at"),
        ):
            _require_aware(value, field_name)
        if self.observed_start_at > self.observed_end_at:
            raise ValueError("observed_start_at must not be after observed_end_at")


@dataclass(frozen=True, slots=True)
class AssetWorkspaceEvent:
    event_id: str
    kind: AssetEvidenceEventKind
    title: str
    occurred_at: datetime | None
    detail: str | None

    def __post_init__(self) -> None:
        _require_text(self.event_id, "event_id")
        if not isinstance(self.kind, AssetEvidenceEventKind):
            raise ValueError("kind must be an AssetEvidenceEventKind")
        _require_text(self.title, "title")
        if self.occurred_at is not None:
            _require_aware(self.occurred_at, "occurred_at")
        if self.detail is not None:
            _require_text(self.detail, "detail")


@dataclass(frozen=True, slots=True)
class AssetWorkspaceReview:
    finding_id: str
    analysis_run_id: str
    capability_id: str
    observed_at: datetime
    status: FindingReviewStatus
    latest_event_at: datetime | None

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.finding_id, "finding_id"),
            (self.analysis_run_id, "analysis_run_id"),
            (self.capability_id, "capability_id"),
        ):
            _require_text(value, field_name)
        _require_aware(self.observed_at, "observed_at")
        if not isinstance(self.status, FindingReviewStatus):
            raise ValueError("status must be a FindingReviewStatus")
        if self.latest_event_at is not None:
            _require_aware(self.latest_event_at, "latest_event_at")


@dataclass(frozen=True, slots=True)
class AssetWorkspaceView:
    asset_id: str
    status: OperationsMonitorStatus
    source_count: int
    attention_count: int
    last_data_at: datetime | None
    history_start_at: datetime | None
    history_end_at: datetime | None
    history_measurement_count: int
    history_channels: Sequence[str]
    analyses: Sequence[AssetWorkspaceAnalysis]
    reviews: Sequence[AssetWorkspaceReview]
    sources: Sequence[AssetWorkspaceSource]
    events: Sequence[AssetWorkspaceEvent]

    def __post_init__(self) -> None:
        _require_text(self.asset_id, "asset_id")
        if not isinstance(self.status, OperationsMonitorStatus):
            raise ValueError("status must be an OperationsMonitorStatus")
        for field_name in (
            "source_count",
            "attention_count",
            "history_measurement_count",
        ):
            _require_non_negative_int(getattr(self, field_name), field_name)
        for field_name in ("last_data_at", "history_start_at", "history_end_at"):
            value = getattr(self, field_name)
            if value is not None:
                _require_aware(value, field_name)
        if (
            self.history_start_at is not None
            and self.history_end_at is not None
            and self.history_start_at > self.history_end_at
        ):
            raise ValueError("history_start_at must not be after history_end_at")

        channels = tuple(self.history_channels)
        if any(not isinstance(item, str) or not item.strip() for item in channels):
            raise ValueError("history_channels must contain non-empty strings")
        if channels != tuple(sorted(set(channels))):
            raise ValueError("history_channels must be unique and sorted")

        analyses = tuple(self.analyses)
        reviews = tuple(self.reviews)
        sources = tuple(self.sources)
        events = tuple(self.events)
        if any(not isinstance(item, AssetWorkspaceAnalysis) for item in analyses):
            raise ValueError("analyses contains an unsupported value")
        if any(not isinstance(item, AssetWorkspaceReview) for item in reviews):
            raise ValueError("reviews contains an unsupported value")
        if any(not isinstance(item, AssetWorkspaceSource) for item in sources):
            raise ValueError("sources contains an unsupported value")
        if any(not isinstance(item, AssetWorkspaceEvent) for item in events):
            raise ValueError("events contains an unsupported value")

        if analyses != tuple(
            sorted(
                analyses,
                key=lambda item: (-item.completed_at.timestamp(), item.analysis_run_id),
            )
        ):
            raise ValueError("analyses must use newest-first deterministic order")
        if reviews != tuple(
            sorted(
                reviews,
                key=lambda item: (-item.observed_at.timestamp(), item.finding_id),
            )
        ):
            raise ValueError("reviews must use newest-first deterministic order")
        if sources != tuple(sorted(sources, key=lambda item: item.source_id)):
            raise ValueError("sources must use source-id order")
        if events != tuple(sorted(events, key=_event_sort_key)):
            raise ValueError("events must use newest-first deterministic order")

        object.__setattr__(self, "history_channels", channels)
        object.__setattr__(self, "analyses", analyses)
        object.__setattr__(self, "reviews", reviews)
        object.__setattr__(self, "sources", sources)
        object.__setattr__(self, "events", events)

    @property
    def latest_analysis_at(self) -> datetime | None:
        return None if not self.analyses else self.analyses[0].completed_at

    @property
    def open_review_count(self) -> int:
        return sum(item.status != FindingReviewStatus.CLOSED for item in self.reviews)


def build_asset_workspace_view(
    *,
    asset_id: str,
    detail: AssetDetail,
    analysis_results: Sequence[OperationalAnalysisResult],
    monitor_asset: OperationsMonitorAsset | None = None,
    history_summary: HistoryAssetSummary | None = None,
    history_channels: Sequence[str] = (),
) -> AssetWorkspaceView:
    """Translate one asset's evidence into the V2 workspace vocabulary."""

    _require_text(asset_id, "asset_id")
    if not isinstance(detail, AssetDetail):
        raise ValueError("detail must be an AssetDetail")
    if detail.asset_identity.asset_id != asset_id:
        raise ValueError("detail must match asset_id")
    if monitor_asset is not None:
        if not isinstance(monitor_asset, OperationsMonitorAsset):
            raise ValueError("monitor_asset must be an OperationsMonitorAsset")
        if monitor_asset.asset_id != asset_id:
            raise ValueError("monitor_asset must match asset_id")
    if history_summary is not None:
        if not isinstance(history_summary, HistoryAssetSummary):
            raise ValueError("history_summary must be a HistoryAssetSummary")
        if history_summary.asset_id != asset_id:
            raise ValueError("history_summary must match asset_id")

    result_values = tuple(analysis_results)
    if any(not isinstance(item, OperationalAnalysisResult) for item in result_values):
        raise ValueError("analysis_results must contain OperationalAnalysisResult values")
    asset_results = tuple(item for item in result_values if item.run.asset_id == asset_id)

    analyses = tuple(
        sorted(
            (
                AssetWorkspaceAnalysis(
                    analysis_run_id=item.run.analysis_run_id,
                    capability_id=item.evidence.capability_id,
                    evidence_id=item.evidence.evidence_id,
                    source_id=item.run.source_id,
                    measurement_point_id=item.run.measurement_point_id,
                    observed_start_at=item.run.observed_start_at,
                    observed_end_at=item.run.observed_end_at,
                    completed_at=item.run.completed_at,
                    data_quality=item.run.data_quality.state.value,
                )
                for item in asset_results
            ),
            key=lambda item: (-item.completed_at.timestamp(), item.analysis_run_id),
        )
    )

    review_events_by_finding = {
        finding.finding_id: tuple(
            event for event in detail.review_events if event.finding_id == finding.finding_id
        )
        for finding in detail.findings
    }
    reviews = tuple(
        sorted(
            (
                AssetWorkspaceReview(
                    finding_id=finding.finding_id,
                    analysis_run_id=finding.analysis_run_id,
                    capability_id=finding.capability_id,
                    observed_at=finding.observed_at,
                    status=finding_review_status(
                        review_events_by_finding[finding.finding_id],
                        finding.finding_id,
                    ),
                    latest_event_at=max(
                        (
                            event.recorded_at
                            for event in review_events_by_finding[finding.finding_id]
                        ),
                        default=None,
                    ),
                )
                for finding in detail.findings
            ),
            key=lambda item: (-item.observed_at.timestamp(), item.finding_id),
        )
    )

    sources = tuple(
        sorted(
            (
                AssetWorkspaceSource(
                    source_id=context.source.source_id,
                    name=context.source.name,
                    source_type=context.source.source_type,
                    status=_source_status(context.health.data_flow_state),
                    last_data_at=context.health.latest_received_at,
                    measurement_point_id=context.source.measurement_point_id,
                    channel_count=len(context.source.channel_identities),
                )
                for context in detail.source_contexts
            ),
            key=lambda item: item.source_id,
        )
    )

    events = tuple(
        sorted(
            (
                AssetWorkspaceEvent(
                    event_id=event.event_id,
                    kind=event.kind,
                    title=_event_title(event.kind),
                    occurred_at=event.event_at,
                    detail=event.detail,
                )
                for event in (*detail.timeline.events, *detail.timeline.unplaced_events)
            ),
            key=_event_sort_key,
        )
    )

    if monitor_asset is None:
        status = _aggregate_source_status(tuple(item.status for item in sources))
        attention_count = 0
        last_data_at = max(
            (item.last_data_at for item in sources if item.last_data_at is not None),
            default=None,
        )
    else:
        status = monitor_asset.status
        attention_count = monitor_asset.attention_count
        last_data_at = monitor_asset.last_data_at

    channels = tuple(sorted(set(history_channels)))
    return AssetWorkspaceView(
        asset_id=asset_id,
        status=status,
        source_count=len(sources),
        attention_count=attention_count,
        last_data_at=last_data_at,
        history_start_at=None if history_summary is None else history_summary.start_at,
        history_end_at=None if history_summary is None else history_summary.end_at,
        history_measurement_count=(
            0 if history_summary is None else history_summary.measurement_count
        ),
        history_channels=channels,
        analyses=analyses,
        reviews=reviews,
        sources=sources,
        events=events,
    )


def _source_status(state: SourceDataFlowState) -> OperationsMonitorStatus:
    if state == SourceDataFlowState.SOURCE_ERROR:
        return OperationsMonitorStatus.ERROR
    if state == SourceDataFlowState.STALE:
        return OperationsMonitorStatus.DELAYED
    if state == SourceDataFlowState.NO_RECEIPT:
        return OperationsMonitorStatus.WAITING
    if state == SourceDataFlowState.FRESH:
        return OperationsMonitorStatus.RUNNING
    if state == SourceDataFlowState.INACTIVE:
        return OperationsMonitorStatus.STOPPED
    return OperationsMonitorStatus.UNAVAILABLE


def _aggregate_source_status(
    statuses: Sequence[OperationsMonitorStatus],
) -> OperationsMonitorStatus:
    if OperationsMonitorStatus.ERROR in statuses:
        return OperationsMonitorStatus.ERROR
    if OperationsMonitorStatus.DELAYED in statuses:
        return OperationsMonitorStatus.DELAYED
    if OperationsMonitorStatus.RUNNING in statuses:
        return OperationsMonitorStatus.RUNNING
    if OperationsMonitorStatus.WAITING in statuses:
        return OperationsMonitorStatus.WAITING
    if OperationsMonitorStatus.STOPPED in statuses:
        return OperationsMonitorStatus.STOPPED
    return OperationsMonitorStatus.UNAVAILABLE


def _event_title(kind: AssetEvidenceEventKind) -> str:
    return {
        AssetEvidenceEventKind.SOURCE_REGISTERED: "Source added",
        AssetEvidenceEventKind.SOURCE_LIFECYCLE_CHANGED: "Source setting changed",
        AssetEvidenceEventKind.SOURCE_OBSERVED: "Source data observed",
        AssetEvidenceEventKind.PLATFORM_RECEIVED: "Data received",
        AssetEvidenceEventKind.OBSERVATION_WINDOW: "Observation recorded",
        AssetEvidenceEventKind.ANALYSIS_EXECUTED: "Analysis completed",
        AssetEvidenceEventKind.CAPABILITY_EVIDENCE: "Analysis evidence recorded",
        AssetEvidenceEventKind.FINDING_OBSERVED: "Review requested",
        AssetEvidenceEventKind.REVIEW_ACTION: "Review updated",
    }[kind]


def _event_sort_key(item: AssetWorkspaceEvent) -> tuple[int, float, str]:
    if item.occurred_at is None:
        return 1, 0.0, item.event_id
    return 0, -item.occurred_at.timestamp(), item.event_id


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
        raise ValueError(f"{field_name} must be timezone-aware")
