"""Historical Asset History contracts independent of the concrete lake runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite
from numbers import Real
from typing import Protocol, runtime_checkable

from industrial_phm.application.source_registration import SourceType


class HistoricalBatchConflictError(ValueError):
    """Raised when a stable history batch identity is reused with different content."""


class HistoryIngestionMode(StrEnum):
    """How a historical measurement entered the Asset History."""

    LIVE = "live"
    BACKFILL = "backfill"
    IMPORT = "import"
    REPLAY = "replay"


class HistoricalEventTimeBasis(StrEnum):
    """Authoritative time basis selected before historical persistence."""

    SOURCE_TIMESTAMP = "source-timestamp"
    SERVER_TIMESTAMP = "server-timestamp"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class HistoricalMeasurement:
    """Normalized measurement-history record with a source-evidence reference.

    The record is an Asset History read model, not a universal raw protocol schema.
    raw_evidence_id points to the source-specific evidence row that preserved the
    original delivery facts.
    """

    raw_evidence_id: str
    source_id: str
    source_type: SourceType
    asset_id: str
    channel_id: str
    event_time_basis: HistoricalEventTimeBasis
    event_at: datetime | None
    value: float | None
    status_good: bool
    ingestion_mode: HistoryIngestionMode
    measurement_point_id: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.raw_evidence_id, "raw_evidence_id")
        _validate_identifier(self.source_id, "source_id")
        if not isinstance(self.source_type, SourceType):
            raise ValueError("source_type must be a SourceType")
        _validate_identifier(self.asset_id, "asset_id")
        if self.measurement_point_id is not None:
            _validate_identifier(self.measurement_point_id, "measurement_point_id")
        _validate_identifier(self.channel_id, "channel_id")
        if not isinstance(self.event_time_basis, HistoricalEventTimeBasis):
            raise ValueError("event_time_basis must be a HistoricalEventTimeBasis")
        if self.event_at is not None:
            _validate_aware_datetime(self.event_at, "event_at")
        if self.event_time_basis == HistoricalEventTimeBasis.UNAVAILABLE:
            if self.event_at is not None:
                raise ValueError("unavailable event time must not carry event_at")
        elif self.event_at is None:
            raise ValueError("available event-time basis requires event_at")

        if self.value is not None:
            if isinstance(self.value, bool) or not isinstance(self.value, Real):
                raise ValueError("value must be numeric or None")
            if not isfinite(float(self.value)):
                raise ValueError("value must be finite when provided")
        if not isinstance(self.status_good, bool):
            raise ValueError("status_good must be boolean")
        if not isinstance(self.ingestion_mode, HistoryIngestionMode):
            raise ValueError("ingestion_mode must be a HistoryIngestionMode")


@dataclass(frozen=True, slots=True)
class HistoricalBatchCommit:
    """Committed historical batch and the DuckLake snapshot produced by it."""

    batch_id: str
    snapshot_id: int
    event_count: int
    committed_at: datetime

    def __post_init__(self) -> None:
        _validate_identifier(self.batch_id, "batch_id")
        _validate_non_negative_int(self.snapshot_id, "snapshot_id")
        _validate_positive_int(self.event_count, "event_count")
        _validate_aware_datetime(self.committed_at, "committed_at")


@dataclass(frozen=True, slots=True)
class HistoricalInputReference:
    """Reproducible Asset History input selection for analysis/baseline provenance."""

    snapshot_id: int
    asset_id: str
    start_at: datetime
    end_at: datetime
    measurement_point_id: str | None = None
    channel_ids: Sequence[str] = ()

    def __post_init__(self) -> None:
        channel_ids = tuple(self.channel_ids)
        _validate_non_negative_int(self.snapshot_id, "snapshot_id")
        validate_asset_history_query(
            self.asset_id,
            start_at=self.start_at,
            end_at=self.end_at,
        )
        if self.measurement_point_id is not None:
            _validate_identifier(self.measurement_point_id, "measurement_point_id")
        for channel_id in channel_ids:
            _validate_identifier(channel_id, "channel_id")
        if len(set(channel_ids)) != len(channel_ids):
            raise ValueError("channel_ids must contain unique values")
        object.__setattr__(self, "channel_ids", channel_ids)


@runtime_checkable
class AssetHistoryReader(Protocol):
    """Read boundary for normalized Asset History measurements."""

    def query_measurements(
        self,
        asset_id: str,
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> tuple[HistoricalMeasurement, ...]:
        """Return event-time-addressable measurements in [start_at, end_at)."""
        ...


def validate_asset_history_query(
    asset_id: str,
    *,
    start_at: datetime,
    end_at: datetime,
) -> None:
    """Validate the common Asset History range-query contract."""
    _validate_identifier(asset_id, "asset_id")
    _validate_aware_datetime(start_at, "start_at")
    _validate_aware_datetime(end_at, "end_at")
    if end_at <= start_at:
        raise ValueError("end_at must be after start_at")


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
