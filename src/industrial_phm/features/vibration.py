"""Stateless acquisition-level vibration feature extraction."""

from __future__ import annotations

import math
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from industrial_phm.contracts import CanonicalTimeSeries

VIBRATION_STATISTICAL_FEATURE_SET_ID = "vibration-statistical-v1"
_STATISTIC_NAMES = (
    "mean",
    "rms",
    "standard_deviation",
    "absolute_peak",
    "peak_to_peak",
    "crest_factor",
    "skewness",
    "excess_kurtosis",
)
_MetadataValue = str | int | float | bool | None
_FlatValue = str | int | float | bool | None


class VibrationFeatureError(ValueError):
    """Raised when a waveform cannot produce the reference vibration feature set."""


@dataclass(frozen=True, slots=True)
class VibrationFeatureVector:
    """Immutable acquisition-level feature vector with source provenance."""

    feature_set_id: str
    asset_id: str
    feature_names: Sequence[str]
    values: Sequence[float]
    metadata: Mapping[str, _MetadataValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        feature_names = tuple(self.feature_names)
        values = tuple(float(value) for value in self.values)
        metadata = MappingProxyType(dict(self.metadata))

        if not self.feature_set_id.strip():
            raise ValueError("feature_set_id must not be empty")
        if not self.asset_id.strip():
            raise ValueError("asset_id must not be empty")
        if not feature_names:
            raise ValueError("feature_names must contain at least one feature")
        if len(feature_names) != len(set(feature_names)):
            raise ValueError("feature_names must be unique")
        if len(feature_names) != len(values):
            raise ValueError("feature_names and values must have the same length")
        if not all(math.isfinite(value) for value in values):
            raise ValueError("feature values must be finite")

        object.__setattr__(self, "feature_names", feature_names)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "metadata", metadata)

    def to_flat_record(self) -> dict[str, _FlatValue]:
        """Return a table-friendly record without flattening lifecycle semantics into features."""
        record: dict[str, _FlatValue] = {
            "feature_set_id": self.feature_set_id,
            "asset_id": self.asset_id,
        }
        record.update((f"meta.{key}", value) for key, value in self.metadata.items())
        record.update(zip(self.feature_names, self.values, strict=True))
        return record


def extract_vibration_features(series: CanonicalTimeSeries) -> VibrationFeatureVector:
    """Extract the fixed v1 statistical baseline independently for one acquisition."""
    sample_count = len(series.values)
    if sample_count < 2:
        raise VibrationFeatureError("vibration feature extraction requires at least two samples")

    feature_names: list[str] = []
    feature_values: list[float] = []

    for channel_index, channel_name in enumerate(series.channels):
        channel_values = tuple(float(row[channel_index]) for row in series.values)
        statistics = _channel_statistics(channel_name, channel_values)
        for statistic_name, value in zip(_STATISTIC_NAMES, statistics, strict=True):
            feature_names.append(f"feature.{channel_name}.{statistic_name}")
            feature_values.append(value)

    return VibrationFeatureVector(
        feature_set_id=VIBRATION_STATISTICAL_FEATURE_SET_ID,
        asset_id=series.asset_id,
        feature_names=feature_names,
        values=feature_values,
        metadata=series.metadata,
    )


def iter_vibration_features(
    series_iterable: Iterable[CanonicalTimeSeries],
) -> Iterator[VibrationFeatureVector]:
    """Transform acquisitions lazily so a full dataset need not be materialized in memory."""
    for series in series_iterable:
        yield extract_vibration_features(series)


def _channel_statistics(channel_name: str, samples: Sequence[float]) -> tuple[float, ...]:
    if not all(math.isfinite(value) for value in samples):
        raise VibrationFeatureError(
            f"vibration channel {channel_name!r} contains non-finite values"
        )

    sample_count = len(samples)
    mean = math.fsum(samples) / sample_count
    mean_square = math.fsum(value * value for value in samples) / sample_count
    rms = math.sqrt(mean_square)
    minimum = min(samples)
    maximum = max(samples)
    absolute_peak = max(abs(minimum), abs(maximum))
    peak_to_peak = maximum - minimum

    second_moment = math.fsum((value - mean) ** 2 for value in samples) / sample_count
    if second_moment <= 0.0:
        raise VibrationFeatureError(
            f"vibration channel {channel_name!r} must have non-zero variance"
        )
    standard_deviation = math.sqrt(second_moment)
    if rms <= 0.0:
        raise VibrationFeatureError(f"vibration channel {channel_name!r} must have non-zero RMS")

    third_moment = math.fsum((value - mean) ** 3 for value in samples) / sample_count
    fourth_moment = math.fsum((value - mean) ** 4 for value in samples) / sample_count
    skewness = third_moment / (second_moment**1.5)
    excess_kurtosis = fourth_moment / (second_moment * second_moment) - 3.0
    crest_factor = absolute_peak / rms

    result = (
        mean,
        rms,
        standard_deviation,
        absolute_peak,
        peak_to_peak,
        crest_factor,
        skewness,
        excess_kurtosis,
    )
    if not all(math.isfinite(value) for value in result):
        raise VibrationFeatureError(
            f"vibration channel {channel_name!r} produced non-finite feature values"
        )
    return result
