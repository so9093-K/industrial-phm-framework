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

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.measurement_history import PROFILE_QUANTILES, MeasurementProfile
from industrial_phm.application.phm_analysis import PhmBinding, SqlitePhmAnalysisStore, StepState
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


def _unit(interpretation_json: str) -> str | None:
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


def comparison(a: dict[str, Any], b: dict[str, Any], b_outside: int | None) -> dict[str, Any]:
    """How period B differs from period A, in measures that do not depend on units."""
    qa, qb = a.get("quantiles"), b.get("quantiles")
    if not qa or not qb:
        return {"median_change": None}
    change = qb[2] - qa[2]
    spread_a, spread_b = qa[3] - qa[1], qb[3] - qb[1]
    return {
        "median_change": change,
        "median_change_percent": 100 * change / abs(qa[2]) if qa[2] else None,
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
                "unit": _unit(interpretation),
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
) -> list[dict[str, Any]]:
    """Per-acquisition features over two acquisition ranges, with record-level quality."""
    if not features or len(features) > 8:
        raise ValueError("choose 1 to 8 features")
    by_period: dict[str, dict[str, Any]] = {}
    for name, first, last in periods:
        if not 0 <= first <= last:
            raise ValueError("an acquisition range must be increasing")
        results = store.results_between(binding.binding_id, first, last, limit=MAX_ACQUISITIONS)
        delivered = snapshots.list_between(
            binding.source_id, binding.asset_id, first, last, limit=MAX_ACQUISITIONS
        )
        analyzed = [r for r in results if r.state is StepState.ANALYZED]
        ordinals = [item.ordinal for item in delivered]
        gaps = [b - a - 1 for a, b in pairwise(ordinals) if b - a > 1]
        times = [item.delivered_at for item in delivered]
        intervals = [(b - a).total_seconds() for a, b in pairwise(times) if b > a]
        by_period[name] = {
            "first": first,
            "last": last,
            "delivered": len(delivered),
            "analyzed": analyzed,
            "skipped": len(results) - len(analyzed),
            "missing_acquisitions": sum(gaps),
            "median_interval_seconds": float(np.median(intervals)) if intervals else None,
            "truncated": len(results) >= MAX_ACQUISITIONS,
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
                "missing_count": period["missing_acquisitions"],
                "unanalyzed_count": period["skipped"],
                "first_position": points[0][0] if points else None,
                "last_position": points[-1][0] if points else None,
                "median_interval_seconds": period["median_interval_seconds"],
                "longest_constant": _constant_run(points),
                "truncated": period["truncated"],
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
                "comparison": comparison(stats.get("a", {}), stats.get("b", {}), outside),
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
