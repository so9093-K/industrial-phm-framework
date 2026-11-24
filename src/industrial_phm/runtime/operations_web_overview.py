"""One asset as a row of the comparison overview: how it ran, its main signal, its first change.

The first change is the one the asset's summary leads with, read from the same computation, so
the overview and the summary never name different changes for one record. A recorded asset's
row is kept while its record is unchanged, and ``OverviewPreparation`` computes the rows before
anyone opens the monitor.
"""

from __future__ import annotations

import hashlib
import logging
import math
import threading
from datetime import datetime, timedelta
from typing import Any

from industrial_phm.application.measurement_history import HistoryAssetSummary
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore, StepState
from industrial_phm.application.phm_signal_comparison import feature_label
from industrial_phm.history import DuckLakeAssetHistory
from industrial_phm.runtime.operations_web_explore import (
    MAX_ATTENTION_ASSETS,
    _history,
    record_findings,
)
from industrial_phm.runtime.operations_web_forecast import feature_unit
from industrial_phm.runtime.operations_web_vibration import acquisition_findings, feature_rank
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

_TRACE = 48
# 관제 화면 한 칸의 너비에서 선이 끊겨 보이지 않을 만큼, 그러나 설비마다 가볍게.
_GROUP_POINTS = 320
_PHASES = ("R상", "S상", "T상")
# 기록 기반 설비의 관제 카드: 그 설비의 기록이 같으면 다시 읽지 않는다. 한 달 기록이면
# 특이사항 계산에 십수 초, 그래프의 묶음 값을 읽는 데만 1초 넘게 걸린다.
_overview_cache: dict[tuple[str, str, str | None], tuple[HistoryAssetSummary, dict[str, Any]]] = {}
_LOGGER = logging.getLogger(__name__)


