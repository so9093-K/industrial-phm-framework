"""Maintenance review work queue for Operations V2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from industrial_phm.application.maintenance_review import (
    FindingReviewAction,
    FindingReviewEvent,
    FindingReviewStatus,
    finding_review_status,
)
from industrial_phm.application.operational import OperationalFinding


@dataclass(frozen=True, slots=True)
class MaintenanceReviewTimelineItem:
    event_id: str
    action: FindingReviewAction
    recorded_at: datetime
    note: str

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("event_id must not be empty")
        if not isinstance(self.action, FindingReviewAction):
            raise ValueError("action must be a FindingReviewAction")
        if self.recorded_at.utcoffset() is None:
            raise ValueError("recorded_at must be timezone-aware")
        if not isinstance(self.note, str):
            raise ValueError("note must be a string")


@dataclass(frozen=True, slots=True)
class MaintenanceQueueItem:
    finding_id: str
    analysis_run_id: str
    asset_id: str
    capability_id: str
    measurement_point_id: str | None
    requested_at: datetime
    status: FindingReviewStatus
    latest_activity_at: datetime | None
    note_count: int
    timeline: Sequence[MaintenanceReviewTimelineItem]

    def __post_init__(self) -> None:
        for value, name in (
            (self.finding_id, "finding_id"),
            (self.analysis_run_id, "analysis_run_id"),
            (self.asset_id, "asset_id"),
            (self.capability_id, "capability_id"),
        ):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.measurement_point_id is not None and not self.measurement_point_id.strip():
            raise ValueError("measurement_point_id must not be empty")
        if self.requested_at.utcoffset() is None:
            raise ValueError("requested_at must be timezone-aware")
        if self.latest_activity_at is not None and self.latest_activity_at.utcoffset() is None:
            raise ValueError("latest_activity_at must be timezone-aware")
        if not isinstance(self.status, FindingReviewStatus):
            raise ValueError("status must be a FindingReviewStatus")
        if self.note_count < 0:
            raise ValueError("note_count must be non-negative")
        timeline = tuple(self.timeline)
        if any(not isinstance(item, MaintenanceReviewTimelineItem) for item in timeline):
            raise ValueError("timeline contains unsupported values")
        if timeline != tuple(sorted(timeline, key=lambda item: (item.recorded_at, item.event_id))):
            raise ValueError("timeline must use append-time order")
        if self.note_count != sum(item.action == FindingReviewAction.NOTE for item in timeline):
            raise ValueError("note_count must match timeline")
        object.__setattr__(self, "timeline", timeline)


@dataclass(frozen=True, slots=True)
class MaintenanceQueueView:
    items: Sequence[MaintenanceQueueItem]

    def __post_init__(self) -> None:
        items = tuple(self.items)
        if any(not isinstance(item, MaintenanceQueueItem) for item in items):
            raise ValueError("items contains unsupported values")
        if len({item.finding_id for item in items}) != len(items):
            raise ValueError("finding_id values must be unique")
        expected = tuple(
            sorted(
                items,
                key=lambda item: (
                    _status_rank(item.status),
                    -_activity_time(item).timestamp(),
                    item.finding_id,
                ),
            )
        )
        if items != expected:
            raise ValueError("items must use workflow-first deterministic order")
        object.__setattr__(self, "items", items)

    def filter(
        self,
        *,
        status: FindingReviewStatus | None = None,
        asset_id: str | None = None,
    ) -> tuple[MaintenanceQueueItem, ...]:
        return tuple(
            item
            for item in self.items
            if (status is None or item.status == status)
            and (asset_id is None or item.asset_id == asset_id)
        )

    @property
    def asset_ids(self) -> tuple[str, ...]:
        return tuple(sorted({item.asset_id for item in self.items}))

    def count(self, status: FindingReviewStatus) -> int:
        if not isinstance(status, FindingReviewStatus):
            raise ValueError("status must be FindingReviewStatus")
        return sum(item.status == status for item in self.items)


def build_maintenance_queue(
    *,
    findings: Sequence[OperationalFinding],
    review_events: Sequence[FindingReviewEvent],
) -> MaintenanceQueueView:
    finding_values = tuple(findings)
    event_values = tuple(review_events)
    if any(not isinstance(item, OperationalFinding) for item in finding_values):
        raise ValueError("findings contains unsupported values")
    if any(not isinstance(item, FindingReviewEvent) for item in event_values):
        raise ValueError("review_events contains unsupported values")
    finding_ids = {item.finding_id for item in finding_values}
    unknown = sorted({event.finding_id for event in event_values} - finding_ids)
    if unknown:
        raise ValueError(f"review_events reference unknown findings: {unknown}")

    items: list[MaintenanceQueueItem] = []
    for finding in finding_values:
        events = tuple(event for event in event_values if event.finding_id == finding.finding_id)
        status = finding_review_status(events, finding.finding_id)
        timeline = tuple(
            MaintenanceReviewTimelineItem(
                event_id=event.event_id,
                action=event.action,
                recorded_at=event.recorded_at,
                note=event.note,
            )
            for event in events
        )
        items.append(
            MaintenanceQueueItem(
                finding_id=finding.finding_id,
                analysis_run_id=finding.analysis_run_id,
                asset_id=finding.asset_id,
                capability_id=finding.capability_id,
                measurement_point_id=finding.measurement_point_id,
                requested_at=finding.observed_at,
                status=status,
                latest_activity_at=max((event.recorded_at for event in events), default=None),
                note_count=sum(event.action == FindingReviewAction.NOTE for event in events),
                timeline=timeline,
            )
        )

    return MaintenanceQueueView(
        tuple(
            sorted(
                items,
                key=lambda item: (
                    _status_rank(item.status),
                    -_activity_time(item).timestamp(),
                    item.finding_id,
                ),
            )
        )
    )


def _status_rank(status: FindingReviewStatus) -> int:
    return {
        FindingReviewStatus.OPEN: 0,
        FindingReviewStatus.ACKNOWLEDGED: 1,
        FindingReviewStatus.CLOSED: 2,
    }[status]


def _activity_time(item: MaintenanceQueueItem) -> datetime:
    return item.latest_activity_at or item.requested_at
