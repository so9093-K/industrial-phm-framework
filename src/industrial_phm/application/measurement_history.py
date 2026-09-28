"""Bounded measurement-history read models for the Operations trend surface."""

from dataclasses import dataclass
from datetime import datetime

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
