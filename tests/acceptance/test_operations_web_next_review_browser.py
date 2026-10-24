"""The maintenance queue links a review only to its exact persisted evidence identity."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

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
                                    "data_quality": {"state": "pass", "issue_codes": []},
                                    "quantities": [],
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

                def reviews(route):
                    params = parse_qs(urlsplit(route.request.url).query)
                    asset = params["asset_id"][0]
                    exact = params.get("finding_id", [None])[0]
                    if exact and (asset != "motor-a" or exact != "finding-archive"):
                        route.fulfill(status=404, json={"error": "review_not_found"})
                        return
                    items = [
                        {
                            "finding_id": "finding-a",
                            "subject": "analysis",
                            "analysis_run_id": "run-a",
                            "evidence_ids": ["evidence-a"],
                            "capability_id": "phase-unbalance",
                            "measurement_point_id": "winding-a",
                            "observed_at": "2026-10-10T00:00:00+00:00",
                            "status": "open",
                            "model": None,
                            "events": [],
                            "events_total": 0,
                        }
                    ]
                    if exact:
                        # This item is deliberately absent from the recent list.
                        items[0]["finding_id"] = exact
                    body = {
                        "schema_version": 1,
                        "asset_id": asset,
                        "meaning": "human-review-records-not-maintenance-or-diagnosis",
                        "reviews": {
                            "items": items if asset == "motor-a" else [],
                            "total": 1 if asset == "motor-a" else 0,
                            "truncated": False,
                        },
                    }
                    route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(body)
                    )

                page.route("**/api/v1/monitor", monitor)
                page.route("**/api/v1/reviews?*", reviews)
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(
                    base + "/web/?page=maintenance&monitor_asset=motor-a",
                    wait_until="networkidle",
                )
                # Direct review links remain available without adding a primary navigation item.
                pw.expect(page.get_by_role("heading", name="정비 검토", level=1)).to_be_visible()
                pw.expect(
                    page.get_by_role("navigation", name="업무 메뉴").get_by_role(
                        "link", name="정비 검토"
                    )
                ).to_have_count(0)
                queue = page.get_by_role("region", name="검토함")
                detail = page.get_by_role("region", name="고른 검토 항목")
                items = queue.get_by_role("listitem")
                pw.expect(items).to_have_count(1)
                pw.expect(items.first).to_contain_text("motor-a · ")
                pw.expect(items.first).to_contain_text("분석 결과 · 검토 대기")
                pw.expect(detail.get_by_role("heading", level=2)).to_contain_text("motor-a · ")
                pw.expect(detail.locator(".badge")).to_have_text("검토 대기")
                pw.expect(detail.locator(".evidence li")).to_contain_text("데이터 출처")
                detail.get_by_text("기술 상세").click()
                pw.expect(detail.get_by_text("finding-a", exact=True)).to_be_visible()
                pw.expect(detail.get_by_text("run-a", exact=True)).to_be_visible()
                pw.expect(detail.get_by_text("evidence-a", exact=True)).to_be_visible()
                # Without the supervisor this screen shows the history but changes nothing.
                read_only = detail.get_by_text("보기 전용이라 검토 기록을 남길 수 없습니다")
                pw.expect(read_only).to_be_visible()
                for action in ("확인함으로 표시", "검토 종료"):
                    assert detail.get_by_role("button", name=action).count() == 0

                evidence_asset["value"] = "motor-b"
                page.get_by_role("button", name="다시 불러오기").click()
                detail = page.get_by_role("region", name="고른 검토 항목")
                pw.expect(detail.get_by_text("이번 목록에서 찾지 못했습니다")).to_be_visible()
                # The review keeps its own subject; another asset's evidence never fills in.
                assert detail.locator(".evidence li").filter(has_text="데이터 출처").count() == 0
                assert page.get_by_role("heading", name="motor-b · ").count() == 0

                # A direct bookmark outside the recent list still opens its exact review.
                page.goto(
                    base + "/web/?page=maintenance&monitor_asset=motor-a&finding_id=finding-archive"
                )
                archived = page.get_by_role("region", name="고른 검토 항목")
                archived.get_by_text("기술 상세").click()
                pw.expect(archived.get_by_text("finding-archive", exact=True)).to_be_visible()
                # The very same finding identity must never resolve for another asset.
                page.goto(
                    base + "/web/?page=maintenance&monitor_asset=motor-b&finding_id=finding-archive"
                )
                pw.expect(
                    page.get_by_role("heading", name="검토 항목을 찾을 수 없습니다")
                ).to_be_visible()
                assert page.get_by_text("finding-archive", exact=True).count() == 0
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
