"""Korean wording of a condition outlook, shared by the Web and the AI briefing.

Every number is written here as the screen shows it. The screen's summary sentences come from
here, and an AI briefing is checked against exactly these facts, so the AI cannot state a number
the screen does not, and its fallback reads the same as the screen.
"""

# ruff: noqa: RUF001

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

KST = timezone(timedelta(hours=9))
READING = {
    "current": "현재 설정",
    "recent": "최근 구간만 학습",
    "responsive": "추세 변화에 민감",
    "linear": "최근 변화 속도 유지",
}
# Two places on the record are "the same moment" within this many acquisitions, or this share
# of the record's length for a timestamped record.
SAME_MOMENT_ACQUISITIONS = 3
SAME_MOMENT_SHARE = 0.02
FACT_LABEL = {
    "signal": "측정값",
    "time_basis": "시간 환산 조건",
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
    "links": "분석 간 연결",
    "check": "과거 자료로 예측 확인",
    "next": "다음에 확인할 것",
}


def num(value: float, digits: int = 3) -> str:
    """A number as the Web's ko-KR formatting shows it: grouped, at most ``digits`` decimals."""
    text = f"{value:,.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def one(value: float) -> str:
    return num(value, 1)


def share(part: int, whole: int) -> str:
    """A count's share as the Web's ``countShare`` writes it: never 0% or 100% unless exact.

    One of 250 hidden values inside the band rounded to "0%", which read as none at all.
    """
    if whole <= 0 or part <= 0:
        return "0%"
    if part >= whole:
        return "100%"
    percent = 100 * part / whole
    if percent < 0.1:
        return "0.1% 미만"
    if percent > 99.9:
        return "99.9% 초과"
    # Halves round up, as JavaScript's Math.round does on the screen.
    if 1 <= percent <= 99:
        return f"{math.floor(percent + 0.5)}%"
    return f"{math.floor(percent * 10 + 0.5) / 10:.1f}%"


def inside_share(check: dict[str, Any]) -> str:
    """How many hidden values fell inside the band, from the check's ratio and count."""
    return share(round(check["inside_interval"] * check["points"]), check["points"])


def signed(value: float) -> str:
    return ("+" if value > 0 else "") + num(value)


def span(seconds: float) -> str:
    # Positive duration ties round the same way as Intl.NumberFormat in the Web.
    def rounded(value: float) -> str:
        return num(math.floor(value * 10 + 0.5) / 10, 1)

    if seconds >= 86_400:
        return rounded(seconds / 86_400) + "일"
    if seconds >= 3_600:
        return rounded(seconds / 3_600) + "시간"
    if seconds >= 60:
        return rounded(seconds / 60) + "분"
    return rounded(seconds) + "초"


def measurement_period(outlook: dict[str, Any]) -> float | None:
    """A declared measurement cadence; an ordinal's internal one-second step is not time."""
    period = outlook.get("period_seconds")
    if (
        outlook.get("time_basis") in {"recorded", "assumed"}
        and isinstance(period, (int, float))
        and math.isfinite(period)
        and period > 0
    ):
        return float(period)
    return None


def interval_note(outlook: dict[str, Any]) -> str:
    if outlook["axis"] != "acquisition":
        return ""
    period = measurement_period(outlook)
    if period is None:
        return "측정 간격 정보 없음 · 시간 환산 불가"
    return (
        "기록된 " + span(period) + " 측정 간격이 유지될 경우"
        if outlook["time_basis"] == "recorded"
        else "가정한 " + span(period) + " 측정 간격이 유지될 경우"
    )


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
    if outlook["offset_unit"] != "acquisition":
        return span(offset)
    period = measurement_period(outlook)
    return span(offset * period) if period is not None else "추가 측정 " + num(offset) + "회"


def reached_at(outlook: dict[str, Any], offset: float) -> str:
    if outlook["offset_unit"] == "acquisition":
        return "#" + str(outlook["record"]["last"] + int(offset))
    last = datetime.fromisoformat(outlook["record"]["last"])
    return _clock((last + timedelta(seconds=offset)).isoformat())


def rate_text(outlook: dict[str, Any], rate: float) -> str:
    return {"acquisition": "측정 1회당 ", "hour": "시간당 ", "day": "하루 "}[
        outlook["rate_unit"]
    ] + signed(rate)


def condition_name(outlook: dict[str, Any], name: str) -> str:
    conditions = outlook["conditions"]
    kind = "하한 " if conditions["direction"] == "lower" else "상한 "
    return ("종료 기준 " if name == "end" else "관리 " + kind) + num(conditions[name])


