"""Five-minute three-phase electrical window features shared by runtime and evaluation.

One function turns time-aligned R/S/T current, R/S/T voltage and frequency samples into the
``electrical-window-v1`` feature vector. The live window runner, package building and the
offline acceptance evaluation all call it, so a model is always scored on exactly the features
it was fitted on. Operating state is decided from current alone (no provider labels): a window
with too few samples at or above the current floor is reported as not evaluated, not as normal.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import fmean, pstdev

from industrial_phm.application.analysis_input import ChannelObservation
from industrial_phm.application.phase_unbalance import unbalance_percent

ELECTRICAL_WINDOW_FEATURE_SET_ID = "electrical-window-v1"
ELECTRICAL_WINDOW_FEATURE_NAMES = (
    "current.phase_r.mean_a",
    "current.phase_s.mean_a",
    "current.phase_t.mean_a",
    "voltage.phase_r.mean_v",
    "voltage.phase_s.mean_v",
    "voltage.phase_t.mean_v",
    "current.unbalance.mean_percent",
    "voltage.unbalance.mean_percent",
    "current.three_phase_mean.std_a",
    "frequency.mean_hz",
)
CURRENT_FLOOR_A = 1.0
MIN_RUNNING_SAMPLES = 3
_PHASES = ("R", "S", "T")


@dataclass(frozen=True, slots=True)
class ElectricalWindowSample:
    """One event time with all seven confirmed channels present and good."""

    at: datetime
    current: tuple[float, float, float]
    voltage: tuple[float, float, float]
    frequency: float

    def __post_init__(self) -> None:
        if self.at.utcoffset() is None:
            raise ValueError("sample time must be timezone-aware")
        values = (*self.current, *self.voltage, self.frequency)
        if len(values) != 7 or not all(math.isfinite(v) and v >= 0 for v in values):
            raise ValueError("electrical window samples need finite non-negative values")


@dataclass(frozen=True, slots=True)
class ElectricalChannelRoles:
    """Channel IDs bound to each role by measurement meaning, never by channel name."""

    current: tuple[str, str, str]
    voltage: tuple[str, str, str]
    frequency: str

    @property
    def channels(self) -> tuple[str, ...]:
        return (*self.current, *self.voltage, self.frequency)


def resolve_electrical_roles(
    observations: Sequence[ChannelObservation],
) -> tuple[ElectricalChannelRoles | None, str | None]:
    """Bind roles from the observations' own semantic snapshots; ambiguity is a reason."""
    roles: dict[tuple[str, str], set[str]] = defaultdict(set)
    for item in observations:
        if item.observed_property == "phase current" and item.unit == "A":
            for phase in _PHASES:
                if item.scope == f"phase {phase}":
                    roles[("current", phase)].add(item.channel_id)
        elif item.observed_property == "phase voltage" and item.unit == "V":
            for phase in _PHASES:
                if item.scope == f"phase {phase}":
                    roles[("voltage", phase)].add(item.channel_id)
        elif item.observed_property == "frequency" and item.unit == "Hz":
            roles[("frequency", "")].add(item.channel_id)
    needed = [("current", p) for p in _PHASES] + [("voltage", p) for p in _PHASES]
    needed.append(("frequency", ""))
    missing = [f"{q} {p}".strip() for q, p in needed if not roles.get((q, p))]
    if missing:
        return None, "confirmed channel meaning missing: " + ", ".join(missing)
    ambiguous = [f"{q} {p}".strip() for q, p in needed if len(roles[(q, p)]) > 1]
    if ambiguous:
        return None, "ambiguous channel meaning: " + ", ".join(ambiguous)
    pick = {key: next(iter(value)) for key, value in roles.items()}
    return (
        ElectricalChannelRoles(
            current=tuple(pick[("current", p)] for p in _PHASES),  # type: ignore[arg-type]
            voltage=tuple(pick[("voltage", p)] for p in _PHASES),  # type: ignore[arg-type]
            frequency=pick[("frequency", "")],
        ),
        None,
    )


def align_electrical_samples(
    observations: Sequence[ChannelObservation], roles: ElectricalChannelRoles
) -> tuple[tuple[ElectricalWindowSample, ...], dict[str, int]]:
    """Strict same-time alignment; incomplete, conflicting or non-good times are counted out."""
    by_time: dict[datetime, dict[str, ChannelObservation]] = defaultdict(dict)
    duplicate: set[datetime] = set()
    wanted = set(roles.channels)
    for item in observations:
        if item.channel_id not in wanted:
            continue
        if item.channel_id in by_time[item.event_at]:
            duplicate.add(item.event_at)
        by_time[item.event_at][item.channel_id] = item
    samples: list[ElectricalWindowSample] = []
    excluded: dict[str, int] = defaultdict(int)
    for at in sorted(by_time):
        group = by_time[at]
        if at in duplicate or any(o.conflicting for o in group.values()):
            excluded["conflicting"] += 1
        elif set(group) != wanted:
            excluded["incomplete"] += 1
        elif not all(o.source_quality_good for o in group.values()):
            excluded["non-good-quality"] += 1
        elif any(
            o.value is None or not math.isfinite(o.value) or o.value < 0 for o in group.values()
        ):
            excluded["missing-value"] += 1
        else:
            value = {channel: float(group[channel].value or 0.0) for channel in wanted}
            samples.append(
                ElectricalWindowSample(
                    at=at,
                    current=tuple(value[c] for c in roles.current),  # type: ignore[arg-type]
                    voltage=tuple(value[c] for c in roles.voltage),  # type: ignore[arg-type]
                    frequency=value[roles.frequency],
                )
            )
    return tuple(samples), dict(excluded)


def electrical_window_features(
    samples: Sequence[ElectricalWindowSample],
) -> tuple[Mapping[str, float] | None, str | None, int]:
    """Return (features, skip reason, running sample count) for one window."""
    running = [s for s in samples if fmean(s.current) >= CURRENT_FLOOR_A and fmean(s.voltage) > 0]
    if len(running) < MIN_RUNNING_SAMPLES:
        return (
            None,
            f"not evaluated: {len(running)} running samples (current >= {CURRENT_FLOOR_A} A), "
            f"{MIN_RUNNING_SAMPLES} required",
            len(running),
        )
    values = [
        *(fmean(s.current[i] for s in running) for i in range(3)),
        *(fmean(s.voltage[i] for s in running) for i in range(3)),
        fmean(unbalance_percent(s.current) for s in running),
        fmean(unbalance_percent(s.voltage) for s in running),
        pstdev(fmean(s.current) for s in running),
        fmean(s.frequency for s in running),
    ]
    return dict(zip(ELECTRICAL_WINDOW_FEATURE_NAMES, values, strict=True)), None, len(running)
