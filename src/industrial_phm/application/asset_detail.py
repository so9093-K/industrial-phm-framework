"""Asset-centric operational detail and evidence timeline projections."""

from __future__ import annotations

from collections.abc import Hashable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from industrial_phm.application.asset_identity import AssetIdentity
from industrial_phm.application.maintenance_review import (
    FindingReviewAction,
    FindingReviewEvent,
)
from industrial_phm.application.observation import AssetObservationSummary
from industrial_phm.application.operational import AnalysisRun, OperationalFinding
from industrial_phm.application.operations_overview import OperationsOverview
from industrial_phm.application.source_health import SourceHealthAssessment
from industrial_phm.application.source_lifecycle import SourceLifecycleState
from industrial_phm.application.source_registration import RegisteredSource


class AssetEvidenceEventKind(StrEnum):
    """Recorded operational event kinds shown in an asset evidence timeline."""

    SOURCE_REGISTERED = "SOURCE_REGISTERED"
    SOURCE_LIFECYCLE_CHANGED = "SOURCE_LIFECYCLE_CHANGED"
    SOURCE_OBSERVED = "SOURCE_OBSERVED"
    PLATFORM_RECEIVED = "PLATFORM_RECEIVED"
    OBSERVATION_WINDOW = "OBSERVATION_WINDOW"
    ANALYSIS_EXECUTED = "ANALYSIS_EXECUTED"
    CAPABILITY_EVIDENCE = "CAPABILITY_EVIDENCE"
    FINDING_OBSERVED = "FINDING_OBSERVED"
    REVIEW_ACTION = "REVIEW_ACTION"


class AssetEvidenceTimeBasis(StrEnum):
    """Clock/semantic basis for one recorded timeline timestamp."""

    REGISTRATION_TIME = "registration-time"
    LIFECYCLE_TIME = "lifecycle-time"
    SOURCE_TIME = "source-time"
    PLATFORM_RECEIPT_TIME = "platform-receipt-time"
    OBSERVATION_TIME = "observation-time"
    ANALYSIS_EXECUTION_TIME = "analysis-execution-time"
    FINDING_OBSERVED_TIME = "finding-observed-time"
    REVIEW_RECORDED_TIME = "review-recorded-time"


_EXPECTED_TIME_BASIS = {
    AssetEvidenceEventKind.SOURCE_REGISTERED: AssetEvidenceTimeBasis.REGISTRATION_TIME,
    AssetEvidenceEventKind.SOURCE_LIFECYCLE_CHANGED: AssetEvidenceTimeBasis.LIFECYCLE_TIME,
    AssetEvidenceEventKind.SOURCE_OBSERVED: AssetEvidenceTimeBasis.SOURCE_TIME,
    AssetEvidenceEventKind.PLATFORM_RECEIVED: AssetEvidenceTimeBasis.PLATFORM_RECEIPT_TIME,
    AssetEvidenceEventKind.OBSERVATION_WINDOW: AssetEvidenceTimeBasis.OBSERVATION_TIME,
    AssetEvidenceEventKind.ANALYSIS_EXECUTED: AssetEvidenceTimeBasis.ANALYSIS_EXECUTION_TIME,
    AssetEvidenceEventKind.CAPABILITY_EVIDENCE: AssetEvidenceTimeBasis.ANALYSIS_EXECUTION_TIME,
    AssetEvidenceEventKind.FINDING_OBSERVED: AssetEvidenceTimeBasis.FINDING_OBSERVED_TIME,
    AssetEvidenceEventKind.REVIEW_ACTION: AssetEvidenceTimeBasis.REVIEW_RECORDED_TIME,
}


