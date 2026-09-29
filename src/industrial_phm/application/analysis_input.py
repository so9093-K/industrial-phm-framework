"""Analysis input shapes shared by history and finalized-window sources.

History analysis reads ChannelObservation groups at a fixed DuckLake snapshot.
Live analysis projects a finalized window's accepted events to the same shape
(ADR-0008); the window range is never re-queried from history, so late arrivals
cannot change what was analyzed.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from industrial_phm.application.measurement_semantics import (
    ChannelSemanticCandidate,
    serialize_channel_semantic_binding,
)
from industrial_phm.application.observation_window import DurableObservationWindow
from industrial_phm.application.opcua_persistent import OpcUaPersistentDataChangeEvent

WINDOW_INPUT_DIGEST_VERSION = "window-accepted-events-v1"


@dataclass(frozen=True, slots=True)
class ChannelObservation:
    """One (source, point, channel, event time) group of analysis input."""

    source_id: str
    measurement_point_id: str | None
    channel_id: str
    event_at: datetime
    value: float | None
    conflicting: bool
    source_quality_good: bool
    observed_property: str | None
    scope: str | None
    unit: str | None
    semantic_version: str | None


@dataclass(frozen=True, slots=True)
class WindowInputReference:
    """What a live analysis read: one finalized window's accepted event set."""

    window_id: str
    source_id: str
    asset_id: str
    measurement_point_id: str | None
    window_start: datetime
    window_end: datetime
    watermark_at_close: datetime
    finalized_at: datetime
    accepted_event_count: int
    rejected_event_count: int
    expected_channel_ids: tuple[str, ...]
    missing_channel_ids: tuple[str, ...]
    input_digest: str
    digest_version: str = WINDOW_INPUT_DIGEST_VERSION

    def __post_init__(self) -> None:
        for name in ("window_id", "source_id", "asset_id", "input_digest", "digest_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        for name in ("window_start", "window_end", "watermark_at_close", "finalized_at"):
            if getattr(self, name).utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.window_end <= self.window_start:
            raise ValueError("window_end must be after window_start")
        for name in ("accepted_event_count", "rejected_event_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        object.__setattr__(self, "expected_channel_ids", tuple(self.expected_channel_ids))
        object.__setattr__(self, "missing_channel_ids", tuple(self.missing_channel_ids))

    @property
    def start_at(self) -> datetime:
        return self.window_start

    @property
    def end_at(self) -> datetime:
        return self.window_end


def _event_fact(event: OpcUaPersistentDataChangeEvent) -> dict[str, object]:
    observation = event.event.notification.observation
    binding = event.event.semantic_binding
    event_at = event.event_time.event_at
    return {
        "delivery": list(event.local_delivery_identity),
        "channel_id": observation.channel_id,
        "event_at": None if event_at is None else event_at.astimezone(UTC).isoformat(),
        # Numeric type is not evidence: an Int32 delivery and its float round trip
        # through durable window storage must digest identically.
        "value": None if observation.value is None else float(observation.value),
        "status_good": observation.status_good,
        "semantic_binding": (
            None if binding is None else serialize_channel_semantic_binding(binding)
        ),
    }


def window_input_digest(events: Sequence[OpcUaPersistentDataChangeEvent]) -> str:
    """SHA-256 of the accepted events that can change an analysis result."""
    encoded = json.dumps(
        [_event_fact(event) for event in events],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def window_input_reference(window: DurableObservationWindow) -> WindowInputReference:
    return WindowInputReference(
        window_id=window.window_id,
        source_id=window.source_id,
        asset_id=window.asset_id,
        measurement_point_id=window.measurement_point_id,
        window_start=window.window_start,
        window_end=window.window_end,
        watermark_at_close=window.watermark_at_close,
        finalized_at=window.finalized_at,
        accepted_event_count=window.accepted_event_count,
        rejected_event_count=window.rejected_event_count,
        expected_channel_ids=tuple(window.expected_channel_ids),
        missing_channel_ids=window.missing_channel_ids,
        input_digest=window_input_digest(tuple(window.events)),
    )


def window_channel_observations(
    window: DurableObservationWindow,
) -> tuple[ChannelObservation, ...]:
    """Project accepted events to the same shape history analysis reads.

    Several accepted deliveries of one channel at one event time (for example a
    replay with a new connection epoch) are flagged conflicting when their values
    differ, never averaged. A group whose deliveries disagree on semantics carries
    none. Meaning comes from each event's own snapshot, not current registration.
    """
    grouped: dict[tuple[str, datetime], list[OpcUaPersistentDataChangeEvent]] = defaultdict(list)
    for event in window.events:
        event_at = event.event_time.event_at
        if event_at is None:  # rejected by the window; kept for type safety
            continue
        grouped[(event.channel_id, event_at.astimezone(UTC))].append(event)
    observations = []
    for (channel_id, event_at), events in sorted(grouped.items(), key=lambda item: item[0][::-1]):
        values = {e.event.notification.observation.value for e in events}
        bindings = {e.event.semantic_binding for e in events}
        binding = next(iter(bindings)) if len(bindings) == 1 else None
        definition = None if binding is None else binding.definition
        observations.append(
            ChannelObservation(
                source_id=window.source_id,
                measurement_point_id=window.measurement_point_id,
                channel_id=channel_id,
                event_at=event_at,
                value=next(iter(values)) if len(values) == 1 else None,
                conflicting=len(values) > 1,
                source_quality_good=all(
                    e.event.notification.observation.status_good for e in events
                ),
                observed_property=None if definition is None else definition.observed_property,
                scope=None if definition is None else definition.scope,
                unit=None if definition is None else definition.unit,
                semantic_version=None if binding is None else binding.version,
            )
        )
    return tuple(observations)


def window_channel_candidates(
    window: DurableObservationWindow,
) -> tuple[ChannelSemanticCandidate, ...]:
    """Interpretations the accepted events carry, for semantic-role selection."""
    counts: dict[tuple[str, str, str | None, str | None, str], int] = defaultdict(int)
    for observation in window_channel_observations(window):
        if observation.observed_property is None or observation.semantic_version is None:
            continue
        key = (
            observation.channel_id,
            observation.observed_property,
            observation.scope,
            observation.unit,
            observation.semantic_version,
        )
        counts[key] += 1
    return tuple(
        ChannelSemanticCandidate(
            measurement_point_id=window.measurement_point_id,
            channel_id=channel_id,
            observed_property=prop,
            scope=scope,
            unit=unit,
            semantic_version=version,
            observation_count=count,
        )
        for (channel_id, prop, scope, unit, version), count in sorted(counts.items())
    )
