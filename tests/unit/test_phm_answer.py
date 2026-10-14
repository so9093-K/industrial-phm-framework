from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.phm_explanation import explanation_context
from industrial_phm.genai import phm_answer
from industrial_phm.genai.local_explanation import ExplanationProvider
from industrial_phm.genai.phm_answer import (
    answer_input,
    check_answer,
    generate_grounded_answer,
    soften,
    text_issues,
)
from tests.support.phm import analyze, deliver, phm_workspace

RMS = "feature.Horizontal_vibration_signals.rms"
PEAK = "feature.Horizontal_vibration_signals.peak_to_peak"
VERTICAL = "feature.Vertical_vibration_signals.rms"


@pytest.fixture(scope="module")
def contexts(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Any]]:
    root = tmp_path_factory.mktemp("answer")
    workspace = phm_workspace(root / "ws")
    for ordinal, scale in enumerate((0.5, 0.6, 3.0, 3.2), start=1):
        deliver(workspace, root / "waves", ordinal, scale)
    analyze(workspace)
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    return {
        binding: explanation_context(
            store, workspace.models_path, snapshots, binding, 4, compare_position=1
        )
        for binding in ("anomaly-a", "rul-a")
    }


def test_model_reads_directions_and_names_not_values(contexts: dict[str, Any]) -> None:
    payload = answer_input(contexts["anomaly-a"])
    assert payload["primary"] == {
        "name": "이상 점수",
        "model": "이상 점수",
        "change": "증가",
        "input_acquisitions": 1,
        "reference": "참고 기준 초과",
    }
    rows = {item["id"]: item for item in payload["candidates"]}
    assert rows[RMS] == {"id": RMS, "label": "수평 진동 RMS", "change": "증가", "size": "뚜렷함"}
    assert rows[VERTICAL]["change"] == "거의 같음"
    assert rows["feature.Horizontal_vibration_signals.skewness"]["size"] is None
    rul = answer_input(contexts["rul-a"])
    assert rul["primary"]["name"] == "잔여 구간 추정" and rul["primary"]["change"] == "감소"
    assert rul["related_models"] == [
        {"name": "이상 점수", "change": "증가", "input_acquisitions": 1}
    ]


def test_references_keep_their_stored_direction_and_unknown_ones_are_dropped(
    contexts: dict[str, Any],
) -> None:
    payload = answer_input(contexts["anomaly-a"])
    answer, issues = check_answer(
        {
            "summary": "이상 점수가 증가했고 수평 진동의 진폭이 함께 증가했습니다.",
            "observations": [
                {"feature": RMS, "change": "감소"},
                {"feature": "feature.invented.rms", "change": "증가"},
                {"feature": RMS, "change": "증가"},
            ],
            "next_signals": [PEAK, "feature.invented.rms", PEAK],
            "next_step": "두 시점의 원본 파형을 비교해 보세요.",
        },
        payload,
    )
    assert answer["observations"] == [{"feature": RMS, "relation": "increased"}]
    assert answer["next_signals"] == [PEAK]
    assert issues == [
        "수평 진동 RMS: 두 시점 사이에 증가입니다. candidates의 change를 그대로 쓰세요."
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("이상 점수가 증가했고 수평 진동 RMS가 함께 증가했습니다.", []),
        ("이상 점수가 증가했습니다. 수평 진동 RMS가 42.9% 늘었습니다.", ["숫자"]),
        ("이상 점수가 증가했습니다. 3상 평균 전류 변동은 비교 대상이 아닙니다.", []),
        ("이상 점수가 증가한 것은 수평 진동이 커졌기 때문입니다.", ["때문"]),
        ("이상 점수가 증가했고 진폭 변화가 점수 상승을 유발했습니다.", ["유발"]),
        ("이상 점수가 증가했지만 원인을 확정할 수 없기 때문에 함께 달라진 신호만 봅니다.", []),
        ("이상 점수가 증가하는 추세입니다.", ["추세"]),
        ("이상 점수가 증가했고 수평 진동이 가장 크게 변했습니다.", ["가장 크"]),
        ("이상 점수가 감소했습니다.", ["저장된 방향"]),
        ("수평 진동 RMS가 증가했습니다.", ["먼저 말하세요"]),
        ("이상 점수가 증가했지만 참고 기준 이하입니다.", ["기준 비교는"]),
        ("이상 점수가 증가해 참고 기준보다 높아졌습니다.", ["기준 비교는"]),
        ("이상 점수가 증가해 참고 기준 초과입니다.", []),
        ("이상 점수가 증가했고 설비는 정상 상태입니다.", ["판정"]),
        ("이상 점수가 증가했고 수평 진동 RMS가 점수에 크게 반영됐습니다.", ["반영 정도"]),
        ("이상 점수가 **증가**했습니다.", ["마크다운"]),
    ],
)
def test_sentences_that_overstate_two_results_are_named(
    contexts: dict[str, Any], text: str, expected: list[str]
) -> None:
    issues = text_issues(text, answer_input(contexts["anomaly-a"]), field="summary")
    assert len(issues) == len(expected), issues
    for issue, fragment in zip(issues, expected, strict=True):
        assert fragment in issue


