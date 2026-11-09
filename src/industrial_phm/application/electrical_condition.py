"""Electrical operating changes and reference-pattern scoring, independent of storage/UI."""

from __future__ import annotations

from bisect import bisect_right
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from statistics import median
from typing import Any

import numpy as np

from industrial_phm.application.analysis_input import ChannelObservation
from industrial_phm.application.operating_state import OperatingLevels
from industrial_phm.application.phase_unbalance import PhaseUnbalanceConfig, unbalance_percent
from industrial_phm.experiments.config import (
    ExperimentConfig,
    FitPartition,
    ModelFamily,
    ReferenceStrategy,
    ScalingStrategy,
)
from industrial_phm.models.input import ModelFitInput, ModelScoringInput
from industrial_phm.models.isolation_forest import fit_isolation_forest


@dataclass(frozen=True, slots=True)
class ElectricalSample:
    at: datetime
    voltage: tuple[float, ...] | None
    current: tuple[float, ...] | None

    def __post_init__(self) -> None:
        if self.at.utcoffset() is None:
            raise ValueError("electrical observation time needs an explicit timezone")
        for values in (self.voltage, self.current):
            if values is not None and (
                len(values) != 3 or any(not np.isfinite(v) or v < 0 for v in values)
            ):
                raise ValueError("electrical samples need three finite nonnegative phase values")


