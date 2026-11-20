"""A selected bearing change carries one period through interpretation and human review."""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

import pytest

from industrial_phm.application.phm_explanation import PhmExplanationStore
from industrial_phm.genai import change_answer
from industrial_phm.genai.local_explanation import ExplanationProvider
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
from tests.support.phm import ScriptedModel, analyze, deliver, phm_workspace


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
    assert "flow" in facts["facts"] and "spectrum_0" in facts["facts"]
    assert "16개 특징" in facts["facts"]["model_input_0"]
    assert "각 측정의 특징 조합" in facts["facts"]["model_input_0"]
    assert "원인을 확정하지는 못합니다" in facts["facts"]["model_limits"]
    assert set(facts["actions"]) == {"compare", "model", "spectrum", "onset"}
    question = "변화 구간의 시작과 지속 범위를 설명해 주세요."
    model = ScriptedModel(
        {
            "summary": "기준보다 높은 진동이 구간 안에서 이어집니다.",
            "next_step": "주파수 비교에서 어떤 대역의 에너지 비중이 커졌는지 확인하세요.",
            "actions": ["spectrum", "compare"],
        }
    )
    monkeypatch.setattr(change_answer, "complete_json", model)
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
        },
    )
    store = PhmExplanationStore(workspace.phm_explanation_path)
    for _ in range(300):
        record = store.get(str(job["explanation_id"]))
        if record and record["status"] != "pending":
            break
        time.sleep(0.01)
    assert record and record["status"] == "complete"
    assert record["answer"]["source"] == "model"
    assert "에너지 비중" in record["answer"]["next_step"]
    sent = json.loads(model.requests[0][1]["content"])
    assert sent["question"] == question
    assert sent["facts"] == {
        key: value for key, value in facts["facts"].items() if not key.startswith("model_")
    }
    assert "model" not in sent["available_actions"]
    assert "primary" not in sent  # No compulsory model-score-first answer.
    assert store.list_for(context["binding_id"], context["position"]) == []
    assert (
        len(
            store.list_for(
                context["binding_id"], context["position"], change_id=chosen["review_key"]
            )
        )
        == 1
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

    # A missing raw file is an analysis limit, not fabricated frequency findings/actions.
    for path in (tmp_path / "waves").glob("*.csv"):
        path.unlink()
    missing = investigation_facts(workspace, context)
    assert set(missing["actions"]) == {"compare", "model"}
    assert "spectrum_0" not in missing["facts"]
    assert "원본 파형" in missing["facts"]["spectrum"]


@pytest.mark.parametrize("invented_field", ["summary", "next_step"])
def test_change_answer_retries_invented_numbers_and_uses_computed_fallback(
    monkeypatch: pytest.MonkeyPatch, invented_field: str
) -> None:
    reply = {
        "summary": "높은 진동이 이어졌습니다.",
        "next_step": "두 기간의 주파수 분포를 비교하세요.",
        "actions": ["spectrum"],
    }
    reply[invented_field] = "999배 증가했습니다."
    bad = ScriptedModel(reply)
    monkeypatch.setattr(change_answer, "complete_json", bad)
    context = {
        "question": "일시적일까?",
        "investigation": {
            "facts": {
                "subject": "변화 16~30회",
                "feature_0": "RMS 1 → 4 g",
                "persistence": "15회 중 15회가 기준 범위 밖",
            },
            "actions": ["compare", "spectrum"],
        },
    }
    answer = change_answer.generate_change_answer(context, ExplanationProvider())
    assert len(bad.requests) == 2 and answer["source"] == "computed"
    assert "999" not in answer["summary"] and "15회 중" in answer["summary"]