_EVENT_ORDER = {
    AssetEvidenceEventKind.SOURCE_REGISTERED: 0,
    AssetEvidenceEventKind.SOURCE_LIFECYCLE_CHANGED: 1,
    AssetEvidenceEventKind.SOURCE_OBSERVED: 2,
    AssetEvidenceEventKind.OBSERVATION_WINDOW: 3,
    AssetEvidenceEventKind.PLATFORM_RECEIVED: 4,
    AssetEvidenceEventKind.ANALYSIS_EXECUTED: 5,
    AssetEvidenceEventKind.CAPABILITY_EVIDENCE: 6,
    AssetEvidenceEventKind.FINDING_OBSERVED: 7,
    AssetEvidenceEventKind.REVIEW_ACTION: 8,
}


@dataclass(frozen=True, slots=True)
class AssetSourceContext:
    """Current registered source and source-health evidence for one asset."""

    source: RegisteredSource
    health: SourceHealthAssessment

    def __post_init__(self) -> None:
        if not isinstance(self.source, RegisteredSource):
            raise ValueError("source must be a RegisteredSource")
        if not isinstance(self.health, SourceHealthAssessment):
            raise ValueError("health must be a SourceHealthAssessment")
        if self.source.source_id != self.health.source_id:
            raise ValueError("source and health must share one source_id")


@dataclass(frozen=True, slots=True)
class AssetEvidenceEvent:
    """One evidence event without collapsing distinct clock semantics."""

    event_id: str
    kind: AssetEvidenceEventKind
    time_basis: AssetEvidenceTimeBasis
    event_at: datetime | None
    source_id: str | None = None
    measurement_point_id: str | None = None
    analysis_run_id: str | None = None
    capability_id: str | None = None
    finding_id: str | None = None
    review_action: FindingReviewAction | None = None
    lifecycle_state: SourceLifecycleState | None = None
    window_start_at: datetime | None = None
    window_end_at: datetime | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.event_id, "event_id")
        if not isinstance(self.kind, AssetEvidenceEventKind):
            raise ValueError("kind must be an AssetEvidenceEventKind")
        if not isinstance(self.time_basis, AssetEvidenceTimeBasis):
            raise ValueError("time_basis must be an AssetEvidenceTimeBasis")
        expected_time_basis = _EXPECTED_TIME_BASIS[self.kind]
        if self.time_basis != expected_time_basis:
            raise ValueError(
                f"{self.kind.value} event requires {expected_time_basis.value} time basis"
            )
        if self.event_at is not None and not isinstance(self.event_at, datetime):
            raise ValueError("event_at must be a datetime when provided")
        for identifier_value, identifier_field in (
            (self.source_id, "source_id"),
            (self.measurement_point_id, "measurement_point_id"),
            (self.analysis_run_id, "analysis_run_id"),
            (self.capability_id, "capability_id"),
            (self.finding_id, "finding_id"),
            (self.detail, "detail"),
        ):
            if identifier_value is not None:
                _validate_identifier(identifier_value, identifier_field)
        if self.review_action is not None and not isinstance(
            self.review_action,
            FindingReviewAction,
        ):
            raise ValueError("review_action must be FindingReviewAction when provided")
        if self.lifecycle_state is not None and not isinstance(
            self.lifecycle_state,
            SourceLifecycleState,
        ):
            raise ValueError("lifecycle_state must be SourceLifecycleState when provided")
        for timestamp_value, timestamp_field in (
            (self.window_start_at, "window_start_at"),
            (self.window_end_at, "window_end_at"),
        ):
            if timestamp_value is not None and not isinstance(timestamp_value, datetime):
                raise ValueError(f"{timestamp_field} must be a datetime when provided")
        if self.window_start_at is not None and self.window_end_at is not None:
            if not _same_timezone_awareness(
                self.window_start_at,
                self.window_end_at,
            ):
                raise ValueError("observation window timestamps must share timezone awareness")
            if self.window_start_at > self.window_end_at:
                raise ValueError("window_start_at must not be after window_end_at")

    @property
    def comparable_at(self) -> datetime | None:
        """Return event time only when it is timezone-aware and cross-event comparable."""
        if self.event_at is None or self.event_at.utcoffset() is None:
            return None
        return self.event_at


