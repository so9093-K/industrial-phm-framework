"""An AI briefing of a condition outlook states only computed facts, as the screen words them."""

# ruff: noqa: RUF001

from __future__ import annotations

from typing import Any

import pytest

from industrial_phm.application.outlook_text import outlook_facts, outlook_sentences
from industrial_phm.genai import outlook_answer
from industrial_phm.genai.analysis_explanation import AnalysisExplanationError
from industrial_phm.genai.local_explanation import ExplanationProvider
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


def test_the_screen_summary_joins_the_move_of_the_record_with_the_margin() -> None:
    outlook = _outlook()
    assert outlook["sentences"] == [
        "#76 이후 값의 86%가 초기 비교 범위 밖이며, 최근 획득당 +0.021씩 변하고 있습니다.",
        "관리 상한 8까지 현재 설정으로 56개 획득, 읽는 방법에 따라 36–56개 획득 "
        "(4가지 중 3가지에서 도달) 남았습니다.",
        "종료 기준 15에는 61개 획득 안에 닿지 않습니다.",
    ]
    facts = outlook["facts"]
    assert facts["change"].endswith("(+389.7%) · 마지막 측정 7.268")
    assert facts["management"].startswith(
        "관리 상한 8까지: 현재 설정 56개 획득 뒤 도달 예상 (#179, 빠르면 47개 획득)"
    )
    assert facts["management"].endswith("마지막 측정은 아직 도달하지 않음")
    assert facts["end"].startswith("잔여수명 · 종료 기준 15까지:")
    assert facts["model"].startswith("Isolation Forest · #123 점수 0.771 · 모델 기준 0.754 초과")


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("관리 상한 8까지 50개 획득 남았습니다.", "'50'"),
        ("관리 상한 15까지 현재 설정으로 56개 획득 뒤 도달합니다.", "기준값"),
        ("관리 상한 8까지 현재 설정으로 42개 획득 뒤 도달합니다.", "도달 시간"),
        ("관리 상한 8까지 61개 획득 뒤 도달합니다.", "도달 시간"),
        ("베어링 마모가 진행되고 있습니다.", "원인"),
        ("곧 베어링을 교체해야 합니다.", "지시"),
        ("이 설비는 정상 상태입니다.", "판정"),
        ("잔여수명은 56개 획득입니다.", "종료 기준"),
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
        "#76부터 기준 범위를 계속 벗어나 최근 획득당 +0.021씩 오르고 있어, 관리 상한 8까지 현재 "
        "설정으로 56개 획득(#179) 남았습니다. 종료 기준 15까지의 잔여수명은 61개 획득 안에 "
        "도달하지 않습니다. 이는 고장 판정이 아닙니다."
    )
    assert outlook_answer.text_issues(text, facts) == []


def test_a_good_answer_is_shown_with_the_facts_its_points_cite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outlook = _outlook()
    model = ScriptedModel(
        {
            "summary": "#76부터 기준 범위를 계속 벗어나 있고 관리 상한 8까지 "
            "36–56개 획득 남았습니다.",
            "points": [
                {"text": "최근 획득당 +0.021씩 오르고 있습니다.", "evidence": ["rate"]},
                {
                    "text": "추세 변화에 민감하게 읽으면 42개 획득입니다.",
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
    bad = {"summary": "잔여수명은 50개 획득입니다.", "points": []}
    fixed = {"summary": "관리 상한 8까지 현재 설정으로 56개 획득 남았습니다.", "points": []}
    model = ScriptedModel(bad, fixed)
    monkeypatch.setattr(outlook_answer, "complete_json", model)
    answer = outlook_answer.generate_outlook_briefing(outlook, "여유?", PROVIDER)
    assert answer["summary"] == fixed["summary"] and answer["checks"]["rewritten"]
    assert answer["checks"]["source"] == "model"
    assert "다시 답하세요" in model.requests[1][-1]["content"]

    mixed = {
        "summary": "관리 상한 8까지 현재 설정으로 56개 획득 남았습니다. 베어링 손상이 의심됩니다.",
        "points": [{"text": "50개 획득 뒤 도달합니다.", "evidence": ["management"]}],
    }
    monkeypatch.setattr(outlook_answer, "complete_json", ScriptedModel(mixed))
    answer = outlook_answer.generate_outlook_briefing(outlook, "여유?", PROVIDER)
    assert answer["checks"]["source"] == "model-trimmed"
    assert answer["summary"] == "관리 상한 8까지 현재 설정으로 56개 획득 남았습니다."
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
        ("종료 기준 15까지 4가지 모두 61개 획득 안 도달 예상입니다.", True),
        ("관리 상한 8까지 도달하지 않았으나, 종료 기준 15까지 도달할 것으로 계산됩니다.", True),
        ("마지막 측정이 이미 관리 상한 8을 넘었습니다.", True),
        (
            "종료 기준 15까지 도달 예상 시점은 현재 설정, 최근 구간만 학습 모두 도달하지 않음.",
            False,
        ),
        ("관리 상한 8까지 현재 설정으로 56개 획득 뒤 도달할 것으로 계산됩니다.", False),
        (
            "최근 구간만 학습 기준으로는 61개 획득 뒤에 도달할 것으로 예상되지만, 마지막 측정값은 "
            "아직 어떤 기준에도 도달하지 않았습니다.",
            True,
        ),
        ("추세 변화에 민감 기준으로는 42개 획득 뒤 도달할 것으로 계산됩니다.", False),
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
        "관리 상한 8까지 가장 빠른 읽기는 최근 변화 속도 유지(36개 획득)이고, 가장 느린 읽기는 "
        "현재 설정(56개 획득)입니다."
    )
    assert answer["points"][0]["evidence"] == ["differences"]
