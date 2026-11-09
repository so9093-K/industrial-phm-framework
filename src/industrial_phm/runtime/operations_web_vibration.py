"""Representative changes in the analysed features of an asset's waveform acquisitions.

Each acquisition is one measurement with features such as RMS and kurtosis per axis. The
features are judged like stored signals: against the first 30% of the acquisitions, choosing
long, record-end and large changes. Acquisitions are placed on a time axis by their recorded
interval only to reuse that judgement; every position is reported back as an acquisition number.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.exploratory_anomaly import interval_comparison, record_changes
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.phm_signal_comparison import (
    feature_label,
    feature_unit,
    stream_amplitude_unit,
)
from industrial_phm.application.signal_exploration import acquisition_binding
from industrial_phm.runtime.operations_web_explore import acquisition_period
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

_ORIGIN = datetime(2000, 1, 1, tzinfo=UTC)
_POINTS = 1000
_SHOWN = 3
_TRACE = 48
_RELATED = 3
# Energy first, then impulsiveness: RMS shows how hard the machine vibrates, kurtosis and
# crest factor whether sharp impacts appear, as bearing faults first do.
_RANK = {"rms": 0, "excess_kurtosis": 1, "crest_factor": 2, "absolute_peak": 3, "peak_to_peak": 3}


def feature_rank(feature: str) -> int:
    """Order in which a feature's changes are looked at, lower first."""
    return _RANK.get(feature.rsplit(".", 1)[-1], 4)


def acquisition_findings(workspace: OperationsWorkspace, asset_id: str) -> dict[str, Any]:
    """Representative changes in an asset's acquisition features, by acquisition number.

    Args:
        workspace: The operations workspace.
        asset_id: The asset.

    Returns:
        The judged features and up to three changes, each with its acquisitions, reference
        values and a short trace; empty when the asset has no analysed acquisitions.
    """
    body: dict[str, Any] = {
        "schema_version": 1,
        "asset_id": asset_id,
        "source_id": None,
        "period_seconds": None,
        "first": None,
        "last": None,
        "judged": 0,
        "features": 0,
        "intervals": [],
        "meaning": "departures-from-the-first-30-percent-not-fault-diagnosis",
    }
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    if not store.path.exists():
        return body
    binding = acquisition_binding(store, asset_id)
    if binding is None:
        return body
    results, _ = store.analyzed_between(binding.binding_id, 0, 2**62, max_points=_POINTS)
    if not results:
        return body
    period = acquisition_period(workspace, asset_id, binding.source_id)
    step = period if period and period > 0 else 1.0
    positions = [result.position for result in results]
    # A sampled record keeps every acquisition between two kept ones with the earlier.
    following = dict(pairwise(positions))
    stride = min((b - a for a, b in pairwise(positions)), default=1)

    def at(position: float) -> datetime:
        return _ORIGIN + timedelta(seconds=(position - 1) * step)

    def number(moment: datetime) -> int:
        return round(1 + (moment - _ORIGIN).total_seconds() / step)

    names = sorted({name for result in results for name in (result.features or {})})
    series: dict[str, list[tuple[datetime, datetime, float]]] = {}
    for name in names:
        points = []
        for result in results:
            value = (result.features or {}).get(name)
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                end = following.get(result.position, result.position + stride)
                points.append((at(result.position), at(end), float(value)))
        if points:
            series[name] = points
    snapshots = (
        SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
        if workspace.acquisition_snapshot_path.is_file()
        else None
    )
    amplitude = stream_amplitude_unit(snapshots, binding.source_id, asset_id) if snapshots else None
    body.update(
        {
            "source_id": binding.source_id,
            "period_seconds": period,
            "first": positions[0],
            "last": positions[-1],
            "features": len(names),
        }
    )
    if not series:
        return body
    try:
        found = record_changes(
            series, limit=_SHOWN, priority={name: feature_rank(name) for name in series}
        )
    except LookupError, ValueError:
        return body
    body["judged"] = sum(
        row["state"] in {"scored", "level-change", "constant"} for row in found["channels"]
    )
    usual = {
        row["key"]: (row["median"], row["spread"])
        for row in found["channels"]
        if row["state"] in {"scored", "level-change"}
    }
    for item in found["intervals"]:
        name = item["channel"]
        median, spread = usual[name]
        reference = (item["baseline"]["from"], item["baseline"]["to"])
        compared = interval_comparison(series[name], reference, (item["start"], item["end"]))
        values = series[name]
        indices = sorted({round(i * (len(values) - 1) / (_TRACE - 1)) for i in range(_TRACE)})
        # Other features that moved over the same acquisitions, energy and impacts first.
        moved = []
        for other, points in series.items():
            if other == name:
                continue
            row = interval_comparison(points, reference, (item["start"], item["end"]))
            if row is not None and row["state"] != "within":
                moved.append((feature_rank(other), -row["distance"], other, row))
        related = [
            {
                "feature": other,
                "label": feature_label(other),
                "unit": feature_unit(other, amplitude),
                "reference": row["reference"],
                "current": row["current"],
                "state": row["state"],
            }
            for _, _, other, row in sorted(moved)[:_RELATED]
        ]
        body["intervals"].append(
            {
                "feature": name,
                "label": feature_label(name),
                "unit": feature_unit(name, amplitude),
                "direction": item["direction"],
                "reason": item["reason"],
                "kind": item["kind"],
                "from": number(item["start"]),
                "to": number(item["end"]) - 1,
                "baseline": {"from": number(reference[0]), "to": number(reference[1]) - 1},
                "reference_value": compared["reference"] if compared else None,
                "typical_value": compared["current"] if compared else None,
                "value": item["value"],
                "usual": {
                    "low": median - found["threshold"] * spread,
                    "high": median + found["threshold"] * spread,
                },
                "trace": [[number(values[i][0]), values[i][2]] for i in indices],
                "related": related,
            }
        )
    return body
