"""Compare two periods of one asset's measurements: statistics, data quality and distribution.

Two kinds of measurement are explored the same way. Stored measurement history (CSV, OPC UA)
is compared over two time periods from its raw observations. Acquisition features (vibration
records) are compared over two acquisition ranges from the stored per-acquisition features.
Nothing here judges health; a period the user picks as A is a comparison, not a normal baseline.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from datetime import UTC, datetime
from itertools import pairwise
from typing import Any

import numpy as np

from industrial_phm.application.acquisition_snapshot import (
    SqliteAcquisitionSnapshotRepository,
    read_snapshot_waveform,
)
from industrial_phm.application.measurement_history import (
    PROFILE_QUANTILES,
    MeasurementPairGroup,
    MeasurementProfile,
)
from industrial_phm.application.phm_analysis import PhmBinding, SqlitePhmAnalysisStore
from industrial_phm.application.phm_signal_comparison import feature_label
from industrial_phm.models.package import StepKind

BINS = 20
MAX_SERIES = 6
MAX_ACQUISITIONS = 4096


def _time(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _number(value: float | None) -> float | None:
    return None if value is None or not math.isfinite(value) else float(value)


def interpretation_unit(interpretation_json: str) -> str | None:
    data = json.loads(interpretation_json)
    for part in ("binding", "semantics"):
        item = data.get(part) if isinstance(data, dict) else None
        definition = item.get("definition", item) if isinstance(item, dict) else None
        if isinstance(definition, dict) and isinstance(definition.get("unit"), str):
            return str(definition["unit"])
    return None


def _stats(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return dict.fromkeys(("minimum", "maximum", "mean", "standard_deviation"), None) | {
            "quantiles": None
        }
    array = np.asarray(values, dtype=float)
    return {
        "minimum": float(array.min()),
        "maximum": float(array.max()),
        "mean": float(array.mean()),
        "standard_deviation": float(array.std(ddof=1)) if array.size > 1 else None,
        "quantiles": [float(q) for q in np.quantile(array, PROFILE_QUANTILES)],
    }


SIGNED_FEATURES = (".mean", ".skewness", ".excess_kurtosis")


def comparison(
    a: dict[str, Any], b: dict[str, Any], b_outside: int | None, *, signed: bool = False
) -> dict[str, Any]:
    """How period B differs from period A, in measures that do not depend on units.

    A percent change is given only for a positive magnitude (both medians above zero and the
    quantity not signed); a shape statistic such as skewness gets its absolute change only.
    """
    qa, qb = a.get("quantiles"), b.get("quantiles")
    if not qa or not qb:
        return {"median_change": None}
    change = qb[2] - qa[2]
    spread_a, spread_b = qa[3] - qa[1], qb[3] - qb[1]
    ratio_ok = not signed and qa[2] > 0 and qb[2] >= 0 and (a.get("minimum") or 0) >= 0
    return {
        "median_change": change,
        "median_change_percent": 100 * change / qa[2] if ratio_ok else None,
        "spread_ratio": spread_b / spread_a if spread_a > 0 else None,
        "b_outside_a_band": b_outside,
        "b_outside_a_band_percent": None
        if b_outside is None or not b["usable_count"]
        else 100 * b_outside / b["usable_count"],
    }


def history_series(
    profiles: Sequence[MeasurementProfile], periods: Sequence[tuple[str, datetime, datetime]]
) -> list[dict[str, Any]]:
    """Group exact period profiles into one comparable series per signal identity."""
    grouped: dict[tuple[str, ...], dict[str, MeasurementProfile]] = {}
    for item in profiles:
        identity = (
            item.channel_id,
            item.source_id,
            item.source_type,
            item.measurement_point_id or "",
            item.interpretation_json,
        )
        grouped.setdefault(identity, {})[item.period] = item
    series = []
    for (channel, source, source_type, point, interpretation), by_period in grouped.items():
        first = next(iter(by_period.values()))
        stats = {name: _history_period(by_period.get(name)) for name, _, _ in periods}
        histogram = None
        if first.histogram_low is not None:
            histogram = {
                "low": first.histogram_low,
                "high": first.histogram_high,
                "bins": len(first.histogram),
                **{
                    name: list(by_period[name].histogram) if name in by_period else None
                    for name, _, _ in periods
                },
            }
        b = by_period.get("b")
        series.append(
            {
                "kind": "history",
                "key": channel,
                "label": channel,
                "unit": interpretation_unit(interpretation),
                "source_id": source,
                "source_type": source_type,
                "measurement_point_id": point or None,
                "interpretation_id": hashlib.sha256(interpretation.encode()).hexdigest()[:16],
                "periods": stats,
                "histogram": histogram,
                "comparison": comparison(
                    stats.get("a", {}), stats.get("b", {}), b.outside_other_band if b else None
                ),
            }
        )
    return series


def _history_period(item: MeasurementProfile | None) -> dict[str, Any]:
    if item is None:
        return {"observation_count": 0, "usable_count": 0, "quantiles": None}
    return {
        "observation_count": item.observation_count,
        "usable_count": item.usable_count,
        "missing_count": item.null_count,
        "non_good_count": item.non_good_count,
        "conflict_count": item.conflict_count,
        "first_at": _time(item.first_event_at),
        "last_at": _time(item.last_event_at),
        "minimum": _number(item.minimum),
        "maximum": _number(item.maximum),
        "mean": _number(item.mean),
        "standard_deviation": _number(item.standard_deviation),
        "quantiles": None if item.quantiles is None else list(item.quantiles),
        "median_interval_seconds": item.median_interval_seconds,
        "largest_gap": None
        if item.largest_gap_seconds is None
        else {
            "seconds": item.largest_gap_seconds,
            "start": _time(item.largest_gap_start),
            "end": _time(item.largest_gap_end),
        },
        "long_gap_count": item.long_gap_count,
        "longest_constant": {
            "count": item.longest_constant_count,
            "start": _time(item.longest_constant_start),
            "end": _time(item.longest_constant_end),
        },
    }


def acquisition_binding(store: SqlitePhmAnalysisStore, asset_id: str) -> PhmBinding | None:
    """The acquisition binding of an asset whose stored results carry the most features."""
    best: tuple[int, PhmBinding] | None = None
    for binding in store.list_bindings():
        if binding.asset_id != asset_id or binding.step_kind is not StepKind.ACQUISITION_SNAPSHOT:
            continue
        results, total = store.analyzed_between(binding.binding_id, 0, 2**62, max_points=1)
        if results and results[-1].features and (best is None or total > best[0]):
            best = (total, binding)
    return None if best is None else best[1]


def acquisition_source(store: SqlitePhmAnalysisStore, binding: PhmBinding) -> dict[str, Any]:
    results, total = store.analyzed_between(binding.binding_id, 0, 2**62, max_points=2)
    latest = results[-1]
    return {
        "binding_id": binding.binding_id,
        "source_id": binding.source_id,
        "features": [
            {"key": name, "label": feature_label(name)} for name in sorted(latest.features or {})
        ],
        "first": results[0].position,
        "last": latest.position,
        "count": total,
    }


def acquisition_series(
    store: SqlitePhmAnalysisStore,
    snapshots: SqliteAcquisitionSnapshotRepository,
    binding: PhmBinding,
    features: Sequence[str],
    periods: Sequence[tuple[str, int, int]],
    *,
    max_points: int = MAX_ACQUISITIONS,
) -> list[dict[str, Any]]:
    """Per-acquisition features over two acquisition ranges, with record-level quality.

    Counts (delivered, analyzed, not analyzed, missing numbers) are exact over each whole
    range. Feature statistics use every analyzed acquisition up to ``max_points``; a longer
    range is sampled evenly over its whole length and reported as sampled.
    """
    if not features or len(features) > 8:
        raise ValueError("choose 1 to 8 features")
    by_period: dict[str, dict[str, Any]] = {}
    for name, first, last in periods:
        if not 0 <= first <= last:
            raise ValueError("an acquisition range must be increasing")
        analyzed, analyzed_total = store.analyzed_between(
            binding.binding_id, first, last, max_points=max_points
        )
        states = store.count_between(binding.binding_id, first, last)
        delivered = snapshots.ordinals_between(binding.source_id, binding.asset_id, first, last)
        ordinals = [ordinal for ordinal, _ in delivered]
        gaps = [b - a - 1 for a, b in pairwise(ordinals) if b - a > 1]
        intervals = [(b - a).total_seconds() for (_, a), (_, b) in pairwise(delivered) if b > a]
        by_period[name] = {
            "first": first,
            "last": last,
            "delivered": len(delivered),
            "analyzed": analyzed,
            "analyzed_total": analyzed_total,
            "skipped": sum(count for state, count in states.items() if state != "analyzed"),
            "missing_acquisitions": sum(gaps),
            "median_interval_seconds": float(np.median(intervals)) if intervals else None,
            "sampled": analyzed_total > len(analyzed),
        }
    series = []
    for feature in features:
        values = {
            name: [
                (r.position, float((r.features or {})[feature]))
                for r in period["analyzed"]
                if isinstance((r.features or {}).get(feature), (int, float))
                and math.isfinite(float((r.features or {})[feature]))
            ]
            for name, period in by_period.items()
        }
        stats: dict[str, dict[str, Any]] = {}
        for name, period in by_period.items():
            points = values[name]
            stats[name] = {
                "observation_count": period["delivered"],
                "usable_count": len(points),
                "analyzed_count": period["analyzed_total"],
                "missing_count": period["missing_acquisitions"],
                "unanalyzed_count": period["skipped"],
                "first_position": points[0][0] if points else None,
                "last_position": points[-1][0] if points else None,
                "median_interval_seconds": period["median_interval_seconds"],
                # Runs of equal values are only meaningful over consecutive acquisitions.
                "longest_constant": None if period["sampled"] else _constant_run(points),
                "sampled": period["sampled"],
                **_stats([v for _, v in points]),
            }
        everything = [v for points in values.values() for _, v in points]
        histogram: dict[str, Any] | None = None
        if everything:
            low, high = min(everything), max(everything)
            histogram = {"low": low, "high": high, "bins": BINS} | {
                name: _histogram([v for _, v in points], low, high)
                for name, points in values.items()
            }
        outside = None
        if "a" in values and "b" in values and stats["a"].get("quantiles"):
            band = stats["a"]["quantiles"]
            outside = sum(1 for _, v in values["b"] if v < band[0] or v > band[4])
        series.append(
            {
                "kind": "acquisition",
                "key": feature,
                "label": feature_label(feature),
                "unit": None,
                "source_id": binding.source_id,
                "binding_id": binding.binding_id,
                "periods": stats,
                "histogram": histogram,
                "comparison": comparison(
                    stats.get("a", {}),
                    stats.get("b", {}),
                    outside,
                    signed=feature.endswith(SIGNED_FEATURES),
                ),
            }
        )
    return series


def _histogram(values: Sequence[float], low: float, high: float) -> list[int]:
    counts = [0] * BINS
    for value in values:
        index = 0 if high <= low else min(int((value - low) / (high - low) * BINS), BINS - 1)
        counts[index] += 1
    return counts


def _constant_run(points: Sequence[tuple[int, float]]) -> dict[str, int | None]:
    best: tuple[int, int | None, int | None] = (0, None, None)
    start = 0
    for index in range(1, len(points) + 1):
        if index == len(points) or points[index][1] != points[start][1]:
            length = index - start
            if length > best[0]:
                best = (length, points[start][0], points[index - 1][0])
            start = index
    return {"count": best[0], "start": best[1], "end": best[2]}


def history_relation(groups: Sequence[MeasurementPairGroup]) -> list[dict[str, Any]]:
    """Paired observations per period, source/point and meaning, with both correlations."""
    return [
        {
            "period": group.period,
            "source_id": group.source_id,
            "measurement_point_id": group.measurement_point_id,
            "x_unit": interpretation_unit(group.x_interpretation_json),
            "y_unit": interpretation_unit(group.y_interpretation_json),
            "meaning_id": hashlib.sha256(
                (group.x_interpretation_json + "\0" + group.y_interpretation_json).encode()
            ).hexdigest()[:16],
            "x_usable_count": group.x_usable_count,
            "y_usable_count": group.y_usable_count,
            "pair_count": group.pair_count,
            "pearson": group.pearson,
            "spearman": group.spearman,
            "sampled": False,
            "points": [[_time(at), x, y] for at, x, y in group.points],
        }
        for group in groups
    ]


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values))
    ranks[order] = np.arange(1, len(values) + 1)
    for value in np.unique(values):
        tied = values == value
        ranks[tied] = ranks[tied].mean()
    return ranks


def _correlation(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return None
    return float(np.corrcoef(x, y)[0, 1])


def acquisition_relation(
    store: SqlitePhmAnalysisStore,
    binding: PhmBinding,
    x_feature: str,
    y_feature: str,
    periods: Sequence[tuple[str, int, int]],
    *,
    max_points: int = MAX_ACQUISITIONS,
    drawn: int = 750,
) -> list[dict[str, Any]]:
    """Two features of the same acquisitions; each pair is one recorded acquisition.

    A range with more than ``max_points`` analyzed acquisitions is sampled evenly over its
    whole length and reported as sampled; ``drawn`` of the pairs are returned for drawing.
    """
    if x_feature == y_feature:
        raise ValueError("pairs need two different features")
    groups = []
    for name, first, last in periods:
        if not 0 <= first <= last:
            raise ValueError("an acquisition range must be increasing")
        results, total = store.analyzed_between(
            binding.binding_id, first, last, max_points=max_points
        )
        pairs = [
            (r.position, float(f[x_feature]), float(f[y_feature]))
            for r in results
            if (f := r.features or {})
            and isinstance(f.get(x_feature), (int, float))
            and isinstance(f.get(y_feature), (int, float))
            and math.isfinite(float(f[x_feature]))
            and math.isfinite(float(f[y_feature]))
        ]
        groups.append(_acquisition_group(name, pairs, binding, total, total > len(results), drawn))
    return groups


def _acquisition_group(
    name: str,
    pairs: Sequence[tuple[int, float, float]],
    binding: PhmBinding,
    analyzed: int,
    sampled: bool,
    drawn: int,
) -> dict[str, Any]:
    x = np.asarray([p[1] for p in pairs], dtype=float)
    y = np.asarray([p[2] for p in pairs], dtype=float)
    step = max(1, -(-len(pairs) // drawn))
    return {
        "period": name,
        "source_id": binding.source_id,
        "binding_id": binding.binding_id,
        "measurement_point_id": None,
        "analyzed_count": analyzed,
        "x_usable_count": len(pairs),
        "y_usable_count": len(pairs),
        "pair_count": len(pairs),
        "pearson": _correlation(x, y),
        "spearman": _correlation(_average_ranks(x), _average_ranks(y)) if len(pairs) else None,
        "sampled": sampled,
        "points": [[position, a, b] for position, a, b in pairs[::step]],
    }


SPECTRUM_SEGMENT = 4096
SPECTRUM_POINTS = 400
SPECTRUM_BANDS = 16


def welch_psd(values: np.ndarray, sampling_rate_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """One-sided Welch PSD: Hann-windowed segments with 50 % overlap, mean removed."""
    size = min(SPECTRUM_SEGMENT, len(values))
    window = np.hanning(size)
    scale = sampling_rate_hz * float((window**2).sum())
    centered = values - values.mean()
    starts = range(0, len(centered) - size + 1, size // 2)
    spectra = [np.abs(np.fft.rfft(centered[i : i + size] * window)) ** 2 / scale for i in starts]
    psd = np.mean(spectra, axis=0)
    psd[1:-1] *= 2
    return np.fft.rfftfreq(size, 1 / sampling_rate_hz), psd


def acquisition_spectrum(
    snapshots: SqliteAcquisitionSnapshotRepository,
    binding: PhmBinding,
    periods: Sequence[tuple[str, int, int]],
    *,
    per_period: int = 8,
) -> dict[str, Any]:
    """Mean Welch PSD of verified raw waveforms, up to ``per_period`` acquisitions per range.

    Acquisitions are spread evenly through each whole range, first and last included. The
    spectrum shows where vibration energy sits and how it moved between the ranges; it does
    not name a fault frequency.
    """
    rates = set()
    channels: tuple[str, ...] | None = None
    spectra: dict[str, dict[str, list[np.ndarray]]] = {}
    used: dict[str, list[int]] = {}
    frequencies = np.zeros(0)
    for name, first, last in periods:
        delivered = snapshots.ordinals_between(binding.source_id, binding.asset_id, first, last)
        if not delivered:
            raise LookupError(f"no delivered acquisition in range {name}")
        indexes = dict.fromkeys(round(i) for i in np.linspace(0, len(delivered) - 1, per_period))
        chosen = [
            snapshot
            for index in indexes
            if (snapshot := snapshots.get(binding.source_id, binding.asset_id, delivered[index][0]))
            is not None
        ]
        used[name] = [item.ordinal for item in chosen]
        for snapshot in chosen:
            waveform = read_snapshot_waveform(snapshot)
            values = np.asarray(waveform.values, dtype=float)
            channels = channels or tuple(waveform.channels)
            if tuple(waveform.channels) != channels:
                raise ValueError("acquisitions in the ranges have different channels")
            rates.add(snapshot.sampling_rate_hz)
            for index, channel in enumerate(channels):
                frequencies, psd = welch_psd(values[:, index], snapshot.sampling_rate_hz)
                spectra.setdefault(channel, {}).setdefault(name, []).append(psd)
    if len(rates) != 1 or channels is None:
        raise ValueError("acquisitions in the ranges have different sampling rates")
    rate = rates.pop()
    # Display bins average neighbouring frequencies; band changes use the full resolution.
    edges = np.linspace(0, len(frequencies), SPECTRUM_POINTS + 1).astype(int)
    shown = [float(frequencies[a:b].mean()) for a, b in pairwise(edges) if b > a]
    bands = np.linspace(0, len(frequencies), SPECTRUM_BANDS + 1).astype(int)
    result = []
    for channel in channels:
        mean = {name: np.mean(spectra[channel][name], axis=0) for name, _, _ in periods}
        changes = []
        for a, b in pairwise(bands):
            power = {name: float(mean[name][a:b].sum()) for name in mean}
            if power.get("a", 0) > 0 and power.get("b", 0) > 0:
                changes.append(
                    {
                        "from_hz": float(frequencies[a]),
                        "to_hz": float(frequencies[b - 1]),
                        "change_db": 10 * math.log10(power["b"] / power["a"]),
                    }
                )
        changes.sort(key=lambda item: -abs(item["change_db"]))
        result.append(
            {
                "channel": channel,
                "label": feature_label(f"feature.{channel}.rms").removesuffix(" RMS"),
                **{
                    name: [float(mean[name][a:b].mean()) for a, b in pairwise(edges) if b > a]
                    for name in mean
                },
                "band_changes": changes[:3],
            }
        )
    return {
        "sampling_rate_hz": rate,
        "segment": min(SPECTRUM_SEGMENT, len(frequencies) * 2 - 2),
        "frequencies": shown,
        "acquisitions": used,
        "channels": result,
    }


def strongest_identity(buckets: Sequence[Any]) -> tuple[tuple[str, str | None, str], list[Any]]:
    """One signal identity of a channel's buckets: the source, point and meaning with the most
    usable values. Sources, points and meanings are never mixed in one series."""
    groups: dict[tuple[str, str | None, str], list[Any]] = {}
    for bucket in buckets:
        key = (bucket.source_id, bucket.measurement_point_id, bucket.interpretation_json)
        groups.setdefault(key, []).append(bucket)
    if not groups:
        raise LookupError("no stored values for this signal")
    return max(groups.items(), key=lambda item: sum(b.usable_count for b in item[1]))
