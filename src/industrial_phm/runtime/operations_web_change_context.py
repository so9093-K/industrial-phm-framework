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
_POINTS = 30


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


def _text(number: float, unit: str | None) -> str:
    """A value as the screen writes it: four significant digits and its unit."""
    return f"{_value(number):g}" + (f" {unit}" if unit else "")


def _compact_trace(points: list[list[Any]]) -> list[list[Any]]:
    """Keep both endpoints and sample in order without inventing intermediate values."""
    if len(points) <= _POINTS:
        return [point[:2] for point in points]
    return [
        points[round(index * (len(points) - 1) / (_POINTS - 1))][:2] for index in range(_POINTS)
    ]


def _span(seconds: float) -> str:
    """'22시간 12분', '2일 3시간': how long a change lasted, as the monitor card says it."""
    minutes = round(seconds / 60)
    days, hours, rest = minutes // 1440, minutes % 1440 // 60, minutes % 60
    parts = [f"{days}일"] * bool(days) + [f"{hours}시간"] * bool(hours)
    parts += [f"{rest}분"] * bool(rest and not days)
    return " ".join(parts) or "1분 미만"


_PHASES = ("R상", "S상", "T상")


def _history_chart(record: dict[str, Any], change: dict[str, Any]) -> list[dict[str, Any]]:
    """The signals the monitor draws for a power change: its phases, then the load current."""
    phased = change["channel"].startswith(_PHASES) and change.get("observed_property")

    def member(row: dict[str, Any]) -> bool:
        same = (row["source_id"], row["measurement_point_id"], row["unit"]) == (
            change["source_id"],
            change["measurement_point_id"],
            change["unit"],
        )
        return same and (
            row["key"] == change["key"]
            or (
                bool(phased)
                and row["channel"].startswith(_PHASES)
                and row.get("observed_property") == change.get("observed_property")
            )
        )

    rows = sorted(filter(member, record["signals"]), key=lambda row: row["channel"])
    load = (change.get("operation") or {}).get("key")
    rows += [row for row in record["signals"] if load and row["key"] == load]
    return [
        {"label": row["label"], "unit": row["unit"], "trace": row.get("preview", [])}
        for row in rows
    ]


def _vibration_chart(
    workspace: OperationsWorkspace, context: dict[str, Any], change: dict[str, Any]
) -> list[dict[str, Any]]:
    """The axes the monitor draws for a vibration change, to the replay position."""
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
        {"label": row["label"], "unit": group["unit"], "trace": row["trace"]}
        for row in sorted(group["series"], key=lambda row: row["key"] != change["feature"])
    ]


