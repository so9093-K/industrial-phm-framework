"""AI briefings remain tied to one outlook data-version and require supervisor CSRF."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


@pytest.mark.parametrize("width", [390, 1024])
@pytest.mark.parametrize("drift", ["data", "settings"])
def test_briefing_version_and_supervisor_write_contract(
    tmp_path: Path, width: int, drift: str
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "briefing")
    initialize_operations_workspace(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "assessed_at": "2026-10-16T00:00:00Z",
                                "assets": {
                                    "items": [
                                        {
                                            "asset_id": "motor-a",
                                            "data_flow_status": "stored-history",
                                            "last_data_at": None,
                                            "attention_count": 0,
                                        }
                                    ],
                                    "total": 1,
                                    "truncated": False,
                                },
                                "system_error_scopes": [],
                            }
                        ),
                    ),
                )
                page.route(
                    "**/api/v1/forecast/options?**",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "schema_version": 1,
                                "asset_id": "motor-a",
                                "history": {
                                    "series": [{"key": "R"}],
                                    "horizons": {
                                        "1h": None,
                                        "24h": "short-history",
                                        "7d": "short-history",
                                        "30d": "short-history",
                                    },
                                },
                            }
                        ),
                    ),
                )
                page.route(
                    "**/api/v1/forecast?**",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "schema_version": 1,
                                "asset_id": "motor-a",
                                "kind": "history",
                                "series": "R",
                                "horizon": "1h",
                                "axis": "time",
                                "measurement_version": "measure-v1",
                                "source_id": "source-a",
                                "measurement_point_id": "point-a",
                                "unit": "A",
                                "meaning": (
                                    "stored-flow-continued-not-failure-time-or-remaining-life"
                                ),
                                "forecast": [["2026-10-16T01:00:00Z", 11.5, 10.5, 12.5]],
                            }
                        ),
                    ),
                )
                versions = {"data": "a" * 64, "prior": 0.05}
                writable = {"yes": True}
                requested = {"yes": False}

                def outlook(route):
                    query = parse_qs(urlsplit(route.request.url).query)
                    assert query["asset_id"] == ["motor-a"]
                    assert query["series"] == ["R"]
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "schema_version": 1,
                                "asset_id": "motor-a",
                                "kind": "history",
                                "series": "R",
                                "axis": "time",
                                "measurement_version": "measure-v1",
                                "data_version": versions["data"],
                                "source_id": "source-a",
                                "measurement_point_id": "point-a",
                                "meaning": "remaining-margin-to-user-conditions-not-a-diagnosis",
                                "conditions": {
                                    "direction": "upper",
                                    "management": 12,
                                    "end": None,
                                },
                                "record": {
                                    "first": "2026-10-15T00:00:00Z",
                                    "last": "2026-10-16T00:00:00Z",
                                    "points": 180,
                                },
                                "scenarios": [],
                                "settings": {
                                    "changepoint_prior_scale": versions["prior"],
                                    "changepoint_range": 0.9,
                                    "training_points": None,
                                    "seasonality": "auto",
                                },
                            }
                        ),
                    )

                page.route("**/api/v1/outlook?**", outlook)
                page.route(
                    "**/api/v1/session",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "schema_version": 1,
                                "csrf_token": "correct-supervisor-csrf-token",
                                "can_change": writable["yes"],
                                "write_scope": (
                                    "supervisor-owned-source-control"
                                    if writable["yes"]
                                    else "read-only-synthetic-demo"
                                ),
                            }
                        ),
                    ),
                )

                def canonical(query: str) -> str:
                    pairs = parse_qs(query)
                    return urlencode(sorted((key, value[0]) for key, value in pairs.items()))

                def briefings(route):
                    selection = canonical(urlsplit(route.request.url).query)
                    response = {
                        "schema_version": 1,
                        "selection": selection,
                        "briefings": [],
                    }
                    if requested["yes"] and "data_version=" + "a" * 64 in selection:
                        response["briefings"] = [
                            {
                                "id": "briefing-a",
                                "question": "이 측정이 어떻게 변했나요?",
                                "model": "local",
                                "status": "complete",
                                "requested_at": "2026-10-16T00:01:00Z",
                                "finished_at": "2026-10-16T00:02:00Z",
                                "answer": {
                                    "summary": "저장된 근거를 설명합니다.",
                                    "points": [
                                        {"text": "관측된 변화입니다.", "evidence": ["change"]}
                                    ],
                                    "evidence": {
                                        "change": {
                                            "label": "관측 변화",
                                            "text": "저장된 측정과 비교 결과",
                                        }
                                    },
                                    "checks": {"source": "computed"},
                                },
                            }
                        ]
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(response),
                    )

                page.route("**/api/v1/outlook/briefings?**", briefings)

                def request_briefing(route):
                    headers = route.request.headers
                    assert headers["x-csrf-token"] == "correct-supervisor-csrf-token"
                    assert headers["content-type"] == "application/json"
                    payload = route.request.post_data_json
                    assert payload == {
                        "asset_id": "motor-a",
                        "kind": "history",
                        "series": "R",
                        "direction": "upper",
                        "changepoint_prior_scale": "0.05",
                        "changepoint_range": "0.9",
                        "seasonality": "auto",
                        "management_limit": "12",
                        "data_version": "a" * 64,
                        "question": "이 측정이 어떻게 변했나요?",
                    }
                    requested["yes"] = True
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "briefing_id": "briefing-a",
                                "status": "pending",
                                "selection": urlencode(
                                    sorted(
                                        (key, value)
                                        for key, value in payload.items()
                                        if key != "question"
                                    )
                                ),
                            }
                        ),
                    )

                page.route("**/api/v1/outlook/briefings/request", request_briefing)
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(
                    base + "/web-next/?view=projection&monitor_asset=motor-a",
                    wait_until="networkidle",
                )
                page.get_by_label("관리 기준 (선택)").fill("12")
                page.get_by_role("button", name="계산하기", exact=True).click()
                ai = page.get_by_role("region", name="AI 해설")
                pw.expect(ai.get_by_role("heading", name="AI 해설")).to_be_visible()
                pw.expect(ai).to_contain_text("아직 이 결과에 대한 해설이 없습니다")
                pw.expect(ai.get_by_role("button", name="해설 만들기")).to_be_enabled()
                ai.get_by_text("직접 질문하기").click()
                ai.get_by_label("AI에게 물을 질문 (최대 600자)").fill("이 측정이 어떻게 변했나요?")
                ai.get_by_role("button", name="질문 보내기").click()
                pw.expect(page.get_by_text("저장된 근거를 설명합니다.")).to_be_visible()
                pw.expect(page.get_by_text("저장된 측정과 비교 결과")).to_be_hidden()
                ai.get_by_text("해설에 쓴 계산 사실").click()
                pw.expect(page.get_by_text("저장된 측정과 비교 결과")).to_be_visible()

                # A new anomaly input can change data_version without moving
                # the recorded measurement version or last sample timestamp.
                if drift == "data":
                    versions["data"] = "b" * 64
                else:
                    versions["prior"] = 0.5
                ai.get_by_role("button", name="해설 다시 확인").click()
                pw.expect(
                    page.get_by_role("heading", name="데이터가 바뀌어 결과를 다시 계산해야 합니다")
                ).to_be_visible()
                assert page.get_by_text("저장된 근거를 설명합니다.").count() == 0
                assert page.get_by_role("heading", name="결과", exact=True).count() == 0

                # When the supervisor is absent, stored evidence stays readable
                # but the AI action must never become enabled.
                versions["data"] = "a" * 64
                versions["prior"] = 0.05
                writable["yes"] = False
                requested["yes"] = False
                page.reload(wait_until="networkidle")
                page.get_by_label("관리 기준 (선택)").fill("12")
                page.get_by_role("button", name="계산하기", exact=True).click()
                ai = page.get_by_role("region", name="AI 해설")
                pw.expect(ai).to_contain_text("보기 전용이라 해설을 만들 수 없습니다")
                assert ai.get_by_role("button", name="해설 만들기").count() == 0
                ai.get_by_text("직접 질문하기").click()
                pw.expect(ai.get_by_role("button", name="질문 보내기")).to_be_disabled()
                assert not requested["yes"]
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()
