"""An AI briefing of a condition outlook states only computed facts, as the screen words them."""

# ruff: noqa: RUF001

from __future__ import annotations

from typing import Any

import pytest

from industrial_phm.application.outlook_text import outlook_facts, outlook_sentences
from industrial_phm.genai import outlook_answer
from industrial_phm.genai.local_explanation import AnalysisExplanationError, ExplanationProvider
from tests.support.phm import ScriptedModel


def _outlook() -> dict[str, Any]:
    """The shape the outlook API returns, for 123 acquisitions of a rising vibration RMS."""
    reach = lambda state, expected=None, earliest=None: {  # noqa: E731
        "state": state,
        "expected": expected,
        "earliest": earliest,
        "latest": None,
    }
    outlook: dict[str, Any] = {
        "axis": "acquisition",
        "time_basis": "recorded",
        "period_seconds": 60.0,
        "offset_unit": "acquisition",
        "rate_unit": "acquisition",
        "label": "수평 진동 RMS",
        "unit": None,
        "record": {"first": 1, "last": 123, "points": 123},
        "degradation": {
            "baseline": {"from": 1, "to": 37, "median": 0.716, "spread": 0.081},
            "recent": {"from": 100, "to": 123, "median": 3.507},
            "latest": 7.268,
            "change": 2.791,
            "change_ratio": 3.897,
            "rate": 0.0206,
            "earlier_rate": 0.0669,
            "spread_ratio": 1.83,
            "departure": {
                "threshold": 3.5,
                "outside": 48,
                "since": 76,
                "since_share": 0.86,
                "latest_distance": 81.2,
            },
        },
        "conditions": {"direction": "upper", "management": 8.0, "end": 15.0},
        "settings": {"changepoint_range": 0.9},
        "search": {"seconds": 3660.0, "acquisitions": 61, "until": 184},
        "scenarios": [
            {
                "id": "current",
                "changepoint_prior_scale": 0.05,
                "training_points": 123,
                "start": 4.516,
                "limits": {"management": reach("expected", 56, 47), "end": reach("beyond")},
            },
            {
                "id": "recent",
                "changepoint_prior_scale": 0.05,
                "training_points": 37,
                "start": 4.27,
                "limits": {"management": reach("beyond"), "end": reach("beyond")},
            },
            {
                "id": "responsive",
                "changepoint_prior_scale": 0.3,
                "training_points": 123,
                "start": 4.55,
                "limits": {"management": reach("expected", 42, 31), "end": reach("beyond")},
            },
            {
                "id": "linear",
                "limits": {"management": reach("expected", 36), "end": reach("beyond")},
            },
        ],
        "anomaly_model": {
            "package_id": "xjtu-sy-iforest-fold-1",
            "step_kind": "acquisition-snapshot",
            "latest": {"position": 123, "score": 0.771, "threshold": 0.754, "exceeds": True},
            "first_exceeding": {"position": 119, "at": None},
            "recent": {"results": 10, "exceeding": 2},
        },
    }
    outlook["sentences"] = outlook_sentences(outlook)
    outlook["facts"] = outlook_facts(outlook)
    return outlook


PROVIDER = ExplanationProvider()


@pytest.mark.parametrize(
    "text",
    [
        "현재 설비의 상태는 기준 구간 중앙값 대비 크게 증가했습니다.",
        "지금 설비는 기준 구간에서 크게 벗어났습니다.",
        "현재 장비의 측정값은 크게 증가했습니다.",
    ],
)
def test_recorded_outlook_cannot_claim_the_equipment_state_now(text: str) -> None:
    assert any("마지막 기록 시점" in issue for issue in outlook_answer.text_issues(text, {}))


@pytest.mark.parametrize(
    "text",
    [
        "마지막 기록 시점의 측정값은 기준 구간 중앙값 대비 크게 증가했습니다.",
        "현재 설정에서 도달하지 않습니다.",
        "현재 설비의 상태를 뜻하지 않습니다.",
    ],
)
def test_record_anchor_and_current_configuration_remain_valid(text: str) -> None:
    assert not outlook_answer.text_issues(text, {})