@dataclass(frozen=True, slots=True)
class AssetEvidenceTimeline:
    """Comparable chronological events plus evidence whose time cannot be aligned."""

    events: Sequence[AssetEvidenceEvent]
    unplaced_events: Sequence[AssetEvidenceEvent]

    def __post_init__(self) -> None:
        events = tuple(self.events)
        unplaced = tuple(self.unplaced_events)
        all_events = (*events, *unplaced)
        if any(not isinstance(item, AssetEvidenceEvent) for item in all_events):
            raise ValueError("timeline values must contain only AssetEvidenceEvent values")
        ids = tuple(item.event_id for item in all_events)
        if len(set(ids)) != len(ids):
            raise ValueError("timeline event_id values must be unique")
        if any(item.comparable_at is None for item in events):
            raise ValueError("events must contain only timezone-aware comparable timestamps")
        if any(item.comparable_at is not None for item in unplaced):
            raise ValueError("unplaced_events must contain only missing or naive timestamps")
        if tuple(sorted(events, key=_comparable_event_sort_key)) != events:
            raise ValueError("events must use chronological evidence ordering")
        if tuple(sorted(unplaced, key=lambda item: item.event_id)) != unplaced:
            raise ValueError("unplaced_events must use deterministic event_id ordering")
        object.__setattr__(self, "events", events)
        object.__setattr__(self, "unplaced_events", unplaced)


@dataclass(frozen=True, slots=True)
class AssetDetail:
    """Asset-scoped operational evidence without automatic condition semantics."""

    asset_identity: AssetIdentity
    source_contexts: Sequence[AssetSourceContext]
    latest_observations: Sequence[AssetObservationSummary]
    analysis_runs: Sequence[AnalysisRun]
    findings: Sequence[OperationalFinding]
    review_events: Sequence[FindingReviewEvent]
    timeline: AssetEvidenceTimeline

    def __post_init__(self) -> None:
        if not isinstance(self.asset_identity, AssetIdentity):
            raise ValueError("asset_identity must be an AssetIdentity")
        source_contexts = tuple(self.source_contexts)
        observations = tuple(self.latest_observations)
        runs = tuple(self.analysis_runs)
        findings = tuple(self.findings)
        review_events = tuple(self.review_events)

        if any(not isinstance(item, AssetSourceContext) for item in source_contexts):
            raise ValueError("source_contexts must contain only AssetSourceContext values")
        if any(not isinstance(item, AssetObservationSummary) for item in observations):
            raise ValueError("latest_observations must contain only AssetObservationSummary values")
        if any(not isinstance(item, AnalysisRun) for item in runs):
            raise ValueError("analysis_runs must contain only AnalysisRun values")
        if any(not isinstance(item, OperationalFinding) for item in findings):
            raise ValueError("findings must contain only OperationalFinding values")
        if any(not isinstance(item, FindingReviewEvent) for item in review_events):
            raise ValueError("review_events must contain only FindingReviewEvent values")
        if not isinstance(self.timeline, AssetEvidenceTimeline):
            raise ValueError("timeline must be an AssetEvidenceTimeline")

        asset_id = self.asset_identity.asset_id
        if any(item.source.asset_id != asset_id for item in source_contexts):
            raise ValueError("source_contexts must belong to asset_identity")
        if any(item.asset_id != asset_id for item in observations):
            raise ValueError("latest_observations must belong to asset_identity")
        if any(item.asset_id != asset_id for item in runs):
            raise ValueError("analysis_runs must belong to asset_identity")
        if any(item.asset_id != asset_id for item in findings):
            raise ValueError("findings must belong to asset_identity")

        _reject_duplicate(
            tuple(item.source.source_id for item in source_contexts),
            "source_contexts source_id",
        )
        _reject_duplicate(
            tuple((item.source_id, item.measurement_point_id) for item in observations),
            "latest_observations source/measurement point",
        )
        _reject_duplicate(
            tuple(item.analysis_run_id for item in runs),
            "analysis_runs analysis_run_id",
        )
        _reject_duplicate(
            tuple(item.finding_id for item in findings),
            "findings finding_id",
        )
        _reject_duplicate(
            tuple(item.event_id for item in review_events),
            "review_events event_id",
        )

        finding_ids = {item.finding_id for item in findings}
        if any(item.finding_id not in finding_ids for item in review_events):
            raise ValueError("review_events must reference a finding in this asset detail")

        object.__setattr__(self, "source_contexts", source_contexts)
        object.__setattr__(self, "latest_observations", observations)
        object.__setattr__(self, "analysis_runs", runs)
        object.__setattr__(self, "findings", findings)
        object.__setattr__(self, "review_events", review_events)


