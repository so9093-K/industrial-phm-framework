"""Application contracts for the persistent OPC UA acquisition worker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from industrial_phm.application.opcua_persistent import (
    OpcUaPersistentSessionEvidence,
)


@runtime_checkable
class OpcUaPersistentSessionEvidenceSink(Protocol):
    """Write boundary for observed persistent-session state transitions."""

    def record_session_evidence(self, evidence: OpcUaPersistentSessionEvidence) -> None:
        """Record one already validated session transition."""
        ...


class InMemoryOpcUaPersistentSessionEvidenceSink:
    """In-memory reference sink for tests and embedded callers."""

    def __init__(self) -> None:
        self._items: list[OpcUaPersistentSessionEvidence] = []

    def record_session_evidence(self, evidence: OpcUaPersistentSessionEvidence) -> None:
        if not isinstance(evidence, OpcUaPersistentSessionEvidence):
            raise ValueError("evidence must be OpcUaPersistentSessionEvidence")
        self._items.append(evidence)

    def list_session_evidence(self) -> tuple[OpcUaPersistentSessionEvidence, ...]:
        return tuple(self._items)


@dataclass(frozen=True, slots=True)
class OpcUaAcquisitionWorkerResult:
    """Finite summary returned only after one worker exits normally."""

    source_id: str
    started_at: datetime
    stopped_at: datetime
    accepted_event_count: int
    replayed_event_count: int
    queue_overflow_count: int

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        _validate_aware_datetime(self.started_at, "started_at")
        _validate_aware_datetime(self.stopped_at, "stopped_at")
        if self.stopped_at < self.started_at:
            raise ValueError("stopped_at must not be before started_at")
        for field_name in (
            "accepted_event_count",
            "replayed_event_count",
            "queue_overflow_count",
        ):
            _validate_non_negative_int(getattr(self, field_name), field_name)
        if self.replayed_event_count > self.accepted_event_count:
            raise ValueError("replayed_event_count must not exceed accepted_event_count")


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
