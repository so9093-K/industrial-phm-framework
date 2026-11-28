"""A selected measured change and what the person sees of it on screen, for the AI to read."""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from industrial_phm.application.condition_outlook import RECENT_MEASUREMENTS
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore, StepState
from industrial_phm.runtime.operations_web_vibration import acquisition_findings
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

# 화면의 시각 표기(asset-timeline의 clockText)와 같은 한국 시간이다.
_KST = ZoneInfo("Asia/Seoul")
_TRACE_SEGMENTS = 5
_PHASES = ("R상", "S상", "T상")


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
        "vibration_current_axes": record["current_axes"],
        "vibration_last": record["last"],
        "until": int(scope["acquisition_until"]) if "acquisition_until" in scope else None,
        "signal_comparison": {"previous_position": change["baseline"]["to"]},
    }


# AI가 대화에서 고를 수 있는 분석. 'compare_same_load'는 대화 안에서 실행해 차트로 보이고,
# 나머지는 이미 있는 분석 화면으로 잇는다(화면이 그 링크를 만든다). 설명은 모델이 고를 때 읽는다.
_HISTORY_ANALYSES = {
    "compare_same_load": "'같은 전류 범위 비교': 같은 전류 범위의 측정끼리 전압을 견주어 부하 "
    "차이 때문인지 가려 본다. 대화 안에 차트로 보인다.",
    "open_compare": "'기간 비교' 화면: 초기와 특이사항 구간의 값과 분포를 자세히 견준다.",
    "open_relation": "'신호 관계' 화면: 이 신호와 함께 달라진 다른 신호를 같은 시각끼리 견준다.",
    "open_phase_balance": "'3상 전력' 화면: R·S·T 세 상의 전압·전류와 불평형을 함께 본다.",
    "open_signals": "'실측 신호' 화면: 같은 시각의 실측 신호들을 그래프로 펼쳐 본다.",
}
_VIBRATION_ANALYSES = {
    "open_compare": "'기간 비교' 화면: 초기와 특이사항 구간의 진동 특징을 자세히 견준다.",
    "open_spectrum": "'주파수' 화면: 어느 주파수 대역의 진동 에너지가 커졌는지 본다. 어디를 "
    "점검할지 가릴 때 본다.",
    "open_signals": "'실측 신호' 화면: 측정마다 진동 값과 원본 파형을 본다.",
    "open_outlook": "'전망·예상 여유' 화면: 지금 속도라면 사람이 정한 기준에 언제 닿을지 본다.",
}


def change_analyses(context: dict[str, Any], *, same_load: bool) -> list[str]:
    """The analyses the AI may pick for this change: only those this change can open.

    Args:
        context: The selected change from ``selected_change``.
        same_load: Whether the same-current comparison can run for this change.

    Returns:
        Analysis names; ``analysis_descriptions`` says what each shows.
    """
    if "vibration_change" in context:
        return list(_VIBRATION_ANALYSES)
    change = context["history_change"]
    available = list(_HISTORY_ANALYSES)
    if not same_load:
        available.remove("compare_same_load")
    if not change.get("related"):
        available.remove("open_relation")
    if not change["channel"].startswith(_PHASES):
        available.remove("open_phase_balance")
    return available


def analysis_descriptions(names: list[str], *, vibration: bool) -> dict[str, str]:
    """What each named analysis shows, as the model reads it when choosing one.

    The names travel with a question; the descriptions are added here, so the message from
    the Web process to the supervisor stays under its size limit.
    """
    known = _VIBRATION_ANALYSES if vibration else _HISTORY_ANALYSES
    return {name: known[name] for name in names if name in known}


def mentioned_analysis(answer: str, offered: dict[str, str]) -> str | None:
    """The one offered analysis screen an answer names, when it names exactly one.

    The model often points to a screen in words instead of opening it. The link under the
    answer is then that screen, not a fixed follow-up that says something else. A screen is
    named by the quoted name its description starts with ('주파수' 화면); the same-current
    comparison runs a chart in the conversation and is never only pointed to.
    """
    found = {
        name
        for name, description in offered.items()
        if name in OPENS
        and (quoted := re.match(r"'([^']+)'", description))
        and quoted.group(1) in answer
    }
    return found.pop() if len(found) == 1 else None


