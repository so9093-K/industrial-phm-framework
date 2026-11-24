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
from industrial_phm.genai.local_explanation import AnalysisExplanationError, ExplanationProvider
from industrial_phm.runtime import operations_web_phm_explanation as runtime
from industrial_phm.runtime.operations_web_change_context import (
    investigation_facts,
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
    facts = investigation_facts(workspace, context)
    assert f"{chosen['from']}~{chosen['to']}" in facts["facts"]["subject"]
    assert "중앙값" in facts["facts"]["feature_0"] and "g" in facts["facts"]["feature_0"]
    assert "회 중" in facts["facts"]["persistence"]
    # 화면과 같은 '지금'과 앞·뒤 절반 값을 답의 근거로 받는다.
    assert "마지막 측정(30번째)" in facts["facts"]["now"] and "배" in facts["facts"]["now"]
    assert "앞 절반" in facts["facts"]["pace"] and "뒤 절반" in facts["facts"]["pace"]
    assert "flow" in facts["facts"] and "spectrum_0" in facts["facts"]
    assert "16개 특징" in facts["facts"]["model_input_0"]
    assert "각 측정의 특징 조합" in facts["facts"]["model_input_0"]
    assert list(facts["facts"])[:4] == ["subject", "feature_0", "now", "pace"]
    # Facts are what was measured; no caveats about what the analysis does not hold.
    assert not {"scope", "conditions", "model_limits", "sampling"} & set(facts["facts"])
    # The conversation is the answer: no checked-list rows or follow-up actions to render.
    assert set(facts) == {"facts", "targets"}
    # Each citable fact names what the screen draws for it: this change, another, or a band.
    assert facts["targets"]["subject"]["review_key"] == chosen["review_key"]
    assert facts["targets"]["spectrum_0"]["kind"] == "spectrum"
    assert not any(key.startswith("model_") for key in facts["targets"])
    together = [row["review_key"] for row in context["episode"]]
    assert chosen["review_key"] in together
    if len(together) > 1:
        assert "order" in facts["facts"] and "episode_0" in facts["facts"]
        assert facts["targets"]["episode_0"]["review_key"] in together
    question = "문제 있어?"
    notice = "수직 진동 크기가 초기의 약 4배입니다."
    model = Replies("기준보다 높은 진동이 구간 안에서 이어집니다.")
    monkeypatch.setattr(change_answer, "complete_text", model)
    monkeypatch.setattr(runtime, "_MANAGERS", {})
    query = urlencode({"asset_id": "bearing-a", "change_id": chosen["review_key"]})
    status, body = handle_phm_read(workspace, "/api/v1/phm/change-explanations", query)
    assert status == 200 and body["explanations"] == [] and not model.requests
    job = runtime.request_phm_explanation(
        workspace.root,
        {
            "asset_id": "bearing-a",
            "change_id": chosen["review_key"],
            "question": question,
            "opening": notice,
        },
    )
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
    # The answer is the sentence and the drawn facts it cites; nothing else to fill each turn.
    assert record["answer"] == {
        "summary": "기준보다 높은 진동이 구간 안에서 이어집니다.",
        "evidence": [],
    }
    # The model reads the notice the screen already showed, the facts, then the question.
    system, *turns = model.requests[0]
    sent = json.loads(system["content"].rsplit("\n\n", 1)[1])
    assert sent["shown"] == notice
    assert sent["facts"] == {
        key: value for key, value in facts["facts"].items() if not key.startswith("model_")
    }
    assert turns == [{"role": "user", "content": question}]
    # A follow-up continues the conversation: the earlier turn and the same notice go along.
    follow = runtime.request_phm_explanation(
        workspace.root,
        {
            "asset_id": "bearing-a",
            "change_id": chosen["review_key"],
            "question": "왜 그래?",
            "parent_id": record["id"],
        },
    )
    assert finished(follow["explanation_id"])["status"] == "complete"
    system, *turns = model.requests[1]
    assert json.loads(system["content"].rsplit("\n\n", 1)[1])["shown"] == notice
    assert turns == [
        {"role": "user", "content": question},
        {"role": "assistant", "content": "기준보다 높은 진동이 구간 안에서 이어집니다."},
        {"role": "user", "content": "왜 그래?"},
    ]
    assert store.list_for(context["binding_id"], context["position"]) == []
    assert (
        len(
            store.list_for(
                context["binding_id"], context["position"], change_id=chosen["review_key"]
            )
        )
        == 2
    )
    another = dict(context, change_id="f" * 64)
    manager = runtime.initialize_explanation_manager(workspace.root)
    with pytest.raises(ValueError, match="same comparison"):
        manager._history(record["id"], another)
    assert manager._history(record["id"], context)[0]["question"] == question

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

    # Without the raw files frequency is left out: no fabricated findings or actions, and no
    # 'could not read' fact for the answer to repeat.
    for path in (tmp_path / "waves").glob("*.csv"):
        path.unlink()
    missing = investigation_facts(workspace, context)
    assert not any(key.startswith("spectrum") for key in missing["facts"])


def test_a_change_answer_keeps_to_the_record_and_fails_instead_of_inventing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = {
        "question": "얼마나 커졌어?",
        "investigation": {
            "facts": {"now": "마지막 측정의 RMS는 5.78 g로, 초기 중앙값의 약 9.28배입니다."},
            "targets": {},
        },
    }
    # The screen's rounding of a recorded number is the same reading.
    rounded = Replies("지금 5.78 g, 초기의 약 9.3배입니다.")
    monkeypatch.setattr(change_answer, "complete_text", rounded)
    answer = change_answer.generate_change_answer(context, ExplanationProvider())
    assert answer["summary"] == "지금 5.78 g, 초기의 약 9.3배입니다."
    # A number in neither the record nor the conversation is asked again, then not shown.
    invented = Replies("999배 증가했습니다.")
    monkeypatch.setattr(change_answer, "complete_text", invented)
    with pytest.raises(AnalysisExplanationError):
        change_answer.generate_change_answer(context, ExplanationProvider())
    assert len(invented.requests) == 2 and "수치만" in invented.requests[-1][-1]["content"]


def test_a_change_answer_may_write_dates_and_clock_times_as_people_do(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """'10월 4일 9시' in an answer is the stored '10월 4일 09:19', not an invented number."""
    selected = {"kind": "change", "review_key": "a" * 64, "label": "R상전압"}
    share = {"kind": "operation", "label": "운전 수준 비중", "detail": "높음 41% → 0%"}
    model = Replies("10월 4일 9시 19분부터 높은 부하의 비중이 41%에서 0%로 줄었습니다.")
    monkeypatch.setattr(change_answer, "complete_text", model)
    context = {
        "question": "부하가 바뀌었나요?",
        "history": [{"question": "무엇이 달라졌어?", "answer": "전압이 높아졌습니다."}],
        "investigation": {
            "facts": {
                "subject": "R상전압의 변화 구간은 2020년 10월 4일 09:19부터 10월 5일 07:31까지",
                "feature_0": "R상전압 222 → 226 V",
                "operating_share": "운전 수준별 측정 비중: 높음 41% → 0%.",
            },
            "targets": {"subject": selected, "feature_0": selected, "operating_share": share},
        },
    }
    answer = change_answer.generate_change_answer(context, ExplanationProvider())
    assert len(model.requests) == 1
    assert model.requests[0][1:] == [
        {"role": "user", "content": "무엇이 달라졌어?"},
        {"role": "assistant", "content": "전압이 높아졌습니다."},
        {"role": "user", "content": context["question"]},
    ]
    # The answer cites the drawn things whose numbers it used, other than the change itself.
    assert answer["evidence"] == [{"fact": "operating_share", **share}]
