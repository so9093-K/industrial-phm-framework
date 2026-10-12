"""AI-Hub 239 air-compressor electrical anomaly packages and their acceptance evaluation.

Implements the operational inference acceptance protocol v1 §3 without provider labels:
per-device packages are fitted on the first 70% of each device's Training/raw record, and the
last 30% is used only to measure (a) the review-window rate with no injection and (b) detection
of known injected changes. Every score goes through the same window feature function, model
package and review-interval rule the operational runner uses.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from industrial_phm.adapters.aihub_power import iter_power_observations
from industrial_phm.adapters.aihub_power_history import AIHUB_239_SEMANTICS_V3, interpret_channel
from industrial_phm.application.analysis_input import ChannelObservation
from industrial_phm.application.electrical_window_features import (
    ELECTRICAL_WINDOW_FEATURE_NAMES,
    ELECTRICAL_WINDOW_FEATURE_SET_ID,
    ElectricalWindowSample,
    align_electrical_samples,
    electrical_window_features,
    resolve_electrical_roles,
)
from industrial_phm.application.phm_analysis import PreparedStep, advance_review_interval
from industrial_phm.models.package import (
    AffinePreprocessing,
    EstimatorKind,
    LoadedModelPackage,
    ModelTask,
    PackageBuild,
    PackageInputSpec,
    PackageOutputSpec,
    ReviewIntervalRule,
    StepKind,
    load_model_package,
    write_model_package,
)

TIMEZONE = "Asia/Seoul"
WINDOW = timedelta(minutes=5)
TRAIN_FRACTION = 0.7
THRESHOLD_QUANTILE = 0.995
INTERVAL_RULE = ReviewIntervalRule(min_consecutive_steps=2, max_gap_steps=1)
DETECTION_WINDOW = timedelta(minutes=20)
MIN_TRAIN_RUNNING = 2_880
MIN_HOLDOUT_RUNNING = 1_440
SEED = 239
INJECTIONS_PER_TYPE = 3
REQUIRED_CHANNELS = ("R상전류", "S상전류", "T상전류", "R상전압", "S상전압", "T상전압", "주파수")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Injection:
    kind: str
    duration: timedelta
    gate: bool

    def apply(
        self, sample: ElectricalWindowSample, start: datetime, phase: int
    ) -> ElectricalWindowSample:
        if not start <= sample.at < start + self.duration:
            return sample
        current, voltage, frequency = list(sample.current), list(sample.voltage), sample.frequency
        if self.kind == "phase-loss":
            current = [c * (0.05 if i == phase else 1.15) for i, c in enumerate(current)]
        elif self.kind == "current-imbalance":
            current[phase] *= 1.25
        elif self.kind == "voltage-sag":
            voltage[phase] *= 0.90
        elif self.kind == "frequency-deviation":
            frequency += 0.5
        elif self.kind == "gradual-load-increase":
            factor = 1 + 0.3 * (sample.at - start) / self.duration
            current = [c * factor for c in current]
        return replace(sample, current=tuple(current), voltage=tuple(voltage), frequency=frequency)  # type: ignore[arg-type]


INJECTIONS = (
    Injection("phase-loss", timedelta(minutes=30), gate=True),
    Injection("current-imbalance", timedelta(minutes=30), gate=True),
    Injection("voltage-sag", timedelta(minutes=30), gate=True),
    Injection("frequency-deviation", timedelta(minutes=30), gate=True),
    Injection("gradual-load-increase", timedelta(hours=6), gate=False),
)


@dataclass(frozen=True, slots=True)
class DeviceRecord:
    member: str
    device_id: str
    samples: tuple[ElectricalWindowSample, ...]
    ineligible_reason: str | None
    excluded: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class WindowRow:
    start: datetime
    features: Mapping[str, float] | None
    reason: str | None


# Loading -----------------------------------------------------------------------


def load_device(archive: Path, member: str, *, archive_sha256: str) -> DeviceRecord:
    """Read one member with semantics-v3 meaning; duplicates with different values conflict."""
    zone = ZoneInfo(TIMEZONE)
    grouped: dict[tuple[str, datetime], set[float | None]] = defaultdict(set)
    device_id = ""
    for record in iter_power_observations(archive, member):
        device_id = record.device_id
        if record.channel_name not in REQUIRED_CHANNELS:
            continue
        at = datetime.fromisoformat(record.timestamp_text).replace(tzinfo=zone).astimezone(UTC)
        grouped[(record.channel_name, at)].add(record.value)
    definitions = {
        name: interpret_channel(
            AIHUB_239_SEMANTICS_V3, name, archive_sha256=archive_sha256, member=member
        ).definition
        for name in REQUIRED_CHANNELS
    }
    observations = []
    for (channel, at), values in grouped.items():
        definition = definitions[channel]
        observations.append(
            ChannelObservation(
                source_id=f"aihub239:{member}",
                measurement_point_id=None,
                channel_id=channel,
                event_at=at,
                value=next(iter(values)) if len(values) == 1 else None,
                conflicting=len(values) > 1,
                source_quality_good=True,
                observed_property=definition.observed_property,
                scope=definition.scope,
                unit=definition.unit,
                semantic_version=AIHUB_239_SEMANTICS_V3,
            )
        )
    roles, reason = resolve_electrical_roles(observations)
    if roles is None:
        return DeviceRecord(member, device_id, (), reason, {})
    samples, excluded = align_electrical_samples(observations, roles)
    return DeviceRecord(member, device_id, samples, None, excluded)


def split_device(
    samples: Sequence[ElectricalWindowSample],
) -> tuple[tuple[ElectricalWindowSample, ...], tuple[ElectricalWindowSample, ...], datetime]:
    """First 70% of the recorded time span trains; the boundary is snapped to the window grid."""
    first, last = samples[0].at, samples[-1].at
    raw = first + (last - first) * TRAIN_FRACTION
    boundary = _window_start(raw)
    return (
        tuple(s for s in samples if s.at < boundary),
        tuple(s for s in samples if s.at >= boundary),
        boundary,
    )


def running_count(samples: Iterable[ElectricalWindowSample]) -> int:
    return sum(1 for s in samples if sum(s.current) / 3 >= 1.0)


def window_rows(samples: Sequence[ElectricalWindowSample]) -> tuple[WindowRow, ...]:
    """Bucket samples into epoch-aligned 5-minute windows, as the runtime coordinator does."""
    buckets: dict[datetime, list[ElectricalWindowSample]] = defaultdict(list)
    for sample in samples:
        buckets[_window_start(sample.at)].append(sample)
    rows = []
    for start in sorted(buckets):
        features, reason, _ = electrical_window_features(buckets[start])
        rows.append(WindowRow(start, features, reason))
    return tuple(rows)


def _window_start(at: datetime) -> datetime:
    seconds = WINDOW.total_seconds()
    return _EPOCH + timedelta(seconds=math.floor((at - _EPOCH).total_seconds() / seconds) * seconds)


# Packages ----------------------------------------------------------------------


def input_spec() -> PackageInputSpec:
    return PackageInputSpec(
        step_kind=StepKind.OBSERVATION_WINDOW,
        channels=("phase current R/S/T [A]", "phase voltage R/S/T [V]", "frequency [Hz]"),
        feature_set_id=ELECTRICAL_WINDOW_FEATURE_SET_ID,
        feature_names=ELECTRICAL_WINDOW_FEATURE_NAMES,
    )


def build_device_package(
    candidate: str,
    train: Sequence[WindowRow],
    models_root: Path,
    *,
    device: DeviceRecord,
    boundary: datetime,
    created_at: datetime,
    code_revision: str,
) -> LoadedModelPackage:
    """Fit one candidate on this device's training windows and verify it by reload."""
    matrix = np.asarray(
        [
            [row.features[name] for name in ELECTRICAL_WINDOW_FEATURE_NAMES]
            for row in train
            if row.features
        ],
        dtype=np.float64,
    )
    if candidate == "isolation-forest":
        kind = EstimatorKind.ISOLATION_FOREST_REFIT
        preprocessing = AffinePreprocessing((0.0,) * matrix.shape[1], (1.0,) * matrix.shape[1])
        state: dict[str, Any] = {
            "n_estimators": 256,
            "max_samples": "auto",
            "contamination": "auto",
            "max_features": 1.0,
            "bootstrap": False,
            "random_seed": SEED,
        }
        fit_rows: list[list[float]] | None = matrix.tolist()
    elif candidate == "pca-residual":
        kind = EstimatorKind.PCA_RESIDUAL
        center = np.median(matrix, axis=0)
        iqr = np.subtract(*np.percentile(matrix, [75, 25], axis=0))
        scale = np.where(iqr > 1e-9, iqr, np.maximum(np.std(matrix, axis=0), 1e-6))
        preprocessing = AffinePreprocessing(tuple(center), tuple(scale))
        standardized = (matrix - center) / scale
        mean = standardized.mean(axis=0)
        _, singular, vt = np.linalg.svd(standardized - mean, full_matrices=False)
        explained = np.cumsum(singular**2) / np.sum(singular**2)
        needed = int(np.searchsorted(explained, 0.95)) + 1
        keep = min(max(1, needed), int(matrix.shape[1]) - 1)
        state = {"mean": mean.tolist(), "components": vt[:keep].tolist()}
        fit_rows = None
    else:
        raise ValueError(f"unknown candidate: {candidate}")
    probe = matrix[:: max(1, len(matrix) // 16)][:16].tolist()
    provisional = write_model_package(
        models_root / "provisional",
        _build(
            candidate,
            kind,
            preprocessing,
            state,
            fit_rows,
            probe,
            0.0,
            device,
            boundary,
            len(matrix),
            created_at,
            code_revision,
        ),
    )
    scores = np.asarray(
        load_model_package(models_root / "provisional" / provisional.package_id).evaluate(
            matrix.tolist()
        )
    )
    threshold = float(np.quantile(scores, THRESHOLD_QUANTILE))
    manifest = write_model_package(
        models_root,
        _build(
            candidate,
            kind,
            preprocessing,
            state,
            fit_rows,
            probe,
            threshold,
            device,
            boundary,
            len(matrix),
            created_at,
            code_revision,
        ),
    )
    return load_model_package(models_root / manifest.package_id)


def _build(
    candidate: str,
    kind: EstimatorKind,
    preprocessing: AffinePreprocessing,
    state: Mapping[str, Any],
    fit_rows: list[list[float]] | None,
    probe: list[list[float]],
    threshold: float,
    device: DeviceRecord,
    boundary: datetime,
    window_count: int,
    created_at: datetime,
    code_revision: str,
) -> PackageBuild:
    return PackageBuild(
        recipe_id=f"aihub-239-electrical-{candidate}-v1",
        estimator_kind=kind,
        input=input_spec(),
        output=PackageOutputSpec(
            task=ModelTask.ANOMALY_SCORE,
            value_name=f"{candidate}-score",
            threshold=threshold,
            threshold_rule=f"train-window-score-quantile-{THRESHOLD_QUANTILE}",
            review_interval=INTERVAL_RULE,
            step_period_seconds=WINDOW.total_seconds(),
            provides_feature_contributions=kind is EstimatorKind.PCA_RESIDUAL,
        ),
        preprocessing=preprocessing,
        estimator_state=state,
        fit_rows=fit_rows,
        probe_rows=probe,
        training_scope={
            "dataset_id": "aihub-239",
            "archive": "Training/raw 3.공기압축기.zip (filekey 44031)",
            "member": device.member,
            "device_id": device.device_id,
            "period": f"first {TRAIN_FRACTION:.0%} of the record, before {boundary.isoformat()}",
            "evaluated_window_count": window_count,
            "semantics_version": AIHUB_239_SEMANTICS_V3,
            "timezone_assumption": TIMEZONE,
        },
        validation={
            "evidence_class": "per-device-holdout-injection-evaluation",
            "protocol": "docs/research/operational-inference-acceptance-protocol.md §3",
            "score_semantics": (
                "departure from this device's training windows; not a failure probability"
            ),
        },
        applicability={"device_id": [device.device_id]},
        created_at=created_at.isoformat(),
        code_revision=code_revision,
    )


# Evaluation --------------------------------------------------------------------


def feature_matrix(rows: Sequence[WindowRow]) -> list[list[float]]:
    """Evaluated windows as rows in the package feature order."""
    return [
        [row.features[name] for name in ELECTRICAL_WINDOW_FEATURE_NAMES]
        for row in rows
        if row.features is not None
    ]


def score_rows(
    package: LoadedModelPackage, rows: Sequence[WindowRow]
) -> list[tuple[WindowRow, float | None]]:
    evaluated = [row for row in rows if row.features]
    values = package.evaluate(feature_matrix(evaluated)) if evaluated else ()
    by_start = {row.start: value for row, value in zip(evaluated, values, strict=True)}
    return [(row, by_start.get(row.start)) for row in rows]


def review_windows(
    scored: Sequence[tuple[WindowRow, float | None]], threshold: float
) -> tuple[list[tuple[datetime, datetime]], list[tuple[datetime, bool]]]:
    """Run the operational interval rule over consecutive windows.

    Returns the intervals opened as (opened_at, interval start) and, per evaluated window,
    whether an interval was open after that window. ``opened_at`` is the end of the window
    that completed the rule, i.e. the earliest moment the runtime could show it.
    """
    tracker: dict[str, Any] = {}
    opened: list[tuple[datetime, datetime]] = []
    states: list[tuple[datetime, bool]] = []
    for index, (row, score) in enumerate(scored):
        if score is None:
            continue  # skipped steps keep state, exactly as the runner does
        step = PreparedStep(
            step_key=f"w{index}",
            position=int(row.start.timestamp()),
            replay=True,
            input_reference={},
            event_start=row.start,
            event_end=row.start + WINDOW,
            features=(score,),
        )
        was_open = bool(tracker.get("open_id"))
        tracker, _ = advance_review_interval(
            tracker,
            step,
            score=score,
            exceeds=score > threshold,
            min_consecutive_steps=INTERVAL_RULE.min_consecutive_steps,
            max_gap_steps=INTERVAL_RULE.max_gap_steps,
        )
        if not was_open and tracker.get("open_id"):
            opened.append(
                (row.start + WINDOW, datetime.fromisoformat(tracker["start"]["start_at"]))
            )
        states.append((row.start, bool(tracker.get("open_id"))))
    return opened, states


def alarm_window_fraction(
    scored: Sequence[tuple[WindowRow, float | None]], threshold: float
) -> tuple[int, int]:
    """Windows inside any review interval / evaluated windows, with no injection."""
    tracker: dict[str, Any] = {}
    inside: set[int] = set()
    evaluated = 0
    for index, (_row, score) in enumerate(scored):
        if score is None:
            continue
        evaluated += 1
        step = PreparedStep(
            step_key=f"w{index}", position=index, replay=True, input_reference={}, features=(score,)
        )
        tracker, writes = advance_review_interval(
            tracker,
            step,
            score=score,
            exceeds=score > threshold,
            min_consecutive_steps=INTERVAL_RULE.min_consecutive_steps,
            max_gap_steps=INTERVAL_RULE.max_gap_steps,
        )
        for write in writes:
            inside.update(range(int(write.start["position"]), int(write.end["position"]) + 1))
    evaluated_positions = {i for i, (_, s) in enumerate(scored) if s is not None}
    return len(inside & evaluated_positions), evaluated


def injection_starts(
    holdout: Sequence[WindowRow], rng: random.Random, count: int, duration: timedelta
) -> list[datetime]:
    """Window starts where the injected span is fully covered by evaluated windows."""
    evaluated = {row.start for row in holdout if row.features}
    needed = max(1, int(duration / WINDOW))
    candidates = [
        row.start
        for row in holdout
        if all(row.start + WINDOW * k in evaluated for k in range(needed))
    ]
    return sorted(rng.sample(candidates, min(count, len(candidates))))


def evaluate_injection(
    package: LoadedModelPackage,
    holdout_samples: Sequence[ElectricalWindowSample],
    injection: Injection,
    start: datetime,
    phase: int,
) -> dict[str, Any]:
    """Inject one change into a copy of the holdout, rescore its neighborhood, and judge.

    Detected means a review interval *opens* no later than 20 minutes after the injection
    starts and begins before the injection ends. When the unmodified data already has an
    interval open at the injection start, the case is reported as masked, not detected.
    """
    threshold = float(package.manifest.output.threshold or 0.0)
    lead = timedelta(hours=1)
    span = [s for s in holdout_samples if start - lead <= s.at < start + injection.duration + lead]
    _, baseline_states = review_windows(score_rows(package, window_rows(span)), threshold)
    masked = any(open_ for at, open_ in baseline_states if at == start - WINDOW)
    opened, _ = review_windows(
        score_rows(package, window_rows([injection.apply(s, start, phase) for s in span])),
        threshold,
    )
    candidates = [
        opened_at
        for opened_at, interval_start in opened
        if opened_at >= start and interval_start < start + injection.duration
    ]
    first = min(candidates) if candidates else None
    return {
        "kind": injection.kind,
        "start": start.isoformat(),
        "phase": "RST"[phase],
        "detected": first is not None and first - start <= DETECTION_WINDOW and not masked,
        "delay_minutes": None if first is None else (first - start).total_seconds() / 60,
        "masked_by_existing_interval": masked,
    }


def device_contributions(
    package: LoadedModelPackage, rows: Sequence[WindowRow]
) -> list[dict[str, float]] | None:
    evaluated = [row for row in rows if row.features]
    if not evaluated:
        return None
    result = package.feature_contributions(feature_matrix(evaluated))
    return None if result is None else list(result)


def choose_development_members(eligible: Sequence[str], reference: str) -> list[str]:
    others = sorted(m for m in eligible if m != reference)
    return [reference, *random.Random(SEED).sample(others, min(5, len(others)))]


ProgressCallback = Callable[[str], None]
