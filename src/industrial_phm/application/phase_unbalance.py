"""Label-free three-phase unbalance evidence from Asset History.

Unbalance at one timestamp is the largest deviation of the three phase values
from their mean, as a percentage of that mean (phase-based definition). It is a
descriptive power-quality measurement: not a fault, health state, alarm or
maintenance recommendation, and it never reads provider annotations.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from statistics import median, quantiles
from typing import Protocol, runtime_checkable
from uuid import uuid4

from industrial_phm.application.asset_history import HistoricalInputReference
from industrial_phm.application.operational import AnalysisRun
from industrial_phm.contracts import (
    DataQualityAssessment,
    DataQualityIssue,
    DataQualitySeverity,
)

PHASE_UNBALANCE_CAPABILITY_ID = "three-phase-unbalance-v1"
PHASE_UNBALANCE_ALGORITHM_VERSION = "phase-unbalance-max-deviation-v2"
_PHASES = ("R", "S", "T")
_MAX_BUCKETS = 1000


class UnbalanceQuantity(StrEnum):
    VOLTAGE = "voltage"
    CURRENT = "current"


# Only observations bound to exactly these meanings are eligible input.
_REQUIRED_SEMANTICS = {
    UnbalanceQuantity.VOLTAGE: ("phase voltage", "V"),
    UnbalanceQuantity.CURRENT: ("phase current", "A"),
}


class ExclusionReason(StrEnum):
    UNCONFIRMED_SEMANTICS = "unconfirmed-semantics"
    NULL_VALUE = "null-value"
    CONFLICTING_VALUE = "conflicting-value"
    NON_GOOD_QUALITY = "non-good-source-quality"
    INCOMPLETE_PHASES = "incomplete-phases"
    LOW_SIGNAL = "low-signal"


_SOURCE_QUALITY_EXCLUSIONS = frozenset(
    {
        ExclusionReason.NULL_VALUE.value,
        ExclusionReason.CONFLICTING_VALUE.value,
        ExclusionReason.NON_GOOD_QUALITY.value,
    }
)


@dataclass(frozen=True, slots=True)
class ChannelObservation:
    """One (source, point, channel, event time) group read from Asset History."""

    source_id: str
    measurement_point_id: str | None
    channel_id: str
    event_at: datetime
    value: float | None
    conflicting: bool
    source_quality_good: bool
    observed_property: str | None
    scope: str | None
    unit: str | None
    semantic_version: str | None


@runtime_checkable
class ChannelObservationReader(Protocol):
    def current_snapshot_id(self) -> int: ...

    def query_channel_observations(
        self,
        asset_id: str,
        *,
        source_id: str,
        channel_ids: Sequence[str],
        start_at: datetime,
        end_at: datetime,
        snapshot_id: int,
    ) -> tuple[ChannelObservation, ...]: ...


@dataclass(frozen=True, slots=True)
class PhaseUnbalanceConfig:
    """Explicit, persisted configuration; defaults follow AI-Hub 239 channel names."""

    voltage_channels: tuple[str, str, str] = ("R상전압", "S상전압", "T상전압")
    current_channels: tuple[str, str, str] = ("R상전류", "S상전류", "T상전류")
    min_mean_voltage_v: float = 50.0
    min_mean_current_a: float = 1.0
    bucket_count: int = 200

    def __post_init__(self) -> None:
        channels = (*self.voltage_channels, *self.current_channels)
        if len(self.voltage_channels) != 3 or len(self.current_channels) != 3:
            raise ValueError("each quantity requires exactly three phase channels")
        if len(set(channels)) != len(channels) or not all(c.strip() for c in channels):
            raise ValueError("phase channels must be unique and nonempty")
        for threshold in (self.min_mean_voltage_v, self.min_mean_current_a):
            if isinstance(threshold, bool) or not math.isfinite(threshold) or threshold <= 0:
                raise ValueError("signal thresholds must be positive and finite")
        if isinstance(self.bucket_count, bool) or not 1 <= self.bucket_count <= _MAX_BUCKETS:
            raise ValueError(f"bucket_count must be between 1 and {_MAX_BUCKETS}")

    def channels(self, quantity: UnbalanceQuantity) -> tuple[str, str, str]:
        if quantity == UnbalanceQuantity.VOLTAGE:
            return self.voltage_channels
        return self.current_channels

    def min_mean(self, quantity: UnbalanceQuantity) -> float:
        if quantity == UnbalanceQuantity.VOLTAGE:
            return self.min_mean_voltage_v
        return self.min_mean_current_a


@dataclass(frozen=True, slots=True)
class UnbalanceBucket:
    start_at: datetime
    end_at: datetime
    sample_count: int
    median_percent: float
    max_percent: float


@dataclass(frozen=True, slots=True)
class UnbalanceSeriesResult:
    """Distribution of per-timestamp unbalance for one quantity; percent units."""

    quantity: UnbalanceQuantity
    evaluated_samples: int
    excluded_samples: dict[str, int]
    median_percent: float | None = None
    p95_percent: float | None = None
    max_percent: float | None = None
    max_at: datetime | None = None
    buckets: tuple[UnbalanceBucket, ...] = ()


@dataclass(frozen=True, slots=True)
class PhaseUnbalanceEvidence:
    """Everything needed to recompute and interpret one unbalance result."""

    evidence_id: str
    analysis_run_id: str
    input_reference: HistoricalInputReference
    source_id: str
    config: PhaseUnbalanceConfig
    semantic_versions: tuple[str, ...]
    results: tuple[UnbalanceSeriesResult, ...]
    capability_id: str = PHASE_UNBALANCE_CAPABILITY_ID
    algorithm_version: str = PHASE_UNBALANCE_ALGORITHM_VERSION
    interpretation: str = field(
        default=(
            "descriptive power-quality measurement; not a fault, health state, alarm or "
            "maintenance recommendation"
        )
    )


@dataclass(frozen=True, slots=True)
class PhaseUnbalanceAnalysis:
    run: AnalysisRun
    evidence: PhaseUnbalanceEvidence

    def __post_init__(self) -> None:
        if self.evidence.analysis_run_id != self.run.analysis_run_id:
            raise ValueError("evidence analysis_run_id must match the run")
        if self.evidence.capability_id not in self.run.capability_ids:
            raise ValueError("evidence capability must be declared by the run")


def unbalance_percent(values: Sequence[float]) -> float:
    """Largest deviation from the mean as a percentage of the mean."""
    mean = sum(values) / len(values)
    return max(abs(v - mean) for v in values) / mean * 100


def _series(
    observations: Sequence[ChannelObservation],
    quantity: UnbalanceQuantity,
    config: PhaseUnbalanceConfig,
    reference: HistoricalInputReference,
) -> tuple[UnbalanceSeriesResult, set[str], list[datetime]]:
    channels = config.channels(quantity)
    phase_of = dict(zip(channels, _PHASES, strict=True))
    prop, unit = _REQUIRED_SEMANTICS[quantity]
    grouped: dict[tuple[str | None, datetime], dict[str, ChannelObservation]] = defaultdict(dict)
    for observation in observations:
        if observation.channel_id in phase_of:
            key = (observation.measurement_point_id, observation.event_at)
            grouped[key][observation.channel_id] = observation
    excluded: Counter[str] = Counter()
    samples: list[tuple[datetime, float]] = []
    versions: set[str] = set()
    for (_, event_at), by_channel in sorted(grouped.items(), key=lambda item: item[0][1]):
        if len(by_channel) != 3:
            excluded[ExclusionReason.INCOMPLETE_PHASES.value] += 1
            continue
        phases = [by_channel[channel] for channel in channels]
        if any(
            o.observed_property != prop
            or o.unit != unit
            or o.scope != f"phase {phase_of[o.channel_id]}"
            for o in phases
        ):
            excluded[ExclusionReason.UNCONFIRMED_SEMANTICS.value] += 1
            continue
        if any(o.conflicting for o in phases):
            excluded[ExclusionReason.CONFLICTING_VALUE.value] += 1
            continue
        if not all(o.source_quality_good for o in phases):
            excluded[ExclusionReason.NON_GOOD_QUALITY.value] += 1
            continue
        values = [o.value for o in phases]
        if any(v is None for v in values):
            excluded[ExclusionReason.NULL_VALUE.value] += 1
            continue
        present = [float(v) for v in values if v is not None]
        if sum(present) / 3 < config.min_mean(quantity):
            excluded[ExclusionReason.LOW_SIGNAL.value] += 1
            continue
        samples.append((event_at, unbalance_percent(present)))
        versions.update(o.semantic_version for o in phases if o.semantic_version)
    if not samples:
        return UnbalanceSeriesResult(quantity, 0, dict(excluded)), versions, []
    percents = [p for _, p in samples]
    max_at, max_percent = max(samples, key=lambda item: (item[1], -item[0].timestamp()))
    width = (reference.end_at - reference.start_at) / config.bucket_count
    by_bucket: dict[int, list[float]] = defaultdict(list)
    for event_at, percent in samples:
        index = min(int((event_at - reference.start_at) / width), config.bucket_count - 1)
        by_bucket[index].append(percent)
    buckets = tuple(
        UnbalanceBucket(
            reference.start_at + width * index,
            min(reference.end_at, reference.start_at + width * (index + 1)),
            len(values),
            median(values),
            max(values),
        )
        for index, values in sorted(by_bucket.items())
    )
    return (
        UnbalanceSeriesResult(
            quantity,
            len(samples),
            dict(excluded),
            median(percents),
            quantiles(percents, n=20, method="inclusive")[18] if len(percents) > 1 else percents[0],
            max_percent,
            max_at,
            buckets,
        ),
        versions,
        [event_at for event_at, _ in samples],
    )


def run_phase_unbalance_analysis(
    history: ChannelObservationReader,
    *,
    asset_id: str,
    source_id: str,
    start_at: datetime,
    end_at: datetime,
    config: PhaseUnbalanceConfig | None = None,
    measurement_point_id: str | None = None,
    snapshot_id: int | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> PhaseUnbalanceAnalysis:
    """Read one source at a fixed history snapshot and compute unbalance evidence.

    Passing a recorded snapshot_id recomputes a previous result exactly, even
    after more history has been appended.
    """
    effective = config or PhaseUnbalanceConfig()
    started_at = now()
    snapshot = history.current_snapshot_id() if snapshot_id is None else snapshot_id
    channels = (*effective.voltage_channels, *effective.current_channels)
    observations = history.query_channel_observations(
        asset_id,
        source_id=source_id,
        channel_ids=channels,
        start_at=start_at,
        end_at=end_at,
        snapshot_id=snapshot,
    )
    points = {observation.measurement_point_id for observation in observations}
    if measurement_point_id is None:
        if len(points) > 1:
            raise ValueError(
                "analysis source contains multiple measurement points; "
                "select measurement_point_id explicitly"
            )
        resolved_point = next(iter(points), None)
    else:
        resolved_point = measurement_point_id
        observations = tuple(
            observation
            for observation in observations
            if observation.measurement_point_id == measurement_point_id
        )
    reference = HistoricalInputReference(
        snapshot_id=snapshot,
        asset_id=asset_id,
        start_at=start_at,
        end_at=end_at,
        measurement_point_id=resolved_point,
        channel_ids=channels,
    )
    results = []
    versions: set[str] = set()
    sample_times: list[datetime] = []
    for quantity in UnbalanceQuantity:
        result, used, times = _series(observations, quantity, effective, reference)
        results.append(result)
        versions |= used
        sample_times += times
    if not sample_times:
        raise ValueError(
            "no eligible three-phase samples; check semantics, range and signal thresholds"
        )
    issues = [
        DataQualityIssue(
            f"excluded-{r.quantity.value}-{reason}",
            DataQualitySeverity.WARNING,
            f"{count} {r.quantity.value} timestamps excluded: {reason}",
        )
        for r in results
        for reason, count in sorted(r.excluded_samples.items())
        if reason in _SOURCE_QUALITY_EXCLUSIONS
    ]
    run_id = f"analysis-run-{uuid4()}"
    completed_at = now()
    run = AnalysisRun(
        analysis_run_id=run_id,
        asset_id=asset_id,
        source_id=source_id,
        observed_start_at=min(sample_times),
        observed_end_at=max(sample_times),
        started_at=started_at,
        completed_at=completed_at,
        data_quality=DataQualityAssessment(issues),
        measurement_point_id=resolved_point,
        capability_ids=(PHASE_UNBALANCE_CAPABILITY_ID,),
    )
    evidence = PhaseUnbalanceEvidence(
        evidence_id=f"evidence-{uuid4()}",
        analysis_run_id=run_id,
        input_reference=reference,
        source_id=source_id,
        config=effective,
        semantic_versions=tuple(sorted(versions)),
        results=tuple(results),
    )
    return PhaseUnbalanceAnalysis(run, evidence)
