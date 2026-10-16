"""Web-next baseline departures keep the asset, baseline, and evidence limits visible."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


@pytest.mark.parametrize("width", [390, 1024, 1440])
def test_departures_are_not_diagnosis_and_selection_survives_reload(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "departures")
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
                monitor = {
                    "assessed_at": "2026-10-16T00:00:00Z",
                    "assets": {
                        "items": [
                            {
                                "asset_id": "motor-a",
                                "data_flow_status": "stored-history",
                                "last_data_at": "2026-10-15T00:00:00Z",
                                "attention_count": 0,
                            },
                            {
                                "asset_id": "motor-b",
                                "data_flow_status": "waiting",
                                "last_data_at": None,
                                "attention_count": None,
                            },
                        ],
                        "total": 2,
                        "truncated": False,
                    },
                    "system_error_scopes": [],
                }
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(monitor)
                    ),
                )

                def channels(route):
                    asset = parse_qs(urlsplit(route.request.url).query)["asset_id"][0]
                    data = {
                        "asset_id": asset,
                        "channels": {
                            "items": ["R"] if asset == "motor-a" else [],
                            "total": 1 if asset == "motor-a" else 0,
                            "truncated": False,
                        },
                    }
                    route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(data)
                    )

                response_override = {"error": None}

                def departures(route):
                    if response_override["error"]:
                        route.fulfill(
                            status=503 if response_override["error"] == "store" else 404,
                            content_type="application/json",
                            body=json.dumps({"error": response_override["error"]}),
                        )
                        return
                    params = parse_qs(urlsplit(route.request.url).query)
                    assert params["asset_id"] == ["motor-a"]
                    assert params["series"] == ["R"]
                    baseline = params["baseline"][0]
                    if baseline == "first-50":
                        route.fulfill(
                            status=404,
                            content_type="application/json",
                            body=json.dumps({"error": "nothing_to_explore"}),
                        )
                        return
                    marked = baseline == "first-30"
                    interval = {
                        "channel": "R",
                        "channels": ["R"],
                        "start": "2026-10-15T01:00:00Z",
                        "end": "2026-10-15T01:01:00Z",
                        "median": 2,
                        "value": 3.4,
                        "distance": 4.2,
                        "direction": "up",
                    }
                    data = {
                        "schema_version": 1,
                        "meaning": "departures-from-a-chosen-baseline-not-fault-diagnosis",
                        "asset_id": "motor-a",
                        "available": ["R"],
                        "series": ["R"],
                        "units": {"R": "A"},
                        "bucket_seconds": 60,
                        "threshold": 3.5,
                        "baseline": {
                            "name": baseline,
                            "from": "2026-10-14T00:00:00Z",
                            "to": "2026-10-14T01:00:00Z",
                        },
                        "channels": [
                            {
                                "key": "R",
                                "state": "scored",
                                "marked": 1 if marked else 0,
                                "median": 2,
                                "spread": 0.3,
                            }
                        ],
                        "score": [["2026-10-15T01:00:00Z", 4.2, "R"]] if marked else [],
                        "intervals": [interval] if marked else [],
                        "interval_count": 1 if marked else 0,
                    }
                    route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(data)
                    )

                page.route("**/api/v1/history/channels?**", channels)
                page.route("**/api/v1/explore/anomaly?**", departures)
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(
                    base + "/web-next/?view=departures&monitor_asset=motor-a",
                    wait_until="networkidle",
                )
                pw.expect(page.get_by_role("heading", name="기준 구간 이탈 조사")).to_be_visible()
                pw.expect(page.get_by_text("기준에서 크게 벗어난 구간")).to_contain_text("1개")
                pw.expect(page.locator(".departures svg circle")).to_have_count(1)
                assert "고장 진단이 아닙니다" in page.locator("main").inner_text()
                page.get_by_label("비교 기준 구간").select_option("all")
                pw.expect(page.get_by_text("기준에서 크게 벗어난 구간")).to_contain_text("0개")
                assert "departure_baseline=all" in page.url
                page.reload(wait_until="networkidle")
                pw.expect(page.get_by_label("비교 기준 구간")).to_have_value("all")
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )

                page.get_by_label("비교 기준 구간").select_option("first-50")
                pw.expect(
                    page.get_by_role("heading", name="저장된 비교 근거가 없습니다")
                ).to_be_visible()
                assert page.get_by_text("0개").count() == 0
                response_override["error"] = "store"
                page.get_by_label("비교 기준 구간").select_option("first-30")
                pw.expect(
                    page.get_by_role("heading", name="기준 이탈 분석 조회 실패")
                ).to_be_visible()
                assert page.get_by_role("heading", name="저장된 비교 근거가 없습니다").count() == 0
                response_override["error"] = "not_found"
                page.get_by_label("비교 기준 구간").select_option("all")
                pw.expect(page.get_by_text("조회 경로를 확인할 수 없습니다")).to_be_visible()
                page.get_by_role("button", name="motor-b").click()
                pw.expect(
                    page.get_by_role("heading", name="이 설비에 저장된 신호가 없습니다")
                ).to_be_visible()
                assert "motor-b" in page.url
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()
