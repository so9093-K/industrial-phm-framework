"""Operational observation read model used by product-facing application services."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from numbers import Real

from industrial_phm.contracts import DataQualityAssessment


@dataclass(frozen=True, slots=True)
class AssetObservationSummary:
    """Validated facts for one observed asset segment.

    The summary intentionally stops before anomaly, diagnosis, prognostics, alarm, or
    maintenance interpretation. It is an application read model for answering whether
    data was observed, when it was observed, through which declared source, and with
    which recorded data-quality evidence.
    """

    asset_id: str
    source_id: str
    channels: Sequence[str]
    sample_count: int
    data_quality: DataQualityAssessment
    measurement_point_id: str | None = None
    observed_start_at: datetime | None = None
    observed_end_at: datetime | None = None
    sampling_rate_hz: float | None = None

    def __post_init__(self) -> None:
        channels = tuple(self.channels)

        _validate_identifier(self.asset_id, "asset_id")
        _validate_identifier(self.source_id, "source_id")
        if self.measurement_point_id is not None:
            _validate_identifier(self.measurement_point_id, "measurement_point_id")

        if isinstance(self.sample_count, bool) or not isinstance(self.sample_count, int):
            raise ValueError("sample_count must be an integer")
        if self.sample_count <= 0:
            raise ValueError("sample_count must be positive")

        if not channels:
            raise ValueError("channels must contain at least one channel")
        for channel in channels:
            _validate_identifier(channel, "channel")
        if len(set(channels)) != len(channels):
            raise ValueError("channels must contain unique names")

        if self.observed_start_at is not None and self.observed_end_at is not None:
            if _is_timezone_aware(self.observed_start_at) != _is_timezone_aware(
                self.observed_end_at
            ):
                raise ValueError(
                    "observed_start_at and observed_end_at must use the same timezone awareness"
                )
            if self.observed_start_at > self.observed_end_at:
                raise ValueError("observed_start_at must not be after observed_end_at")

        if self.sampling_rate_hz is not None and (
            isinstance(self.sampling_rate_hz, bool)
            or not isinstance(self.sampling_rate_hz, Real)
            or not isfinite(self.sampling_rate_hz)
            or self.sampling_rate_hz <= 0
        ):
            raise ValueError("sampling_rate_hz must be a positive finite number")

        if not isinstance(self.data_quality, DataQualityAssessment):
            raise ValueError("data_quality must be a DataQualityAssessment")

        object.__setattr__(self, "channels", channels)


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _is_timezone_aware(value: datetime) -> bool:
    return value.utcoffset() is not None