def list_operational_asset_identities(
    *,
    sources: Sequence[RegisteredSource] = (),
    latest_observations: Sequence[AssetObservationSummary] = (),
    analysis_runs: Sequence[AnalysisRun] = (),
    findings: Sequence[OperationalFinding] = (),
) -> tuple[AssetIdentity, ...]:
    """Return deterministic asset identity union from current and historical evidence."""
    source_values = tuple(sources)
    observation_values = tuple(latest_observations)
    run_values = tuple(analysis_runs)
    finding_values = tuple(findings)
    if any(not isinstance(item, RegisteredSource) for item in source_values):
        raise ValueError("sources must contain only RegisteredSource values")
    if any(not isinstance(item, AssetObservationSummary) for item in observation_values):
        raise ValueError("latest_observations must contain only AssetObservationSummary values")
    if any(not isinstance(item, AnalysisRun) for item in run_values):
        raise ValueError("analysis_runs must contain only AnalysisRun values")
    if any(not isinstance(item, OperationalFinding) for item in finding_values):
        raise ValueError("findings must contain only OperationalFinding values")

    asset_ids = {item.asset_id for item in source_values}
    asset_ids.update(item.asset_id for item in observation_values)
    asset_ids.update(item.asset_id for item in run_values)
    asset_ids.update(item.asset_id for item in finding_values)
    return tuple(AssetIdentity(asset_id) for asset_id in sorted(asset_ids))


def build_asset_detail(
    asset_identity: AssetIdentity,
    *,
    sources: Sequence[RegisteredSource],
    overview: OperationsOverview,
    latest_observations: Sequence[AssetObservationSummary] = (),
    analysis_runs: Sequence[AnalysisRun] = (),
    findings: Sequence[OperationalFinding] = (),
    review_events: Sequence[FindingReviewEvent] = (),
) -> AssetDetail:
    """Build one asset-scoped detail and multi-clock evidence timeline."""
    if not isinstance(asset_identity, AssetIdentity):
        raise ValueError("asset_identity must be an AssetIdentity")
    if not isinstance(overview, OperationsOverview):
        raise ValueError("overview must be an OperationsOverview")

    source_values = tuple(sources)
    if any(not isinstance(item, RegisteredSource) for item in source_values):
        raise ValueError("sources must contain only RegisteredSource values")
    _reject_duplicate(tuple(item.source_id for item in source_values), "sources source_id")

    health_by_source = {item.source_id: item for item in overview.source_health_assessments}
    asset_sources = tuple(
        sorted(
            (
                AssetSourceContext(
                    source=source,
                    health=_require_source_health(source.source_id, health_by_source),
                )
                for source in source_values
                if source.asset_id == asset_identity.asset_id
            ),
            key=lambda item: item.source.source_id,
        )
    )

    observation_values = tuple(latest_observations)
    if any(not isinstance(item, AssetObservationSummary) for item in observation_values):
        raise ValueError("latest_observations must contain only AssetObservationSummary values")
    asset_observations = tuple(
        sorted(
            (item for item in observation_values if item.asset_id == asset_identity.asset_id),
            key=lambda item: (item.source_id, item.measurement_point_id or ""),
        )
    )

    run_values = tuple(analysis_runs)
    if any(not isinstance(item, AnalysisRun) for item in run_values):
        raise ValueError("analysis_runs must contain only AnalysisRun values")
    asset_runs = tuple(
        sorted(
            (item for item in run_values if item.asset_id == asset_identity.asset_id),
            key=lambda item: (item.completed_at, item.analysis_run_id),
        )
    )

    finding_values = tuple(findings)
    if any(not isinstance(item, OperationalFinding) for item in finding_values):
        raise ValueError("findings must contain only OperationalFinding values")
    asset_findings = tuple(
        sorted(
            (item for item in finding_values if item.asset_id == asset_identity.asset_id),
            key=lambda item: (item.observed_at, item.finding_id),
        )
    )
    asset_finding_ids = {item.finding_id for item in asset_findings}

    event_values = tuple(review_events)
    if any(not isinstance(item, FindingReviewEvent) for item in event_values):
        raise ValueError("review_events must contain only FindingReviewEvent values")
    asset_review_events = tuple(
        sorted(
            (item for item in event_values if item.finding_id in asset_finding_ids),
            key=lambda item: (item.recorded_at, item.event_id),
        )
    )

    timeline = _build_asset_timeline(
        source_contexts=asset_sources,
        observations=asset_observations,
        analysis_runs=asset_runs,
        findings=asset_findings,
        review_events=asset_review_events,
    )
    return AssetDetail(
        asset_identity=asset_identity,
        source_contexts=asset_sources,
        latest_observations=asset_observations,
        analysis_runs=asset_runs,
        findings=asset_findings,
        review_events=asset_review_events,
        timeline=timeline,
    )