def asset_overview(
    workspace: OperationsWorkspace, asset_id: str, *, like: str | None = None
) -> dict[str, Any]:
    """The overview row of one asset.

    Args:
        workspace: The operations workspace.
        asset_id: The asset.
        like: The channel (or vibration feature) the monitored group is built around, so every
            asset of one dataset shows the same signals. Without it, the asset's first change.

    Returns:
        The kind of record, the operating shares, the main signal's latest value and short
        trace, the first change of the summary with how many there are, the data issues, and
        the monitored group: the changed signal with its other phases or axes over the record.
    """
    body: dict[str, Any] = {
        "schema_version": 1,
        "asset_id": asset_id,
        "kind": None,
        "operation": None,
        "main": None,
        "group": None,
        # 묶음 아래 같은 시간축에 그리는 부하 신호(전류): 전압이 오른 때의 부하가 함께 보인다.
        "companion": None,
        "finding": None,
        "history_interval": None,
        "vibration_interval": None,
        "finding_count": 0,
        "judged": 0,
        "copied": 0,
    }
    history = _history(workspace)
    summary = (
        next((a for a in history.list_history_assets() if a.asset_id == asset_id), None)
        if history is not None
        else None
    )
    if history is not None and summary is not None:
        key = (str(workspace.root), asset_id, like)
        held = _overview_cache.get(key)
        if held is not None and held[0] == summary:
            return held[1]
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
                # 상태 요약과 같은 값: 변화한 기록의 마지막 구간 평균.
                "latest": next(
                    (
                        {
                            "at": row["latest"]["at"],
                            "position": None,
                            "value": row["latest"]["value"],
                        }
                        for row in found["signals"]
                        if row["key"] == first["key"] and row.get("latest")
                    ),
                    None,
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
        if like is not None:
            # 같은 데이터셋의 설비는 같은 이름의 신호로 묶어야 줄끼리 비교된다. 없으면 묶음도 없다.
            focus = next((row for row in found["signals"] if row["channel"] == like), None)
        else:
            focus = body["history_interval"] or main
        if focus is not None:
            body["group"] = _history_group(history, asset_id, found, focus)
        group = body["group"]
        if operation is not None and group is not None and group.get("unit") != operation["unit"]:
            load = next(
                (row for row in found["signals"] if row["key"] == operation["context"]["key"]),
                None,
            )
            if load is not None:
                body["companion"] = _history_group(history, asset_id, found, load)
        if len(_overview_cache) > 4 * MAX_ATTENTION_ASSETS:
            _overview_cache.clear()
        _overview_cache[key] = (summary, body)
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
        focus = like or (found["intervals"][0]["feature"] if found["intervals"] else feature)
        body["group"] = _vibration_group(
            workspace, store, asset_id, binding.binding_id, binding.source_id, focus
        ) | {"period_seconds": found["period_seconds"]}
    return body


class OverviewPreparation:
    """Keeps each recorded asset's monitor row computed before anyone opens the monitor.

    Without it, a restarted server computes every recorded asset on the first visit; a month
    of 35 signals takes over ten seconds. The first pass computes every asset. Later passes
    compute an asset whose record changed once it held still for one pass, so a record still
    being written (a live source, an import in progress) is left to the screen that asks.
    """

    def __init__(self, workspace: OperationsWorkspace) -> None:
        """Prepare the rows of one workspace.

        Args:
            workspace: The workspace the Web server reads, with the same root path.
        """
        self._workspace = workspace
        self._seen: dict[str, HistoryAssetSummary] | None = None
        self._failed: dict[str, HistoryAssetSummary] = {}

    def run_once(self) -> list[str]:
        """Compute the rows that are missing or out of date.

        Returns:
            The assets whose rows were computed in this pass.
        """
        history = _history(self._workspace)
        if history is None:
            return []
        first, seen = self._seen is None, dict(self._seen or {})
        computed: list[str] = []
        for summary in history.list_history_assets()[:MAX_ATTENTION_ASSETS]:
            asset_id = summary.asset_id
            held = _overview_cache.get((str(self._workspace.root), asset_id, None))
            steady = first or seen.get(asset_id) == summary
            seen[asset_id] = summary
            if (
                (held is not None and held[0] == summary)
                or not steady
                or self._failed.get(asset_id) == summary
            ):
                continue
            try:
                asset_overview(self._workspace, asset_id)
            except Exception:
                # 같은 기록으로는 다시 시도하지 않는다. 화면이 물으면 그때 직접 계산한다.
                _LOGGER.exception("monitor row of %s could not be prepared", asset_id)
                self._failed[asset_id] = summary
                continue
            computed.append(asset_id)
        self._seen = seen
        return computed

    def run(self, stop: threading.Event, *, interval_seconds: float = 30.0) -> None:
        """Prepare rows once every ``interval_seconds`` until ``stop`` is set.

        Args:
            stop: Set to end the loop.
            interval_seconds: The wait between passes.
        """
        while not stop.is_set():
            try:
                self.run_once()
            except Exception:
                # 저장소를 잠시 읽지 못해도 다음 주기에 다시 본다.
                _LOGGER.exception("monitor rows could not be prepared")
            stop.wait(interval_seconds)


def _history_group(
    history: DuckLakeAssetHistory,
    asset_id: str,
    found: dict[str, Any],
    focus: dict[str, Any],
) -> dict[str, Any] | None:
    """The focus signal and its other phases on the focus record's own time axis.

    Args:
        history: The stored measurement history.
        asset_id: The asset.
        found: The asset's record findings, for the signals and their identities.
        focus: The signal the asset is monitored by (its first change, else its main signal).

    Returns:
        The group's name, unit and record, and one bucket-mean trace per member, or None
        when the focus signal is not among the judged signals.
    """
    phased = focus["channel"].startswith(_PHASES) and focus.get("observed_property") is not None

    def member(row: dict[str, Any]) -> bool:
        if (row["source_id"], row["measurement_point_id"], row["unit"]) != (
            focus["source_id"],
            focus["measurement_point_id"],
            focus["unit"],
        ):
            return False
        # 한 상의 변화는 같은 의미의 다른 상과 겹쳐 봐야 함께 움직였는지 보인다.
        return row["key"] == focus["key"] or (
            phased
            and row["channel"].startswith(_PHASES)
            and row["observed_property"] == focus["observed_property"]
        )

    members = sorted(filter(member, found["signals"]), key=lambda row: row["channel"])[:8]
    if not any(row["key"] == focus["key"] for row in members):
        return None
    start = datetime.fromisoformat(focus["record"]["from"])
    end = max(datetime.fromisoformat(focus["record"]["to"]), start + timedelta(seconds=1))
    aggregation = history.query_multi_signal_measurement_aggregation(
        asset_id,
        channel_ids=[row["channel"] for row in members],
        start_at=start,
        end_at=end,
        bucket_count=_GROUP_POINTS,
        source_id=focus["source_id"],
        measurement_point_id=focus["measurement_point_id"],
    )
    series = []
    for row in members:
        own = [
            bucket
            for bucket in aggregation.buckets
            if bucket.channel_id == row["channel"]
            and bucket.mean is not None
            and hashlib.sha256(bucket.interpretation_json.encode()).hexdigest()
            == row["interpretation_id"]
        ]
        series.append(
            {
                "key": row["key"],
                "channel": row["channel"],
                "label": row["label"],
                "short": row["channel"][:2] if len(members) > 1 else row["label"],
                "trace": [[bucket.bucket_start.isoformat(), bucket.mean] for bucket in own],
                "trace_join": [
                    index > 0
                    and (bucket.bucket_start - own[index - 1].bucket_start).total_seconds()
                    <= aggregation.bucket_seconds * 1.5
                    for index, bucket in enumerate(own)
                ],
            }
        )
    single = focus.get("label") or focus["channel"]
    return {
        "label": focus["channel"][1:] if len(members) > 1 else single,
        "unit": focus["unit"],
        "axis": "time",
        "focus": focus["key"],
        "record": {"from": focus["record"]["from"], "to": focus["record"]["to"]},
        "bucket_seconds": aggregation.bucket_seconds,
        "period_seconds": None,
        "series": series,
    }


def _vibration_group(
    workspace: OperationsWorkspace,
    store: SqlitePhmAnalysisStore,
    asset_id: str,
    binding_id: str,
    source_id: str,
    focus: str,
) -> dict[str, Any]:
    """The focus feature and the same statistic of the other vibration axes, per acquisition.

    Args:
        workspace: The operations workspace, for units.
        store: The analysis store.
        asset_id: The asset.
        binding_id: The binding whose analyzed acquisitions are read.
        source_id: The binding's source, for units.
        focus: The feature the asset is monitored by.

    Returns:
        The group's name, unit and acquisition range, and one trace per member.
    """
    results, total = store.analyzed_between(binding_id, 0, 2**62, max_points=_GROUP_POINTS)
    statistic = focus.rpartition(".")[2]
    names = sorted(
        {
            name
            for result in results
            for name in (result.features or {})
            if name.startswith("feature.") and name.rpartition(".")[2] == statistic
        }
        | {focus}
    )
    # 표본으로 줄였으면 표본 간격까지는 이어진 측정으로 본다.
    stride = (
        max(1.0, (results[-1].position - results[0].position) / max(1, len(results) - 1))
        if len(results) < total and results
        else 1.0
    )
    series = []
    for name in names:
        points = [
            [result.position, float(value)]
            for result in results
            if isinstance(value := (result.features or {}).get(name), (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        ]
        label = feature_label(name)
        series.append(
            {
                "key": name,
                "channel": name,
                "label": label,
                "short": label.split(" ", 1)[0] if len(names) > 1 else label,
                "trace": points,
                "trace_join": [
                    index > 0 and point[0] - points[index - 1][0] <= stride * 1.5
                    for index, point in enumerate(points)
                ],
            }
        )
    label = feature_label(focus)
    return {
        "label": label.split(" ", 1)[1] if len(names) > 1 and " " in label else label,
        "unit": feature_unit(workspace, asset_id, source_id, focus),
        "axis": "acquisition",
        "focus": focus,
        "record": {
            "from": results[0].position if results else None,
            "to": results[-1].position if results else None,
        },
        "bucket_seconds": None,
        "series": series,
    }


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