def screen_view(workspace: OperationsWorkspace, context: dict[str, Any]) -> dict[str, Any]:
    """What the person sees on the monitor for the selected change, in the screen's words.

    The card (the change, how long, whether it still goes on, the values it compared and the
    load at the same time), the values at the last measurement and the chart's signals. The
    AI answers from this; it is given no sentences about what the data lacks.

    Args:
        workspace: The operations workspace.
        context: The selected change from ``selected_change``.

    Returns:
        A small JSON view of the screen, read to the replay position when there is one.
    """
    history = "history_change" in context
    change = context["history_change"] if history else context["vibration_change"]
    until = context["until"]
    unit = change.get("unit")

    def when(value: str | int) -> str:
        # 화면의 말: 전력은 한국 시각, 진동은 몇 번째 측정.
        if not history:
            return f"{value}번째 측정"
        moment = datetime.fromisoformat(str(value)).astimezone(_KST)
        return f"{moment.month}월 {moment.day}일 {moment:%H:%M}"

    def tick(value: str | int) -> str | int:
        # 그래프의 가로축은 짧게(메시지 크기 제한 8KB 안에서 점을 더 보낸다).
        if not history:
            return value
        return datetime.fromisoformat(str(value)).astimezone(_KST).strftime("%m-%d %H:%M")

    operation = None
    if history:
        from industrial_phm.runtime.operations_web_explore import record_findings

        record = record_findings(
            workspace,
            context["asset_id"],
            until=datetime.fromisoformat(until) if until is not None else None,
        )
        chart = _history_chart(record, change)
        operation_key = (change.get("operation") or {}).get("key")
        operation = next((row for row in record["operation"] if row["key"] == operation_key), None)
    else:
        chart = _vibration_chart(workspace, context, change)
    chart = [
        row | {"trace": [point for point in row["trace"] if math.isfinite(point[1])]}
        for row in chart
    ]
    start, end = (change["start"], change["end"]) if history else (change["from"], change["to"])
    card: dict[str, Any] = {"신호": change["label"]}
    own = next((row["trace"] for row in chart if row["label"] == change["label"]), None)
    last = own[-1] if own else None
    ongoing = False
    if last is not None:
        if history:
            width = timedelta(seconds=float(change.get("bucket_seconds") or 0))
            ongoing = datetime.fromisoformat(end) + width >= datetime.fromisoformat(last[0])
        else:
            ongoing = end >= last[0]
        # '문제 있어?'는 지금을 묻는다: 이어지는지 끝났는지를 말로, 신호 바로 다음에 둔다.
        card["지금도 이어지는지"] = "기록 끝까지 이어짐" if ongoing else f"{when(end)}에 끝남"
    lasted = (
        _span((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())
        if history
        else f"{end - start + 1}회 측정"
    )
    card["언제"] = f"{when(start)}부터 {lasted}"
    before, after = change["reference_value"], change["typical_value"]
    if before is not None and after is not None:
        compared = "초기 → 특이사항 구간"
        band = change.get("band")
        if operation and band is not None and 0 < band <= len(operation["levels"]):
            # 한 운전 수준의 측정끼리 견준 값이다. 화면 제목('약 11 A 운전일 때')처럼 값 옆에
            # 붙인다. 따로 두었더니 모델이 다른 부하로 돈 마지막 값과 견주었다.
            level = operation["levels"][band - 1]
            compared += f" (약 {_text(level['typical'], operation.get('unit'))} 운전 중인 측정끼리)"
        card[compared] = f"{_text(before, None)} → {_text(after, unit)}"
        if not history and ongoing and last is not None and before:
            # 계속 커지는 진동은 관제 카드처럼 지금 값으로 말한다('지금 초기의 약 9.3배').
            card["지금"] = f"{_text(last[1], unit)} (초기의 약 {last[1] / before:.1f}배)"
    if load := change.get("load"):
        card[f"같은 기간 {load['label']}"] = (
            f"{_text(load['reference'], None)} → {_text(load['current'], load['unit'])}"
        )
    if halves := change.get("halves"):
        first, second = (f"{half['change']:+.3g}" for half in halves)
        card["특이사항 구간 앞 절반 → 뒤 절반에 움직인 양"] = (
            f"{first} → {second} {unit or ''}".strip()
        )
    related = [
        f"{row['label']} {_text(row['reference'], None)} → {_text(row['current'], row['unit'])}"
        for row in change.get("related", [])
    ]
    return {
        # 출처('저장 기록')나 '판정이 없다' 같은 말은 넣지 않는다: 모델이 그 말을 답으로 옮겼다.
        "설비": context["asset_id"],
        "특이사항": card,
        **({"같은 기간 다른 신호": related} if related else {}),
        "지금 값(마지막 측정)": {
            row["label"]: f"{_text(row['trace'][-1][1], row['unit'])} ({when(row['trace'][-1][0])})"
            for row in chart
            if row["trace"]
        },
        "그래프(시각, 값)" if history else "그래프(측정 번호, 값)": {
            row["label"]: [[tick(x), _value(value)] for x, value in _compact_trace(row["trace"])]
            for row in chart
            if row["trace"]
        },
    }