def _build_asset_timeline(
    *,
    source_contexts: Sequence[AssetSourceContext],
    observations: Sequence[AssetObservationSummary],
    analysis_runs: Sequence[AnalysisRun],
    findings: Sequence[OperationalFinding],
    review_events: Sequence[FindingReviewEvent],
) -> AssetEvidenceTimeline:
    values: list[AssetEvidenceEvent] = []

    for context in source_contexts:
        source = context.source
        health = context.health
        values.append(
            AssetEvidenceEvent(
                event_id=f"source:{source.source_id}:registered",
                kind=AssetEvidenceEventKind.SOURCE_REGISTERED,
                time_basis=AssetEvidenceTimeBasis.REGISTRATION_TIME,
                event_at=source.registered_at,
                source_id=source.source_id,
                measurement_point_id=source.measurement_point_id,
            )
        )
        values.append(
            AssetEvidenceEvent(
                event_id=f"source:{source.source_id}:lifecycle",
                kind=AssetEvidenceEventKind.SOURCE_LIFECYCLE_CHANGED,
                time_basis=AssetEvidenceTimeBasis.LIFECYCLE_TIME,
                event_at=health.lifecycle.changed_at,
                source_id=source.source_id,
                measurement_point_id=source.measurement_point_id,
                lifecycle_state=health.lifecycle.state,
                detail=health.lifecycle.detail,
            )
        )
        if health.receipt is not None:
            values.append(
                AssetEvidenceEvent(
                    event_id=f"source:{source.source_id}:observed",
                    kind=AssetEvidenceEventKind.SOURCE_OBSERVED,
                    time_basis=AssetEvidenceTimeBasis.SOURCE_TIME,
                    event_at=health.receipt.observed_at,
                    source_id=source.source_id,
                    measurement_point_id=source.measurement_point_id,
                )
            )
            values.append(
                AssetEvidenceEvent(
                    event_id=f"source:{source.source_id}:received",
                    kind=AssetEvidenceEventKind.PLATFORM_RECEIVED,
                    time_basis=AssetEvidenceTimeBasis.PLATFORM_RECEIPT_TIME,
                    event_at=health.receipt.received_at,
                    source_id=source.source_id,
                    measurement_point_id=source.measurement_point_id,
                )
            )

    for observation in observations:
        values.append(
            AssetEvidenceEvent(
                event_id=_observation_event_id(observation),
                kind=AssetEvidenceEventKind.OBSERVATION_WINDOW,
                time_basis=AssetEvidenceTimeBasis.OBSERVATION_TIME,
                event_at=observation.observed_end_at,
                source_id=observation.source_id,
                measurement_point_id=observation.measurement_point_id,
                window_start_at=observation.observed_start_at,
                window_end_at=observation.observed_end_at,
            )
        )

    for run in analysis_runs:
        values.append(
            AssetEvidenceEvent(
                event_id=f"analysis:{run.analysis_run_id}:executed",
                kind=AssetEvidenceEventKind.ANALYSIS_EXECUTED,
                time_basis=AssetEvidenceTimeBasis.ANALYSIS_EXECUTION_TIME,
                event_at=run.completed_at,
                source_id=run.source_id,
                measurement_point_id=run.measurement_point_id,
                analysis_run_id=run.analysis_run_id,
            )
        )
        for capability_id in run.capability_ids:
            values.append(
                AssetEvidenceEvent(
                    event_id=(f"analysis:{run.analysis_run_id}:capability:{capability_id}"),
                    kind=AssetEvidenceEventKind.CAPABILITY_EVIDENCE,
                    time_basis=AssetEvidenceTimeBasis.ANALYSIS_EXECUTION_TIME,
                    event_at=run.completed_at,
                    source_id=run.source_id,
                    measurement_point_id=run.measurement_point_id,
                    analysis_run_id=run.analysis_run_id,
                    capability_id=capability_id,
                )
            )

    for finding in findings:
        values.append(
            AssetEvidenceEvent(
                event_id=f"finding:{finding.finding_id}:observed",
                kind=AssetEvidenceEventKind.FINDING_OBSERVED,
                time_basis=AssetEvidenceTimeBasis.FINDING_OBSERVED_TIME,
                event_at=finding.observed_at,
                measurement_point_id=finding.measurement_point_id,
                analysis_run_id=finding.analysis_run_id,
                capability_id=finding.capability_id,
                finding_id=finding.finding_id,
            )
        )

    for event in review_events:
        values.append(
            AssetEvidenceEvent(
                event_id=f"review:{event.event_id}",
                kind=AssetEvidenceEventKind.REVIEW_ACTION,
                time_basis=AssetEvidenceTimeBasis.REVIEW_RECORDED_TIME,
                event_at=event.recorded_at,
                finding_id=event.finding_id,
                review_action=event.action,
                detail=event.note or None,
            )
        )

    comparable = tuple(
        sorted(
            (item for item in values if item.comparable_at is not None),
            key=_comparable_event_sort_key,
        )
    )
    unplaced = tuple(
        sorted(
            (item for item in values if item.comparable_at is None),
            key=lambda item: item.event_id,
        )
    )
    return AssetEvidenceTimeline(events=comparable, unplaced_events=unplaced)


def _require_source_health(
    source_id: str,
    health_by_source: dict[str, SourceHealthAssessment],
) -> SourceHealthAssessment:
    try:
        return health_by_source[source_id]
    except KeyError as error:
        raise ValueError(
            f"registered source is missing from current Operations overview: {source_id}"
        ) from error


def _observation_event_id(observation: AssetObservationSummary) -> str:
    point = observation.measurement_point_id or "-"
    return f"observation:{observation.source_id}:{point}"


def _comparable_event_sort_key(
    item: AssetEvidenceEvent,
) -> tuple[datetime, int, str]:
    comparable = item.comparable_at
    if comparable is None:
        raise AssertionError("comparable timeline event unexpectedly lacks aware time")
    return comparable, _EVENT_ORDER[item.kind], item.event_id


def _same_timezone_awareness(left: datetime, right: datetime) -> bool:
    return (left.utcoffset() is None) == (right.utcoffset() is None)


def _reject_duplicate[T: Hashable](values: Sequence[T], label: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{label} values must be unique")


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
