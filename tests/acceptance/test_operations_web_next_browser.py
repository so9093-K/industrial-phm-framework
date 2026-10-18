"""The isolated Web-next view must distinguish an observation from a failed read."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.web_next import choose_asset, expect_place


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
                page.goto(base + "/web/", wait_until="networkidle")
                pw.expect(page.get_by_role("heading", name="관측 현황", level=1)).to_be_visible()
                pw.expect(page.get_by_role("heading", name="설비 2개")).to_be_visible()
                rows = page.get_by_role("list").locator("a.row")
                # The asset with something to check comes first.
                pw.expect(rows.first).to_contain_text("asset-two")
                pw.expect(rows.first).to_contain_text("확인할 항목 1건")
                pw.expect(rows.first).to_contain_text("수신 대기")
                rows.first.focus()
                rows.first.press("Enter")
                pw.expect(page.get_by_role("heading", name="asset-two", level=1)).to_be_visible()
                expect_place(pw, page, "상태 요약")
                assert "page=assets" in page.url and "monitor_asset=asset-two" in page.url
                page.reload(wait_until="networkidle")
                pw.expect(page.get_by_role("heading", name="asset-two", level=1)).to_be_visible()
                page.get_by_role("navigation", name="업무 메뉴").get_by_role(
                    "link", name="관측 현황"
                ).click()
                pw.expect(page.get_by_role("heading", name="설비 2개")).to_be_visible()
                # A page change moves keyboard and screen-reader focus to the new content.
                pw.expect(page.locator("#main")).to_be_focused()

                page.unroute("**/api/v1/monitor")
                page.route("**/api/v1/monitor", lambda route: route.abort())
                page.get_by_role("button", name="다시 불러오기").click()
                pw.expect(page.get_by_role("alert")).to_contain_text(
                    "설비 목록을 불러오지 못했습니다"
                )
                pw.expect(page.get_by_role("alert")).to_contain_text(
                    "데이터가 없다는 뜻은 아닙니다"
                )
                assert page.get_by_role("heading", name="설비 2개").count() == 0
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
                page.goto(base + "/web/", wait_until="networkidle")
                pw.expect(
                    page.get_by_role("heading", name="등록된 설비가 없습니다")
                ).to_be_visible()
                pw.expect(
                    page.get_by_role("status").filter(
                        has_text="일부 저장소나 수집 상태를 확인하지 못했습니다"
                    )
                ).to_be_visible()
                pw.expect(page.get_by_role("link", name="데이터 연결하기")).to_have_attribute(
                    "href", "/web/?page=system&section=connections"
                )
                assert page.get_by_role("heading", name="설비 0개").count() == 0
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
                            }
                        ),
                    ),
                )
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(
                    base + "/web/?view=reviews&monitor_asset=motor-a", wait_until="networkidle"
                )
                # A former address is replaced by its new place, not left half-understood.
                assert "page=maintenance" in page.url and "view=" not in page.url
                page.goto(
                    base + "/web/?page=assets&tab=outlook&data=history&monitor_asset=motor-a"
                    "&monitor_channel=R&projection_direction=lower"
                    "&capture_id=old&unanticipated_selection=old",
                    wait_until="networkidle",
                )
                pw.expect(page.get_by_role("heading", name="motor-a", level=1)).to_be_visible()
                expect_place(pw, page, "상태 전망")
                choose_asset(page, "motor-b")
                pw.expect(page.get_by_role("heading", name="motor-b", level=1)).to_be_visible()
                expect_place(pw, page, "상태 전망")
                for stale in (
                    "monitor_channel",
                    "projection_direction",
                    "capture_id",
                    "unanticipated",
                ):
                    assert stale not in page.url, page.url
                page.go_back(wait_until="domcontentloaded")
                pw.expect(page.get_by_role("heading", name="motor-a", level=1)).to_be_visible()
                assert "capture_id=old" in page.url
                page.go_forward(wait_until="domcontentloaded")
                pw.expect(page.get_by_role("heading", name="motor-b", level=1)).to_be_visible()
                page.get_by_role("navigation", name="설비 화면").get_by_role(
                    "link", name="신호", exact=True
                ).click()
                expect_place(pw, page, "신호")
                page.go_back(wait_until="domcontentloaded")
                expect_place(pw, page, "상태 전망")
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
                        body=json.dumps(
                            {
                                "assessed_at": "2026-10-16T00:00:00Z",
                                "assets": {
                                    "items": [
                                        {
                                            "asset_id": "motor-b",
                                            "data_flow_status": "stored-history",
                                            "last_data_at": None,
                                            "attention_count": 0,
                                        }
                                    ],
                                    "total": 2,
                                    "truncated": True,
                                },
                                "system_error_scopes": [],
                            }
                        ),
                    ),
                )
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/?page=assets&tab=outlook"
                    "&monitor_asset=motor-a",
                    wait_until="networkidle",
                )
                pw.expect(
                    page.get_by_role("heading", name="선택한 설비가 이번 목록에 없습니다")
                ).to_be_visible()
                assert page.get_by_role("heading", name="motor-b", level=1).count() == 0
                assert page.get_by_role("navigation", name="설비 화면").count() == 0
                assert "monitor_asset=motor-a" in page.url
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def test_session_read_failure_is_not_read_only_and_retry_is_explicit(tmp_path: Path) -> None:
    """A supervisor outage cannot masquerade as an ordinary read-only workspace.

    Every retry must read the actual supervisor session; a failed request
    must never grant the previous writable capability.
    """
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "session-feedback")
    initialize_operations_workspace(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    status = {"kind": "failed", "requests": 0}

    def session(route):
        status["requests"] += 1
        if status["kind"] == "failed":
            route.fulfill(status=503, content_type="application/json", body="{}")
            return
        enabled = status["kind"] == "writer"
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "schema_version": 1,
                    "can_change": enabled,
                    "write_scope": "supervisor-owned-source-control" if enabled else "read-only",
                    "csrf_token": "valid-supervisor-csrf-token" if enabled else None,
                }
            ),
        )

    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 390, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/api/v1/session", session)
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(base + "/web/?page=system", wait_until="networkidle")
                pw.expect(
                    page.get_by_role("status").filter(has_text="쓰기 권한 확인 실패 · 보기만 가능")
                ).to_be_visible()
                assert page.get_by_text("운영 중 · 기록 가능").count() == 0
                status["kind"] = "readonly"
                page.get_by_role("button", name="권한 다시 확인").click()
                pw.expect(page.get_by_role("status").filter(has_text="보기 전용")).to_be_visible()
                assert page.get_by_role("button", name="권한 다시 확인").count() == 0
                assert status["requests"] >= 2

                status["kind"] = "writer"
                page.reload(wait_until="networkidle")
                pw.expect(
                    page.get_by_role("status").filter(has_text="운영 중 · 기록 가능")
                ).to_be_visible()
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()
