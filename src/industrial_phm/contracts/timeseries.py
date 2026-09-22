"""Canonical time-series contract used at the adapter/core boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from numbers import Real
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class CanonicalTimeSeries:
    """Immutable representation of one asset's multivariate time-series segment.

    The contract deliberately contains only domain-neutral fields. Dataset-specific
    details belong in ``metadata`` or remain inside the domain adapter.

    ``timestamps`` may be omitted for regularly sampled segments when
    ``sampling_rate_hz`` is provided. In that case sample position defines the
    segment-local time offset and the contract does not invent an absolute start time.

    Mutable input containers are copied into immutable tuples at construction time so
    validated invariants cannot be invalidated later by caller-side mutation.
    """

    asset_id: str
    timestamps: Sequence[datetime] | None
    channels: Sequence[str]
    values: Sequence[Sequence[float]]
    sampling_rate_hz: float | None = None
    labels: Sequence[str | int | bool | None] | None = None
    rul: Sequence[float | None] | None = None
    metadata: Mapping[str, str | int | float | bool | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        timestamps = tuple(self.timestamps) if self.timestamps is not None else None
        channels = tuple(self.channels)
        values = tuple(tuple(row) for row in self.values)
        labels = tuple(self.labels) if self.labels is not None else None
        rul = tuple(self.rul) if self.rul is not None else None
        metadata = MappingProxyType(dict(self.metadata))

        if not self.asset_id.strip():
            raise ValueError("asset_id must not be empty")
        if not channels:
            raise ValueError("channels must contain at least one channel")
        if len(set(channels)) != len(channels):
            raise ValueError("channels must be unique")
        if timestamps is not None and len(timestamps) != len(values):
            raise ValueError("timestamps and values must have the same number of samples")
        if self.sampling_rate_hz is not None:
            if not isfinite(self.sampling_rate_hz):
                raise ValueError("sampling_rate_hz must be finite when provided")
            if self.sampling_rate_hz <= 0:
                raise ValueError("sampling_rate_hz must be positive when provided")
        if timestamps is None and self.sampling_rate_hz is None:
            raise ValueError("timestamps may be omitted only when sampling_rate_hz is provided")

        channel_count = len(channels)
        for row in values:
            if len(row) != channel_count:
                raise ValueError("each values row must match the number of channels")
            if any(
                isinstance(value, bool)
                or not isinstance(value, Real)
                or not isfinite(value)
                for value in row
            ):
                raise ValueError("values must contain only finite numbers")

        sample_count = len(values)
        if labels is not None and len(labels) != sample_count:
            raise ValueError("labels must align with samples when provided")
        if rul is not None:
            if len(rul) != sample_count:
                raise ValueError("rul must align with samples when provided")
            if any(
                value is not None
                and (
                    isinstance(value, bool)
                    or not isinstance(value, Real)
                    or not isfinite(value)
                )
                for value in rul
            ):
                raise ValueError("rul must contain only finite numbers or None")

        object.__setattr__(self, "timestamps", timestamps)
        object.__setattr__(self, "channels", channels)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "labels", labels)
        object.__setattr__(self, "rul", rul)
        object.__setattr__(self, "metadata", metadata)
