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
                page.get_by_role("button", name="asset-two").focus()
                page.get_by_role("button", name="asset-two").press("Enter")
                pw.expect(page.locator(".detail dd").first).to_have_text("asset-two")
                assert "monitor_asset=asset-two" in page.url
                assert (
                    page.get_by_role("link", name="원본 신호와 저장 이력 확인").get_attribute(
                        "href"
                    )
                    == "/web/?monitor_asset=asset-two#signals"
                )
                page.reload(wait_until="networkidle")
                pw.expect(page.locator(".detail dd").first).to_have_text("asset-two")

                page.unroute("**/api/v1/monitor")
                page.route("**/api/v1/monitor", lambda route: route.abort())
                page.get_by_role("button", name="다시 불러오기").click()
                pw.expect(page.get_by_role("alert")).to_contain_text(
                    "조회 결과를 확인할 수 없습니다"
                )
                assert page.get_by_role("heading", name="조회된 설비 2개").count() == 0
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


def test_web_next_empty_and_partial_read_are_not_asset_health(tmp_path: Path) -> None:
    """Uncertain evidence remains visible even when the asset list is empty."""
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "empty-uncertain")
    initialize_operations_workspace(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1024, "height": 900}, locale="ko-KR")
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "assessed_at": "2026-10-10T03:00:00Z",
                                "assets": {"items": [], "total": 0, "truncated": False},
                                "system_error_scopes": ["history"],
                            }
                        ),
                    ),
                )
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(base + "/web-next/", wait_until="networkidle")
                pw.expect(
                    page.get_by_role("heading", name="조회된 설비가 없습니다")
                ).to_be_visible()
                pw.expect(
                    page.get_by_role("status").filter(
                        has_text="일부 저장소·수집 근거를 확인하지 못했습니다"
                    )
                ).to_be_visible()
                pw.expect(page.get_by_role("link", name="데이터 연결 화면 열기")).to_have_attribute(
                    "href", "/web/#connect"
                )
                assert page.get_by_role("heading", name="선택한 설비의 관측 사실").count() == 0
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()



def test_asset_history_navigation_clears_old_context_and_restores_selection(
    tmp_path: Path,
) -> None:
    """Switching assets cannot reuse another asset's query, even after back/forward."""
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "route-history")
    initialize_operations_workspace(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1024, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({
                            "assessed_at": "2026-10-16T00:00:00Z",
                            "assets": {
                                "items": [
                                    {"asset_id": "motor-a", "data_flow_status": "stored-history",
                                     "last_data_at": None, "attention_count": 0},
                                    {"asset_id": "motor-b", "data_flow_status": "waiting",
                                     "last_data_at": None, "attention_count": 0},
                                ],
                                "total": 2, "truncated": False,
                            },
                            "system_error_scopes": [],
                        }),
                    ),
                )
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(base + "/web-next/?view=reviews&monitor_asset=motor-a"
                          "&monitor_channel=R&projection_direction=lower"
                          "&capture_id=old&unanticipated_selection=old", wait_until="networkidle")
                pw.expect(page.get_by_role("button", name="motor-a")).to_have_attribute(
                    "aria-pressed", "true"
                )
                page.get_by_role("button", name="motor-b").click()
                pw.expect(page.get_by_role("button", name="motor-b")).to_have_attribute(
                    "aria-pressed", "true"
                )
                assert page.url.endswith("/web-next/?view=reviews&monitor_asset=motor-b")
                page.go_back(wait_until="domcontentloaded")
                pw.expect(page.get_by_role("button", name="motor-a")).to_have_attribute(
                    "aria-pressed", "true"
                )
                assert "capture_id=old" in page.url
                page.go_forward(wait_until="domcontentloaded")
                pw.expect(page.get_by_role("button", name="motor-b")).to_have_attribute(
                    "aria-pressed", "true"
                )
                assert "monitor_channel=R" not in page.url
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def test_unknown_asset_deep_link_does_not_show_another_asset(
    tmp_path: Path,
) -> None:
    """A direct link to unavailable evidence must fail closed, not fall back."""
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "unknown-asset")
    initialize_operations_workspace(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 390, "height": 900}, locale="ko-KR")
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({
                            "assessed_at": "2026-10-16T00:00:00Z",
                            "assets": {
                                "items": [{"asset_id": "motor-b",
                                           "data_flow_status": "stored-history",
                                           "last_data_at": None, "attention_count": 0}],
                                "total": 2, "truncated": True,
                            },
                            "system_error_scopes": [],
                        }),
                    ),
                )
                page.goto(f"http://127.0.0.1:{server.server_port}/web-next/"
                          "?monitor_asset=motor-a", wait_until="networkidle")
                pw.expect(page.get_by_role("heading", name="선택한 설비가 이번 조회에 없습니다")
                          ).to_be_visible()
                assert page.get_by_role("heading", name="선택한 설비의 관측 사실").count() == 0
                assert "monitor_asset=motor-a" in page.url
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
