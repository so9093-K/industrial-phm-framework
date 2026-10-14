from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.application.phm_explanation import PhmExplanationStore
from industrial_phm.genai.analysis_explanation import AnalysisExplanationError
from industrial_phm.genai.local_explanation import ExplanationProvider, complete_json
from industrial_phm.runtime.operations_web_phm_explanation import (
    ExplanationManager,
    request_phm_review,
)
from tests.support.phm import analyze, deliver, phm_workspace


def test_job_records_immutable_context_and_interrupted_generation_is_not_success(
    tmp_path: Path,
) -> None:
    store = PhmExplanationStore(tmp_path / "explanations.sqlite")
    context = {
        "binding_id": "b",
        "position": 3,
        "analysis_run_id": "run",
        "package_id": "p",
        "output": {"score": 0.5},
    }
    identifier = store.request(context, model="local-main", owner="old")
    context["output"]["score"] = 99
    assert store.get(identifier)["context"]["output"]["score"] == 0.5
    store.recover("new")
    assert store.get(identifier)["status"] == "failed"
    store.finish(identifier, owner="old", text="stale completion")
    assert store.get(identifier)["text"] == ""


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/v1",
        "https://example.com/v1",
        "http://user:secret@127.0.0.1/v1",
        "http://127.0.0.1:9400/v1?key=secret",
    ],
)
def test_provider_rejects_unconfigured_remote_or_credentials_in_url(url: str) -> None:
    with pytest.raises(AnalysisExplanationError):
        ExplanationProvider(base_url=url)


@pytest.mark.parametrize("chat_status", [200, 422])
def test_schema_constrained_chat_and_responses_fallback_keep_model_and_messages(
    chat_status: int,
) -> None:
    seen = []
    answer = {"summary": "stored comparison answer"}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((self.path, body))
            if chat_status != 200 and self.path.endswith("/chat/completions"):
                self.send_response(chat_status)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            text = json.dumps(answer)
            payload = (
                {"choices": [{"message": {"content": text}}]}
                if self.path.endswith("/chat/completions")
                else {
                    "output": [
                        {"type": "message", "content": [{"type": "output_text", "text": text}]}
                    ]
                }
            )
            self.wfile.write(json.dumps(payload).encode())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    schema = {"type": "object", "properties": {"summary": {"type": "string"}}}
    messages = [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "{}"},
        {"role": "assistant", "content": "draft"},
        {"role": "user", "content": "fix"},
    ]
    try:
        result = complete_json(
            ExplanationProvider(base_url=f"http://127.0.0.1:{server.server_port}/v1"),
            messages,
            schema,
        )
        assert result == answer
        assert len(seen) == (1 if chat_status == 200 else 2)
        chat = seen[0][1]
        assert chat["model"] == "local-main" and "store" not in chat
        assert chat["messages"] == messages
        assert chat["response_format"]["json_schema"]["schema"] == schema
        if chat_status != 200:
            responses = seen[1][1]
            assert responses["instructions"] == "rules" and responses["store"] is False
            assert [m["role"] for m in responses["input"]] == ["user", "assistant", "user"]
            assert responses["text"]["format"]["schema"] == schema
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_ai_unavailable_still_allows_direct_review_of_exact_stored_result(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    for i in range(1, 4):
        deliver(workspace, tmp_path / "waves", i, 0.5)
    analyze(workspace)
    result = request_phm_review(
        workspace.root, {"binding_id": "anomaly-a", "position": 3, "explanation_id": None}
    )
    assert result["status"] == "open" and result["analysis_run_id"]
    assert not workspace.phm_explanation_path.exists()


def test_explanation_manager_never_changes_score_and_review_cannot_link_other_result(
    tmp_path: Path, monkeypatch
) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    for i in range(1, 4):
        deliver(workspace, tmp_path / "waves", i, 0.5)
    analyze(workspace)
    from industrial_phm.runtime import operations_web_phm_explanation as runtime

    answer = {
        "summary": "source-bound answer",
        "observations": [],
        "next_signals": [],
        "next_step": "next",
        "checks": {"summary_source": "model"},
    }
    monkeypatch.setattr(runtime, "generate_grounded_answer", lambda context, provider: answer)
    manager = ExplanationManager(workspace.root)
    job = manager.request("anomaly-a", 3)
    for _ in range(100):
        record = manager.store.get(job["explanation_id"])
        if record["status"] != "pending":
            break
        time.sleep(0.01)
    assert record["status"] == "complete" and record["context"]["position"] == 3
    assert record["answer"] == answer and record["text"] == "source-bound answer next"
    linked = request_phm_review(
        workspace.root, {"binding_id": "anomaly-a", "position": 3, "explanation_id": record["id"]}
    )
    assert linked["explanation_id"] == record["id"]
    with pytest.raises(ValueError, match="does not match"):
        request_phm_review(
            workspace.root,
            {"binding_id": "anomaly-a", "position": 2, "explanation_id": record["id"]},
        )


def test_facts_state_meanings_the_model_must_not_reinterpret() -> None:
    from industrial_phm.application.phm_explanation import explanation_facts

    rul = explanation_facts(
        {
            "task": "rul-estimate",
            "estimate": -55.221,
            "unit": "acquisition-interval",
            "endpoint_semantics": "last-recorded-acquisition",
            "change_from_previous": 16.07,
            "applicability": "inside",
        },
        {
            "per_asset": [
                {"asset_id": "b1", "mean_absolute_error": 73.94, "mean_signed_error": 17.3}
            ]
        },
        asset_id="b1",
        recorded_replay=True,
    )
    text = "\n".join(rul)
    assert "마지막으로 기록된 획득까지 남은" in text and "물리적 고장 시각이 아닙니다" in text
    assert "기록 종료점을 이미 지났다" in text
    assert "운영 합격 판정이 기록되어 있지 않습니다" in text
    assert "MAE 73.94" in text and "기록 데이터 재생" in text

    anomaly = "\n".join(
        explanation_facts(
            {
                "task": "anomaly-score",
                "score": 2.5,
                "threshold": 1.0,
                "exceeds_threshold": True,
                "feature_contributions": {"a": 0.1, "b": 2.0, "c": 0.4},
                "applicability": "unknown",
            },
            {"acceptance": "FAIL (protocol v1 §3)"},
            asset_id="x",
            recorded_replay=False,
        )
    )
    assert "임계값 1.00 를 초과" in anomaly and "b=2.00" in anomaly.replace(", ", ",")
    assert "FAIL (protocol v1 §3)" in anomaly and "RUL" not in anomaly


def test_status_verdicts_are_flagged_but_negations_are_not() -> None:
    from industrial_phm.genai.local_explanation import verdict_phrases

    observed = "이 데이터는 정상 범위 내에 있음을 시사합니다. 이상 없음으로 보이며 고장입니다."
    assert verdict_phrases(observed) == ["고장입니다", "이상 없음", "정상 범위"]
    assert verdict_phrases("임계값 이하는 '정상' 판정이 아닙니다. 고장 판정이 아닙니다.") == []
    assert verdict_phrases("현재 이상 징후가 심각하지 않으며 위험이 낮습니다.") == [
        "위험이 낮",
        "이상 징후가 심각하지 않",
    ]