def test_contribution_claims_name_only_the_model_top_features(contexts: dict[str, Any]) -> None:
    payload = {
        **answer_input(contexts["anomaly-a"]),
        "contribution_order": ["수평 진동 RMS", "수평 진동 피크-피크", "수평 진동 표준편차"],
    }
    text = (
        "이상 점수가 증가했고 수평 진동 절대 피크도 커졌으며, "
        "모델 점수에는 수평 진동 RMS가 크게 반영됐습니다."
    )
    assert text_issues(text, payload, field="summary") == []
    wrong = "이상 점수가 증가했고 수평 진동 절대 피크가 점수에 크게 반영됐습니다."
    assert "수평 진동 RMS" in text_issues(wrong, payload, field="summary")[0]


def test_rul_answer_is_checked_against_rul_not_against_other_models(
    contexts: dict[str, Any],
) -> None:
    payload = answer_input(contexts["rul-a"])
    text = "잔여 구간 추정이 줄었고, 같은 입력의 이상 점수는 높아졌습니다."
    assert text_issues(text, payload, field="summary") == []
    assert "저장된 방향" in text_issues("잔여 구간 추정이 늘었습니다.", payload, field="summary")[0]


def test_common_two_point_phrasing_is_rewritten_not_rejected() -> None:
    assert soften("RMS가 증가하는 경향을 보였습니다.") == "RMS가 증가했습니다."
    assert soften("전압이 감소하는 추세를 보이며 전류는") == "전압이 감소하며 전류는"


def _fake_model(monkeypatch: pytest.MonkeyPatch, drafts: list[dict[str, Any]], review=None):
    calls: list[list[dict[str, str]]] = []

    def complete(provider, messages, schema, *, max_tokens=1200):
        calls.append(messages)
        if "causal" in schema["properties"]:
            return review or {
                "causal": False,
                "trend": False,
                "contradiction": False,
                "verdict": False,
                "answers_question": True,
                "quote": "",
            }
        return drafts.pop(0)

    monkeypatch.setattr(phm_answer, "complete_json", complete)
    return calls


def _draft(summary: str, next_step: str = "두 시점의 원본 파형을 비교해 보세요.") -> dict[str, Any]:
    return {
        "summary": summary,
        "observations": [{"feature": RMS, "change": "증가"}],
        "next_signals": [PEAK],
        "next_step": next_step,
    }


