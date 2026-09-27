"""Operational observation read model used by product-facing application services."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from math import isfinite
from numbers import Real
from string import hexdigits

from industrial_phm.application.asset_identity import (
    AssetIdentity,
    ChannelIdentity,
    MeasurementPointIdentity,
)
from industrial_phm.contracts import DataQualityAssessment


@dataclass(frozen=True, slots=True)
class SourceSnapshotEvidence:
    """Exact byte identity for one prepared source snapshot."""

    name: str
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        _validate_identifier(self.name, "source snapshot name")
        has_invalid_character = any(character not in hexdigits for character in self.sha256)
        if len(self.sha256) != 64 or has_invalid_character:
            raise ValueError(
                "source snapshot sha256 must contain exactly 64 hexadecimal characters"
            )
        if self.sha256 != self.sha256.lower():
            raise ValueError("source snapshot sha256 must use lowercase hexadecimal characters")
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int):
            raise ValueError("source snapshot size_bytes must be an integer")
        if self.size_bytes <= 0:
            raise ValueError("source snapshot size_bytes must be positive")


@dataclass(frozen=True, slots=True)
class ObservationValidationPolicy:
    """Declared source-validation settings relevant to operational interpretation."""

    minimum_sample_count: int
    source_timestamp_field: str | None = None
    sampling_rate_tolerance_ratio: float | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.minimum_sample_count, bool)
            or not isinstance(self.minimum_sample_count, int)
            or self.minimum_sample_count <= 0
        ):
            raise ValueError("minimum_sample_count must be a positive integer")
        if self.source_timestamp_field is not None:
            _validate_identifier(self.source_timestamp_field, "source_timestamp_field")
        if self.sampling_rate_tolerance_ratio is not None and (
            isinstance(self.sampling_rate_tolerance_ratio, bool)
            or not isinstance(self.sampling_rate_tolerance_ratio, Real)
            or not isfinite(self.sampling_rate_tolerance_ratio)
            or self.sampling_rate_tolerance_ratio < 0
        ):
            raise ValueError("sampling_rate_tolerance_ratio must be a finite non-negative number")


@dataclass(frozen=True, slots=True)
class AssetObservationSummary:
    """Validated facts for one observed asset segment.

    The summary intentionally stops before anomaly, diagnosis, prognostics, alarm, or
    maintenance interpretation. It is an application read model for answering whether
    data was observed, when it was observed, through which declared source, and with
    which recorded data-quality and source-provenance evidence.
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
    source_snapshot: SourceSnapshotEvidence | None = None
    validation_policy: ObservationValidationPolicy | None = None

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
        if self.source_snapshot is not None and not isinstance(
            self.source_snapshot,
            SourceSnapshotEvidence,
        ):
            raise ValueError("source_snapshot must be SourceSnapshotEvidence when provided")
        if self.validation_policy is not None and not isinstance(
            self.validation_policy,
            ObservationValidationPolicy,
        ):
            raise ValueError("validation_policy must be ObservationValidationPolicy when provided")

        object.__setattr__(self, "channels", channels)

    @property
    def asset_identity(self) -> AssetIdentity:
        """Return the observed physical asset identity."""
        return AssetIdentity(self.asset_id)

    @property
    def measurement_point_identity(self) -> MeasurementPointIdentity | None:
        """Return the optional observed measurement-point identity."""
        if self.measurement_point_id is None:
            return None
        return MeasurementPointIdentity(
            asset_id=self.asset_id,
            measurement_point_id=self.measurement_point_id,
        )

    @property
    def channel_identities(self) -> tuple[ChannelIdentity, ...]:
        """Return channels scoped by the recorded asset and measurement point."""
        return tuple(
            ChannelIdentity(
                asset_id=self.asset_id,
                measurement_point_id=self.measurement_point_id,
                channel_id=channel_id,
            )
            for channel_id in self.channels
        )


@dataclass(frozen=True, slots=True)
class AssetObservationTimeline:
    """Time-ordered observed segments for one asset measurement point."""

    segments: Sequence[AssetObservationSummary]

    def __post_init__(self) -> None:
        segments = tuple(self.segments)
        if not segments:
            raise ValueError("observation timeline must contain at least one segment")
        if any(not isinstance(segment, AssetObservationSummary) for segment in segments):
            raise ValueError(
                "observation timeline segments must contain only AssetObservationSummary values"
            )

        asset_id = segments[0].asset_id
        measurement_point_id = segments[0].measurement_point_id
        expected_awareness: bool | None = None
        for segment in segments:
            if segment.asset_id != asset_id:
                raise ValueError("observation timeline segments must share one asset_id")
            if segment.measurement_point_id != measurement_point_id:
                raise ValueError(
                    "observation timeline segments must share one measurement_point_id"
                )
            if segment.observed_start_at is None or segment.observed_end_at is None:
                raise ValueError(
                    "observation timeline requires explicit observed start/end timestamps"
                )

            awareness = _is_timezone_aware(segment.observed_start_at)
            if expected_awareness is None:
                expected_awareness = awareness
            elif awareness != expected_awareness:
                raise ValueError(
                    "observation timeline timestamps must use consistent timezone awareness"
                )

        for previous, current in pairwise(segments):
            previous_end = previous.observed_end_at
            current_start = current.observed_start_at
            if previous_end is None or current_start is None:
                raise AssertionError("validated timeline segment timestamps unexpectedly missing")
            try:
                overlaps_or_reverses = previous_end >= current_start
            except TypeError as error:
                raise ValueError(
                    "observation timeline timestamps must use consistent timezone awareness"
                ) from error
            if overlaps_or_reverses:
                raise ValueError(
                    "observation timeline segments must be strictly ordered and non-overlapping"
                )

        object.__setattr__(self, "segments", segments)

    @property
    def asset_id(self) -> str:
        """Return the common asset identity."""
        return self.segments[0].asset_id

    @property
    def measurement_point_id(self) -> str | None:
        """Return the common measurement-point identity."""
        return self.segments[0].measurement_point_id

    @property
    def asset_identity(self) -> AssetIdentity:
        """Return the common physical asset identity."""
        return self.segments[0].asset_identity

    @property
    def measurement_point_identity(self) -> MeasurementPointIdentity | None:
        """Return the common optional measurement-point identity."""
        return self.segments[0].measurement_point_identity

    @property
    def segment_count(self) -> int:
        """Return the number of observed source segments."""
        return len(self.segments)

    @property
    def observed_start_at(self) -> datetime:
        """Return the first recorded observation timestamp."""
        value = self.segments[0].observed_start_at
        if value is None:
            raise AssertionError("validated timeline start timestamp unexpectedly missing")
        return value

    @property
    def observed_end_at(self) -> datetime:
        """Return the last recorded observation timestamp."""
        value = self.segments[-1].observed_end_at
        if value is None:
            raise AssertionError("validated timeline end timestamp unexpectedly missing")
        return value

    @property
    def latest(self) -> AssetObservationSummary:
        """Return the latest observed segment."""
        return self.segments[-1]


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _is_timezone_aware(value: datetime) -> bool:
    return value.utcoffset() is not None