def electrical_samples(
    observations: Sequence[ChannelObservation],
    *,
    source_id: str,
    point_id: str | None,
    voltage_channels: tuple[str, ...],
    current_channels: tuple[str, ...],
) -> tuple[tuple[ElectricalSample, ...], dict[str, int]]:
    """Strict time alignment; no filling gaps, merging points or interpreting names."""
    grouped: dict[datetime, dict[str, list[ChannelObservation]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for observation in observations:
        if observation.source_id == source_id and observation.measurement_point_id == point_id:
            grouped[observation.event_at][observation.channel_id].append(observation)
    excluded: Counter[str] = Counter()
    samples = []
    for at, channels in sorted(grouped.items()):
        quantities: list[tuple[float, ...] | None] = []
        for names, prop, unit in (
            (voltage_channels, "phase voltage", "V"),
            (current_channels, "phase current", "A"),
        ):
            if not names:
                quantities.append(None)
                continue
            values = []
            reason = None
            for phase, name in zip("RST", names, strict=True):
                rows = channels.get(name, [])
                if len(rows) != 1:
                    reason = "missing-or-duplicate-phase"
                    break
                row = rows[0]
                if row.conflicting or not row.source_quality_good:
                    reason = "conflict-or-bad-quality"
                    break
                if row.value is None:
                    reason = "missing-value"
                    break
                if (row.observed_property, row.unit, row.scope) != (prop, unit, f"phase {phase}"):
                    reason = "unconfirmed-meaning"
                    break
                if not np.isfinite(row.value) or row.value < 0:
                    reason = "invalid-electrical-value"
                    break
                values.append(row.value)
            if reason:
                excluded[reason] += 1
                quantities.append(None)
            else:
                quantities.append(tuple(values))
        samples.append(ElectricalSample(at, *quantities))
    return tuple(samples), dict(excluded)


def _mean(values: tuple[float, ...] | None) -> float | None:
    return None if values is None else sum(values) / len(values)


def _cadence(samples: Sequence[ElectricalSample]) -> float:
    intervals = [(b.at - a.at).total_seconds() for a, b in pairwise(samples)]
    return median(intervals) if intervals else 60.0


def _summary(samples: Sequence[ElectricalSample]) -> dict[str, object]:
    config = PhaseUnbalanceConfig()
    currents = [
        (sum(sample.current) / 3, sample.at) for sample in samples if sample.current is not None
    ]
    voltages = [
        unbalance_percent(sample.voltage)
        for sample in samples
        if sample.voltage is not None and sum(sample.voltage) / 3 >= config.min_mean_voltage_v
    ]
    imbalance = [
        unbalance_percent(sample.current)
        for sample in samples
        if sample.current is not None and sum(sample.current) / 3 >= config.min_mean_current_a
    ]
    cadence = _cadence(samples)
    active_seconds = observed_seconds = 0.0
    transitions = 0
    for index, sample in enumerate(samples):
        value = _mean(sample.current)
        if value is None:
            continue
        following = samples[index + 1] if index + 1 < len(samples) else None
        if following is None or following.current is None:
            continue
        duration = (following.at - sample.at).total_seconds()
        if 0 < duration <= min(cadence * 1.5, 120):
            observed_seconds += duration
            if value >= config.min_mean_current_a:
                active_seconds += duration
            transitions += (value >= config.min_mean_current_a) != (
                sum(following.current) / 3 >= config.min_mean_current_a
            )
    peak = max(currents, key=lambda item: item[0]) if currents else (None, None)
    return {
        "sample_count": len(samples),
        "current_mean_a": float(np.mean([value for value, _ in currents])) if currents else None,
        "current_peak_a": peak[0],
        "current_peak_at": None if peak[1] is None else peak[1].isoformat(),
        "current_above_floor_hours": active_seconds / 3600 if observed_seconds else None,
        "current_observed_hours": observed_seconds / 3600 if currents else None,
        "current_above_floor_fraction": active_seconds / observed_seconds
        if observed_seconds
        else None,
        "current_floor_a": config.min_mean_current_a,
        "current_transitions": transitions if currents else None,
        "voltage_unbalance_max_percent": max(voltages) if voltages else None,
        "voltage_unbalance_max_at": max(
            (
                sample
                for sample in samples
                if sample.voltage is not None
                and sum(sample.voltage) / 3 >= config.min_mean_voltage_v
            ),
            key=lambda sample: unbalance_percent(sample.voltage or (1, 1, 1)),
        ).at.isoformat()
        if voltages
        else None,
        "voltage_unbalance_p95_percent": float(np.quantile(voltages, 0.95)) if voltages else None,
        "current_unbalance_p95_percent": float(np.quantile(imbalance, 0.95)) if imbalance else None,
        "current_unbalance_evaluated": len(imbalance),
        "current_low_signal_count": len(currents) - len(imbalance),
    }


_MODEL = {"random_seed": 42, "n_estimators": 128, "model": "Isolation Forest"}


def _pattern(
    reference: Sequence[ElectricalSample],
    target: Sequence[ElectricalSample],
    channels: tuple[str, ...],
    *,
    include_voltage: bool,
    include_current: bool,
    levels: OperatingLevels | None = None,
) -> tuple[dict[str, object], dict[datetime, float]]:
    def feature(sample: ElectricalSample) -> tuple[float, ...] | None:
        if (include_voltage and sample.voltage is None) or (
            include_current and sample.current is None
        ):
            return None
        return (
            *((sample.voltage or ()) if include_voltage else ()),
            *((sample.current or ()) if include_current else ()),
        )

    fit_rows = [(sample, row) for sample in reference if (row := feature(sample)) is not None]
    score_rows = [(sample, row) for sample in target if (row := feature(sample)) is not None]
    if levels is None or not include_current:
        whole = _scored(fit_rows, score_rows, channels, include_voltage=include_voltage)
        if whole is None:
            return {"state": "insufficient-reference", "reference_samples": len(fit_rows)}, {}
        return {
            "state": "scored",
            "policy_version": "electrical-reference-pattern-v1",
            **_MODEL,
            "reference_samples": len(fit_rows),
            "fit_samples": whole.fit_samples,
            "scored_samples": len(score_rows),
            "threshold": whole.threshold,
            "reference_quantile": 0.99,
            "above_reference_count": whole.above,
            "above_reference_percent": whole.above / len(score_rows) * 100,
            "notable": whole.notable,
            "meaning": "departure-from-selected-reference-not-fault-probability",
        }, whole.scores

    def band(sample: ElectricalSample) -> int:
        return bisect_right(levels.edges, sum(sample.current or ()) / 3)

    # Each operating level is compared only with the same level in the reference period, so a
    # load the reference rarely ran at is not taken for a departure from its pattern.
    parts: list[dict[str, object]] = []
    scores: dict[datetime, float] = {}
    notable: list[dict[str, Any]] = []
    fitted = scored = above = 0
    for level in sorted({band(sample) for sample, _ in [*fit_rows, *score_rows]}):
        own_fit = [item for item in fit_rows if band(item[0]) == level]
        own_score = [item for item in score_rows if band(item[0]) == level]
        part: dict[str, object] = {
            "band": level,
            "reference_samples": len(own_fit),
            "target_samples": len(own_score),
            "state": "not-in-target",
        }
        if own_score:
            own = _scored(own_fit, own_score, channels, include_voltage=include_voltage)
            part["state"] = "insufficient-reference" if own is None else "scored"
            if own is not None:
                part["above_reference_count"] = own.above
                fitted += own.fit_samples
                scored += len(own_score)
                above += own.above
                scores |= {at: score / own.threshold for at, score in own.scores.items()}
                notable += [
                    {**item, "score": item["score"] / own.threshold, "band": level}
                    for item in own.notable
                ]
        parts.append(part)
    if not scored:
        return {
            "state": "insufficient-reference",
            "reference_samples": len(fit_rows),
            "split": "operating-level",
            "levels": parts,
        }, {}
    return {
        "state": "scored",
        "policy_version": "electrical-reference-pattern-v2-operating-level",
        "split": "operating-level",
        **_MODEL,
        "reference_samples": len(fit_rows),
        "fit_samples": fitted,
        "scored_samples": scored,
        "unscored_samples": len(score_rows) - scored,
        # Scores are divided by their own level's threshold, so one line at 1 marks every level.
        "threshold": 1.0,
        "score_scale": "ratio-to-same-level-threshold",
        "reference_quantile": 0.99,
        "above_reference_count": above,
        "above_reference_percent": above / scored * 100,
        "notable": sorted(notable, key=lambda item: -item["score"])[:5],
        "levels": parts,
        "meaning": "departure-from-selected-reference-not-fault-probability",
    }, scores


@dataclass(frozen=True, slots=True)
class _Scored:
    """One reference-pattern fit and the target scores it gave."""

    threshold: float
    fit_samples: int
    scores: dict[datetime, float]
    above: int
    notable: list[dict[str, Any]]


def _scored(
    fit_rows: Sequence[tuple[ElectricalSample, tuple[float, ...]]],
    score_rows: Sequence[tuple[ElectricalSample, tuple[float, ...]]],
    channels: tuple[str, ...],
    *,
    include_voltage: bool,
) -> _Scored | None:
    """Fit on the reference rows and score the target rows; None when the reference is too thin."""
    if len(fit_rows) < 60 or len({row for _, row in fit_rows}) < 8 or not score_rows:
        return None
    # Deterministic reference-only fitting. No target rows enter calibration or the model.
    indices = np.linspace(0, len(fit_rows) - 1, min(2048, len(fit_rows)), dtype=int)
    fitted_rows = [fit_rows[int(index)] for index in indices]
    config = ExperimentConfig(
        experiment_id="electrical-reference-pattern-v1",
        dataset_id="asset-history",
        split_id="reference-before-target",
        fold_id="selected-asset-source-point",
        fit_partition=FitPartition.TRAIN,
        feature_set_id="electrical-phase-values-v1",
        selected_features=channels,
        reference_strategy=ReferenceStrategy.ALL_TRAIN_OBSERVATIONS,
        sampling_policy_id="reference-evenly-spaced-max-2048-v1",
        scaling_strategy=ScalingStrategy.IDENTITY,
        model_family=ModelFamily.ISOLATION_FOREST,
        model_parameters={
            "n_estimators": 128,
            "max_samples": min(256, len(fitted_rows)),
            "contamination": "auto",
            "max_features": 1.0,
            "bootstrap": False,
        },
        random_seed=42,
    )
    fit_input = ModelFitInput(
        config.experiment_id,
        config.feature_set_id,
        channels,
        [row for _, row in fitted_rows],
        [sample.at.isoformat() for sample, _ in fitted_rows],
        config.sampling_policy_id,
        42,
        len(fit_rows),
        len(fit_rows),
    )
    model = fit_isolation_forest(config, fit_input)
    reference_scores = model.score(
        ModelScoringInput(
            config.experiment_id,
            config.feature_set_id,
            channels,
            [row for _, row in fit_rows],
            [sample.at.isoformat() for sample, _ in fit_rows],
        )
    ).scores
    threshold = float(np.quantile(reference_scores, 0.99))
    scores = model.score(
        ModelScoringInput(
            config.experiment_id,
            config.feature_set_id,
            channels,
            [row for _, row in score_rows],
            [sample.at.isoformat() for sample, _ in score_rows],
        )
    ).scores
    by_time = {sample.at: score for (sample, _), score in zip(score_rows, scores, strict=True)}
    flagged = sum(score > threshold for score in scores)
    matrix = np.asarray([row for _, row in fit_rows])
    limits = np.quantile(matrix, [0.05, 0.5, 0.95], axis=0)
    notable: list[dict[str, Any]] = []
    for index in sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:5]:
        sample, row = score_rows[index]
        # Companion signal differences are descriptive, not causal model attribution.
        deviations = [
            abs(value - limits[1, i]) / max(limits[2, i] - limits[0, i], 0.1)
            for i, value in enumerate(row)
        ]
        strongest = int(np.argmax(deviations))
        notable.append(
            {
                "at": sample.at.isoformat(),
                "score": scores[index],
                "above_reference": scores[index] > threshold,
                "channel_id": channels[strongest],
                "value": row[strongest],
                "reference_median": float(limits[1, strongest]),
                "reference_p05": float(limits[0, strongest]),
                "reference_p95": float(limits[2, strongest]),
                "unit": "V" if include_voltage and strongest < 3 else "A",
            }
        )
    return _Scored(threshold, len(fitted_rows), by_time, flagged, notable)


def analyze_electrical_condition(
    reference: Sequence[ElectricalSample],
    target: Sequence[ElectricalSample],
    *,
    channels: tuple[str, ...],
    include_voltage: bool,
    include_current: bool,
    reference_start: datetime,
    reference_end: datetime | None = None,
    target_start: datetime,
    target_end: datetime,
    levels: OperatingLevels | None = None,
) -> dict[str, object]:
    """Explain measured change against a strictly earlier reference period.

    With operating levels, each observation's pattern is compared only with the reference
    observations at the same level of three-phase mean current.
    """
    reference_end = reference_end or target_start
    if not reference_start < reference_end <= target_start < target_end:
        raise ValueError("reference and target periods must be increasing and disjoint")
    if any(not reference_start <= sample.at < reference_end for sample in reference):
        raise ValueError("reference contains samples outside its earlier period")
    if any(not target_start <= sample.at < target_end for sample in target):
        raise ValueError("target samples outside selected period")
    if len(reference) > 3600 or len(target) > 3600:
        raise ValueError("condition analysis exceeds 3600 timestamps per period")
    for samples in (reference, target):
        if any(a.at >= b.at for a, b in pairwise(samples)):
            raise ValueError("condition samples must have unique increasing times")
    baseline = _summary(reference)
    observed = _summary(target)
    pattern, scores = _pattern(
        reference,
        target,
        channels,
        include_voltage=include_voltage,
        include_current=include_current,
        levels=levels,
    )
    config = PhaseUnbalanceConfig()
    timeline = [
        {
            "at": sample.at.isoformat(),
            "current_mean_a": _mean(sample.current),
            "voltage_phase_v": sample.voltage,
            "current_phase_a": sample.current,
            "voltage_mean_v": _mean(sample.voltage),
            "voltage_unbalance_percent": unbalance_percent(sample.voltage)
            if sample.voltage is not None and sum(sample.voltage) / 3 >= config.min_mean_voltage_v
            else None,
            "current_unbalance_percent": unbalance_percent(sample.current)
            if sample.current is not None and sum(sample.current) / 3 >= config.min_mean_current_a
            else None,
            "pattern_score": scores.get(sample.at),
        }
        for sample in target
    ]
    return {"reference": baseline, "target": observed, "pattern": pattern, "timeline": timeline}
