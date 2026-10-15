"""An AI briefing is asked through the supervisor's action and read back by its selection."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytest.importorskip("prophet", reason="install the forecast extra")

from industrial_phm.genai import outlook_answer
from industrial_phm.runtime import operations_web_outlook_briefing as briefing_runtime
from industrial_phm.runtime.operations_web_actions import (
    WEB_SUPERVISOR_ONLY_ACTION_ROUTES,
    execute_web_source_action,
)
from industrial_phm.runtime.operations_web_outlook import condition_outlook, outlook_arguments
from tests.integration.test_operations_web_forecast import _serve
from tests.support.phm import ScriptedModel, analyze, deliver, phm_workspace

ROUTE = "/api/v1/outlook/briefings/request"


def test_a_briefing_recomputes_the_outlook_and_is_read_by_its_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal in range(1, 65):
        scale = 0.5 + 0.002 * (ordinal % 3) if ordinal <= 40 else 0.5 + 0.06 * (ordinal - 40)
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    model = ScriptedModel(
        {
            "summary": "#41부터 기준 범위를 벗어나 관리 상한 2.4까지 4개 획득 남았습니다.",
            "points": [{"text": "최근 획득당 +0.067씩 오르고 있습니다.", "evidence": ["rate"]}],
        }
    )
    monkeypatch.setattr(outlook_answer, "complete_json", model)
    monkeypatch.setattr(briefing_runtime, "_MANAGERS", {})
    selection = {
        "asset_id": "bearing-a",
        "kind": "acquisition",
        "series": "feature.Horizontal_vibration_signals.rms",
        "management_limit": "2.4",
        "end_limit": "3.0",
        "direction": "upper",
    }
    selection["data_version"] = condition_outlook(workspace, **outlook_arguments(selection))[
        "data_version"
    ]
    assert ROUTE in WEB_SUPERVISOR_ONLY_ACTION_ROUTES
    job = execute_web_source_action(
        workspace.root.resolve(), ROUTE, {**selection, "question": "기준까지 얼마나 남았어?"}
    )
    assert job["status"] == "pending"
    get, stop = _serve(workspace.root)
    try:
        for _ in range(300):
            status, body = get("/api/v1/outlook/briefings", **selection)
            if status == 200 and body["briefings"] and body["briefings"][0]["status"] != "pending":
                break
            time.sleep(0.05)
        (record,) = body["briefings"]
        assert record["id"] == job["briefing_id"] and record["status"] == "complete"
        assert record["question"] == "기준까지 얼마나 남았어?" and record["model"] == "local-main"
        answer = record["answer"]
        assert answer["checks"]["source"] == "model", answer["checks"]
        assert answer["evidence"]["rate"]["text"].startswith("최근 획득당 +0.067")
        # The facts the model saw were computed by the supervisor, not sent by the browser.
        sent = json.loads(model.requests[0][1]["content"])
        assert sent["facts"]["management"].startswith("관리 상한 2.4까지: 현재 설정")
        assert "owner" not in record and str(tmp_path) not in json.dumps(body)
        # Another selection has its own briefings.
        status, other = get("/api/v1/outlook/briefings", **{**selection, "end_limit": "4"})
        assert status == 200 and other["briefings"] == []
        assert (
            get(
                "/api/v1/outlook/briefings",
                **{**selection, "data_version": "0" * 64},
            )[1]["briefings"]
            == []
        )
        # A later acquisition changes the outlook's revision, without altering
        # its selected signal, threshold or Prophet settings.
        deliver(workspace, tmp_path / "waves", 65, 2.2)
        analyze(workspace)
        new_version = condition_outlook(workspace, **outlook_arguments(selection))["data_version"]
        assert new_version != selection["data_version"]
        assert (
            get(
                "/api/v1/outlook/briefings",
                **{**selection, "data_version": new_version},
            )[1]["briefings"]
            == []
        )
        assert get("/api/v1/outlook/briefings", **selection, unknown="1")[0] == 400
    finally:
        stop()

    with pytest.raises(ValueError):
        execute_web_source_action(workspace.root.resolve(), ROUTE, {"asset_id": "bearing-a"})
    with pytest.raises(ValueError):
        execute_web_source_action(
            workspace.root.resolve(), ROUTE, {**selection, "management_limit": "nan"}
        )
    with pytest.raises(ValueError):
        execute_web_source_action(
            workspace.root.resolve(), ROUTE, {**selection, "question": "가" * 601}
        )
