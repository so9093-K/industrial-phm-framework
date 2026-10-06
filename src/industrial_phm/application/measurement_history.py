"""Bounded measurement-history read models for the Operations trend surface."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from industrial_phm.application.asset_history import HistoricalMeasurement


@dataclass(frozen=True, slots=True)
class HistoryAssetSummary:
    asset_id: str
    start_at: datetime
    end_at: datetime
    measurement_count: int


@dataclass(frozen=True, slots=True)
class MeasurementHistoryPoint:
    measurement: HistoricalMeasurement
    conflicting_duplicate: bool
    source_metadata_json: str | None = None
    source_file: str | None = None
    source_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class MeasurementHistoryPage:
    points: tuple[MeasurementHistoryPoint, ...]
    truncated: bool
    point_budget: int

    def __post_init__(self) -> None:
        if not 1 <= self.point_budget <= 10000 or len(self.points) > self.point_budget:
            raise ValueError("history page exceeds the supported point budget")


class HistoryEventTimeState(StrEnum):
    RECORDED = "recorded"
    FUTURE = "future-timestamp"
    UNAVAILABLE = "time-unavailable"


@dataclass(frozen=True, slots=True)
class LatestMeasurementAge:
    point: MeasurementHistoryPoint
    event_time_state: HistoryEventTimeState
    age_seconds: float | None


def assess_latest_measurement(
    point: MeasurementHistoryPoint,
    *,
    as_of: datetime,
) -> LatestMeasurementAge:
    """Age of stored history. No receipt or expected-live freshness is inferred."""
    if as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    event_at = point.measurement.event_at
    if event_at is None:
        return LatestMeasurementAge(point, HistoryEventTimeState.UNAVAILABLE, None)
    age = (as_of - event_at).total_seconds()
    state = HistoryEventTimeState.FUTURE if age < 0 else HistoryEventTimeState.RECORDED
    return LatestMeasurementAge(point, state, age)


def resolve_measurement_range(
    preset: str,
    *,
    as_of: datetime,
    start_at: datetime,
    end_at: datetime,
) -> tuple[datetime, datetime]:
    """Resolve relative ranges at query time, not at page initialization."""
    if as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    durations = {
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
    }
    if preset in durations:
        return as_of - durations[preset], as_of
    if preset != "custom":
        raise ValueError("unknown measurement range preset")
    if start_at.utcoffset() is None or end_at.utcoffset() is None or end_at <= start_at:
        raise ValueError("custom range must be increasing and timezone-aware")
    return start_at, end_at


@dataclass(frozen=True, slots=True)
class MeasurementHistoryBucket:
    source_id: str
    source_type: str
    measurement_point_id: str | None
    bucket_start: datetime
    bucket_end: datetime
    first_event_at: datetime
    last_event_at: datetime
    observation_count: int
    usable_count: int
    null_count: int
    non_good_count: int
    conflict_count: int
    minimum: float | None
    maximum: float | None
    mean: float | None
    interpretation_json: str


@dataclass(frozen=True, slots=True)
class MeasurementHistoryAggregation:
    """Presentation-only buckets over the full requested interval, not source statistics."""

    start_at: datetime
    end_at: datetime
    bucket_seconds: float
    snapshot_id: int
    buckets: tuple[MeasurementHistoryBucket, ...]


@dataclass(frozen=True, slots=True)
class MultiSignalMeasurementHistoryBucket:
    channel_id: str
    source_id: str
    source_type: str
    measurement_point_id: str | None
    bucket_start: datetime
    bucket_end: datetime
    first_event_at: datetime
    last_event_at: datetime
    observation_count: int
    usable_count: int
    null_count: int
    non_good_count: int
    conflict_count: int
    minimum: float | None
    maximum: float | None
    mean: float | None
    interpretation_json: str


@dataclass(frozen=True, slots=True)
class MultiSignalMeasurementHistoryAggregation:
    """Bounded per-channel presentation buckets sharing one requested time axis."""

    start_at: datetime
    end_at: datetime
    bucket_seconds: float
    snapshot_id: int
    buckets: tuple[MultiSignalMeasurementHistoryBucket, ...]
