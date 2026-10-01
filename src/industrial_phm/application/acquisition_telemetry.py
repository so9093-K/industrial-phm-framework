"""Latest operational telemetry for the continuous acquisition runtime."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from industrial_phm.application.history_writer import SpoolHistoryBatchWriteResult
from industrial_phm.application.opcua_persistent import (
    OpcUaPersistentDataChangeEvent,
    OpcUaPersistentSessionEvidence,
    OpcUaPersistentSessionState,
)
from industrial_phm.application.window_coordinator import (
    ObservationWindowCoordinatorCycleResult,
)


class AcquisitionFailureComponent(StrEnum):
    OPCUA_WORKER = "opcua-worker"
    HISTORY_WRITER = "history-writer"
    WINDOW_COORDINATOR = "window-coordinator"


class CollectionServiceRuntimeState(StrEnum):
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CollectionServiceRuntimeTelemetry:
    """Process-level collection service evidence, separate from source session state."""

    state: CollectionServiceRuntimeState
    started_at: datetime
    heartbeat_at: datetime
    reconcile_count: int
    owned_source_count: int
    last_failure_at: datetime | None = None
    last_failure: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, CollectionServiceRuntimeState):
            raise ValueError("state must be CollectionServiceRuntimeState")
        _validate_aware_datetime(self.started_at, "started_at")
        _validate_aware_datetime(self.heartbeat_at, "heartbeat_at")
        if self.heartbeat_at < self.started_at:
            raise ValueError("heartbeat_at must not be before started_at")
        _validate_non_negative_int(self.reconcile_count, "reconcile_count")
        _validate_non_negative_int(self.owned_source_count, "owned_source_count")
        if (self.last_failure_at is None) != (self.last_failure is None):
            raise ValueError("last failure time and detail must be recorded together")
        if self.last_failure_at is not None:
            _validate_aware_datetime(self.last_failure_at, "last_failure_at")
            if self.last_failure_at > self.heartbeat_at:
                raise ValueError("last_failure_at must not be after heartbeat_at")
        if self.last_failure is not None:
            _validate_detail(self.last_failure, "last_failure")


@dataclass(frozen=True, slots=True)
class AcquisitionSessionTelemetry:
    source_id: str
    worker_started_at: datetime
    state: OpcUaPersistentSessionState
    state_changed_at: datetime
    connection_epoch: int
    reconnect_attempt_index: int
    callback_queue_overflow_count: int
    connected_since: datetime | None = None
    last_disconnect_at: datetime | None = None
    detail: str | None = None
    callback_queue_maxsize: int | None = None
    callback_queue_depth: int | None = None
    callback_queue_high_watermark: int | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        _validate_aware_datetime(self.worker_started_at, "worker_started_at")
        if not isinstance(self.state, OpcUaPersistentSessionState):
            raise ValueError("state must be OpcUaPersistentSessionState")
        _validate_aware_datetime(self.state_changed_at, "state_changed_at")
        if self.state_changed_at < self.worker_started_at:
            raise ValueError("state_changed_at must not be before worker_started_at")
        _validate_non_negative_int(self.connection_epoch, "connection_epoch")
        _validate_non_negative_int(
            self.reconnect_attempt_index,
            "reconnect_attempt_index",
        )
        _validate_non_negative_int(
            self.callback_queue_overflow_count,
            "callback_queue_overflow_count",
        )
        for field_name in (
            "connected_since",
            "last_disconnect_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _validate_aware_datetime(value, field_name)
                if value < self.worker_started_at:
                    raise ValueError(f"{field_name} must not be before worker_started_at")
                if value > self.state_changed_at:
                    raise ValueError(f"{field_name} must not be after state_changed_at")

        if self.state == OpcUaPersistentSessionState.CONNECTED:
            if self.connected_since is None:
                raise ValueError("CONNECTED session telemetry requires connected_since")
        elif self.connected_since is not None:
            raise ValueError("non-CONNECTED session telemetry must not carry connected_since")

        for field_name in (
            "callback_queue_maxsize",
            "callback_queue_depth",
            "callback_queue_high_watermark",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _validate_non_negative_int(value, field_name)
        if self.callback_queue_maxsize is not None and self.callback_queue_maxsize < 1:
            raise ValueError("callback_queue_maxsize must be at least 1")
        if (
            self.callback_queue_depth is not None
            and self.callback_queue_maxsize is not None
            and self.callback_queue_depth > self.callback_queue_maxsize
        ):
            raise ValueError("callback_queue_depth must not exceed callback_queue_maxsize")
        if (
            self.callback_queue_high_watermark is not None
            and self.callback_queue_maxsize is not None
            and self.callback_queue_high_watermark > self.callback_queue_maxsize
        ):
            raise ValueError("callback_queue_high_watermark must not exceed callback_queue_maxsize")
        if (
            self.callback_queue_depth is not None
            and self.callback_queue_high_watermark is not None
            and self.callback_queue_high_watermark < self.callback_queue_depth
        ):
            raise ValueError("callback_queue_high_watermark must not be below callback_queue_depth")
        if self.detail is not None:
            _validate_detail(self.detail, "detail")


@dataclass(frozen=True, slots=True)
class AcquisitionFlowTelemetry:
    source_id: str
    worker_started_at: datetime
    accepted_event_count: int
    replayed_event_count: int
    bad_status_event_count: int
    updated_at: datetime
    last_delivery_identity: tuple[str, int, int] | None = None
    last_source_timestamp: datetime | None = None
    last_received_at: datetime | None = None
    last_ingested_at: datetime | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        _validate_aware_datetime(self.worker_started_at, "worker_started_at")
        _validate_aware_datetime(self.updated_at, "updated_at")
        if self.updated_at < self.worker_started_at:
            raise ValueError("updated_at must not be before worker_started_at")
        for field_name in (
            "accepted_event_count",
            "replayed_event_count",
            "bad_status_event_count",
        ):
            _validate_non_negative_int(getattr(self, field_name), field_name)
        if self.replayed_event_count > self.accepted_event_count:
            raise ValueError("replayed_event_count must not exceed accepted_event_count")
        if self.bad_status_event_count > self.accepted_event_count:
            raise ValueError("bad_status_event_count must not exceed accepted_event_count")

        for field_name in (
            "last_source_timestamp",
            "last_received_at",
            "last_ingested_at",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _validate_aware_datetime(value, field_name)

        if self.accepted_event_count == 0:
            if (
                self.last_delivery_identity is not None
                or self.last_received_at is not None
                or self.last_ingested_at is not None
            ):
                raise ValueError("empty flow telemetry must not carry latest delivery timing")
        else:
            if self.last_delivery_identity is None:
                raise ValueError("non-empty flow telemetry requires last_delivery_identity")
            _validate_local_delivery_identity(self.last_delivery_identity)
            if self.last_delivery_identity[0] != self.source_id:
                raise ValueError("last_delivery_identity source_id must match source_id")
            if self.last_received_at is None or self.last_ingested_at is None:
                raise ValueError("non-empty flow telemetry requires received/ingested timing")

    def average_event_rate_hz(self, *, as_of: datetime) -> float | None:
        _validate_aware_datetime(as_of, "as_of")
        if as_of < self.worker_started_at:
            raise ValueError("as_of must not be before worker_started_at")
        elapsed = (as_of - self.worker_started_at).total_seconds()
        if elapsed <= 0:
            return None
        return self.accepted_event_count / elapsed


@dataclass(frozen=True, slots=True)
class AcquisitionHistoryTelemetry:
    source_id: str
    batch_id: str
    snapshot_id: int
    batch_event_count: int
    source_event_count: int
    committed_at: datetime
    acknowledged_at: datetime
    recovered_existing_commit: bool

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        _validate_identifier(self.batch_id, "batch_id")
        _validate_non_negative_int(self.snapshot_id, "snapshot_id")
        _validate_positive_int(self.batch_event_count, "batch_event_count")
        _validate_positive_int(self.source_event_count, "source_event_count")
        if self.source_event_count > self.batch_event_count:
            raise ValueError("source_event_count must not exceed batch_event_count")
        _validate_aware_datetime(self.committed_at, "committed_at")
        _validate_aware_datetime(self.acknowledged_at, "acknowledged_at")
        if self.acknowledged_at < self.committed_at:
            raise ValueError("acknowledged_at must not be before committed_at")
        if not isinstance(self.recovered_existing_commit, bool):
            raise ValueError("recovered_existing_commit must be boolean")


@dataclass(frozen=True, slots=True)
class AcquisitionWindowTelemetry:
    source_id: str
    updated_at: datetime
    watermark: datetime | None
    active_window_count: int
    finalized_window_count: int
    historical_event_count: int
    in_order_count: int
    out_of_order_count: int
    late_count: int
    timing_unavailable_count: int
    unexpected_channel_count: int
    future_timestamp_count: int
    buffer_full_count: int
    duplicate_count: int
    last_finalized_window_id: str | None = None
    last_finalized_window_end: datetime | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        _validate_aware_datetime(self.updated_at, "updated_at")
        if self.watermark is not None:
            _validate_aware_datetime(self.watermark, "watermark")
        for field_name in (
            "active_window_count",
            "finalized_window_count",
            "historical_event_count",
            "in_order_count",
            "out_of_order_count",
            "late_count",
            "timing_unavailable_count",
            "unexpected_channel_count",
            "future_timestamp_count",
            "buffer_full_count",
            "duplicate_count",
        ):
            _validate_non_negative_int(getattr(self, field_name), field_name)

        if self.last_finalized_window_id is None:
            if self.last_finalized_window_end is not None:
                raise ValueError("last_finalized_window_end requires last_finalized_window_id")
        else:
            _validate_identifier(
                self.last_finalized_window_id,
                "last_finalized_window_id",
            )
            if self.last_finalized_window_end is None:
                raise ValueError("last_finalized_window_id requires last_finalized_window_end")
            _validate_aware_datetime(
                self.last_finalized_window_end,
                "last_finalized_window_end",
            )


@dataclass(frozen=True, slots=True)
class AcquisitionFailureTelemetry:
    source_id: str
    component: AcquisitionFailureComponent
    occurred_at: datetime
    detail: str

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        if not isinstance(self.component, AcquisitionFailureComponent):
            raise ValueError("component must be AcquisitionFailureComponent")
        _validate_aware_datetime(self.occurred_at, "occurred_at")
        _validate_detail(self.detail, "detail")


@dataclass(frozen=True, slots=True)
class AcquisitionLastReceiptTelemetry:
    """A source's latest live receipt from an earlier collector worker.

    Flow telemetry restarts empty with every worker; this keeps the receive-clock
    fact (``received_at``) across restarts without mixing in storage times.
    """

    source_id: str
    received_at: datetime
    source_timestamp: datetime | None
    delivery_identity: tuple[str, int, int]

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        _validate_aware_datetime(self.received_at, "received_at")
        if self.source_timestamp is not None:
            _validate_aware_datetime(self.source_timestamp, "source_timestamp")
        if self.delivery_identity[0] != self.source_id:
            raise ValueError("delivery_identity must belong to source_id")


@dataclass(frozen=True, slots=True)
class AcquisitionTelemetrySnapshot:
    """Presenter-ready runtime facts without a synthetic healthy/unhealthy verdict."""

    source_id: str
    session: AcquisitionSessionTelemetry | None = None
    flow: AcquisitionFlowTelemetry | None = None
    history: AcquisitionHistoryTelemetry | None = None
    window: AcquisitionWindowTelemetry | None = None
    failure: AcquisitionFailureTelemetry | None = None
    last_receipt: AcquisitionLastReceiptTelemetry | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        for field_name in ("session", "flow", "history", "window", "failure", "last_receipt"):
            value = getattr(self, field_name)
            if value is not None and value.source_id != self.source_id:
                raise ValueError(f"{field_name} source_id must match snapshot source_id")

    @property
    def last_received_at(self) -> datetime | None:
        """Latest live receipt time, from this worker's flow or an earlier worker."""
        if self.flow is not None and self.flow.last_received_at is not None:
            return self.flow.last_received_at
        return None if self.last_receipt is None else self.last_receipt.received_at


