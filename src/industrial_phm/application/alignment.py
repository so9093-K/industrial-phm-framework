"""Protocol-independent temporal alignment of multi-channel observations (ADR-0009).

Raw observations are never modified. An aligned sample refers to each channel's
original observation and states whether it was observed at the sample time or
carried forward from an earlier observation, and how old it is.
"""

from __future__ import annotations

import bisect
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from industrial_phm.application.analysis_input import ChannelObservation


class AlignmentPolicyKind(StrEnum):
    STRICT = "strict-v1"
    BOUNDED_PREVIOUS = "bounded-previous-v1"


class ValueOrigin(StrEnum):
    OBSERVED = "observed"
    CARRIED = "carried"


class AlignmentExclusion(StrEnum):
    INCOMPLETE = "incomplete-phases"
    NO_RECENT_VALUE = "no-recent-phase-value"


@dataclass(frozen=True, slots=True)
class TemporalAlignmentPolicy:
    """Which observations may form one multi-channel sample.

    ``strict-v1`` needs every channel at the same timestamp. ``bounded-previous-v1``
    carries a channel's latest earlier observation when it is at most ``max_age``
    old; it never uses a later observation. Its ``max_age`` has no default and must
    cite a ``basis`` (device update period, datasheet, calibration result).
    """

    kind: AlignmentPolicyKind = AlignmentPolicyKind.STRICT
    max_age: timedelta | None = None
    basis: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, AlignmentPolicyKind):
            raise ValueError("kind must be an AlignmentPolicyKind")
        if self.kind == AlignmentPolicyKind.STRICT:
            if self.max_age is not None or self.basis is not None:
                raise ValueError("strict alignment takes no max_age or basis")
            return
        if not isinstance(self.max_age, timedelta) or self.max_age <= timedelta(0):
            raise ValueError("bounded-previous alignment requires a positive max_age")
        if not isinstance(self.basis, str) or not self.basis.strip():
            raise ValueError("bounded-previous alignment requires the basis for its max_age")

    @property
    def is_strict(self) -> bool:
        return self.kind == AlignmentPolicyKind.STRICT

    def identity(self) -> dict[str, object]:
        """Canonical, JSON-ready identity for evidence and analysis identity."""
        return {
            "kind": self.kind.value,
            "max_age_seconds": None if self.max_age is None else self.max_age.total_seconds(),
            "basis": self.basis,
        }


STRICT_ALIGNMENT = TemporalAlignmentPolicy()


@dataclass(frozen=True, slots=True)
class AlignedValue:
    observation: ChannelObservation
    origin: ValueOrigin
    age: timedelta


@dataclass(frozen=True, slots=True)
class AlignedSample:
    """Values of the requested channels, in request order, for one sample time."""

    aligned_at: datetime
    values: tuple[AlignedValue, ...]

    @property
    def carried(self) -> tuple[AlignedValue, ...]:
        return tuple(v for v in self.values if v.origin == ValueOrigin.CARRIED)


@dataclass(frozen=True, slots=True)
class AlignmentResult:
    samples: tuple[AlignedSample, ...]
    excluded: dict[str, int]


def align_observations(
    observations: Sequence[ChannelObservation],
    channels: Sequence[str],
    policy: TemporalAlignmentPolicy = STRICT_ALIGNMENT,
) -> AlignmentResult:
    """Deterministically align one measurement point's observations of ``channels``.

    A candidate sample time is every timestamp at which any requested channel was
    observed. Observations are those given (for example a finalized window's
    accepted events); nothing outside them is looked up.
    """
    wanted = tuple(channels)
    if len(set(wanted)) != len(wanted) or not wanted:
        raise ValueError("channels must be unique and nonempty")
    points = {o.measurement_point_id for o in observations if o.channel_id in wanted}
    if len(points) > 1:
        raise ValueError("alignment requires observations of a single measurement point")
    by_channel: dict[str, list[ChannelObservation]] = defaultdict(list)
    for observation in observations:
        if observation.channel_id in wanted:
            by_channel[observation.channel_id].append(observation)
    series = {c: sorted(by_channel[c], key=lambda o: o.event_at) for c in wanted}
    times = {c: [o.event_at for o in series[c]] for c in wanted}
    excluded: Counter[str] = Counter()
    samples = []
    for anchor in sorted({o.event_at for group in series.values() for o in group}):
        values: list[AlignedValue | None] = []
        for channel in wanted:
            index = bisect.bisect_right(times[channel], anchor) - 1
            if index < 0:
                values.append(None)
                continue
            observation = series[channel][index]
            age = anchor - observation.event_at
            if age == timedelta(0):
                values.append(AlignedValue(observation, ValueOrigin.OBSERVED, age))
            elif policy.kind == AlignmentPolicyKind.BOUNDED_PREVIOUS and (
                policy.max_age is not None and age <= policy.max_age
            ):
                values.append(AlignedValue(observation, ValueOrigin.CARRIED, age))
            else:
                values.append(None)
        present = tuple(v for v in values if v is not None)
        if len(present) == len(wanted):
            samples.append(AlignedSample(anchor, present))
        elif policy.is_strict:
            excluded[AlignmentExclusion.INCOMPLETE.value] += 1
        else:
            excluded[AlignmentExclusion.NO_RECENT_VALUE.value] += 1
    return AlignmentResult(tuple(samples), dict(excluded))
