"""The isolated Web-next view must distinguish an observation from a failed read."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


@pytest.mark.parametrize("width", [390, 1024, 1440])
def test_web_next_read_only_observation_and_navigation(tmp_path: Path, width: int) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "pilot")
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
                base = f"http://127.0.0.1:{server.server_port}"
                recorded = {
                    "assessed_at": "2026-10-10T03:00:00Z",
                    "assets": {
                        "items": [
                            {
                                "asset_id": "asset-one",
                                "data_flow_status": "stored-history",
                                "last_data_at": "2026-10-10T00:00:00Z",
                                "attention_count": 0,
                            },
                            {
                                "asset_id": "asset-two",
                                "data_flow_status": "waiting",
                                "last_data_at": None,
                                "attention_count": 1,
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
                        status=200,
                        content_type="application/json",
                        body=json.dumps(recorded),
                    ),
                )
                page.goto(base + "/web-next/", wait_until="networkidle")
                pw.expect(page.get_by_role("heading", name="설비 관측 현황")).to_be_visible()
                pw.expect(page.get_by_role("heading", name="조회된 설비 2개")).to_be_visible()
                page.get_by_role("button", name="asset-two").click()
                pw.expect(page.locator(".detail dd").first).to_have_text("asset-two")
                assert "monitor_asset=asset-two" in page.url
                assert page.get_by_role("link", name="원본 신호와 저장 이력 확인").get_attribute(
                    "href"
                ) == "/web/?monitor_asset=asset-two#signals"
                page.reload(wait_until="networkidle")
                pw.expect(page.locator(".detail dd").first).to_have_text("asset-two")

                page.unroute("**/api/v1/monitor")
                page.route("**/api/v1/monitor", lambda route: route.abort())
                page.get_by_role("button", name="다시 불러오기").click()
                pw.expect(page.get_by_role("alert")).to_contain_text("조회 결과를 확인할 수 없습니다")
                assert page.get_by_role("heading", name="조회된 설비 2개").count() == 0
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 2")
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()
