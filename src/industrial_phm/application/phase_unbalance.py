"""Label-free three-phase unbalance evidence from Asset History.

Unbalance at one timestamp is the largest deviation of the three phase values
from their mean, as a percentage of that mean (phase-based definition). It is a
descriptive power-quality measurement: not a fault, health state, alarm or
maintenance recommendation, and it never reads provider annotations.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from statistics import median, quantiles
from typing import Protocol, runtime_checkable
from uuid import uuid4

from industrial_phm.application.alignment import (
    STRICT_ALIGNMENT,
    TemporalAlignmentPolicy,
    align_observations,
)
from industrial_phm.application.analysis_input import (
    ChannelObservation,
    WindowInputReference,
    window_channel_candidates,
    window_channel_observations,
    window_input_reference,
)
from industrial_phm.application.asset_history import HistoricalInputReference
from industrial_phm.application.measurement_semantics import ChannelSemanticCandidate
from industrial_phm.application.observation_window import DurableObservationWindow
from industrial_phm.application.operational import AnalysisRun
from industrial_phm.contracts import (
    DataQualityAssessment,
    DataQualityIssue,
    DataQualitySeverity,
)

PHASE_UNBALANCE_CAPABILITY_ID = "three-phase-unbalance-v1"
PHASE_UNBALANCE_ALGORITHM_VERSION = "phase-unbalance-max-deviation-v2"
PHASE_UNBALANCE_POLICY_DIGEST_VERSION = "phase-unbalance-policy-v1"
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
    NO_RECENT_PHASE_VALUE = "no-recent-phase-value"
    LOW_SIGNAL = "low-signal"


class ChannelSelection(StrEnum):
    """How a quantity's three input channels were chosen."""

    SEMANTIC_ROLE = "semantic-role"
    EXPLICIT = "explicit"
    UNRESOLVED = "unresolved"


_SOURCE_QUALITY_EXCLUSIONS = frozenset(
    {
        ExclusionReason.NULL_VALUE.value,
        ExclusionReason.CONFLICTING_VALUE.value,
        ExclusionReason.NON_GOOD_QUALITY.value,
    }
)


@runtime_checkable
class ChannelObservationReader(Protocol):
    def current_snapshot_id(self) -> int: ...

    def list_channel_semantics(
        self,
        asset_id: str,
        *,
        source_id: str,
        start_at: datetime,
        end_at: datetime,
        snapshot_id: int,
    ) -> tuple[ChannelSemanticCandidate, ...]: ...

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
    """Explicit, persisted configuration.

    Channels left as None are chosen by semantic role (phase voltage/current, scope
    phase R/S/T, unit V/A) from the input's bound semantics, so no source-specific
    channel name is assumed. Given channels are used as an explicit override.
    """

    voltage_channels: tuple[str, str, str] | None = None
    current_channels: tuple[str, str, str] | None = None
    min_mean_voltage_v: float = 50.0
    min_mean_current_a: float = 1.0
    bucket_count: int = 200
    alignment: TemporalAlignmentPolicy = STRICT_ALIGNMENT

    def __post_init__(self) -> None:
        if not isinstance(self.alignment, TemporalAlignmentPolicy):
            raise ValueError("alignment must be a TemporalAlignmentPolicy")
        given = [c for c in (self.voltage_channels, self.current_channels) if c is not None]
        if any(len(group) != 3 for group in given):
            raise ValueError("each quantity requires exactly three phase channels")
        channels = [channel for group in given for channel in group]
        if len(set(channels)) != len(channels) or not all(c.strip() for c in channels):
            raise ValueError("phase channels must be unique and nonempty")
        for threshold in (self.min_mean_voltage_v, self.min_mean_current_a):
            if isinstance(threshold, bool) or not math.isfinite(threshold) or threshold <= 0:
                raise ValueError("signal thresholds must be positive and finite")
        if isinstance(self.bucket_count, bool) or not 1 <= self.bucket_count <= _MAX_BUCKETS:
            raise ValueError(f"bucket_count must be between 1 and {_MAX_BUCKETS}")

    def channels(self, quantity: UnbalanceQuantity) -> tuple[str, str, str] | None:
        if quantity == UnbalanceQuantity.VOLTAGE:
            return self.voltage_channels
        return self.current_channels

    def min_mean(self, quantity: UnbalanceQuantity) -> float:
        if quantity == UnbalanceQuantity.VOLTAGE:
            return self.min_mean_voltage_v
        return self.min_mean_current_a


