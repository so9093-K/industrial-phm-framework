"""Canonical time-series contract used at the adapter/core boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Mapping, Sequence


@dataclass(frozen=True, slots=True)
class CanonicalTimeSeries:
    """Immutable representation of one asset's multivariate time-series segment.

    The contract deliberately contains only domain-neutral fields. Dataset-specific
    details belong in ``metadata`` or remain inside the domain adapter.
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
        if not self.asset_id.strip():
            raise ValueError("asset_id must not be empty")
        if not self.channels:
            raise ValueError("channels must contain at least one channel")
        if len(set(self.channels)) != len(self.channels):
            raise ValueError("channels must be unique")
        if len(self.timestamps) != len(self.values):
            raise ValueError("timestamps and values must have the same number of samples")
        if self.sampling_rate_hz is not None and self.sampling_rate_hz <= 0:
            raise ValueError("sampling_rate_hz must be positive when provided")

        channel_count = len(self.channels)
        for row in self.values:
            if len(row) != channel_count:
                raise ValueError("each values row must match the number of channels")

        sample_count = len(self.timestamps)
        if self.labels is not None and len(self.labels) != sample_count:
            raise ValueError("labels must align with timestamps when provided")
        if self.rul is not None and len(self.rul) != sample_count:
            raise ValueError("rul must align with timestamps when provided")

        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
