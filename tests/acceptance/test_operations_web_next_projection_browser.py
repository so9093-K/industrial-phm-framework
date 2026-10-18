"""Version-matched Web-next forecast and outlook are paired only with exact evidence."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.web_next import expect_place


@pytest.mark.parametrize("width", [390, 1024])
def test_versioned_projection_blocks_mismatched_measurements(tmp_path: Path, width: int) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "projection")
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
                                "last_data_at": "2026-10-16T00:00:00Z",
                                "attention_count": 0,
                            }
                        ],
                        "total": 1,
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
                options = {
                    "schema_version": 1,
                    "asset_id": "motor-a",
                    "history": {
                        "series": [{"key": "current", "label": "current"}],
                        "horizons": {
                            "1h": None,
                            "24h": "short-history",
                            "7d": "short-history",
                            "30d": "short-history",
                        },
                    },
                }
                page.route(
                    "**/api/v1/forecast/options?**",
                    lambda route: route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(options)
                    ),
                )
                version = {"outlook": "same"}
                forecast = {
                    "schema_version": 1,
                    "asset_id": "motor-a",
                    "kind": "history",
                    "series": "current",
                    "horizon": "1h",
                    "axis": "time",
                    "measurement_version": "same",
                    "source_id": "motor-file",
                    "measurement_point_id": "winding",
                    "unit": "A",
                    "meaning": "stored-flow-continued-not-failure-time-or-remaining-life",
                    "forecast": [["2026-10-16T00:30:00Z", 14, 12, 16]],
                }
                page.route(
                    "**/api/v1/forecast?**",
                    lambda route: route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(forecast)
                    ),
                )

                def serve_outlook(route):
                    data = {
                        "schema_version": 1,
                        "asset_id": "motor-a",
                        "kind": "history",
                        "series": "current",
                        "axis": "time",
                        "source_id": "motor-file",
                        "measurement_point_id": "winding",
                        "measurement_version": version["outlook"],
                        "data_version": "outlook-and-AI-context",
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
                        "scenarios": [
                            {
                                "id": "current",
                                "limits": {
                                    "management": {
                                        "state": "expected",
                                        "expected": 3600,
                                        "earliest": 3000,
                                        "latest": 4000,
                                    },
                                },
                            }
                        ],
                    }
                    route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(data)
                    )

                page.route("**/api/v1/outlook?**", serve_outlook)
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(
                    base + "/web/?view=projection&monitor_asset=motor-a",
                    wait_until="networkidle",
                )
                expect_place(pw, page, "상태 전망")
                page.get_by_label("관리 기준 (선택)").fill("12")
                page.get_by_role("button", name="계산하기", exact=True).click()
                pw.expect(page.get_by_role("heading", name="결과", exact=True)).to_be_visible()
                pw.expect(page.locator(".tiles")).to_contain_text("관리 기준 12")
                page.get_by_text("예측값 표 · 1시간").click()
                pw.expect(page.get_by_role("columnheader", name="예측 시각")).to_be_visible()
                assert "projection_management=12" in page.url
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )
                version["outlook"] = "new-history"
                page.get_by_role("button", name="계산하기", exact=True).click()
                pw.expect(
                    page.get_by_role("heading", name="데이터가 바뀌어 결과를 다시 계산해야 합니다")
                ).to_be_visible()
                assert page.get_by_role("heading", name="결과", exact=True).count() == 0
                page.reload(wait_until="networkidle")
                pw.expect(page.get_by_label("관리 기준 (선택)")).to_have_value("12")
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()
