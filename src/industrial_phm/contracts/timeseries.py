"""Canonical time-series contract used at the adapter/core boundary."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType


@dataclass(frozen=True, slots=True)
class CanonicalTimeSeries:
    """Immutable representation of one asset's multivariate time-series segment.

    The contract deliberately contains only domain-neutral fields. Dataset-specific
    details belong in ``metadata`` or remain inside the domain adapter.

    Mutable input containers are copied into immutable tuples at construction time so
    validated invariants cannot be invalidated later by caller-side mutation.
    """

    asset_id: str
    timestamps: Sequence[datetime]
    channels: Sequence[str]
    values: Sequence[Sequence[float]]
    sampling_rate_hz: float | None = None
    labels: Sequence[str | int | bool | None] | None = None
    rul: Sequence[float | None] | None = None
    metadata: Mapping[str, str | int | float | bool | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        timestamps = tuple(self.timestamps)
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
        if len(timestamps) != len(values):
            raise ValueError("timestamps and values must have the same number of samples")
        if self.sampling_rate_hz is not None and self.sampling_rate_hz <= 0:
            raise ValueError("sampling_rate_hz must be positive when provided")

        channel_count = len(channels)
        for row in values:
            if len(row) != channel_count:
                raise ValueError("each values row must match the number of channels")

        sample_count = len(timestamps)
        if labels is not None and len(labels) != sample_count:
            raise ValueError("labels must align with timestamps when provided")
        if rul is not None and len(rul) != sample_count:
            raise ValueError("rul must align with timestamps when provided")

        object.__setattr__(self, "timestamps", timestamps)
        object.__setattr__(self, "channels", channels)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "labels", labels)
        object.__setattr__(self, "rul", rul)
        object.__setattr__(self, "metadata", metadata)