@pytest.mark.parametrize("direction,edge", [("upper", "상단"), ("lower", "하단")])
def test_possible_and_beyond_do_not_become_definite_no_reach(direction: str, edge: str) -> None:
    outlook = _outlook()
    outlook["conditions"]["direction"] = direction
    for scenario in outlook["scenarios"]:
        scenario["limits"]["management"] = {
            "state": "possible" if scenario["id"] in {"current", "responsive"} else "beyond",
            "expected": None,
            "earliest": 4 if scenario["id"] in {"current", "responsive"} else None,
            "latest": None,
        }
    sentences = outlook_sentences(outlook)
    assert f"일부 예측 범위 {edge}에서만 도달 가능" in sentences[1]
    assert "닿지 않습니다" not in sentences[1]
    facts = outlook_facts(outlook)
    assert "0가지에서 도달 예상" in facts["management"]
    assert "2가지에서 예측 범위만 도달 가능" in facts["management"]
    assert "예측 범위에서만 4분 뒤 도달" in facts["management"]


@pytest.mark.parametrize(
    ("utterance", "accepted"),
    [
        ("관리 상한 8에는 예측 범위 상단에서만 4분 뒤 도달할 수 있습니다.", True),
        ("관리 상한 8에는 예측 범위 상단에서만 4분 뒤 도달 가능합니다.", True),
        ("관리 상한 8에는 예측 범위 하단에서만 4분 뒤 도달 가능합니다.", False),
        ("관리 상한 8에는 4분 뒤 도달합니다.", False),
        ("관리 상한 8에는 예측 범위 하단에서만 4분 뒤 도달할 수 있습니다.", False),
        ("관리 상한 8에는 예측 범위 상단에서만 5분 뒤 도달할 수 있습니다.", False),
        ("관리 상한 8에는 기간 내 중심 예측으로 도달할 것으로 예상됩니다.", False),
    ],
)
def test_possible_reach_is_accepted_only_as_qualified_range_claim(
    utterance: str, accepted: bool
) -> None:
    outlook = _outlook()
    for scenario in outlook["scenarios"]:
        scenario["limits"]["management"] = {
            "state": "possible" if scenario["id"] == "current" else "beyond",
            "expected": None,
            "earliest": 4 if scenario["id"] == "current" else None,
            "latest": None,
        }
    facts = outlook_facts(outlook)
    issues = outlook_answer.text_issues(utterance, facts, outlook_answer.condition_reach(outlook))
    assert (not issues) is accepted, issues


def test_expected_and_possible_are_counted_separately() -> None:
    outlook = _outlook()
    outlook["scenarios"][1]["limits"]["management"] = {
        "state": "possible",
        "expected": None,
        "earliest": 39,
        "latest": None,
    }
    facts = outlook_facts(outlook)
    assert "3가지에서 도달 예상" in facts["management"]
    assert "1가지에서 예측 범위만 도달 가능" in facts["management"]
    assert "4가지 중 3가지에서 도달" in outlook_sentences(outlook)[1]
    assert "그 밖의 1가지는 예측 범위에서만 도달 가능합니다" in outlook_sentences(outlook)[1]


def test_the_screen_summary_joins_the_move_of_the_record_with_the_margin() -> None:
    outlook = _outlook()
    assert outlook["sentences"] == [
        "#76 이후 값의 86%가 초기 비교 범위 밖이며, 최근 측정 1회당 +0.021씩 변하고 있습니다.",
        "관리 상한 8까지 현재 설정으로 56분, 읽는 방법에 따라 36분–56분 "
        "(4가지 중 3가지에서 도달) 남았습니다.",
        "종료 기준 15에는 1시간 안에 닿지 않습니다.",
    ]
    facts = outlook["facts"]
    assert facts["change"].endswith("(+389.7%) · 마지막 측정 7.268")
    assert facts["management"].startswith(
        "관리 상한 8까지: 현재 설정 56분 뒤 도달 예상 (#179, 빠르면 47분)"
    )
    assert facts["management"].endswith("마지막 측정은 아직 도달하지 않음")
    assert facts["end"].startswith("잔여수명 · 종료 기준 15까지:")
    assert facts["model"].startswith("Isolation Forest · #123 점수 0.771 · 모델 기준 0.754 초과")
    # The early range reads as values; a multiple of a spread nobody sees is not a fact.
    assert "초기 비교 범위 0.432~1" in facts["departure"]
    assert facts["departure"].endswith("· 마지막 측정 7.268 (범위 밖)")
    assert "배 거리" not in facts["departure"]


