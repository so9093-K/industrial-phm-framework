"""Durable acquisition-spool contracts for continuous source delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from industrial_phm.application.opcua_persistent import OpcUaPersistentDataChangeEvent


class AcquisitionSpoolFullError(RuntimeError):
    """Raised when the bounded durable spool cannot accept another delivery."""


class AcquisitionSpoolStateError(RuntimeError):
    """Raised when durable spool state violates the single-writer contract."""


class AcquisitionSpoolFormatError(ValueError):
    """Raised when persisted spool payload/state is malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class AcquisitionSpoolBatch:
    """Stable pending delivery batch retained until downstream acknowledgement."""

    batch_id: str
    created_at: datetime
    events: tuple[OpcUaPersistentDataChangeEvent, ...]

    def __post_init__(self) -> None:
        _validate_identifier(self.batch_id, "batch_id")
        _validate_aware_datetime(self.created_at, "created_at")
        if not isinstance(self.events, tuple):
            raise ValueError("events must be a tuple")
        if not self.events:
            raise ValueError("events must not be empty")
        if any(not isinstance(event, OpcUaPersistentDataChangeEvent) for event in self.events):
            raise ValueError("events must contain OpcUaPersistentDataChangeEvent values")
        identities = tuple(event.local_delivery_identity for event in self.events)
        if len(set(identities)) != len(identities):
            raise ValueError("events must have distinct local delivery identities")

    @property
    def event_count(self) -> int:
        return len(self.events)


@runtime_checkable
class AcquisitionSpool(Protocol):
    """Crash-safe delivery boundary between source workers and historical storage."""

    def pending_event_count(self) -> int:
        """Return all durable events not yet acknowledged downstream."""
        ...

    def get_active_batch(self) -> AcquisitionSpoolBatch | None:
        """Return the currently assigned unacknowledged batch, if one exists."""
        ...

    def acknowledge_batch(self, batch_id: str, *, acknowledged_at: datetime) -> int:
        """Remove one successfully committed downstream batch and return its event count."""
        ...


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
