"""Persistent OPC UA session and event-time contracts.

The long-lived acquisition worker now executes these semantics, while this module remains
network/runtime independent. It does not itself open connections, persist notifications,
assemble windows, or claim gap-free delivery.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite
from numbers import Real

from industrial_phm.application.source_subscription import (
    RegisteredOpcUaDataChangeEvent,
)


class OpcUaPersistentSessionState(StrEnum):
    """Observable application state of one long-lived OPC UA source session."""

    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECT_WAIT = "RECONNECT_WAIT"
    STOPPED = "STOPPED"


@dataclass(frozen=True, slots=True)
class OpcUaPersistentSessionPolicy:
    """Runtime policy for reconnect timing and bounded connector callback buffering."""

    publishing_interval_ms: float = 500.0
    queue_maxsize: int = 128
    reconnect_initial_delay_seconds: float = 1.0
    reconnect_max_delay_seconds: float = 30.0
    reconnect_backoff_multiplier: float = 2.0

    def __post_init__(self) -> None:
        _validate_positive_finite(self.publishing_interval_ms, "publishing_interval_ms")
        if isinstance(self.queue_maxsize, bool) or not isinstance(self.queue_maxsize, int):
            raise ValueError("queue_maxsize must be an integer")
        if self.queue_maxsize < 1:
            raise ValueError("queue_maxsize must be at least 1")
        _validate_positive_finite(
            self.reconnect_initial_delay_seconds,
            "reconnect_initial_delay_seconds",
        )
        _validate_positive_finite(
            self.reconnect_max_delay_seconds,
            "reconnect_max_delay_seconds",
        )
        if self.reconnect_max_delay_seconds < self.reconnect_initial_delay_seconds:
            raise ValueError("reconnect_max_delay_seconds must be at least the initial delay")
        _validate_positive_finite(
            self.reconnect_backoff_multiplier,
            "reconnect_backoff_multiplier",
        )
        if self.reconnect_backoff_multiplier < 1.0:
            raise ValueError("reconnect_backoff_multiplier must be at least 1")

    def reconnect_delay_seconds(self, reconnect_attempt_index: int) -> float:
        """Return capped backoff for a zero-based reconnect attempt index."""
        if isinstance(reconnect_attempt_index, bool) or not isinstance(
            reconnect_attempt_index, int
        ):
            raise ValueError("reconnect_attempt_index must be an integer")
        if reconnect_attempt_index < 0:
            raise ValueError("reconnect_attempt_index must not be negative")

        delay = float(self.reconnect_initial_delay_seconds)
        maximum = float(self.reconnect_max_delay_seconds)
        multiplier = float(self.reconnect_backoff_multiplier)
        for _ in range(reconnect_attempt_index):
            if delay >= maximum:
                return maximum
            delay = min(maximum, delay * multiplier)
        return delay


@dataclass(frozen=True, slots=True)
class OpcUaPersistentSessionEvidence:
    """One recorded persistent-session state transition snapshot.

    connection_epoch is a durable per-source local connection generation. It increments
    only after a successful connection and does not reset when the worker process restarts.
    reconnect_attempt_index counts retry attempts within one worker run and is never a
    server sequence.
    """

    source_id: str
    state: OpcUaPersistentSessionState
    changed_at: datetime
    connection_epoch: int = 0
    reconnect_attempt_index: int = 0
    detail: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        if not isinstance(self.state, OpcUaPersistentSessionState):
            raise ValueError("state must be an OpcUaPersistentSessionState")
        _validate_aware_datetime(self.changed_at, "changed_at")
        _validate_non_negative_int(self.connection_epoch, "connection_epoch")
        _validate_non_negative_int(
            self.reconnect_attempt_index,
            "reconnect_attempt_index",
        )
        if (
            self.state == OpcUaPersistentSessionState.DISCONNECTED
            and self.reconnect_attempt_index != 0
        ):
            raise ValueError("initial DISCONNECTED evidence requires zero reconnect attempt")
        if self.state == OpcUaPersistentSessionState.CONNECTED and self.connection_epoch < 1:
            raise ValueError("CONNECTED session evidence requires connection_epoch >= 1")
        if self.state == OpcUaPersistentSessionState.RECONNECT_WAIT and self.detail is None:
            raise ValueError("RECONNECT_WAIT session evidence requires detail")
        if self.detail is not None:
            _validate_identifier(self.detail, "detail")


_ALLOWED_SESSION_TRANSITIONS = {
    OpcUaPersistentSessionState.DISCONNECTED: {
        OpcUaPersistentSessionState.CONNECTING,
        OpcUaPersistentSessionState.STOPPED,
    },
    OpcUaPersistentSessionState.CONNECTING: {
        OpcUaPersistentSessionState.CONNECTED,
        OpcUaPersistentSessionState.RECONNECT_WAIT,
        OpcUaPersistentSessionState.STOPPED,
    },
    OpcUaPersistentSessionState.CONNECTED: {
        OpcUaPersistentSessionState.RECONNECT_WAIT,
        OpcUaPersistentSessionState.STOPPED,
    },
    OpcUaPersistentSessionState.RECONNECT_WAIT: {
        OpcUaPersistentSessionState.CONNECTING,
        OpcUaPersistentSessionState.STOPPED,
    },
    OpcUaPersistentSessionState.STOPPED: set(),
}


def validate_opcua_persistent_session_transition(
    before: OpcUaPersistentSessionEvidence,
    after: OpcUaPersistentSessionEvidence,
) -> None:
    """Validate one reconnect/session transition without executing it."""
    if not isinstance(before, OpcUaPersistentSessionEvidence):
        raise ValueError("before must be OpcUaPersistentSessionEvidence")
    if not isinstance(after, OpcUaPersistentSessionEvidence):
        raise ValueError("after must be OpcUaPersistentSessionEvidence")
    if before.source_id != after.source_id:
        raise ValueError("persistent session transition must keep the same source_id")
    if after.changed_at < before.changed_at:
        raise ValueError("persistent session changed_at must not move backwards")
    if after.state not in _ALLOWED_SESSION_TRANSITIONS[before.state]:
        raise ValueError(
            f"invalid persistent session transition: {before.state.value} -> {after.state.value}"
        )

    expected_epoch = before.connection_epoch
    if (
        before.state == OpcUaPersistentSessionState.CONNECTING
        and after.state == OpcUaPersistentSessionState.CONNECTED
    ):
        expected_epoch += 1
    if after.connection_epoch != expected_epoch:
        raise ValueError("connection_epoch must increment only on CONNECTING -> CONNECTED")

    expected_attempt = before.reconnect_attempt_index
    if (
        before.state == OpcUaPersistentSessionState.RECONNECT_WAIT
        and after.state == OpcUaPersistentSessionState.CONNECTING
    ):
        expected_attempt += 1
    if after.reconnect_attempt_index != expected_attempt:
        raise ValueError(
            "reconnect_attempt_index must increment only on RECONNECT_WAIT -> CONNECTING"
        )


class OpcUaEventTimeBasis(StrEnum):
    """Authoritative clock selected for event-time processing."""

    SOURCE_TIMESTAMP = "source-timestamp"
    SERVER_TIMESTAMP = "server-timestamp"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class OpcUaEventTimePolicy:
    """Explicit selection policy for protocol event time."""

    allow_server_timestamp_fallback: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.allow_server_timestamp_fallback, bool):
            raise ValueError("allow_server_timestamp_fallback must be boolean")


@dataclass(frozen=True, slots=True)
class OpcUaEventTimeEvidence:
    """Preserved protocol/platform timing facts for one DataChange event.

    received_at is connector callback receipt time and ingested_at is durable acceptance by
    the persistent-ingestion boundary. Neither value is silently promoted to event time.
    """

    basis: OpcUaEventTimeBasis
    source_timestamp: datetime | None
    server_timestamp: datetime | None
    received_at: datetime
    ingested_at: datetime
    event_at: datetime | None

    def __post_init__(self) -> None:
        if not isinstance(self.basis, OpcUaEventTimeBasis):
            raise ValueError("basis must be an OpcUaEventTimeBasis")
        if self.source_timestamp is not None:
            _validate_aware_datetime(self.source_timestamp, "source_timestamp")
        if self.server_timestamp is not None:
            _validate_aware_datetime(self.server_timestamp, "server_timestamp")
        _validate_aware_datetime(self.received_at, "received_at")
        _validate_aware_datetime(self.ingested_at, "ingested_at")
        if self.ingested_at < self.received_at:
            raise ValueError("ingested_at must not be before received_at")
        if self.event_at is not None:
            _validate_aware_datetime(self.event_at, "event_at")

        if self.basis == OpcUaEventTimeBasis.SOURCE_TIMESTAMP:
            if self.source_timestamp is None or self.event_at != self.source_timestamp:
                raise ValueError(
                    "source-timestamp event time requires event_at == source_timestamp"
                )
        elif self.basis == OpcUaEventTimeBasis.SERVER_TIMESTAMP:
            if self.source_timestamp is not None:
                raise ValueError("server-timestamp fallback is only valid without source_timestamp")
            if self.server_timestamp is None or self.event_at != self.server_timestamp:
                raise ValueError(
                    "server-timestamp event time requires event_at == server_timestamp"
                )
        else:
            if self.source_timestamp is not None:
                raise ValueError("available source_timestamp must be selected as event time")
            if self.event_at is not None:
                raise ValueError("unavailable event time must not carry event_at")


@dataclass(frozen=True, slots=True)
class OpcUaPersistentDataChangeEvent:
    """Registered DataChange event projected into one connection epoch.

    event_index is local ordering within connection_epoch. It is not an OPC UA server
    sequence number and does not prove exactly-once or gap-free delivery.
    """

    event: RegisteredOpcUaDataChangeEvent
    connection_epoch: int
    event_index: int
    event_time: OpcUaEventTimeEvidence

    def __post_init__(self) -> None:
        if not isinstance(self.event, RegisteredOpcUaDataChangeEvent):
            raise ValueError("event must be a RegisteredOpcUaDataChangeEvent")
        _validate_positive_int(self.connection_epoch, "connection_epoch")
        _validate_non_negative_int(self.event_index, "event_index")
        if not isinstance(self.event_time, OpcUaEventTimeEvidence):
            raise ValueError("event_time must be an OpcUaEventTimeEvidence")

        observation = self.event.notification.observation
        if self.event_time.source_timestamp != observation.source_timestamp:
            raise ValueError("event_time source_timestamp must match protocol observation")
        if self.event_time.server_timestamp != observation.server_timestamp:
            raise ValueError("event_time server_timestamp must match protocol observation")
        if self.event_time.received_at != observation.received_at:
            raise ValueError("event_time received_at must match protocol observation")

    @property
    def source_id(self) -> str:
        return self.event.source_id

    @property
    def channel_id(self) -> str:
        return self.event.channel_id

    @property
    def local_delivery_identity(self) -> tuple[str, int, int]:
        """Return platform-local delivery identity without claiming server sequencing."""
        return self.source_id, self.connection_epoch, self.event_index


def project_opcua_persistent_data_change_event(
    event: RegisteredOpcUaDataChangeEvent,
    *,
    connection_epoch: int,
    event_index: int,
    ingested_at: datetime,
    event_time_policy: OpcUaEventTimePolicy | None = None,
) -> OpcUaPersistentDataChangeEvent:
    """Project one registered DataChange event without changing protocol timestamps."""
    if not isinstance(event, RegisteredOpcUaDataChangeEvent):
        raise ValueError("event must be a RegisteredOpcUaDataChangeEvent")
    _validate_positive_int(connection_epoch, "connection_epoch")
    _validate_non_negative_int(event_index, "event_index")
    _validate_aware_datetime(ingested_at, "ingested_at")
    policy = OpcUaEventTimePolicy() if event_time_policy is None else event_time_policy
    if not isinstance(policy, OpcUaEventTimePolicy):
        raise ValueError("event_time_policy must be OpcUaEventTimePolicy")

    observation = event.notification.observation
    source_timestamp = observation.source_timestamp
    server_timestamp = observation.server_timestamp
    if source_timestamp is not None:
        basis = OpcUaEventTimeBasis.SOURCE_TIMESTAMP
        event_at = source_timestamp
    elif policy.allow_server_timestamp_fallback and server_timestamp is not None:
        basis = OpcUaEventTimeBasis.SERVER_TIMESTAMP
        event_at = server_timestamp
    else:
        basis = OpcUaEventTimeBasis.UNAVAILABLE
        event_at = None

    event_time = OpcUaEventTimeEvidence(
        basis=basis,
        source_timestamp=source_timestamp,
        server_timestamp=server_timestamp,
        received_at=observation.received_at,
        ingested_at=ingested_at,
        event_at=event_at,
    )
    return OpcUaPersistentDataChangeEvent(
        event=event,
        connection_epoch=connection_epoch,
        event_index=event_index,
        event_time=event_time,
    )


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


def _validate_positive_finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ValueError(f"{field_name} must be a finite number")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