def search_text(outlook: dict[str, Any]) -> str:
    if outlook["offset_unit"] == "acquisition":
        return after(outlook, outlook["search"]["acquisitions"])
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
            "possible": any(state == "possible" for state in states),
            "direction": outlook["conditions"]["direction"],
            "possible_offsets": {
                READING[scenario["id"]]: (
                    after(outlook, scenario["limits"][name]["earliest"])
                    if scenario["limits"][name]["state"] == "possible"
                    else None
                )
                for scenario in outlook["scenarios"]
            },
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
        READING[scenario["id"]]: {
            "reached": any(
                reached["state"] in {"expected", "already"}
                for reached in scenario["limits"].values()
            ),
            "possible": any(
                reached["state"] == "possible" for reached in scenario["limits"].values()
            ),
        }
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
            possible = [item for item in every if item["state"] == "possible"]
            if possible:
                edge = "하단" if outlook["conditions"]["direction"] == "lower" else "상단"
                sentences.append(
                    label
                    + ": 중심 예측은 "
                    + search_text(outlook)
                    + " 내 미도달 · 일부 예측 범위 "
                    + edge
                    + "에서만 도달 가능."
                )
            else:
                sentences.append(label + "에는 " + search_text(outlook) + " 안에 닿지 않습니다.")
            continue
        low, high = min(reached), max(reached)
        if low == high:
            spread = after(outlook, low)
        elif outlook["offset_unit"] == "acquisition" and measurement_period(outlook) is None:
            spread = f"추가 측정 {num(low)}–{num(high)}회"
        else:
            spread = after(outlook, low) + "–" + after(outlook, high)
        now = every[0]["expected"] if every[0]["state"] == "expected" else None
        possible_count = sum(item["state"] == "possible" for item in every)
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
        if possible_count:
            sentences[-1] += f" 그 밖의 {possible_count}가지는 예측 범위에서만 도달 가능합니다."
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


def _departure_range(indicator: dict[str, Any], departure: dict[str, Any]) -> str:
    """The early comparison range as values, not as a multiple of a spread nobody sees."""
    baseline, threshold = indicator["baseline"], departure["threshold"]
    low = baseline["median"] - threshold * baseline["spread"]
    high = baseline["median"] + threshold * baseline["spread"]
    return (
        f" · 초기 비교 범위 {num(low)}~{num(high)}"
        f" (기준 구간 중앙값에서 변동폭의 {num(threshold)}배 안)"
        f" · 마지막 측정 {num(indicator['latest'])}"
        + (" (범위 밖)" if abs(departure["latest_distance"]) >= threshold else " (범위 안)")
    )


def _model_text(model: dict[str, Any]) -> str:
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
    acquisitions = model["step_kind"] == "acquisition-snapshot"
    run = next((item for item in reversed(model.get("intervals") or []) if item.get("open")), None)
    first = model.get("first_exceeding")

    def where_first(item: dict[str, Any]) -> str:
        return (
            _clock(item["at"])
            if not acquisitions and item.get("at")
            else "#" + str(item["position"])
        )

    # Crossings are told by place and count only. The model's run rule tolerates results below the
    # threshold inside a run, so no word for a kind of run ("continuous") is put in a fact.
    total = model.get("exceeding")
    if first:
        text += (f" · 기준 초과 {total}회" if isinstance(total, int) else " · 기준 초과") + (
            f" (처음 {where_first(first)})"
        )
    elif total == 0:
        text += " · 기준 초과 없음"
    if run is not None:
        start = (
            _clock(run["start_at"])
            if not acquisitions and run.get("start_at")
            else "#" + str(run["start_position"])
        )
        text += f" · {start} 이후 기준 초과 {run['steps']}회"
    recent = model["recent"]
    return text + f" · 최근 {recent['results']}개 중 {recent['exceeding']}개 초과"


def _models(outlook: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        model
        for model in outlook.get("anomaly_models") or [outlook.get("anomaly_model")]
        if model and model.get("latest")
    ]


def _model_start(outlook: dict[str, Any], model: dict[str, Any]) -> Any:
    """Where the model's open run starts, else its first crossing."""
    return (_model_crossings(outlook, model) or (None, None))[0]


def _model_crossings(
    outlook: dict[str, Any], model: dict[str, Any]
) -> tuple[Any, int | None] | None:
    """Where to count a model's crossings from, and how many there are from there: its open run's
    start and the crossings in that run, else its first crossing and all of them."""
    acquisitions = outlook["axis"] == "acquisition"
    run = next((item for item in reversed(model.get("intervals") or []) if item.get("open")), None)
    if run is not None:
        start = run["start_position"] if acquisitions else run.get("start_at")
        return start, run.get("steps")
    first = model.get("first_exceeding")
    if first is None:
        return None
    total = model.get("exceeding")
    return (first["position"] if acquisitions else first.get("at")), (
        total if isinstance(total, int) else None
    )


def _gap(outlook: dict[str, Any], one: Any, two: Any) -> tuple[str, bool]:
    """How far apart two places on the record are, and whether that is the same moment."""
    if outlook["axis"] == "acquisition":
        steps = abs(int(one) - int(two))
        return (f"{steps}회 차이" if steps else "같은 측정"), steps <= SAME_MOMENT_ACQUISITIONS
    first, last = (datetime.fromisoformat(outlook["record"][k]) for k in ("first", "last"))
    seconds = abs((datetime.fromisoformat(one) - datetime.fromisoformat(two)).total_seconds())
    record = max(1.0, (last - first).total_seconds())
    return span(seconds) + " 차이", seconds <= SAME_MOMENT_SHARE * record


