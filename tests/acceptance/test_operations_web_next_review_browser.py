"""Read-only review inbox must link the exact persisted evidence identity only."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


@pytest.mark.parametrize("width", [390, 1024])
def test_review_inbox_preserves_run_and_evidence_identity(tmp_path: Path, width: int) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "review-inbox")
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
                evidence_asset = {"value": "motor-a"}

                def monitor(route):
                    response = {
                        "assessed_at": "2026-10-16T00:00:00Z",
                        "assets": {
                            "items": [
                                {
                                    "asset_id": "motor-a",
                                    "data_flow_status": "stored-history",
                                    "last_data_at": "2026-10-16T00:00:00Z",
                                    "attention_count": 1,
                                },
                                {
                                    "asset_id": "motor-b",
                                    "data_flow_status": "waiting",
                                    "last_data_at": None,
                                    "attention_count": 0,
                                },
                            ],
                            "total": 2,
                            "truncated": False,
                        },
                        "system_error_scopes": [],
                        "review_requests": {
                            "items": [
                                {
                                    "finding_id": "finding-a",
                                    "asset_id": "motor-a",
                                    "analysis_run_id": "run-a",
                                    "evidence_ids": ["evidence-a"],
                                    "status": "open",
                                }
                            ],
                            "total": 1,
                            "truncated": False,
                        },
                        "phase_unbalance_analyses": {
                            "items": [
                                {
                                    "analysis_run_id": "run-a",
                                    "evidence_id": "evidence-a",
                                    "asset_id": evidence_asset["value"],
                                    "source_id": "source-a",
                                    "measurement_point_id": "winding-a",
                                    "capability_id": "phase-unbalance",
                                    "completed_at": "2026-10-10T00:00:00Z",
                                    "data_quality": {"state": "usable"},
                                }
                            ],
                            "total": 1,
                            "truncated": False,
                        },
                        "file_feature_analyses": {
                            "items": [],
                            "total": 0,
                            "truncated": False,
                        },
                    }
                    route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(response)
                    )

                page.route("**/api/v1/monitor", monitor)
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(
                    base + "/web-next/?view=reviews&monitor_asset=motor-a",
                    wait_until="networkidle",
                )
                # The former review address lands on the maintenance task with every asset.
                pw.expect(page.get_by_role("heading", name="정비 검토", level=1)).to_be_visible()
                pw.expect(
                    page.get_by_role("navigation", name="업무 메뉴").get_by_role(
                        "link", name="정비 검토"
                    )
                ).to_have_attribute("aria-current", "page")
                review = page.locator(".item")
                pw.expect(review).to_have_count(1)
                pw.expect(review.get_by_role("heading")).to_contain_text("motor-a · ")
                pw.expect(review).to_contain_text("검토 대기")
                pw.expect(review.locator(".evidence li")).to_contain_text("데이터 출처")
                review.get_by_text("기술 상세").click()
                pw.expect(review.get_by_text("finding-a", exact=True)).to_be_visible()
                pw.expect(review.get_by_text("run-a", exact=True)).to_be_visible()
                pw.expect(review.get_by_text("evidence-a", exact=True)).to_be_visible()
                pw.expect(
                    page.get_by_role("link", name="이전 화면에서 메모·확인·종료하기")
                ).to_have_attribute("href", "/web/?monitor_asset=motor-a#evidence")
                assert page.get_by_role("button", name="검토 완료").count() == 0

                evidence_asset["value"] = "motor-b"
                page.get_by_role("button", name="다시 불러오기").click()
                pw.expect(page.get_by_text("이번 목록에서 찾지 못했습니다")).to_be_visible()
                # The review keeps its own subject; another asset's evidence never fills in.
                assert page.locator(".evidence li").filter(has_text="데이터 출처").count() == 0
                assert page.get_by_role("heading", name="motor-b · ").count() == 0
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
