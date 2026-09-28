"""Durable acquisition-spool contracts for continuous source delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from industrial_phm.application.opcua_persistent import (
    OpcUaEventTimePolicy,
    OpcUaPersistentDataChangeEvent,
)
from industrial_phm.application.source_subscription import RegisteredOpcUaDataChangeEvent


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
    payload_bytes: int

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
        _validate_positive_int(self.payload_bytes, "payload_bytes")

    @property
    def event_count(self) -> int:
        return len(self.events)


@dataclass(frozen=True, slots=True)
class AcquisitionSpoolPendingStats:
    """Unassigned durable deliveries available for the next micro-batch."""

    event_count: int
    payload_bytes: int
    oldest_accepted_at: datetime | None

    def __post_init__(self) -> None:
        _validate_non_negative_int(self.event_count, "event_count")
        _validate_non_negative_int(self.payload_bytes, "payload_bytes")
        if self.event_count == 0:
            if self.payload_bytes != 0 or self.oldest_accepted_at is not None:
                raise ValueError("empty pending stats require zero bytes and no oldest_accepted_at")
            return
        if self.payload_bytes < 1:
            raise ValueError("non-empty pending stats require payload_bytes >= 1")
        if self.oldest_accepted_at is None:
            raise ValueError("non-empty pending stats require oldest_accepted_at")
        _validate_aware_datetime(self.oldest_accepted_at, "oldest_accepted_at")


@runtime_checkable
class AcquisitionSpool(Protocol):
    """Crash-safe OPC UA delivery boundary for the first continuous-runtime slice."""

    def get_last_connection_epoch(self, source_id: str) -> int:
        """Return the last durable connection epoch reserved for one source."""
        ...

    def reserve_next_connection_epoch(
        self,
        source_id: str,
        *,
        expected_previous_epoch: int,
    ) -> int:
        """Atomically reserve and return the next source connection epoch."""
        ...

    def accept_opcua_event(
        self,
        event: RegisteredOpcUaDataChangeEvent,
        *,
        connection_epoch: int,
        event_index: int,
        accepted_at: datetime,
        event_time_policy: OpcUaEventTimePolicy | None = None,
    ) -> OpcUaPersistentDataChangeEvent:
        """Durably accept one local delivery and return the stored persistent event."""
        ...

    def assign_next_batch(
        self,
        *,
        batch_id: str,
        max_events: int,
        max_bytes: int | None = None,
        created_at: datetime,
    ) -> AcquisitionSpoolBatch | None:
        """Reuse the active batch or assign oldest pending events to a stable batch.

        max_bytes is a soft bound for a batch: a single oversized first event is still
        assigned so the spool cannot deadlock on one durable delivery.
        """
        ...

    def pending_unassigned_stats(self) -> AcquisitionSpoolPendingStats:
        """Return count/bytes/oldest acceptance for events not in the active batch."""
        ...

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


def _validate_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")


def _validate_positive_int(value: int, field_name: str) -> None:
    _validate_non_negative_int(value, field_name)
    if value < 1:
        raise ValueError(f"{field_name} must be at least 1")
