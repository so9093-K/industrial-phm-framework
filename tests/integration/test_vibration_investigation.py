"""A selected bearing change carries one period through interpretation and human review."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import pytest

from industrial_phm.application.phm_explanation import PhmExplanationStore
from industrial_phm.genai import change_answer
from industrial_phm.genai.local_explanation import ExplanationProvider
from industrial_phm.runtime import operations_web_phm_explanation as runtime
from industrial_phm.runtime.operations_web_change_context import (
    asset_label,
    screen_view,
    selected_change,
)
from industrial_phm.runtime.operations_web_change_review import (
    capture_change,
    handle_change_reviews_read,
    review_change,
)
from industrial_phm.runtime.operations_web_phm import handle_phm_read
from industrial_phm.runtime.operations_web_review_index import handle_review_asset_index
from industrial_phm.runtime.operations_web_vibration import acquisition_findings
from tests.support.phm import analyze, deliver, phm_workspace


class Replies:
    """Stands in for the local model's plain chat replies, in order; keeps what it was sent."""

    def __init__(self, *texts: str) -> None:
        self.texts = list(texts)
        self.requests: list[list[dict[str, str]]] = []

    def __call__(
        self, provider: object, messages: list[dict[str, str]], *, max_tokens: int = 400
    ) -> str:
        self.requests.append(list(messages))
        return self.texts.pop(0) if len(self.texts) > 1 else self.texts[0]


