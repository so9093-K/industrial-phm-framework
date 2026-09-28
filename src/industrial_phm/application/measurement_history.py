"""Bounded measurement-history read models for the Operations trend surface."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from math import isfinite

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


class MeasurementCurrency(StrEnum):
    RECENT = "recent"
    STALE = "stale"
    FUTURE = "future-timestamp"
    UNAVAILABLE = "time-unavailable"


@dataclass(frozen=True, slots=True)
class LatestMeasurementStatus:
    point: MeasurementHistoryPoint
    currency: MeasurementCurrency
    age_seconds: float | None


def assess_latest_measurement(
    point: MeasurementHistoryPoint,
    *,
    as_of: datetime,
    stale_after_seconds: float,
) -> LatestMeasurementStatus:
    """Event-time currency of stored history, independent of source/asset health."""
    if as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    if (
        isinstance(stale_after_seconds, bool)
        or not isfinite(stale_after_seconds)
        or stale_after_seconds <= 0
    ):
        raise ValueError("stale_after_seconds must be positive and finite")
    event_at = point.measurement.event_at
    if event_at is None:
        return LatestMeasurementStatus(point, MeasurementCurrency.UNAVAILABLE, None)
    age = (as_of - event_at).total_seconds()
    currency = (
        MeasurementCurrency.FUTURE
        if age < 0
        else MeasurementCurrency.STALE
        if age > stale_after_seconds
        else MeasurementCurrency.RECENT
    )
    return LatestMeasurementStatus(point, currency, age)


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
    durations = {"15m": timedelta(minutes=15), "24h": timedelta(hours=24), "7d": timedelta(days=7)}
    if preset in durations:
        return as_of - durations[preset], as_of
    if preset != "custom":
        raise ValueError("unknown measurement range preset")
    if start_at.utcoffset() is None or end_at.utcoffset() is None or end_at <= start_at:
        raise ValueError("custom range must be increasing and timezone-aware")
    return start_at, end_at