def test_the_analyses_are_joined_by_where_they_start_and_the_past_check_says_how_to_read() -> None:
    outlook = _outlook()
    sustained = {
        **outlook["anomaly_model"],
        "package_id": "xjtu-lstm-autoencoder-fold-1",
        "intervals": [{"start_position": 77, "end_position": 123, "open": True}],
    }
    quiet = {**outlook["anomaly_model"], "first_exceeding": None, "intervals": []}
    outlook["anomaly_models"] = [sustained, quiet]
    outlook["check"] = {
        "points": 25,
        "mean_absolute_error": 1.53,
        "naive_mean_absolute_error": 1.62,
        "inside_interval": 0.0,
    }
    facts = outlook_facts(outlook)
    assert facts["links"] == (
        "측정값이 초기 비교 범위를 벗어나기 시작 #76; "
        "LSTM 기준 초과 시작 #77 (1회 차이, 같은 무렵); Isolation Forest 기준 초과 없음 · "
        "같은 무렵을 가리키는 이상 탐지 모델과 기준을 넘지 않은 이상 탐지 모델이 함께 있음 "
        "(이상 탐지 모델끼리 다르게 말함)"
    )
    assert facts["check"].startswith(
        "기록의 마지막 25개를 가리고 같은 방법으로 예측: 실제 값이 예측"
    )
    assert facts["check"].endswith("대략의 범위로 읽어야 함")
    assert facts["next"] == (
        "다음 측정에서 값이 기준에 다가가는지 확인 · #76 전후 원본 파형과 주파수 비교 · "
        "기준을 넘지 않은 이상 탐지 모델의 점수가 같은 무렵 어떻게 움직였는지 확인 · "
        "판단과 근거를 검토 기록에 남기기"
    )
    # An answer that relays these facts in their own words passes the checks.
    text = (
        "마지막 기록 #123 기준으로 측정값은 #76부터 초기 비교 범위를 벗어났고 LSTM도 #77부터 "
        "기준을 넘었지만 Isolation Forest는 기준을 넘지 않아 이상 탐지 모델끼리 다르게 말합니다."
    )
    assert outlook_answer.text_issues(text, facts) == []
    alone = _outlook()
    alone["anomaly_model"]["intervals"] = []
    assert "다르게 말함" not in outlook_facts(alone)["links"]


def test_models_that_disagree_are_all_in_the_facts() -> None:
    outlook = _outlook()
    quiet = {
        **outlook["anomaly_model"],
        "package_id": "xjtu-lstm-autoencoder-fold-1",
        "latest": {"position": 123, "score": 0.9, "threshold": 1.77, "exceeds": False},
        "first_exceeding": None,
        "recent": {"results": 10, "exceeding": 0},
    }
    outlook["anomaly_models"] = [outlook["anomaly_model"], quiet]
    text = outlook_facts(outlook)["model"]
    assert text.startswith("Isolation Forest · #123 점수 0.771 · 모델 기준 0.754 초과")
    assert "; LSTM" in text and "모델 기준 1.77 이하" in text
    assert text.endswith(
        "이상 탐지 모델 2개 중 1개가 마지막 측정에서 기준 초과 (이상 탐지 모델끼리 다르게 말함)"
    )


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("관리 상한 8까지 50분 남았습니다.", "'50'"),
        ("관리 상한 15까지 현재 설정으로 56분 뒤 도달합니다.", "기준값"),
        ("관리 상한 8까지 현재 설정으로 42분 뒤 도달합니다.", "도달 시간"),
        ("관리 상한 8까지 61분 뒤 도달합니다.", "도달 시간"),
        ("베어링 마모가 진행되고 있습니다.", "원인"),
        ("곧 베어링을 교체해야 합니다.", "지시"),
        ("이 설비는 정상 상태입니다.", "판정"),
        ("잔여수명은 56분입니다.", "종료 기준"),
        ("고장이 임박했습니다.", "고장"),
        ("**요약**: 증가했습니다.", "마크다운"),
    ],
)
def test_a_text_that_states_more_than_the_facts_is_named(text: str, reason: str) -> None:
    from industrial_phm.application.outlook_text import condition_reach

    outlook = _outlook()
    structured = condition_reach(outlook) if reason in {"기준값", "도달 시간"} else None
    issues = outlook_answer.text_issues(text, outlook["facts"], structured)
    assert any(reason in issue for issue in issues), issues


def test_a_text_that_copies_the_facts_passes() -> None:
    facts = _outlook()["facts"]
    text = (
        "#76부터 기준 범위를 계속 벗어나 최근 측정 1회당 +0.021씩 오르고 있어, "
        "관리 상한 8까지 현재 "
        "설정으로 56분(#179) 남았습니다. 종료 기준 15까지의 잔여수명은 1시간 안에 "
        "도달하지 않습니다. 이는 고장 판정이 아닙니다."
    )
    assert outlook_answer.text_issues(text, facts) == []