def _links(outlook: dict[str, Any]) -> str | None:
    """Whether the measured values and every anomaly model point at the same moment."""
    departure = outlook["degradation"].get("departure") or {}
    since, models = departure.get("since"), _models(outlook)
    if since is None or not models:
        return None
    parts = [f"측정값이 초기 비교 범위를 벗어나기 시작 {place(outlook, since)}"]
    agreeing, quiet = 0, 0
    for model in models:
        name, crossings = model_label(model["package_id"]), _model_crossings(outlook, model)
        start, count = crossings or (None, None)
        if start is None:
            quiet += 1
            parts.append(f"{name} 기준 초과 없음")
            continue
        gap, same = _gap(outlook, start, since)
        agreeing += same
        parts.append(
            f"{name} {place(outlook, start)} 이후 기준 초과"
            + (f" {count}회" if count is not None else "")
            + f" ({gap}"
            + (", 같은 무렵)" if same else ")")
        )
    text = "; ".join(parts)
    if agreeing and quiet:
        text += (
            " · 같은 무렵을 가리키는 이상 탐지 모델과 기준을 넘지 않은 이상 탐지 모델이 함께 있음"
            " (이상 탐지 모델끼리 다르게 말함)"
        )
    elif agreeing == len(models):
        text += " · 측정값과 모든 이상 탐지 모델이 같은 무렵을 가리킴"
    return text


def check_is_weak(check: dict[str, Any]) -> bool:
    """Whether the hidden stretch mostly fell outside the band or a flat line did as well."""
    return bool(
        check["inside_interval"] < 0.5
        or check["mean_absolute_error"] >= 0.8 * check["naive_mean_absolute_error"]
    )


def _check(outlook: dict[str, Any]) -> str | None:
    check = outlook.get("check")
    if not check:
        return None
    error, naive = check["mean_absolute_error"], check["naive_mean_absolute_error"]
    weak = check_is_weak(check)
    return (
        f"기록의 마지막 {check['points']}개를 가리고 같은 방법으로 예측: 실제 값이 예측 범위 "
        f"안에 든 비율 {inside_share(check)} · 평균 오차 {num(error)} (마지막 값을 그대로 "
        f"이어 쓰면 {num(naive)})"
        + (
            " · 기준까지의 여유는 정확한 시각이 아니라 대략의 범위로 읽어야 함"
            if weak
            else " · 예측이 실제 값을 대체로 따라감"
        )
    )


def _next(outlook: dict[str, Any]) -> str:
    """The checks a person can make next on this screen and the ones it links to."""
    items = []
    if outlook["conditions"]["management"] is not None or outlook["conditions"]["end"] is not None:
        items.append("다음 측정에서 값이 기준에 다가가는지 확인")
    since = (outlook["degradation"].get("departure") or {}).get("since")
    if since is not None:
        items.append(
            f"{place(outlook, since)} 전후 원본 파형과 주파수 비교"
            if outlook["axis"] == "acquisition"
            else f"{place(outlook, since)} 전후 원본 신호 확인"
        )
    models = _models(outlook)
    over = [model for model in models if _model_start(outlook, model) is not None]
    if over and len(over) < len(models):
        items.append("기준을 넘지 않은 이상 탐지 모델의 점수가 같은 무렵 어떻게 움직였는지 확인")
    items.append("판단과 근거를 검토 기록에 남기기")
    return " · ".join(items)


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
            place(outlook, departure["since"])
            + " 이후 값의 "
            + one(departure["since_share"] * 100)
            + "%가 초기 비교 범위 밖"
            if departure["since"] is not None
            else f"초기 비교 범위 밖인 값 {num(departure['outside'])}개"
            if departure["outside"]
            else "초기 비교 범위 밖인 값 없음"
        ) + _departure_range(indicator, departure)
    # Every anomaly model on this input, so a model that stays quiet never speaks for all.
    models = _models(outlook)
    if models:
        text = "; ".join(_model_text(model) for model in models)
        if len(models) > 1:
            over = sum(model["latest"].get("exceeds") is True for model in models)
            text += f" · 이상 탐지 모델 {len(models)}개 중 {over}개가 마지막 측정에서 기준 초과" + (
                " (이상 탐지 모델끼리 다르게 말함)" if 0 < over < len(models) else ""
            )
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
        possible = sum(scenario["limits"][name]["state"] == "possible" for scenario in scenarios)
        facts[name] = (
            ("잔여수명 · " if name == "end" else "")
            + condition_name(outlook, name)
            + "까지: "
            + "; ".join(cells)
            + f" ({len(scenarios)}가지 중 {reached}가지에서 도달 예상)"
            + (f" · {possible}가지에서 예측 범위만 도달 가능" if possible else "")
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
    if note := interval_note(outlook):
        facts["time_basis"] = note
    if links := _links(outlook):
        facts["links"] = links
    if check := _check(outlook):
        facts["check"] = check
    facts["next"] = _next(outlook)
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
