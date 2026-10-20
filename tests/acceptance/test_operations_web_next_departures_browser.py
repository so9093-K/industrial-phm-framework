"""Web-next baseline departures keep the asset, baseline, and evidence limits visible."""

from __future__ import annotations

import json
import re
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.web_next import choose_asset, expect_place


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
                    base + "/web/?view=departures&monitor_asset=motor-a",
                    wait_until="networkidle",
                )
                expect_place(pw, page, "이상 징후", "기준 구간 이탈")
                pw.expect(page.get_by_text("기준에서 크게 벗어난 구간")).to_contain_text("1개")
                chart = page.locator(".departures svg[role=img]")
                drawn = re.compile(r"^M\S+ \S+ L")
                pw.expect(chart.locator("path.line")).to_have_attribute("d", drawn)
                pw.expect(chart.locator("rect.found")).to_have_count(1)
                onset = page.get_by_label("첫 기준 초과 확인", exact=True)
                pw.expect(onset).to_contain_text("KST")
                pw.expect(chart.locator("line.onset-line")).to_have_count(1)
                onset.get_by_role("button", name="시간별 값 보기 →").click()
                pw.expect(page.locator('tr[data-onset="true"]')).to_be_focused()
                assert "고장 가능성" in page.locator("main").inner_text()
                page.get_by_label("비교 기준 구간").select_option("all")
                pw.expect(page.get_by_text("기준에서 크게 벗어난 구간")).to_contain_text("0개")
                pw.expect(page.get_by_label("첫 기준 초과 확인", exact=True)).to_have_count(0)
                assert "departure_baseline=all" in page.url
                page.reload(wait_until="networkidle")
                pw.expect(page.get_by_label("비교 기준 구간")).to_have_value("all")
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )

                page.get_by_label("비교 기준 구간").select_option("first-50")
                pw.expect(
                    page.get_by_role("heading", name="비교할 저장 기록이 없습니다")
                ).to_be_visible()
                assert page.get_by_text("0개").count() == 0
                response_override["error"] = "store"
                page.get_by_label("비교 기준 구간").select_option("first-30")
                pw.expect(
                    page.get_by_role("heading", name="기준 이탈 결과를 불러오지 못했습니다")
                ).to_be_visible()
                assert page.get_by_role("heading", name="비교할 저장 기록이 없습니다").count() == 0
                response_override["error"] = "not_found"
                page.get_by_label("비교 기준 구간").select_option("all")
                pw.expect(
                    page.get_by_text("결과를 찾을 위치를 확인하지 못했습니다")
                ).to_be_visible()
                choose_asset(page, "motor-b")
                expect_place(pw, page, "이상 징후", "기준 구간 이탈")
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