def test_a_good_answer_is_shown_with_the_facts_its_points_cite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outlook = _outlook()
    model = ScriptedModel(
        {
            "summary": "#76부터 기준 범위를 계속 벗어나 있고 관리 상한 8까지 36–56분 남았습니다.",
            "points": [
                {"text": "최근 측정 1회당 +0.021씩 오르고 있습니다.", "evidence": ["rate"]},
                {
                    "text": "추세 변화에 민감하게 읽으면 42분입니다.",
                    "evidence": ["management", "nope"],
                },
            ],
        }
    )
    monkeypatch.setattr(outlook_answer, "complete_json", model)
    answer = outlook_answer.generate_outlook_briefing(outlook, "여유가 얼마나 있어?", PROVIDER)
    assert answer["checks"]["source"] == "model" and not answer["checks"]["rewritten"]
    assert answer["points"][1]["evidence"] == ["management"]
    assert set(answer["evidence"]) == {"rate", "management"}
    assert answer["evidence"]["rate"]["label"] == "변화 속도"
    sent = model.requests[0]
    assert '"question": "여유가 얼마나 있어?"' in sent[1]["content"]
    assert "facts" in sent[1]["content"]


def test_a_failing_draft_is_rewritten_once_and_then_trimmed_to_what_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outlook = _outlook()
    bad = {"summary": "잔여수명은 50분입니다.", "points": []}
    fixed = {"summary": "관리 상한 8까지 현재 설정으로 56분 남았습니다.", "points": []}
    model = ScriptedModel(bad, fixed)
    monkeypatch.setattr(outlook_answer, "complete_json", model)
    answer = outlook_answer.generate_outlook_briefing(outlook, "여유?", PROVIDER)
    assert answer["summary"] == fixed["summary"] and answer["checks"]["rewritten"]
    assert answer["checks"]["source"] == "model"
    assert "다시 답하세요" in model.requests[1][-1]["content"]

    mixed = {
        "summary": "관리 상한 8까지 현재 설정으로 56분 남았습니다. 베어링 손상이 의심됩니다.",
        "points": [{"text": "50분 뒤 도달합니다.", "evidence": ["management"]}],
    }
    monkeypatch.setattr(outlook_answer, "complete_json", ScriptedModel(mixed))
    answer = outlook_answer.generate_outlook_briefing(outlook, "여유?", PROVIDER)
    assert answer["checks"]["source"] == "model-trimmed"
    assert answer["summary"] == "관리 상한 8까지 현재 설정으로 56분 남았습니다."
    # Its only point failed; the screen's facts stand in.
    assert answer["points"][0]["evidence"] == ["change"]

    monkeypatch.setattr(
        outlook_answer, "complete_json", ScriptedModel({"summary": "고장입니다.", "points": []})
    )
    answer = outlook_answer.generate_outlook_briefing(outlook, "여유?", PROVIDER)
    assert answer["checks"]["source"] == "computed"
    assert answer["summary"] == " ".join(outlook["sentences"])


def test_without_a_model_the_screen_summary_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(*args: object, **kwargs: object) -> object:
        raise AnalysisExplanationError("configured explanation provider unavailable")

    monkeypatch.setattr(outlook_answer, "complete_json", unavailable)
    answer = outlook_answer.generate_outlook_briefing(_outlook(), "여유?", PROVIDER)
    assert answer["checks"] == {"source": "computed", "model_unavailable": True}
    assert answer["evidence"]["management"]["label"] == "관리 기준"


@pytest.mark.parametrize(
    ("text", "flagged"),
    [
        ("종료 기준 15까지 4가지 모두 61분 안 도달 예상입니다.", True),
        ("관리 상한 8까지 도달하지 않았으나, 종료 기준 15까지 도달할 것으로 계산됩니다.", True),
        ("마지막 측정이 이미 관리 상한 8을 넘었습니다.", True),
        (
            "종료 기준 15까지 도달 예상 시점은 현재 설정, 최근 구간만 학습 모두 도달하지 않음.",
            False,
        ),
        ("관리 상한 8까지 현재 설정으로 56분 뒤 도달할 것으로 계산됩니다.", False),
        (
            "최근 구간만 학습 기준으로는 61분 뒤에 도달할 것으로 예상되지만, 마지막 측정값은 "
            "아직 어떤 기준에도 도달하지 않았습니다.",
            True,
        ),
        ("추세 변화에 민감 기준으로는 42분 뒤 도달할 것으로 계산됩니다.", False),
    ],
)
def test_a_reach_the_outlook_does_not_compute_is_named(text: str, flagged: bool) -> None:
    from industrial_phm.application.outlook_text import condition_reach

    outlook = _outlook()
    issues = outlook_answer.reach_issues(text, condition_reach(outlook))
    assert bool(issues) is flagged, issues


