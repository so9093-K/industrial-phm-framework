"""A selected measured change and what the person sees of it on screen, for the AI to read."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore, StepState
from industrial_phm.runtime.operations_web_vibration import acquisition_findings
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

# 화면의 시각 표기(asset-timeline의 clockText)와 같은 한국 시간이다.
_KST = ZoneInfo("Asia/Seoul")
# 신호마다 그래프에서 넘기는 점 수: 모양이 읽히는 만큼만(점이 많으면 모델의 첫 응답이 느려진다).
_POINTS = 12


def selected_change(
    workspace: OperationsWorkspace, asset: str, key: str, scope: dict[str, str] | None = None
) -> dict[str, Any]:
    """The change a conversation is about, read as the screen read it (to a replay position).

    Args:
        workspace: The operations workspace.
        asset: The asset.
        key: The change's review key.
        scope: The replay position (``record_until`` or ``acquisition_until``), if any.

    Returns:
        The change and the stored analysis it belongs to; ``until`` is the replay position.

    Raises:
        ValueError: The change is no longer among the record's changes.
    """
    from industrial_phm.runtime.operations_web_explore import record_findings, record_selection

    scope = record_selection(scope or {})
    if "record_until" not in scope:
        record = acquisition_findings(
            workspace,
            asset,
            until=int(scope["acquisition_until"]) if "acquisition_until" in scope else None,
        )
    else:
        record = {"intervals": []}
    change = next((row for row in record["intervals"] if row["review_key"] == key), None)
    if change is None:
        if "acquisition_until" in scope:
            raise ValueError("선택한 변화가 달라졌습니다. 기록을 다시 불러오세요.")
        until = datetime.fromisoformat(scope["record_until"]) if "record_until" in scope else None
        record = record_findings(workspace, asset, until=until)
        change = next((row for row in record["intervals"] if row["review_key"] == key), None)
        if change is None:
            raise ValueError("선택한 변화가 달라졌습니다. 기록을 다시 불러오세요.")
        return {
            "binding_id": "history:" + change["key"],
            "package_id": None,
            "analysis_run_id": None,
            "position": int(datetime.fromisoformat(change["end"]).timestamp() * 1000),
            "asset_id": asset,
            "source_id": change["source_id"],
            "change_id": key,
            "history_change": change,
            "until": scope.get("record_until"),
            "signal_comparison": {"previous_position": change["baseline"]["to"]},
        }
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    binding = next(row for row in store.list_bindings() if row.binding_id == record["binding_id"])
    result = store.latest_result(
        binding.binding_id, state=StepState.ANALYZED, before_position=change["to"] + 1
    )
    if result is None:
        raise ValueError("이 변화의 분석 결과를 찾지 못했습니다.")
    return {
        "binding_id": binding.binding_id,
        "package_id": binding.package_id,
        "position": result.position,
        "analysis_run_id": result.analysis_run_id,
        "asset_id": asset,
        "source_id": binding.source_id,
        "change_id": key,
        "vibration_change": change,
        "until": int(scope["acquisition_until"]) if "acquisition_until" in scope else None,
        "signal_comparison": {"previous_position": change["baseline"]["to"]},
    }


def _value(number: float) -> float:
    return float(f"{number:.4g}")


def _compact_trace(points: list[list[Any]]) -> list[list[Any]]:
    """Keep both endpoints and sample in order without inventing intermediate values."""
    if len(points) <= _POINTS:
        return [point[:2] for point in points]
    return [
        points[round(index * (len(points) - 1) / (_POINTS - 1))][:2] for index in range(_POINTS)
    ]


def _history_signals(record: dict[str, Any], change: dict[str, Any]) -> list[dict[str, Any]]:
    # Other same-period comparisons already carry their values alongside the graph.
    keys = [change["key"]]
    operation = (change.get("operation") or {}).get("key")
    if operation:
        keys.append(operation)
    signals = {row["key"]: row for row in record["signals"]}
    return [
        {
            "label": signal["label"],
            "unit": signal["unit"],
            "latest": [signal["latest"]["at"], signal["latest"]["value"]]
            if signal.get("latest")
            else None,
            "trace": signal.get("preview", []),
        }
        for key in dict.fromkeys(keys)
        if (signal := signals.get(key)) is not None
    ]


def _vibration_signals(
    workspace: OperationsWorkspace, context: dict[str, Any], change: dict[str, Any]
) -> list[dict[str, Any]]:
    from industrial_phm.runtime.operations_web_overview import _vibration_group

    group = _vibration_group(
        workspace,
        SqlitePhmAnalysisStore(workspace.phm_analysis_path),
        context["asset_id"],
        context["binding_id"],
        context["source_id"],
        change["feature"],
        until=context["until"],
    )
    return [
        {
            "label": row["label"],
            "unit": group["unit"],
            "latest": row["trace"][-1] if row["trace"] else None,
            "trace": row["trace"],
        }
        for row in sorted(group["series"], key=lambda row: row["key"] != change["feature"])
    ]


def screen_view(workspace: OperationsWorkspace, context: dict[str, Any]) -> dict[str, Any]:
    """Give the model the selected change and a small view of the same stored signals."""
    history = "history_change" in context
    change = context["history_change"] if history else context["vibration_change"]
    until = context["until"]

    def at(value: str | int) -> str | int:
        return (
            datetime.fromisoformat(str(value)).astimezone(_KST).strftime("%Y-%m-%d %H:%M")
            if history
            else value
        )

    def told(value: str | int) -> str:
        # 끝난 때를 말로: 진동은 몇 번째 측정, 전력은 한국 시각.
        return f"{at(value)}" if history else f"{value}번째 측정"

    operation = None
    if history:
        from industrial_phm.runtime.operations_web_explore import record_findings

        record = record_findings(
            workspace,
            context["asset_id"],
            until=datetime.fromisoformat(until) if until is not None else None,
        )
        signals = _history_signals(record, change)
        operation_key = (change.get("operation") or {}).get("key")
        operation = next((row for row in record["operation"] if row["key"] == operation_key), None)
    else:
        signals = _vibration_signals(workspace, context, change)
    start, end = (change["start"], change["end"]) if history else (change["from"], change["to"])
    card = {
        "신호": change["label"],
        "단위": change.get("unit"),
        "변화 시작": at(start),
        "변화 끝": at(end),
        "초기 중앙값": _value(change["reference_value"])
        if change["reference_value"] is not None
        else None,
        "변화 구간 중앙값": _value(change["typical_value"])
        if change["typical_value"] is not None
        else None,
    }
    latest = signals[0]["latest"] if signals else None
    if latest is not None:
        if history:
            width = timedelta(seconds=float(change.get("bucket_seconds") or 0))
            ongoing = datetime.fromisoformat(end) + width >= datetime.fromisoformat(latest[0])
        else:
            ongoing = end >= latest[0]
        # 참/거짓 값보다 화면의 말로 줄 때 모델이 '지금 어떤지'에 쓴다.
        card["지금도 이어지는지"] = "기록 끝까지 이어짐" if ongoing else f"{told(end)}에 끝남"
    band = change.get("band")
    if operation and band is not None and 0 < band <= len(operation["levels"]):
        # 두 중앙값은 한 운전 수준의 측정끼리 견준 값이다. 화면 제목('약 11 A 운전일 때')처럼
        # 값 옆에 붙인다. 따로 두었더니 모델이 다른 부하로 돈 마지막 값과 견주어 '전압 저하'라고
        # 읽었다.
        level = operation["levels"][band - 1]
        unit = f" {operation['unit']}" if operation.get("unit") else ""
        running = f"약 {_value(level['typical']):g}{unit} 운전 중인 측정끼리"
        card["초기 중앙값"] = {"값": card["초기 중앙값"], "조건": running}
        card["변화 구간 중앙값"] = {"값": card["변화 구간 중앙값"], "조건": running}
    if load := change.get("load"):
        card["같은 기간의 평균 전류(모든 운전 수준)"] = {
            "신호": load["label"],
            "단위": load["unit"],
            "초기": _value(load["reference"]),
            "변화 구간": _value(load["current"]),
        }
    if halves := change.get("halves"):
        card["변화 구간 앞·뒤 절반의 관측 변화량"] = [
            {**half, "change": _value(half["change"])} for half in halves
        ]

    # 지금 어떤지가 '문제 있어?'의 답이다: 신호 다음에 둔다(모델은 앞에 놓인 것부터 쓴다).
    first = ("신호", "지금도 이어지는지")
    card = {key: card[key] for key in first if key in card} | {
        key: value for key, value in card.items() if key not in first
    }
    return {
        # 데이터의 출처나 '판정이 없다' 같은 말은 넣지 않는다: 모델이 그 말을 답으로 옮겼다
        # ("고장이나 교체 판정 결과는 기록되어 있지 않습니다").
        "설비": context["asset_id"],
        "가로축": "한국 시각" if history else "측정 순서",
        "선택한 변화": card,
        "함께 비교한 신호": [
            {
                "신호": row["label"],
                "단위": row["unit"],
                "초기 중앙값": _value(row["reference"]),
                "변화 구간 중앙값": _value(row["current"]),
            }
            for row in change.get("related", [])
        ],
        "신호별 마지막 값과 추이": [
            {
                "신호": signal["label"],
                "단위": signal["unit"],
                "마지막 측정": (
                    [at(latest[0]), _value(latest[1])]
                    if (latest := signal["latest"]) and math.isfinite(latest[1])
                    else None
                ),
                "추이": [
                    [at(x), _value(value)]
                    for x, value in _compact_trace(signal["trace"])
                    if math.isfinite(value)
                ],
            }
            for signal in signals
        ],
    }