def phase_unbalance_policy_digest(config: PhaseUnbalanceConfig | None = None) -> str:
    """Stable identity of the requested analysis policy before role resolution."""
    policy = config or PhaseUnbalanceConfig()
    payload = {
        "version": PHASE_UNBALANCE_POLICY_DIGEST_VERSION,
        "voltage_channels": (
            None if policy.voltage_channels is None else list(policy.voltage_channels)
        ),
        "current_channels": (
            None if policy.current_channels is None else list(policy.current_channels)
        ),
        "min_mean_voltage_v": float(policy.min_mean_voltage_v),
        "min_mean_current_a": float(policy.min_mean_current_a),
        "bucket_count": policy.bucket_count,
        # Strict alignment is the original behavior; omitting it keeps the identity
        # of results recorded before alignment policies existed.
        **(
            {}
            if policy.alignment.is_strict
            else {"alignment": policy.alignment.computational_identity()}
        ),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


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
    channels: tuple[str, ...] = ()
    channel_selection: ChannelSelection = ChannelSelection.EXPLICIT
    carried_values: int = 0
    max_carry_age_seconds: float | None = None
    p95_carry_age_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class PhaseUnbalanceEvidence:
    """Everything needed to recompute and interpret one unbalance result."""

    evidence_id: str
    analysis_run_id: str
    input_reference: HistoricalInputReference | WindowInputReference
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


def resolve_phase_channels(
    candidates: Sequence[ChannelSemanticCandidate],
) -> dict[UnbalanceQuantity, tuple[str, str, str] | None]:
    """Choose one channel per quantity and phase by bound meaning.

    A quantity is resolved only when each of R, S and T maps to exactly one
    channel. Two channels claiming one role, or one channel claiming two roles,
    is ambiguous and must be settled by explicit configuration.
    """
    roles: dict[tuple[UnbalanceQuantity, str], set[str]] = defaultdict(set)
    for candidate in candidates:
        for quantity, (prop, unit) in _REQUIRED_SEMANTICS.items():
            for phase in _PHASES:
                if (
                    candidate.observed_property == prop
                    and candidate.unit == unit
                    and candidate.scope == f"phase {phase}"
                ):
                    roles[(quantity, phase)].add(candidate.channel_id)
    claimed: dict[str, set[tuple[UnbalanceQuantity, str]]] = defaultdict(set)
    for role, channels in roles.items():
        for channel in channels:
            claimed[channel].add(role)
    ambiguous = {role: sorted(chs) for role, chs in roles.items() if len(chs) > 1}
    ambiguous.update(
        {role: [channel] for channel, rs in claimed.items() if len(rs) > 1 for role in rs}
    )
    if ambiguous:
        detail = "; ".join(
            f"{quantity.value} phase {phase}: {', '.join(channels)}"
            for (quantity, phase), channels in sorted(ambiguous.items())
        )
        raise ValueError(f"ambiguous phase channel roles ({detail}); configure channels explicitly")
    resolved: dict[UnbalanceQuantity, tuple[str, str, str] | None] = {}
    for quantity in UnbalanceQuantity:
        r, s, t = (sorted(roles[(quantity, phase)]) for phase in _PHASES)
        resolved[quantity] = (r[0], s[0], t[0]) if r and s and t else None
    return resolved


def _series(
    observations: Sequence[ChannelObservation],
    quantity: UnbalanceQuantity,
    channels: tuple[str, str, str],
    selection: ChannelSelection,
    config: PhaseUnbalanceConfig,
    start_at: datetime,
    end_at: datetime,
) -> tuple[UnbalanceSeriesResult, set[str], list[datetime]]:
    phase_of = dict(zip(channels, _PHASES, strict=True))
    prop, unit = _REQUIRED_SEMANTICS[quantity]
    aligned = align_observations(observations, channels, config.alignment)
    excluded: Counter[str] = Counter(aligned.excluded)
    samples: list[tuple[datetime, float]] = []
    versions: set[str] = set()
    carry_ages: list[float] = []
    for sample in aligned.samples:
        event_at = sample.aligned_at
        phases = [value.observation for value in sample.values]
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
        carry_ages += [value.age.total_seconds() for value in sample.carried]
    if not samples:
        return (
            UnbalanceSeriesResult(
                quantity, 0, dict(excluded), channels=channels, channel_selection=selection
            ),
            versions,
            [],
        )
    percents = [p for _, p in samples]
    max_at, max_percent = max(samples, key=lambda item: (item[1], -item[0].timestamp()))
    width = (end_at - start_at) / config.bucket_count
    by_bucket: dict[int, list[float]] = defaultdict(list)
    for event_at, percent in samples:
        index = min(int((event_at - start_at) / width), config.bucket_count - 1)
        by_bucket[index].append(percent)
    buckets = tuple(
        UnbalanceBucket(
            start_at + width * index,
            min(end_at, start_at + width * (index + 1)),
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
            channels,
            selection,
            len(carry_ages),
            max(carry_ages, default=None),
            (
                quantiles(carry_ages, n=20, method="inclusive")[18]
                if len(carry_ages) > 1
                else next(iter(carry_ages), None)
            ),
        ),
        versions,
        [event_at for event_at, _ in samples],
    )


_Chosen = dict[UnbalanceQuantity, tuple[str, str, str] | None]


def _choose_channels(
    requested: PhaseUnbalanceConfig,
    candidates: Callable[[], Sequence[ChannelSemanticCandidate]],
    measurement_point_id: str | None,
) -> tuple[_Chosen, dict[UnbalanceQuantity, ChannelSelection], PhaseUnbalanceConfig]:
    """Explicit channels win; the rest are resolved by semantic role."""
    selection: dict[UnbalanceQuantity, ChannelSelection] = {}
    chosen: _Chosen = {quantity: requested.channels(quantity) for quantity in UnbalanceQuantity}
    if any(group is None for group in chosen.values()):
        found = tuple(candidates())
        if measurement_point_id is not None:
            found = tuple(c for c in found if c.measurement_point_id == measurement_point_id)
        elif len({c.measurement_point_id for c in found}) > 1:
            raise ValueError(
                "analysis source contains multiple measurement points; "
                "select measurement_point_id explicitly"
            )
        by_role = resolve_phase_channels(found)
        for quantity, given in chosen.items():
            if given is None:
                chosen[quantity] = by_role[quantity]
                selection[quantity] = (
                    ChannelSelection.UNRESOLVED
                    if by_role[quantity] is None
                    else ChannelSelection.SEMANTIC_ROLE
                )
    for quantity in UnbalanceQuantity:
        selection.setdefault(quantity, ChannelSelection.EXPLICIT)
    if all(group is None for group in chosen.values()):
        raise ValueError(
            "no three-phase voltage or current channels are bound by semantic role; "
            "check semantic bindings or configure channels explicitly"
        )
    # The persisted configuration names the channels actually used, so a recorded
    # result recomputes from its evidence without resolving roles again.
    effective = PhaseUnbalanceConfig(
        voltage_channels=chosen[UnbalanceQuantity.VOLTAGE],
        current_channels=chosen[UnbalanceQuantity.CURRENT],
        min_mean_voltage_v=requested.min_mean_voltage_v,
        min_mean_current_a=requested.min_mean_current_a,
        bucket_count=requested.bucket_count,
        alignment=requested.alignment,
    )
    return chosen, selection, effective


def _used_channels(chosen: _Chosen) -> tuple[str, ...]:
    return tuple(channel for group in chosen.values() if group is not None for channel in group)


def _analyze(
    observations: Sequence[ChannelObservation],
    chosen: _Chosen,
    selection: dict[UnbalanceQuantity, ChannelSelection],
    effective: PhaseUnbalanceConfig,
    *,
    reference: HistoricalInputReference | WindowInputReference,
    asset_id: str,
    source_id: str,
    measurement_point_id: str | None,
    started_at: datetime,
    now: Callable[[], datetime],
) -> PhaseUnbalanceAnalysis:
    """Capability core shared by history-snapshot and finalized-window input."""
    results = []
    versions: set[str] = set()
    sample_times: list[datetime] = []
    for quantity in UnbalanceQuantity:
        quantity_channels = chosen[quantity]
        if quantity_channels is None:
            results.append(
                UnbalanceSeriesResult(
                    quantity, 0, {}, channel_selection=ChannelSelection.UNRESOLVED
                )
            )
            continue
        result, used_versions, times = _series(
            observations,
            quantity,
            quantity_channels,
            selection[quantity],
            effective,
            reference.start_at,
            reference.end_at,
        )
        results.append(result)
        versions |= used_versions
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
    run = AnalysisRun(
        analysis_run_id=run_id,
        asset_id=asset_id,
        source_id=source_id,
        observed_start_at=min(sample_times),
        observed_end_at=max(sample_times),
        started_at=started_at,
        completed_at=now(),
        data_quality=DataQualityAssessment(issues),
        measurement_point_id=measurement_point_id,
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
    requested = config or PhaseUnbalanceConfig()
    started_at = now()
    snapshot = history.current_snapshot_id() if snapshot_id is None else snapshot_id
    chosen, selection, effective = _choose_channels(
        requested,
        lambda: history.list_channel_semantics(
            asset_id, source_id=source_id, start_at=start_at, end_at=end_at, snapshot_id=snapshot
        ),
        measurement_point_id,
    )
    channels = _used_channels(chosen)
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
    return _analyze(
        observations,
        chosen,
        selection,
        effective,
        reference=reference,
        asset_id=asset_id,
        source_id=source_id,
        measurement_point_id=resolved_point,
        started_at=started_at,
        now=now,
    )


def run_phase_unbalance_on_window(
    window: DurableObservationWindow,
    *,
    config: PhaseUnbalanceConfig | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> PhaseUnbalanceAnalysis:
    """Analyze exactly the events a finalized window accepted (ADR-0008).

    The window range is never re-queried from history; the evidence records the
    window identity and a digest of its accepted events.
    """
    requested = config or PhaseUnbalanceConfig()
    started_at = now()
    chosen, selection, effective = _choose_channels(
        requested, lambda: window_channel_candidates(window), window.measurement_point_id
    )
    channels = set(_used_channels(chosen))
    observations = tuple(o for o in window_channel_observations(window) if o.channel_id in channels)
    return _analyze(
        observations,
        chosen,
        selection,
        effective,
        reference=window_input_reference(window),
        asset_id=window.asset_id,
        source_id=window.source_id,
        measurement_point_id=window.measurement_point_id,
        started_at=started_at,
        now=now,
    )
