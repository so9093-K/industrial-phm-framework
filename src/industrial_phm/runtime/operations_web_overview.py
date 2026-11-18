"""One asset as a row of the comparison overview: how it ran, its main signal, its first change.

The first change is the one the asset's summary leads with, read from the same computation, so
the overview and the summary never name different changes for one record.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta
from typing import Any

from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore, StepState
from industrial_phm.application.phm_signal_comparison import feature_label
from industrial_phm.history import DuckLakeAssetHistory
from industrial_phm.runtime.operations_web_explore import _history, record_findings
from industrial_phm.runtime.operations_web_forecast import feature_unit
from industrial_phm.runtime.operations_web_vibration import acquisition_findings, feature_rank
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

_TRACE = 48


def asset_overview(workspace: OperationsWorkspace, asset_id: str) -> dict[str, Any]:
    """The overview row of one asset.

    Args:
        workspace: The operations workspace.
        asset_id: The asset.

    Returns:
        The kind of record, the operating shares, the main signal's latest value and short
        trace, the first change of the summary with how many there are, and the data issues.
    """
    body: dict[str, Any] = {
        "schema_version": 1,
        "asset_id": asset_id,
        "kind": None,
        "operation": None,
        "main": None,
        "finding": None,
        "history_interval": None,
        "vibration_interval": None,
        "finding_count": 0,
        "judged": 0,
        "copied": 0,
    }
    history = _history(workspace)
    if history is not None and any(a.asset_id == asset_id for a in history.list_history_assets()):
        found = record_findings(workspace, asset_id)
        body["kind"] = "history"
        body["judged"] = found["judged"]
        body["copied"] = sum(row["state"] == "copied" for row in found["signals"])
        body["finding_count"] = len(found["intervals"])
        if found["intervals"]:
            first = found["intervals"][0]
            body["history_interval"] = first
            body["finding"] = {
                key: first.get(key)
                for key in ("label", "unit", "band", "direction", "kind", "start", "end", "value")
            } | {
                "reference": first.get("reference_value"),
                "typical": first.get("typical_value"),
                "operation_key": (first.get("operation") or {}).get("key"),
                "latest": _latest_stored(
                    history,
                    asset_id,
                    first["channel"],
                    first["source_id"],
                    first.get("measurement_point_id"),
                ),
            }
        first_operation = ((body["history_interval"] or {}).get("operation") or {}).get("key")
        operation = (
            next((row for row in found["operation"] if row["key"] == first_operation), None)
            if first_operation
            else found["operation"][0]
            if found["operation"]
            else None
        )
        if operation is not None:
            body["operation"] = {
                key: operation[key] for key in ("key", "label", "stopped_below", "levels")
            } | {"shares": operation["shares"]["record"]}
        main = (
            operation["context"] | {"label": operation["label"], "unit": operation["unit"]}
            if operation
            else _first_judged(found)
        )
        if main is not None:
            body["main"] = _history_main(history, asset_id, main)
        return body
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    if not store.path.exists():
        return body
    found = acquisition_findings(workspace, asset_id)
    # Use the exact binding selected by the change calculation, including if ingestion
    # progresses between this read and the separate representative-signal query.
    binding = next(
        (item for item in store.list_bindings() if item.binding_id == found["binding_id"]), None
    )
    if binding is None:
        return body
    body["kind"] = "vibration"
    body["judged"] = found["judged"]
    body["finding_count"] = len(found["intervals"])
    if found["intervals"]:
        first = found["intervals"][0]
        body["vibration_interval"] = first | {
            "source_id": binding.source_id,
            "binding_id": binding.binding_id,
            "period_seconds": found["period_seconds"],
        }
        body["finding"] = {
            key: first[key] for key in ("label", "unit", "direction", "kind", "from", "to", "value")
        } | {"reference": first["reference_value"], "typical": first["typical_value"]}
        # 마지막 저장값은 변화한 특징의 값이어야 변화와 같은 이야기로 읽힌다.
        newest = store.latest_result(binding.binding_id, state=StepState.ANALYZED)
        value = (newest.features or {}).get(first["feature"]) if newest else None
        body["finding"]["latest"] = (
            {"at": None, "position": newest.position, "value": float(value)}
            if newest is not None
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            else None
        )
    results, _ = store.analyzed_between(binding.binding_id, 0, 2**62, max_points=_TRACE)
    names = sorted({name for result in results for name in (result.features or {})})
    if results and names:
        feature = min(names, key=lambda name: (feature_rank(name), name))
        points = [
            [result.position, float(value)]
            for result in results
            if isinstance(value := (result.features or {}).get(feature), (int, float))
        ]
        latest = points[-1] if points else None
        body["main"] = {
            "label": next(
                (row["label"] for row in found["intervals"] if row["feature"] == feature), None
            )
            or feature_label(feature),
            "unit": feature_unit(workspace, asset_id, binding.source_id, feature),
            "latest": {"position": latest[0], "value": latest[1]} if latest else None,
            "trace": points,
            "trace_join": [
                index > 0 and point[0] == points[index - 1][0] + 1
                for index, point in enumerate(points)
            ],
            "axis": "acquisition",
            "period_seconds": found["period_seconds"],
        }
    return body


def _first_judged(found: dict[str, Any]) -> dict[str, Any] | None:
    """Without a current, the signal of the first change, else the first judged signal."""
    keys = [item["key"] for item in found["intervals"]]
    keys += [
        row["key"]
        for row in found["signals"]
        if row["state"] in {"scored", "level-change", "constant", "cumulative"}
    ]
    rows = {row["key"]: row for row in found["signals"]}
    return next((rows[key] for key in keys if key in rows), None)


def _history_main(
    history: DuckLakeAssetHistory, asset_id: str, context: dict[str, Any]
) -> dict[str, Any]:
    """The signal's latest stored value of its own source and point, and its record's trace."""
    record = context["record"]
    start = datetime.fromisoformat(record["from"])
    end = datetime.fromisoformat(record["to"])
    if end <= start:
        end = start + timedelta(seconds=1)
    aggregation = history.query_multi_signal_measurement_aggregation(
        asset_id,
        channel_ids=[context["channel"]],
        start_at=start,
        end_at=end,
        bucket_count=_TRACE,
        source_id=context["source_id"],
        measurement_point_id=context["measurement_point_id"],
    )
    own = [
        bucket
        for bucket in aggregation.buckets
        if hashlib.sha256(bucket.interpretation_json.encode()).hexdigest()
        == context["interpretation_id"]
        and bucket.mean is not None
    ]
    return {
        "context": context,
        "label": context.get("label") or context["channel"],
        "unit": context.get("unit"),
        "latest": _latest_stored(
            history,
            asset_id,
            context["channel"],
            context["source_id"],
            context["measurement_point_id"],
        ),
        "trace": [[bucket.bucket_start.isoformat(), bucket.mean] for bucket in own],
        "trace_join": [
            index > 0
            and (bucket.bucket_start - own[index - 1].bucket_start).total_seconds()
            <= aggregation.bucket_seconds * 1.5
            for index, bucket in enumerate(own)
        ],
        "axis": "time",
    }


def _latest_stored(
    history: DuckLakeAssetHistory,
    asset_id: str,
    channel: str,
    source_id: str,
    point_id: str | None,
) -> dict[str, Any] | None:
    """The last stored value of one channel of one source and point, with its time."""
    latest = next(
        (
            point.measurement
            for point in history.query_latest_measurements(asset_id, channel_id=channel)
            if point.measurement.source_id == source_id
            and point.measurement.measurement_point_id == point_id
            and point.measurement.value is not None
            and not point.conflicting_duplicate
        ),
        None,
    )
    if latest is None or latest.event_at is None:
        return None
    return {"at": latest.event_at.isoformat(), "position": None, "value": latest.value}