# 분석 화면(대화를 연 곳)의 이름. 그 화면에서 물으면 화면이 보여 주는 수치를 함께 읽는다.
VIEWS = {
    "compare": "기간 비교",
    "relation": "신호 관계",
    "spectrum": "주파수",
    "electrical": "3상 전력",
    "signals": "실측 신호",
    "anomaly": "이상 점수",
}
# 대화에서 AI가 함께 여는 분석과 그 분석 화면.
OPENS = {
    "open_compare": "compare",
    "open_relation": "relation",
    "open_spectrum": "spectrum",
    "open_phase_balance": "electrical",
    "open_signals": "signals",
    "open_outlook": "outlook",
}


def _value(number: float) -> float:
    return float(f"{number:.4g}")


def _text(number: float, unit: str | None, digits: int = 3) -> str:
    """A value as the monitor card writes it: three significant digits ('5.78 g', '226 V').

    The model repeats the digits it is given; four ('5.784g', '0.6231g') read unlike the card.
    """
    value = float(f"{number:.{digits}g}")
    text = f"{value:,.0f}" if abs(value) >= 1000 else f"{value:g}"
    return text + (f" {unit}" if unit else "")


def _reading(number: float, unit: str | None) -> str:
    """A current reading as the card's value list writes it: voltages keep a decimal (214.8 V)."""
    return _text(number, unit, 4 if unit == "V" else 3)


def _about(number: float) -> str:
    """'약 11 A 운전'의 11: 화면(record-findings의 bandName)처럼 두 자리로 어림한다."""
    value = float(f"{number:.2g}")
    return f"{value:,.0f}" if abs(value) >= 10 else f"{value:g}"


def asset_label(workspace: OperationsWorkspace, asset_id: str) -> str:
    """The equipment's name as the monitor shows it: a declared name, '베어링 1-1', or its ID."""
    from industrial_phm.application import JsonSourceRepository
    from industrial_phm.application.asset_display import resolve_asset_display_names

    if workspace.source_registry_path.is_file():
        sources = JsonSourceRepository(workspace.source_registry_path).list_sources()
        if declared := resolve_asset_display_names(sources).name(asset_id):
            return declared
    if bearing := re.fullmatch(r"Bearing(\d+)_(\d+)", asset_id):
        return f"베어링 {bearing[1]}-{bearing[2]}"
    return asset_id


def _compact_trace(points: list[list[Any]]) -> list[list[Any]]:
    """Keep both endpoints and each segment's extremes in measurement order."""
    if len(points) <= 2 + 2 * _TRACE_SEGMENTS:
        return [point[:2] for point in points]
    interior = len(points) - 2
    sampled = [points[0][:2]]
    for index in range(_TRACE_SEGMENTS):
        start = 1 + index * interior // _TRACE_SEGMENTS
        end = 1 + (index + 1) * interior // _TRACE_SEGMENTS
        positions = range(start, end)
        low = min(positions, key=lambda at: points[at][1])
        high = max(positions, key=lambda at: points[at][1])
        sampled.extend(points[at][:2] for at in sorted({low, high}))
    sampled.append(points[-1][:2])
    return sampled