def test_a_question_about_differences_falls_back_to_the_computed_differences() -> None:
    answer = outlook_answer.computed_briefing(_outlook(), "예측 조건에 따라 왜 달라져?")
    assert answer["summary"].startswith(
        "관리 상한 8까지 가장 빠른 읽기는 최근 변화 속도 유지(36분)이고, 가장 느린 읽기는 "
        "현재 설정(56분)입니다."
    )
    assert answer["points"][0]["evidence"] == ["differences"]


@pytest.mark.parametrize(
    "basis,period,expected",
    [
        ("recorded", 60.0, "56분"),
        ("assumed", 120.0, "1.9시간"),
        ("ordinal", 1.0, "추가 측정 56회"),
        (None, 60.0, "추가 측정 56회"),
        ("recorded", 0.0, "추가 측정 56회"),
    ],
)
def test_margin_uses_declared_cadence_without_turning_positions_into_time(
    basis: str | None, period: float, expected: str
) -> None:
    from industrial_phm.application.outlook_text import after, interval_note

    outlook = _outlook()
    outlook.update(time_basis=basis, period_seconds=period)
    assert after(outlook, 56) == expected
    if basis == "recorded" and period:
        assert "기록된 1분" in interval_note(outlook)
    if expected.startswith("추가"):
        assert "시간 환산 불가" in interval_note(outlook)
    elif basis == "assumed":
        assert "가정한 2분" in interval_note(outlook)
    # The recorded ordinal identity and API offsets are unaffected by display units.
    assert outlook["record"]["last"] == 123
    assert outlook["scenarios"][0]["limits"]["management"]["expected"] == 56


def test_ai_rejects_measurement_counts_as_elapsed_minutes_without_cadence() -> None:
    from industrial_phm.application.outlook_text import condition_reach

    outlook = _outlook()
    outlook.update(time_basis="ordinal", period_seconds=1.0)
    facts = outlook_facts(outlook)
    relations = condition_reach(outlook)
    assert not outlook_answer.text_issues(
        "관리 상한 8까지 현재 설정으로 추가 측정 56회 후 도달할 것으로 계산됩니다.",
        facts,
        relations,
    )
    assert outlook_answer.text_issues(
        "관리 상한 8까지 현재 설정으로 56분 후 도달할 것으로 계산됩니다.", facts, relations
    )


def test_a_crossing_still_going_on_is_named_apart_from_an_earlier_one_off() -> None:
    outlook = _outlook()
    outlook["anomaly_model"] = {
        **outlook["anomaly_model"],
        "package_id": "xjtu-lstm-autoencoder-fold-1",
        "first_exceeding": {"position": 30, "at": None},
        "intervals": [{"start_position": 76, "end_position": 123, "open": True}],
    }
    text = outlook_facts(outlook)["model"]
    assert "기준 초과가 이어지기 시작 #76 · 그 전에 처음 기준을 넘은 측정 #30" in text
    assert "처음 초과 #30" not in text


def test_a_margin_always_comes_with_how_far_the_past_check_lets_one_trust_it() -> None:
    outlook = _outlook()
    outlook["check"] = {
        "points": 25,
        "mean_absolute_error": 1.53,
        "naive_mean_absolute_error": 1.62,
        "inside_interval": 0.0,
    }
    cited = {
        "text": "관리 상한 8까지 56분 뒤 도달할 것으로 계산했습니다.",
        "evidence": ["management"],
    }
    answer = outlook_answer.with_check({"summary": "...", "points": [cited] * 4}, outlook)
    assert len(answer["points"]) == 4 and answer["points"][-1]["evidence"] == ["check"]
    assert answer["points"][-1]["text"].endswith("대략의 범위로 읽어야 합니다.")
    plain = {"summary": "...", "points": [{"text": "변화", "evidence": ["change"]}]}
    assert outlook_answer.with_check(plain, outlook)["points"] == plain["points"]
