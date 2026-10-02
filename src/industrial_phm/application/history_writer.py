"""Application contracts for draining the durable acquisition spool into history."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from numbers import Real
from typing import Protocol, runtime_checkable

from industrial_phm.application.asset_history import (
    HistoricalBatchAppendResult,
    HistoricalBatchCommit,
    HistoryIngestionMode,
)
from industrial_phm.application.opcua_persistent import OpcUaPersistentDataChangeEvent


@dataclass(frozen=True, slots=True)
class SpoolToHistoryWriterPolicy:
    """Bounded micro-batch flush policy for the single-writer v1 runtime."""

    max_events: int = 1_000
    max_bytes: int = 1_048_576
    max_interval_seconds: float = 0.5
    poll_interval_seconds: float = 0.1

    def __post_init__(self) -> None:
        _validate_positive_int(self.max_events, "max_events")
        _validate_positive_int(self.max_bytes, "max_bytes")
        _validate_positive_finite(self.max_interval_seconds, "max_interval_seconds")
        _validate_positive_finite(self.poll_interval_seconds, "poll_interval_seconds")


@dataclass(frozen=True, slots=True)
class SpoolHistoryBatchWriteResult:
    """One acknowledged spool batch and its historical commit provenance."""

    commit: HistoricalBatchCommit
    payload_bytes: int
    write_started_at: datetime
    acknowledged_at: datetime
    recovered_existing_commit: bool

    def __post_init__(self) -> None:
        if not isinstance(self.commit, HistoricalBatchCommit):
            raise ValueError("commit must be a HistoricalBatchCommit")
        _validate_positive_int(self.payload_bytes, "payload_bytes")
        _validate_aware_datetime(self.write_started_at, "write_started_at")
        _validate_aware_datetime(self.acknowledged_at, "acknowledged_at")
        if self.acknowledged_at < self.write_started_at:
            raise ValueError("acknowledged_at must not be before write_started_at")
        if not isinstance(self.recovered_existing_commit, bool):
            raise ValueError("recovered_existing_commit must be boolean")

    @property
    def batch_id(self) -> str:
        return self.commit.batch_id

    @property
    def event_count(self) -> int:
        return self.commit.event_count

    @property
    def snapshot_id(self) -> int:
        return self.commit.snapshot_id

    @property
    def elapsed_seconds(self) -> float:
        return (self.acknowledged_at - self.write_started_at).total_seconds()


@dataclass(frozen=True, slots=True)
class SpoolHistoryWriterResult:
    """Finite summary returned when the continuous writer stops."""

    started_at: datetime
    stopped_at: datetime
    batch_count: int
    event_count: int
    recovered_batch_count: int

    def __post_init__(self) -> None:
        _validate_aware_datetime(self.started_at, "started_at")
        _validate_aware_datetime(self.stopped_at, "stopped_at")
        if self.stopped_at < self.started_at:
            raise ValueError("stopped_at must not be before started_at")
        _validate_non_negative_int(self.batch_count, "batch_count")
        _validate_non_negative_int(self.event_count, "event_count")
        _validate_non_negative_int(self.recovered_batch_count, "recovered_batch_count")
        if self.recovered_batch_count > self.batch_count:
            raise ValueError("recovered_batch_count must not exceed batch_count")


@runtime_checkable
class OpcUaHistoricalBatchStore(Protocol):
    """Historical sink contract required by the spool writer."""

    def append_or_recover_opcua_batch(
        self,
        events: Sequence[OpcUaPersistentDataChangeEvent],
        *,
        batch_id: str,
        ingestion_mode: HistoryIngestionMode = HistoryIngestionMode.LIVE,
    ) -> HistoricalBatchAppendResult:
        """Atomically append one batch or recover its identical prior commit."""
        ...

    def get_opcua_batch_commit(
        self,
        events: Sequence[OpcUaPersistentDataChangeEvent],
        *,
        batch_id: str,
        ingestion_mode: HistoryIngestionMode = HistoryIngestionMode.LIVE,
    ) -> HistoricalBatchCommit | None:
        """Return an identical prior commit, or fail when batch identity conflicts."""
        ...

    def append_opcua_batch(
        self,
        events: Sequence[OpcUaPersistentDataChangeEvent],
        *,
        batch_id: str,
        ingestion_mode: HistoryIngestionMode = HistoryIngestionMode.LIVE,
    ) -> HistoricalBatchCommit:
        """Commit one exact batch atomically."""
        ...


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