def _span(seconds: float) -> str:
    """'22시간 12분', '2일 3시간': how long a change lasted, as the monitor card says it."""
    minutes = round(seconds / 60)
    days, hours, rest = minutes // 1440, minutes % 1440 // 60, minutes % 60
    parts = [f"{days}일"] * bool(days) + [f"{hours}시간"] * bool(hours)
    parts += [f"{rest}분"] * bool(rest and not days)
    return " ".join(parts) or "1분 미만"


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
        until=context["vibration_last"],
    )
    return [
        {"key": row["key"], "label": row["label"], "unit": group["unit"], "trace": row["trace"]}
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
        # 그래프의 가로축은 짧게 적고, 카드의 변화 시점과 짚은 점은 원래 시각으로 읽는다.
        if not history:
            return value
        return datetime.fromisoformat(str(value)).astimezone(_KST).strftime("%m-%d %H:%M")

    operation = None
    current_axes = {row["channel"]: row for row in context.get("vibration_current_axes", [])}
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
            ongoing = end == last[0] == context["vibration_last"]
        # '문제 있어?'는 지금을 묻는다: 이어지는지 끝났는지를 말로, 신호 바로 다음에 둔다.
        card["지금도 이어지는지"] = "기록 끝까지 이어짐" if ongoing else f"{when(end)}에 끝남"
    lasted = (
        _span((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())
        if history
        else f"{end - start + 1}회 측정"
    )
    card["언제"] = f"{when(start)}부터 {lasted}"
    before, after = change["reference_value"], change["typical_value"]
    compared = "초기 → 특이사항 구간"
    if before is not None and after is not None:
        band = change.get("band")
        if operation and band is not None and 0 < band <= len(operation["levels"]):
            # 한 운전 수준의 측정끼리 견준 값이다. 화면 제목('약 11 A 운전일 때')처럼 값 옆에
            # 붙인다. 따로 두었더니 모델이 다른 부하로 돈 마지막 값과 견주었다.
            level = operation["levels"][band - 1]
            unit_name = f" {operation['unit']}" if operation.get("unit") else ""
            compared += f" (약 {_about(level['typical'])}{unit_name} 운전 중인 측정끼리)"
        card[compared] = f"{_text(before, None)} → {_text(after, unit)}"
        if not history and ongoing and (axis := current_axes.get(change["feature"])):
            card["지금"] = f"{_text(axis['value'], unit)} (초기의 약 {axis['ratio_label']})"
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
    phases: dict[str, tuple[Any, Any]] = {}
    if (
        history
        and change["channel"].startswith(_PHASES)
        and change.get("observed_property") == "phase voltage"
    ):
        phases[change["channel"][:2]] = (before, after)
        for row in change.get("related", []):
            if (
                row["channel"].startswith(_PHASES)
                and row.get("observed_property") == change["observed_property"]
                and row.get("source_id") == change["source_id"]
                and row.get("measurement_point_id") == change["measurement_point_id"]
            ):
                phases[row["channel"][:2]] = (row["reference"], row["current"])
    common_shift = None
    if len(phases) == 3 and all(a is not None and b is not None for a, b in phases.values()):
        if all(b > a for a, b in phases.values()):
            common_shift = "세 상 전압의 대표값이 모두 높아짐"
        elif all(b < a for a, b in phases.values()):
            common_shift = "세 상 전압의 대표값이 모두 낮아짐"
    recent: dict[str, str] = {}
    if not history:
        from industrial_phm.runtime.operations_web_forecast import recent_feature_values

        last_at = context["vibration_last"]
        earlier_at = last_at - RECENT_MEASUREMENTS
        readings = recent_feature_values(
            SqlitePhmAnalysisStore(workspace.phm_analysis_path), context["binding_id"], last_at
        )
        for row in chart:
            series = readings.get(row["key"], {})
            earlier, latest_value = series.get(earlier_at), series.get(last_at)
            if earlier is not None and latest_value is not None:
                recent[row["label"]] = (
                    f"{when(earlier_at)} {_text(earlier, None)} → {when(last_at)} "
                    f"{_text(latest_value, row['unit'])}" + _times(earlier, latest_value, history)
                )
    now: dict[str, str] = {}
    if history:
        # '지금은 괜찮아?'는 지금을 묻는다. 지금까지 이어지는 특이사항이 어느 신호인지와
        # 살펴본 신호 수를 준다. 이 수가 없을 때 모델은 '정상 범위 안에서 운전 중'이라고 지어냈다.
        record_end = datetime.fromisoformat(record["record"]["to"])
        width = timedelta(seconds=float(record.get("bucket_seconds") or 0))
        still = sorted(
            {
                row["label"]
                for row in record["intervals"]
                if datetime.fromisoformat(row["end"]) + width >= record_end
            }
        )
        now["초기 범위를 벗어나 지금까지 이어지는 신호"] = (
            f"{len(still)}개"
            + (f"({', '.join(still[:5])})" if still else "")
            + f", 살펴본 신호 {record['judged']}개 중"
        )

    def latest(row: dict[str, Any]) -> str:
        at, value = row["trace"][-1][0], row["trace"][-1][1]
        text = f"{_reading(value, row['unit'])} ({when(at)})"
        axis = current_axes.get(row.get("key"))
        return text + (f" · 초기의 약 {axis['ratio_label']}" if axis else "")

    order = ", ".join(f"{row['label']} 약 {row['ratio_label']}" for row in current_axes.values())
    pointed: dict[str, Any] = {}
    if (at := context.get("at")) is not None:
        # 사람이 그래프에서 짚고 물은 곳: 그때 각 신호의 값과, 특이사항 구간 안인지 밖인지.
        if history:
            moment = datetime.fromisoformat(at)

            def distance(x: Any) -> float:
                return abs((datetime.fromisoformat(x) - moment).total_seconds())

            inside = datetime.fromisoformat(start) <= moment <= datetime.fromisoformat(end)
        else:
            position = int(at)

            def distance(x: Any) -> float:
                return abs(int(x) - position)

            inside = start <= position <= end
        pointed = {
            "그래프에서 짚은 곳": {
                "때": when(at),
                "특이사항 구간": "안" if inside else "밖",
                "값": {
                    row["label"]: _reading(
                        min(row["trace"], key=lambda point: distance(point[0]))[1], row["unit"]
                    )
                    for row in chart
                    if row["trace"]
                },
            }
        }
    return {
        # 출처('저장 기록')나 '판정이 없다' 같은 말은 넣지 않는다: 모델이 그 말을 답으로 옮겼다.
        "설비": asset_label(workspace, context["asset_id"]),
        # 짚고 물은 곳이 이 질문의 대상이다: 카드보다 앞에 둔다.
        **pointed,
        "특이사항": card,
        **({"함께 관찰한 변화": f"{compared}: {common_shift}"} if common_shift else {}),
        **({"같은 기간 다른 신호": related} if related else {}),
        "지금 값(마지막 측정)": {row["label"]: latest(row) for row in chart if row["trace"]},
        **({"지금 초기 대비 변화 폭 순서": order} if len(current_axes) > 1 else {}),
        **now,
        **({f"최근 {RECENT_MEASUREMENTS}회 측정 동안": recent} if recent else {}),
        "그래프(시각, 값)" if history else "그래프(측정 번호, 값)": {
            row["label"]: [[tick(x), _value(value)] for x, value in _compact_trace(row["trace"])]
            for row in chart
            if row["trace"]
        },
    }


def _times(before: float, after: float, history: bool) -> str:
    """A vibration value's multiple of an earlier one (' (약 4.4배)'); power values give none.

    진동은 몇 배로 커졌는지가 축과 특징을 견주는 말이다. 모델이 두 축을 '둘 다 약 3.5배'로
    뭉뚱그리지 않게 배수를 계산해 준다. 전압처럼 1배 근처를 오가는 값에는 붙이지 않는다.
    """
    if history or not before > 0 or not after > 0:
        return ""
    return f" (약 {after / before:.1f}배)"


def _spans(change: dict[str, Any]) -> list[tuple[str, int, int]]:
    baseline = change["baseline"]
    return [("a", baseline["from"], baseline["to"]), ("b", change["from"], change["to"])]


def _median_comparison(row: dict[str, Any]) -> str | None:
    a, b = row["periods"]["a"], row["periods"]["b"]
    if not a["quantiles"] or not b["quantiles"]:
        return None
    before = _text(a["quantiles"][2], None)
    after = _text(b["quantiles"][2], row["unit"])
    text = f"초기 {before} → 특이사항 구간 {after}"
    if (outside := row["comparison"].get("b_outside_a_band")) is not None:
        text += f", 특이사항 구간 {b['usable_count']:,}회 중 {outside:,}회가 초기 범위 밖"
    return text


def _vibration_compare(workspace: OperationsWorkspace, context: dict[str, Any]) -> dict[str, str]:
    """Read the selected vibration feature's median in the two periods."""
    from industrial_phm.application.acquisition_snapshot import (
        SqliteAcquisitionSnapshotRepository,
    )
    from industrial_phm.application.signal_exploration import acquisition_series

    change = context["vibration_change"]
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    binding = next(
        (row for row in store.list_bindings() if row.binding_id == context["binding_id"]), None
    )
    if binding is None:
        return {}
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    rows = acquisition_series(store, snapshots, binding, [change["feature"]], _spans(change))
    return {row["label"]: compared for row in rows if (compared := _median_comparison(row))}


def _history_compare(workspace: OperationsWorkspace, context: dict[str, Any]) -> dict[str, str]:
    """What '기간 비교' shows for a power change: the medians at the change's operating level."""
    from http import HTTPStatus
    from urllib.parse import urlencode

    from industrial_phm.runtime.operations_web_explore import handle_explore_read

    change = context["history_change"]
    baseline, until = change["baseline"], context["until"]
    start, end = (datetime.fromisoformat(change[name]) for name in ("start", "end"))
    end = max(end, start + timedelta(seconds=max(change.get("bucket_seconds") or 0, 1)))
    if until is not None:
        end = min(end, datetime.fromisoformat(until))
    query = {
        "asset_id": context["asset_id"],
        "kind": "history",
        "series": change["channel"],
        "a_from": baseline["from"],
        "a_to": baseline["to"],
        "b_from": start.isoformat(),
        "b_to": end.isoformat(),
        **({"record_until": until} if until is not None else {}),
    }
    if change.get("band") is not None:
        query |= {
            "level": str(change["band"]),
            "level_source": change["source_id"],
            "level_point": change["measurement_point_id"] or "",
        }
    status, body = handle_explore_read(workspace, "/api/v1/explore/profile", urlencode(query))
    if status != HTTPStatus.OK:
        return {}
    out: dict[str, str] = {}
    for row in body["series"]:
        if (row["source_id"], row["measurement_point_id"], row["interpretation_id"]) != (
            change["source_id"],
            change["measurement_point_id"],
            change["interpretation_id"],
        ):
            continue
        if compared := _median_comparison(row):
            out[row["label"]] = compared
    return out


def _vibration_spectrum(workspace: OperationsWorkspace, context: dict[str, Any]) -> dict[str, str]:
    """What '주파수' shows: each axis's whole energy and the band whose share moved most."""
    from industrial_phm.application.acquisition_snapshot import (
        SqliteAcquisitionSnapshotRepository,
    )
    from industrial_phm.application.signal_exploration import acquisition_spectrum

    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    binding = next(
        (row for row in store.list_bindings() if row.binding_id == context["binding_id"]), None
    )
    if binding is None:
        return {}
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    try:
        spectrum = acquisition_spectrum(snapshots, binding, _spans(context["vibration_change"]))
    except ValueError, LookupError, OSError:
        return {}
    out: dict[str, str] = {}
    for channel in spectrum["channels"]:
        bands = channel["band_shares"]
        if not bands:
            continue
        band = max(bands, key=lambda item: abs(item["b"] - item["a"]))
        # 크기는 RMS의 '초기의 약 N배' 하나로 말한다. 전체 에너지 배율(RMS의 제곱)을 더하면
        # 같은 변화에 배수가 둘이 되어, 주파수 화면처럼 어디서 커졌는지만 넘긴다.
        out[channel["label"]] = (
            f"{band['from_hz']:,.0f}~{band['to_hz']:,.0f} Hz 비중 "
            f"{band['a'] * 100:.3g}% → {band['b'] * 100:.3g}%"
        )
    return out


def view_facts(
    workspace: OperationsWorkspace, context: dict[str, Any], view: str
) -> dict[str, str]:
    """Read the initial chart for period or spectrum links suggested from monitoring."""
    history = "history_change" in context
    if view == "compare":
        return (
            _history_compare(workspace, context)
            if history
            else _vibration_compare(workspace, context)
        )
    if view == "spectrum" and not history:
        return _vibration_spectrum(workspace, context)
    return {}