@dataclass(frozen=True, slots=True)
class AcquisitionSpoolTelemetrySnapshot:
    """Durable spool facts sampled directly from the spool database."""

    sampled_at: datetime
    pending_event_count: int
    payload_bytes: int
    oldest_accepted_at: datetime | None
    active_batch_id: str | None = None
    active_batch_event_count: int = 0
    active_batch_payload_bytes: int = 0

    def __post_init__(self) -> None:
        _validate_aware_datetime(self.sampled_at, "sampled_at")
        for field_name in (
            "pending_event_count",
            "payload_bytes",
            "active_batch_event_count",
            "active_batch_payload_bytes",
        ):
            _validate_non_negative_int(getattr(self, field_name), field_name)
        if self.pending_event_count == 0:
            if self.payload_bytes != 0 or self.oldest_accepted_at is not None:
                raise ValueError(
                    "empty spool telemetry requires zero bytes and no oldest_accepted_at"
                )
        elif self.oldest_accepted_at is None:
            raise ValueError("non-empty spool telemetry requires oldest_accepted_at")
        if self.oldest_accepted_at is not None:
            _validate_aware_datetime(self.oldest_accepted_at, "oldest_accepted_at")
            if self.oldest_accepted_at > self.sampled_at:
                raise ValueError("oldest_accepted_at must not be after sampled_at")
        if self.active_batch_id is None:
            if self.active_batch_event_count != 0 or self.active_batch_payload_bytes != 0:
                raise ValueError("missing active batch requires zero active batch counts")
        else:
            _validate_identifier(self.active_batch_id, "active_batch_id")
            _validate_positive_int(
                self.active_batch_event_count,
                "active_batch_event_count",
            )
            _validate_positive_int(
                self.active_batch_payload_bytes,
                "active_batch_payload_bytes",
            )
            if self.active_batch_event_count > self.pending_event_count:
                raise ValueError("active_batch_event_count must not exceed pending_event_count")
            if self.active_batch_payload_bytes > self.payload_bytes:
                raise ValueError("active_batch_payload_bytes must not exceed payload_bytes")

    @property
    def oldest_pending_age_seconds(self) -> float | None:
        if self.oldest_accepted_at is None:
            return None
        return (self.sampled_at - self.oldest_accepted_at).total_seconds()


