"""Korean wording of a condition outlook, shared by the Web and the AI briefing.

Every number is written here as the screen shows it. The screen's summary sentences come from
here, and an AI briefing is checked against exactly these facts, so the AI cannot state a number
the screen does not, and its fallback reads the same as the screen.
"""

# ruff: noqa: RUF001

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

KST = timezone(timedelta(hours=9))
READING = {
    "current": "현재 설정",
    "recent": "최근 구간만 학습",
    "responsive": "추세 변화에 민감",
    "linear": "최근 변화 속도 유지",
}
FACT_LABEL = {
    "signal": "측정값",
    "change": "기준 대비 변화",
    "baseline": "기준 구간",
    "rate": "변화 속도",
    "spread": "변동폭",
    "departure": "기준 범위 이탈",
    "model": "이상 탐지 모델",
    "management": "관리 기준",
    "end": "종료 기준",
    "readings": "예측 조건",
    "differences": "조건별 차이",
    "forecast": "Prophet 설정",
    "search": "계산 범위",
}


def num(value: float, digits: int = 3) -> str:
    """A number as the Web's ko-KR formatting shows it: grouped, at most ``digits`` decimals."""
    text = f"{value:,.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def one(value: float) -> str:
    return num(value, 1)


def signed(value: float) -> str:
    return ("+" if value > 0 else "") + num(value)


def span(seconds: float) -> str:
    if seconds >= 86_400:
        return one(seconds / 86_400) + "일"
    if seconds >= 3_600:
        return one(seconds / 3_600) + "시간"
    if seconds >= 60:
        return one(seconds / 60) + "분"
    return one(seconds) + "초"


def _clock(value: str, *, zone: bool = True) -> str:
    text = datetime.fromisoformat(value).astimezone(KST).strftime("%Y-%m-%d %H:%M")
    return text + " KST" if zone else text


def place(outlook: dict[str, Any], value: Any) -> str:
    return "#" + str(value) if outlook["axis"] == "acquisition" else _clock(value)


def window(outlook: dict[str, Any], part: dict[str, Any]) -> str:
    if outlook["axis"] == "acquisition":
        return f"#{part['from']}–#{part['to']}"
    return _clock(part["from"]) + " ~ " + _clock(part["to"], zone=False)


def after(outlook: dict[str, Any], offset: float) -> str:
    return num(offset) + "개 획득" if outlook["offset_unit"] == "acquisition" else span(offset)


def reached_at(outlook: dict[str, Any], offset: float) -> str:
    if outlook["offset_unit"] == "acquisition":
        return "#" + str(outlook["record"]["last"] + int(offset))
    last = datetime.fromisoformat(outlook["record"]["last"])
    return _clock((last + timedelta(seconds=offset)).isoformat())


def rate_text(outlook: dict[str, Any], rate: float) -> str:
    return {"acquisition": "획득당 ", "hour": "시간당 ", "day": "하루 "}[
        outlook["rate_unit"]
    ] + signed(rate)


def condition_name(outlook: dict[str, Any], name: str) -> str:
    conditions = outlook["conditions"]
    kind = "하한 " if conditions["direction"] == "lower" else "상한 "
    return ("종료 기준 " if name == "end" else "관리 " + kind) + num(conditions[name])


def search_text(outlook: dict[str, Any]) -> str:
    if outlook["offset_unit"] == "acquisition":
        return num(outlook["search"]["acquisitions"]) + "개 획득"
    return span(outlook["search"]["seconds"])


def change_text(outlook: dict[str, Any]) -> str:
    indicator = outlook["degradation"]
    ratio = indicator["change_ratio"]
    if ratio is not None:
        return signed(round(ratio * 1000) / 10) + "%"
    return signed(indicator["change"])


