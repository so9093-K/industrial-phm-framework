"""Explanation and human review of one stored PHM result through the real Web routes."""

from __future__ import annotations

import json
import time
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from typing import Any

import pytest

from industrial_phm.genai import phm_answer
from industrial_phm.runtime import operations_web_phm_explanation as explanation_runtime
from industrial_phm.runtime.operations_web_actions import execute_web_source_action
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.phm import ScriptedModel, analyze, deliver, phm_workspace


def test_explanation_and_review_lifecycle_are_readable_without_touching_model_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.6, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    model = ScriptedModel(
        {
            "summary": "이상 점수가 증가했고 수평 진동 RMS가 함께 커졌습니다.",
            "observations": [
                {"feature": "feature.Horizontal_vibration_signals.rms", "change": "증가"}
            ],
            "next_signals": [],
            "next_step": "두 시점의 원본 파형을 비교해 보세요.",
        }
    )
    monkeypatch.setattr(phm_answer, "complete_json", model)
    monkeypatch.setattr(explanation_runtime, "_MANAGERS", {})
    root = workspace.root.resolve()
    job = execute_web_source_action(
        root, "/api/v1/phm/explanations/request", {"binding_id": "anomaly-a", "position": 3}
    )
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def get(path: str) -> tuple[int, dict[str, Any]]:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            connection.request("GET", path, headers={"Host": f"127.0.0.1:{server.server_port}"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    try:
        query = "binding_id=anomaly-a&position=3"
        for _ in range(200):
            status, body = get("/api/v1/phm/explanations?" + query)
            if status == 200 and body["explanations"][0]["status"] != "pending":
                break
            time.sleep(0.01)
        assert status == 200
        (record,) = body["explanations"]
        assert record["id"] == job["explanation_id"] and record["status"] == "complete"
        assert record["model"] == "local-main"
        assert (
            record["answer"]["summary"] == "이상 점수가 증가했고 수평 진동 RMS가 함께 커졌습니다."
        )
        assert record["answer"]["observations"] == [
            {"feature": "feature.Horizontal_vibration_signals.rms", "relation": "increased"}
        ]
        assert record["text"].startswith(record["answer"]["summary"])
        sent = json.loads(model.requests[0][1]["content"])
        assert sent["primary"]["name"] == "이상 점수" and sent["question"]
        assert "owner" not in record and str(tmp_path) not in json.dumps(body)

        status, review = get("/api/v1/phm/review?" + query)
        assert status == 200 and review["finding_id"] is None

        requested = execute_web_source_action(
            root,
            "/api/v1/phm/reviews/request",
            {"binding_id": "anomaly-a", "position": 3, "explanation_id": record["id"]},
        )
        assert requested["status"] == "open"
        finding = requested["finding_id"]
        for action, expected in (("acknowledge", "acknowledged"), ("close", "closed")):
            execute_web_source_action(
                root,
                "/api/v1/reviews/action",
                {"finding_id": finding, "action": action, "note": f"{action} by operator"},
            )
            status, review = get("/api/v1/phm/review?" + query)
            assert status == 200 and review["status"] == expected
        assert [event["action"] for event in review["events"]] == ["acknowledge", "close"]

        status, series = get("/api/v1/phm/series?binding_id=anomaly-a")
        step = next(item for item in series["steps"] if item["position"] == 3)
        assert step["output"] == record["context"]["output"]
        assert get("/api/v1/phm/review?binding_id=anomaly-a")[0] == 400
        assert get("/api/v1/phm/explanations?binding_id=anomaly-a&position=0")[0] == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