@dataclass(frozen=True, slots=True)
class AcquisitionTelemetrySurface:
    """Operational telemetry surface; spool facts are global pipeline evidence."""

    source: AcquisitionTelemetrySnapshot
    spool: AcquisitionSpoolTelemetrySnapshot


@runtime_checkable
class AcquisitionTelemetryRecorder(Protocol):
    def record_session_configuration(
        self,
        source_id: str,
        *,
        callback_queue_maxsize: int,
        recorded_at: datetime,
    ) -> None: ...

    def record_session_evidence(
        self,
        evidence: OpcUaPersistentSessionEvidence,
    ) -> None: ...

    def record_callback_queue_overflow(
        self,
        source_id: str,
        *,
        occurred_at: datetime,
    ) -> None: ...

    def record_opcua_event(self, event: OpcUaPersistentDataChangeEvent) -> None: ...

    def record_history_batch(
        self,
        result: SpoolHistoryBatchWriteResult,
        *,
        source_event_counts: Mapping[str, int],
    ) -> None: ...

    def record_window_cycle(
        self,
        cycle: ObservationWindowCoordinatorCycleResult,
        *,
        recorded_at: datetime,
    ) -> None: ...

    def record_failure(self, failure: AcquisitionFailureTelemetry) -> None: ...


@runtime_checkable
class CollectionServiceRuntimeRecorder(Protocol):
    def record_collection_service_start(
        self,
        *,
        started_at: datetime,
    ) -> None: ...

    def record_collection_service_heartbeat(
        self,
        *,
        heartbeat_at: datetime,
        reconcile_count: int,
        owned_source_count: int,
    ) -> None: ...

    def record_collection_service_failure(
        self,
        detail: str,
        *,
        occurred_at: datetime,
    ) -> None: ...

    def record_collection_service_stop(
        self,
        *,
        stopped_at: datetime,
        reconcile_count: int,
    ) -> None: ...