def margin_text(outlook: dict[str, Any], reached: dict[str, Any]) -> str:
    """One reading's margin to one condition, in a few words."""
    if reached["state"] == "already":
        return "이미 도달"
    if reached["state"] == "expected":
        parts = [reached_at(outlook, reached["expected"])]
        if reached["earliest"] is not None and reached["earliest"] != reached["expected"]:
            parts.append("빠르면 " + after(outlook, reached["earliest"]))
        if reached["latest"] is not None and reached["latest"] != reached["expected"]:
            parts.append("늦으면 " + after(outlook, reached["latest"]))
        return after(outlook, reached["expected"]) + " 뒤 도달 예상 (" + ", ".join(parts) + ")"
    if reached["state"] == "possible":
        return "예측 범위에서만 " + after(outlook, reached["earliest"]) + " 뒤 도달"
    return (
        search_text(outlook)
        + " 뒤("
        + place(outlook, outlook["search"]["until"])
        + ")까지 도달하지 않음"
    )


def condition_reach(outlook: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """What may be said to reach: each condition (by its number) and each reading (by its name)."""
    conditions = {}
    for name in ("management", "end"):
        if outlook["conditions"][name] is None or not outlook["scenarios"]:
            continue
        states = [scenario["limits"][name]["state"] for scenario in outlook["scenarios"]]
        conditions[name] = {
            "value": num(outlook["conditions"][name]),
            "already": states[0] == "already",
            "reached": any(state in {"expected", "already"} for state in states),
            "expected_offsets": {
                READING[scenario["id"]]: (
                    None
                    if scenario["limits"][name]["expected"] is None
                    else after(outlook, scenario["limits"][name]["expected"])
                )
                for scenario in outlook["scenarios"]
            },
        }
    readings = {
        READING[scenario["id"]]: any(
            reached["state"] in {"expected", "already"} for reached in scenario["limits"].values()
        )
        for scenario in outlook["scenarios"]
    }
    return {"conditions": conditions, "readings": readings}


def outlook_sentences(outlook: dict[str, Any]) -> list[str]:
    """The move of the record, then how far each condition is under the four readings."""
    indicator, departure = outlook["degradation"], outlook["degradation"]["departure"]
    motion = "최근 " + rate_text(outlook, indicator["rate"]) + "씩 변하고 있습니다."
    if departure and departure["since"] is not None:
        lead = (
            place(outlook, departure["since"])
            + " 이후 값의 "
            + one(departure["since_share"] * 100)
            + "%가 초기 비교 범위 밖이며, "
        )
    elif departure and departure["outside"]:
        lead = f"초기 비교 범위를 벗어난 값이 {num(departure['outside'])}개이고, "
    else:
        lead = "초기 비교 범위 밖인 값은 없고, "
    sentences = [lead + motion]
    for name in ("management", "end"):
        if outlook["conditions"][name] is None or not outlook["scenarios"]:
            continue
        label = condition_name(outlook, name)
        every = [scenario["limits"][name] for scenario in outlook["scenarios"]]
        if every[0]["state"] == "already":
            sentences.append("마지막 측정이 이미 " + label + "에 도달했습니다.")
            continue
        reached = [item["expected"] for item in every if item["state"] == "expected"]
        if not reached:
            sentences.append(label + "에는 " + search_text(outlook) + " 안에 닿지 않습니다.")
            continue
        low, high = min(reached), max(reached)
        if low == high:
            spread = after(outlook, low)
        elif outlook["offset_unit"] == "acquisition":
            spread = f"{num(low)}–{num(high)}개 획득"
        else:
            spread = span(low) + "–" + span(high)
        now = every[0]["expected"] if every[0]["state"] == "expected" else None
        partly = (
            f" ({len(every)}가지 중 {len(reached)}가지에서 도달)"
            if len(reached) < len(every)
            else ""
        )
        sentences.append(
            (label + "까지의 잔여수명은 " if name == "end" else label + "까지 ")
            + ("현재 설정으로 " + after(outlook, now) + ", " if now is not None else "")
            + "읽는 방법에 따라 "
            + spread
            + partly
            + ("입니다." if name == "end" else " 남았습니다.")
        )
    return sentences


def difference_sentences(outlook: dict[str, Any]) -> list[str]:
    """Why the four readings give different margins, in sentences."""
    indicator, scenarios = outlook["degradation"], outlook["scenarios"]
    sentences = []
    for name in ("management", "end"):
        if outlook["conditions"][name] is None or not scenarios:
            continue
        reached = [
            (s["limits"][name]["expected"], READING[s["id"]])
            for s in scenarios
            if s["limits"][name]["state"] == "expected"
        ]
        label = condition_name(outlook, name)
        if len(reached) >= 2 and min(reached)[0] != max(reached)[0]:
            fastest, slowest = min(reached), max(reached)
            sentences.append(
                f"{label}까지 가장 빠른 읽기는 {fastest[1]}({after(outlook, fastest[0])})이고, "
                f"가장 느린 읽기는 {slowest[1]}({after(outlook, slowest[0])})입니다."
            )
    current = next((s for s in scenarios if s["id"] == "current"), None)
    if current is not None:
        sentences.append(
            f"Prophet 읽기는 모델이 읽은 흐름의 예측 시작값 {num(current['start'])}에서, "
            f"최근 변화 속도 유지는 마지막 측정 {num(indicator['latest'])}에서 시작합니다."
        )
    recent = next((s for s in scenarios if s["id"] == "recent"), None)
    if recent is not None:
        sentences.append(
            f"최근 구간만 학습은 최근 {num(recent['training_points'])}개만 읽고, "
            "추세 변화에 민감은 늦게 바뀐 추세를 더 따릅니다."
        )
    return sentences


def outlook_facts(outlook: dict[str, Any]) -> dict[str, str]:
    """Every fact a briefing may use, keyed by what it is about, worded as the screen words it."""
    indicator = outlook["degradation"]
    facts = {
        "signal": outlook["label"]
        + (f" ({outlook['unit']})" if outlook.get("unit") else "")
        + " · "
        + (
            f"#{outlook['record']['first']}–#{outlook['record']['last']}"
            if outlook["axis"] == "acquisition"
            else window(
                outlook, {"from": outlook["record"]["first"], "to": outlook["record"]["last"]}
            )
        )
        + f" · 값 {num(outlook['record']['points'])}개",
        "change": f"기준 구간 중앙값 {num(indicator['baseline']['median'])} → 최근 구간 중앙값 "
        f"{num(indicator['recent']['median'])} ({change_text(outlook)}) · 마지막 측정 "
        f"{num(indicator['latest'])}",
        "baseline": f"기준 구간 {window(outlook, indicator['baseline'])} (기록의 처음 30%)"
        f" · 최근 구간 {window(outlook, indicator['recent'])}",
        "rate": "최근 "
        + rate_text(outlook, indicator["rate"])
        + (
            " · 그 전 " + rate_text(outlook, indicator["earlier_rate"])
            if indicator["earlier_rate"] is not None
            else ""
        ),
    }
    if indicator["spread_ratio"] is not None:
        facts["spread"] = f"최근 구간 변동폭이 기준 구간의 {one(indicator['spread_ratio'])}배"
    departure = indicator["departure"]
    if departure is not None:
        facts["departure"] = (
            (
                place(outlook, departure["since"]) + "부터 기준 범위를 계속 벗어남"
                if departure["since"] is not None
                else f"기준 범위를 벗어난 값 {num(departure['outside'])}개 · 계속되지 않음"
                if departure["outside"]
                else "기준 범위를 벗어난 값 없음"
            )
            + f" · 기준 범위는 기준 중앙값에서 변동폭의 {num(departure['threshold'])}배 안"
            + f" · 마지막 측정은 기준 변동폭의 {one(abs(departure['latest_distance']))}배 거리"
        )
    model = outlook.get("anomaly_model")
    if model and model.get("latest"):
        latest = model["latest"]
        where = (
            "#" + str(latest["position"])
            if model["step_kind"] == "acquisition-snapshot"
            else _clock(latest["at"])
            if latest.get("at")
            else "#" + str(latest["position"])
        )
        text = f"{model_label(model['package_id'])} · {where} 점수 {num(latest['score'])}"
        if isinstance(latest.get("threshold"), (int, float)):
            text += f" · 모델 기준 {num(latest['threshold'])} " + (
                "초과" if latest.get("exceeds") else "이하"
            )
        if model.get("first_exceeding"):
            first = model["first_exceeding"]
            text += " · 처음 초과 " + (
                _clock(first["at"])
                if model["step_kind"] != "acquisition-snapshot" and first.get("at")
                else "#" + str(first["position"])
            )
        recent = model["recent"]
        text += f" · 최근 {recent['results']}개 중 {recent['exceeding']}개 초과"
        facts["model"] = text
    scenarios = outlook["scenarios"]
    for name in ("management", "end"):
        if outlook["conditions"][name] is None or not scenarios:
            continue
        cells = [
            READING[scenario["id"]] + " " + margin_text(outlook, scenario["limits"][name])
            for scenario in scenarios
        ]
        reached = sum(scenario["limits"][name]["state"] == "expected" for scenario in scenarios)
        facts[name] = (
            ("잔여수명 · " if name == "end" else "")
            + condition_name(outlook, name)
            + "까지: "
            + "; ".join(cells)
            + f" ({len(scenarios)}가지 중 {reached}가지에서 도달 예상)"
            + (
                " · 마지막 측정은 아직 도달하지 않음"
                if scenarios[0]["limits"][name]["state"] != "already"
                else ""
            )
        )
    if scenarios:
        notes = {
            "current": lambda s: (
                f"민감도 {num(s['changepoint_prior_scale'])} · {num(s['training_points'])}개 학습"
            ),
            "recent": lambda s: f"최근 {num(s['training_points'])}개 학습",
            "responsive": lambda s: f"추세 민감도 {num(s['changepoint_prior_scale'])}",
            "linear": lambda s: "마지막 측정에서 " + rate_text(outlook, indicator["rate"]),
        }
        facts["readings"] = f"읽는 방법 {len(scenarios)}가지: " + " · ".join(
            f"{READING[s['id']]}({notes[s['id']](s)})" for s in scenarios
        )
        differences = _differences(outlook)
        if differences:
            facts["differences"] = differences
        current = scenarios[0]
        facts["forecast"] = (
            f"Prophet · 추세 민감도 {num(current['changepoint_prior_scale'])} · 변화점 범위 "
            f"{num(outlook['settings']['changepoint_range'])}"
            f" · {num(current['training_points'])}개 학습"
            f" · 예측 시작값 {num(current['start'])} · 마지막 측정 {num(indicator['latest'])}"
        )
        facts["search"] = (
            place(outlook, outlook["search"]["until"])
            + f"까지 계산 ({search_text(outlook)}, 학습 기록 길이의 절반)"
        )
    return facts


def _differences(outlook: dict[str, Any]) -> str:
    """Why the readings disagree: where each starts and how much of the record it reads."""
    indicator, scenarios = outlook["degradation"], outlook["scenarios"]
    parts = []
    for name in ("management", "end"):
        if outlook["conditions"][name] is None:
            continue
        reached = [
            (s["limits"][name]["expected"], READING[s["id"]])
            for s in scenarios
            if s["limits"][name]["state"] == "expected"
        ]
        if len(reached) >= 2:
            fastest, slowest = min(reached), max(reached)
            if fastest[0] != slowest[0]:
                parts.append(
                    f"{condition_name(outlook, name)}: 가장 빠른 읽기 {fastest[1]} "
                    f"{after(outlook, fastest[0])}, 가장 느린 읽기 {slowest[1]} "
                    f"{after(outlook, slowest[0])}"
                )
    current = next((s for s in scenarios if s["id"] == "current"), None)
    if current is not None:
        parts.append(
            f"Prophet 읽기는 모델이 읽은 흐름의 예측 시작값 {num(current['start'])}에서, "
            f"최근 변화 속도 유지는 마지막 측정 {num(indicator['latest'])}에서 시작"
        )
    recent = next((s for s in scenarios if s["id"] == "recent"), None)
    if recent is not None:
        parts.append(f"최근 구간만 학습은 최근 {num(recent['training_points'])}개만 읽음")
    responsive = next((s for s in scenarios if s["id"] == "responsive"), None)
    if responsive is not None:
        parts.append(
            f"추세 변화에 민감은 추세 민감도 {num(responsive['changepoint_prior_scale'])}로 "
            "늦게 바뀐 추세를 더 따름"
        )
    return " · ".join(parts)


def model_label(package_id: str) -> str:
    """The algorithm name the screen shows for an anomaly model."""
    lowered = package_id.lower()
    for marker, name in (
        ("lstm", "LSTM"),
        ("autoencoder", "LSTM"),
        ("pca", "PCA"),
        ("iforest", "Isolation Forest"),
    ):
        if marker in lowered:
            return name
    return "이상 탐지 모델"
