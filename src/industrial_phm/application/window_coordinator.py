"""Contracts for rebuilding/finalizing observation windows from durable history."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
from numbers import Real
from typing import Protocol, runtime_checkable

from industrial_phm.application.observation_window import (
    DurableObservationWindow,
    ObservationWindowEventDisposition,
    ObservationWindowIngestResult,
)
from industrial_phm.application.opcua_persistent import OpcUaPersistentDataChangeEvent


@dataclass(frozen=True, slots=True)
class ObservationWindowCoordinatorPolicy:
    """Fixed aligned event-time windows with bounded out-of-orderness watermark."""

    window_duration_seconds: float = 60.0
    allowed_lateness_seconds: float = 5.0
    max_buffered_events: int = 10_000
    max_future_skew_seconds: float = 30.0
    poll_interval_seconds: float = 0.5
    alignment_origin: datetime = field(
        default_factory=lambda: datetime(1970, 1, 1, tzinfo=UTC)
    )

    def __post_init__(self) -> None:
        _validate_positive_finite(self.window_duration_seconds, "window_duration_seconds")
        _validate_non_negative_finite(
            self.allowed_lateness_seconds,
            "allowed_lateness_seconds",
        )
        _validate_positive_int(self.max_buffered_events, "max_buffered_events")
        _validate_non_negative_finite(
            self.max_future_skew_seconds,
            "max_future_skew_seconds",
        )
        _validate_positive_finite(self.poll_interval_seconds, "poll_interval_seconds")
        _validate_aware_datetime(self.alignment_origin, "alignment_origin")


@dataclass(frozen=True, slots=True)
class ObservationWindowCoordinatorCycleResult:
    """One deterministic rebuild/finalization pass over durable source history."""

    source_id: str
    finalized_windows: Sequence[DurableObservationWindow]
    event_results: Sequence[ObservationWindowIngestResult]
    watermark: datetime | None
    active_window_count: int

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        finalized = tuple(self.finalized_windows)
        if any(not isinstance(item, DurableObservationWindow) for item in finalized):
            raise ValueError("finalized_windows must contain DurableObservationWindow values")
        if tuple(sorted(finalized, key=lambda item: (item.window_start, item.window_id))) != finalized:
            raise ValueError("finalized_windows must use deterministic window order")

        event_results = tuple(self.event_results)
        if any(not isinstance(item, ObservationWindowIngestResult) for item in event_results):
            raise ValueError("event_results must contain ObservationWindowIngestResult values")
        if self.watermark is not None:
            _validate_aware_datetime(self.watermark, "watermark")
        _validate_non_negative_int(self.active_window_count, "active_window_count")
        object.__setattr__(self, "finalized_windows", finalized)
        object.__setattr__(self, "event_results", event_results)

    @property
    def historical_event_count(self) -> int:
        return len(self.event_results)

    @property
    def finalized_window_count(self) -> int:
        return len(self.finalized_windows)

    def disposition_count(self, disposition: ObservationWindowEventDisposition) -> int:
        if not isinstance(disposition, ObservationWindowEventDisposition):
            raise ValueError("disposition must be ObservationWindowEventDisposition")
        return sum(item.disposition == disposition for item in self.event_results)



@dataclass(frozen=True, slots=True)
class ContinuousObservationWindowCoordinatorResult:
    """Finite summary returned after an explicitly stopped continuous coordinator."""

    source_id: str
    started_at: datetime
    stopped_at: datetime
    cycle_count: int
    last_watermark: datetime | None

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        _validate_aware_datetime(self.started_at, "started_at")
        _validate_aware_datetime(self.stopped_at, "stopped_at")
        if self.stopped_at < self.started_at:
            raise ValueError("stopped_at must not be before started_at")
        _validate_non_negative_int(self.cycle_count, "cycle_count")
        if self.last_watermark is not None:
            _validate_aware_datetime(self.last_watermark, "last_watermark")


@runtime_checkable
class OpcUaHistoricalEventReader(Protocol):
    """Durable raw-event reader required by the window coordinator."""

    def query_opcua_events(
        self,
        source_id: str,
    ) -> tuple[OpcUaPersistentDataChangeEvent, ...]:
        """Return source events in deterministic durable-ingestion order."""
        ...


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")


def _validate_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")


def _validate_positive_int(value: int, field_name: str) -> None:
    _validate_non_negative_int(value, field_name)
    if value < 1:
        raise ValueError(f"{field_name} must be at least 1")


def _validate_non_negative_finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ValueError(f"{field_name} must be a finite number")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")


def _validate_positive_finite(value: float, field_name: str) -> None:
    _validate_non_negative_finite(value, field_name)
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