def test_one_vibration_change_is_explained_reviewed_and_reopened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = phm_workspace((tmp_path / "ws").resolve())
    for ordinal in range(1, 31):
        deliver(
            workspace,
            tmp_path / "waves",
            ordinal,
            0.5 if ordinal < 16 else 2.0,
            amplitude_unit="g",
            vertical_scale=1.0 if ordinal < 23 else 5.0,
        )
    analyze(workspace)
    changes = acquisition_findings(workspace, "bearing-a")["intervals"]
    chosen = changes[0]
    assert acquisition_findings(workspace, "bearing-a")["intervals"] == changes
    context = selected_change(workspace, "bearing-a", chosen["review_key"])
    screen = screen_view(workspace, context)
    # 모델은 관제 화면에 보이는 그대로를 받는다: 설비 이름, 카드, 지금 값, 그래프.
    assert screen["설비"] == "bearing-a"
    assert asset_label(workspace, "Bearing1_1") == "베어링 1-1"
    card = screen["특이사항"]
    assert list(card)[:2] == ["신호", "지금도 이어지는지"]
    assert card["신호"] == chosen["label"]
    assert card["지금도 이어지는지"] == "기록 끝까지 이어짐"
    count = chosen["to"] - chosen["from"] + 1
    assert card["언제"] == f"{chosen['from']}번째 측정부터 {count}회 측정"
    assert card["지금"].endswith("배)")
    assert screen["지금 값(마지막 측정)"][chosen["label"]].endswith("g (30번째 측정)")
    chart = screen["그래프(측정 번호, 값)"]
    assert next(iter(chart)) == chosen["label"] and chart[chosen["label"]][-1][0] == 30
    # 출처나 '판정이 없다'는 말은 모델에 주지 않는다: 그 말을 답으로 옮겼다.
    assert "기록" not in screen and "화면의 특이사항" not in screen
    question = "문제 있어?"
    model = Replies("기준보다 높은 진동이 구간 안에서 이어집니다.")
    monkeypatch.setattr(change_answer, "complete_text", model)
    # 함께 보여 줄 분석을 고르는 모델: 첫 질문은 바로 답하고, '왜 그래?'에는 주파수 화면을 연다.
    offered: list[set[str]] = []

    def choose(_provider: object, messages: list[dict[str, str]], tools: dict[str, str]) -> str:
        offered.append(set(tools))
        return "open_spectrum" if messages[-1]["content"] == "왜 그래?" else "reply"

    monkeypatch.setattr(change_answer, "select_tool", choose)
    monkeypatch.setattr(runtime, "_MANAGERS", {})
    address = {"asset_id": "bearing-a", "change_id": chosen["review_key"]}
    conversation = uuid4().hex
    request = {**address, "conversation_id": conversation}
    path = "/api/v1/phm/change-explanations"
    status, body = handle_phm_read(workspace, path, urlencode(request))
    assert status == 200 and body["explanations"] == [] and not model.requests
    assert handle_phm_read(workspace, path, urlencode(address))[0] == 400
    prepared = runtime.prepare_web_explanation(workspace, request | {"question": question})
    with pytest.raises(ValueError, match="unexpected explanation fields"):
        runtime.prepare_web_explanation(workspace, prepared)
    job = runtime.request_phm_explanation(workspace.root, prepared)
    store = PhmExplanationStore(workspace.phm_explanation_path)

    def finished(identifier: object) -> dict[str, Any]:
        for _ in range(300):
            record = store.get(str(identifier))
            if record and record["status"] != "pending":
                return record
            time.sleep(0.01)
        raise AssertionError("the answer did not finish")

    record = finished(job["explanation_id"])
    assert record["status"] == "complete"
    assert record["answer"] == {"summary": "기준보다 높은 진동이 구간 안에서 이어집니다."}
    assert "screen" not in record["context"]
    system, *turns = model.requests[0]
    assert json.loads(system["content"].rsplit("\n\n", 1)[1]) == {"screen": screen}
    assert turns == [{"role": "user", "content": question}]
    follow = runtime.request_phm_explanation(
        workspace.root,
        request | {"question": "왜 그래?", "parent_id": record["id"]},
    )
    next_record = finished(follow["explanation_id"])
    assert next_record["status"] == "complete"
    assert "history" not in next_record["context"]
    # 진동 변화에서 고를 수 있는 분석은 이미 있는 화면들이다. 고른 화면은 답에 실리고,
    # 답은 그 화면을 소개하라는 데이터를 받는다.
    assert offered[0] == {"reply", "open_compare", "open_spectrum", "open_signals"}
    assert next_record["answer"]["analysis"] == "open_spectrum"
    system, *turns = model.requests[1]
    data = json.loads(system["content"].rsplit("\n\n", 1)[1])
    # 고른 화면은 답 아래 링크로 열리고, 답은 그 화면의 수치(축마다 에너지와 비중이 바뀐 대역)를
    # 화면 데이터보다 먼저 읽는다. 그 화면을 소개하라고 시키지는 않는다.
    assert list(data) == ["주파수 화면", "screen"] and data["screen"] == screen
    assert all("Hz 비중" in line for line in data["주파수 화면"].values())
    assert turns == [
        {"role": "user", "content": question},
        {"role": "assistant", "content": "기준보다 높은 진동이 구간 안에서 이어집니다."},
        {"role": "user", "content": "왜 그래?"},
    ]
    assert store.list_for(context["binding_id"], context["position"]) == []
    assert [
        row["id"] for row in handle_phm_read(workspace, path, urlencode(request))[1]["explanations"]
    ] == [next_record["id"], record["id"]]
    another = request | {"conversation_id": uuid4().hex}
    assert handle_phm_read(workspace, path, urlencode(another))[1]["explanations"] == []
    with pytest.raises(ValueError, match="same comparison"):
        runtime.request_phm_explanation(
            workspace.root, another | {"question": "왜 그래?", "parent_id": record["id"]}
        )
    # 그래프에서 짚고 물으면 그 측정의 값과 특이사항 구간 안인지가 화면 데이터 맨 앞에 온다.
    pointed = another | {"question": "여기는 어때?", "at": str(chosen["from"])}
    fresh = runtime.request_phm_explanation(workspace.root, pointed)
    done = finished(fresh["explanation_id"])
    assert done["status"] == "complete"
    assert done["context"]["pointed"] == f"{chosen['from']}번째 측정"
    sent = json.loads(model.requests[2][0]["content"].rsplit("\n\n", 1)[1])["screen"]
    assert next(iter(sent)) == "설비" and list(sent)[1] == "그래프에서 짚은 곳"
    assert sent["그래프에서 짚은 곳"]["특이사항 구간"] == "안"
    assert model.requests[2][1:] == [{"role": "user", "content": "여기는 어때?"}]
    with pytest.raises(ValueError, match="pointed"):
        runtime.prepare_web_explanation(workspace, another | {"question": "?", "at": "어제"})
    # 화면에서 고른 다른 기간과 방향을 읽고, 모니터링 대표 변화는 다시 계산하지 않는다.
    views = (
        (
            "spectrum",
            "주파수",
            {
                "수평 진동 전체 에너지(모든 주파수 합)": "B가 A의 27.3배",
                "800~1,594 Hz가 차지하는 비중": "A 18% → B 63%",
            },
        ),
        (
            "compare",
            "기간 비교",
            {"기간 A": "7~12번째 측정", "기간 B": "14~20번째 측정", "중앙값": "1.1 → 2.3 g"},
        ),
    )
    for view, name, values in views:
        asked = runtime.prepare_web_explanation(
            workspace,
            another
            | {
                "question": "이 화면에서 뭐가 달라졌어?",
                "view": view,
                "view_snapshot": json.dumps(values, ensure_ascii=False),
            },
        )
        assert asked["screen"] == {"설비": "bearing-a", f"지금 보고 있는 {name} 화면": values}
        assert f"open_{view}" not in asked["_change"]["analyses"]
    with pytest.raises(ValueError, match="analysis view"):
        runtime.prepare_web_explanation(workspace, another | {"question": "?", "view": "signals"})
    with pytest.raises(ValueError, match="analysis view results"):
        runtime.prepare_web_explanation(
            workspace, another | {"question": "?", "view": "signals", "view_snapshot": "[]"}
        )

    selection = {"asset_id": "bearing-a", "finding_id": chosen["review_key"]}
    capture = capture_change(workspace.root, selection)
    write = {
        "asset_id": "bearing-a",
        "capture_id": capture["capture_id"],
        "action": "acknowledge",
        "note": record["answer"]["summary"],
        "decision": "observe",
        "event_id": str(uuid4()),
    }
    review_change(workspace.root, write)
    review_change(
        workspace.root,
        {
            **write,
            "action": "note",
            "note": "주파수 비교 확인",
            "decision": None,
            "event_id": str(uuid4()),
        },
    )
    status, restored = handle_change_reviews_read(workspace, urlencode(selection))
    saved = restored["captures"][0]
    assert status == 200 and saved["snapshot"]["change"]["kind"] == "vibration"
    assert saved["snapshot"]["change"]["finding"] == chosen
    assert saved["review"]["status"] == "acknowledged"
    assert len(saved["review"]["events"]) == 2
    assert handle_review_asset_index(workspace, "")[1]["asset_ids"] == ["bearing-a"]


def test_change_chat_uses_one_completion_with_the_actual_question_and_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = Replies("**기록상 변화는 있었습니다.** 그때 전류도 낮아졌습니다.")
    monkeypatch.setattr(change_answer, "complete_text", model)
    context = {
        "question": "왜 그래?",
        "history": [
            {"question": "뭐가 달라졌어?", "answer": "전압이 올랐어요."},
            {"question": "문제 있어?", "answer": "기록에 변화는 있었어요."},
        ],
        "screen": {"선택한 변화": {"초기 중앙값": 222, "변화 구간 중앙값": 226}},
    }
    assert change_answer.generate_change_answer(context, ExplanationProvider()) == {
        "summary": "**기록상 변화는 있었습니다.** 그때 전류도 낮아졌습니다."
    }
    assert len(model.requests) == 1
    assert model.requests[0][1:] == [
        {"role": "user", "content": "뭐가 달라졌어?"},
        {"role": "assistant", "content": "전압이 올랐어요."},
        {"role": "user", "content": "문제 있어?"},
        {"role": "assistant", "content": "기록에 변화는 있었어요."},
        {"role": "user", "content": "왜 그래?"},
    ]
