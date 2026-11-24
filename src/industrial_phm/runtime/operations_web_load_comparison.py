"""The existing period comparison, scoped to the voltage change open in AI investigation."""

from __future__ import annotations

from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Any
from urllib.parse import urlencode

from industrial_phm.runtime.operations_web_explore import handle_explore_read
from industrial_phm.runtime.operations_workspace import OperationsWorkspace


def load_comparison_query(context: dict[str, Any]) -> dict[str, str] | None:
    change = context.get("history_change")
    if not change or change["unit"] != "V" or not change.get("band"):
        return None
    baseline = change["baseline"]
    start, end = (datetime.fromisoformat(change[name]) for name in ("start", "end"))
    end = max(end, start + timedelta(seconds=max(change.get("bucket_seconds") or 0, 1)))
    if context["until"] is not None:
        end = min(end, datetime.fromisoformat(context["until"]))
    if start >= end:
        return None
    return {
        "asset_id": context["asset_id"],
        "kind": "history",
        "series": change["channel"],
        "a_from": baseline["from"],
        "a_to": baseline["to"],
        "b_from": start.isoformat(),
        "b_to": end.isoformat(),
        "level": str(change["band"]),
        "level_source": change["source_id"],
        "level_point": change["measurement_point_id"] or "",
        **({"record_until": context["until"]} if context["until"] is not None else {}),
    }


def read_load_comparison(
    workspace: OperationsWorkspace, query: dict[str, str], interpretation: str
) -> dict[str, Any]:
    status, body = handle_explore_read(workspace, "/api/v1/explore/profile", urlencode(query))
    if status != HTTPStatus.OK:
        return {"status": "unavailable" if status in {400, 404} else "failed"}
    row = next(
        (
            item
            for item in body["series"]
            if item["source_id"] == query["level_source"]
            and (item["measurement_point_id"] or "") == query["level_point"]
            and item["interpretation_id"] == interpretation
        ),
        None,
    )
    if row is None or not all(row["periods"][name]["quantiles"] for name in ("a", "b")):
        return {"status": "unavailable"}
    return {
        "status": "ready",
        "profile": {**body, "series": [row]},
        "channel": query["series"],
        "until": query.get("record_until"),
    }


def load_comparison_for_answer(result: dict[str, Any]) -> dict[str, Any]:
    """The comparison as the chart in the conversation shows it, in the screen's words.

    Numbers alone ('초기 중앙값': 221.94) were read past; the model answered from the card
    instead. Written as the chart reads ('221.9 → 226.2 V'), the answer starts from it.
    """
    if result["status"] != "ready":
        return {"상태": "같은 전류 범위에서 두 구간을 비교할 측정이 부족함"}
    profile = result["profile"]
    row = profile["series"][0]
    level = profile["operation"]["levels"][profile["level"] - 1]
    a, b = (row["periods"][name] for name in ("a", "b"))
    unit = f" {row['unit']}" if row["unit"] else ""
    current = f"전류 {level['low']:.4g} A 이상" + (
        f" {level['high']:.4g} A 미만" if level["high"] is not None else ""
    )
    change = row["comparison"]["median_change"]
    return {
        "신호": row["label"],
        "견준 범위": current,
        "초기 → 특이사항 구간 중앙값": (
            f"{a['quantiles'][2]:.4g} → {b['quantiles'][2]:.4g}{unit}"
            f" ({abs(change):.3g}{unit} {'높음' if change > 0 else '낮음'})"
        ),
        "측정 수": f"초기 {a['usable_count']:,}회, 특이사항 구간 {b['usable_count']:,}회",
    }