@runtime_checkable
class CollectionServiceRuntimeRepository(Protocol):
    def get_collection_service_runtime(self) -> CollectionServiceRuntimeTelemetry | None: ...


@runtime_checkable
class AcquisitionSpoolTelemetryReader(Protocol):
    def telemetry_snapshot(
        self,
        *,
        sampled_at: datetime,
    ) -> AcquisitionSpoolTelemetrySnapshot: ...


@runtime_checkable
class AcquisitionTelemetryRepository(Protocol):
    def get(self, source_id: str) -> AcquisitionTelemetrySnapshot: ...

    def list_snapshots(self) -> tuple[AcquisitionTelemetrySnapshot, ...]: ...


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _validate_detail(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
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


def _validate_local_delivery_identity(value: tuple[str, int, int]) -> None:
    if not isinstance(value, tuple) or len(value) != 3:
        raise ValueError("local_delivery_identity must be a 3-tuple")
    source_id, connection_epoch, event_index = value
    _validate_identifier(source_id, "local_delivery_identity source_id")
    _validate_positive_int(connection_epoch, "local_delivery_identity connection_epoch")
    _validate_non_negative_int(event_index, "local_delivery_identity event_index")


def build_acquisition_telemetry_surface(
    repository: AcquisitionTelemetryRepository,
    spool: AcquisitionSpoolTelemetryReader,
    source_id: str,
    *,
    sampled_at: datetime,
) -> AcquisitionTelemetrySurface:
    """Build one deterministic operational surface without asset-health inference."""
    _validate_identifier(source_id, "source_id")
    _validate_aware_datetime(sampled_at, "sampled_at")
    return AcquisitionTelemetrySurface(
        source=repository.get(source_id),
        spool=spool.telemetry_snapshot(sampled_at=sampled_at),
    )