def test_answer_that_passes_is_kept_after_one_review(
    contexts: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _fake_model(
        monkeypatch, [_draft("이상 점수가 증가했고 수평 진동 RMS가 함께 커졌습니다.")]
    )
    answer = generate_grounded_answer(contexts["anomaly-a"], ExplanationProvider())
    assert answer["summary"] == "이상 점수가 증가했고 수평 진동 RMS가 함께 커졌습니다."
    assert answer["checks"]["summary_source"] == "model" and not answer["checks"]["rewritten"]
    assert len(calls) == 2
    sent = json.loads(calls[0][1]["content"])
    assert sent["question"] == contexts["anomaly-a"]["question"]
    assert "0.5" not in json.dumps(sent["candidates"])


def test_failed_draft_is_rewritten_once_with_the_reasons(
    contexts: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _fake_model(
        monkeypatch,
        [
            _draft("이상 점수가 오른 것은 수평 진동 RMS가 커졌기 때문입니다."),
            _draft("이상 점수가 증가했고 수평 진동 RMS가 함께 커졌습니다."),
        ],
    )
    answer = generate_grounded_answer(contexts["anomaly-a"], ExplanationProvider())
    assert answer["checks"]["rewritten"] and answer["checks"]["summary_source"] == "model"
    assert "'때문'" in calls[1][-1]["content"]
    assert answer["checks"]["first_summary"].endswith("때문입니다.")


def test_reviewer_only_triggers_a_rewrite_and_never_replaces_the_answer(
    contexts: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    review = {
        "causal": True,
        "trend": False,
        "contradiction": False,
        "verdict": False,
        "answers_question": True,
        "quote": "커졌습니다",
    }
    text = "이상 점수가 증가했고 수평 진동 RMS가 함께 커졌습니다."
    calls = _fake_model(monkeypatch, [_draft(text), _draft(text)], review)
    answer = generate_grounded_answer(contexts["anomaly-a"], ExplanationProvider())
    assert answer["summary"] == text and answer["checks"]["summary_source"] == "model"
    assert len(calls) == 3


def test_sentences_that_still_fail_are_dropped_and_stored_facts_fill_the_gap(
    contexts: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    stubborn = _draft(
        "이상 점수가 오른 것은 진폭이 커졌기 때문입니다. 수평 진동 RMS가 함께 증가했습니다.",
        "추세를 3개 더 보세요.",
    )
    _fake_model(monkeypatch, [stubborn, dict(stubborn)])
    answer = generate_grounded_answer(contexts["anomaly-a"], ExplanationProvider())
    assert answer["checks"]["summary_source"] == "model-trimmed"
    assert answer["summary"] == (
        "두 시점 사이에 이상 점수가 높아졌습니다. 수평 진동 RMS가 함께 증가했습니다."
    )
    assert answer["next_step"].startswith("두 시점의 원본 신호에서")


def test_when_nothing_can_be_verified_the_comparison_answers(
    contexts: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong = _draft("이상 점수가 감소했기 때문에 설비는 정상 상태입니다.")
    _fake_model(monkeypatch, [wrong, dict(wrong)])
    answer = generate_grounded_answer(contexts["anomaly-a"], ExplanationProvider())
    assert answer["checks"]["summary_source"] == "verified-comparison"
    assert answer["summary"].startswith(
        "두 시점 사이에 이상 점수가 높아졌습니다. 같은 두 시점에서 "
    )
    assert "수평 진동 RMS 증가" in answer["summary"]
    assert answer["observations"] == [{"feature": RMS, "relation": "increased"}]


def test_store_keeps_the_structured_answer(tmp_path: Path) -> None:
    from industrial_phm.application.phm_explanation import PhmExplanationStore

    store = PhmExplanationStore(tmp_path / "explanations.sqlite")
    context = {"binding_id": "b", "position": 3, "analysis_run_id": "r", "package_id": "p"}
    identifier = store.request(context, model="local-main", owner="me")
    answer = {"summary": "s", "observations": [], "next_signals": [], "next_step": "n"}
    store.finish(identifier, owner="me", text="s n", answer=answer)
    assert store.get(identifier)["answer"] == answer
