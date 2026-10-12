"""Users can find a starting action and separate research from workspace evidence."""

from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


@pytest.mark.parametrize("width", [1024, 1440])
def test_empty_workspace_start_routes_research_and_read_failures(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "empty")
    initialize_operations_workspace(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 800}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                base = f"http://127.0.0.1:{server.server_port}/web/"
                page.goto(base, wait_until="networkidle")
                pw.expect(page.locator("#workspace-state")).to_have_text("빈 작업공간")
                pw.expect(page.locator("#workspace-start")).to_be_visible()
                pw.expect(page.locator("#first-run")).to_be_hidden()
                pw.expect(page.locator("#connect")).to_be_hidden()
                pw.expect(page.locator("#operator-meaning")).to_be_hidden()
                for link in page.locator("#workspace-start a").all():
                    box = link.bounding_box()
                    assert box and box["y"] >= 0 and box["y"] + box["height"] <= 800
                page.get_by_role("link", name="기존 연구 결과 보기").click()
                pw.expect(page.locator("#view-title")).to_have_text("기존 연구 결과")
                pw.expect(page.locator("#workspace-start")).to_be_hidden()
                pw.expect(page.locator("#research-state")).to_contain_text("11건")
                result = page.locator(".research-result").filter(
                    has_text="xjtu-sy-lstm-autoencoder-fold-1-development-v1"
                )
                result.locator("summary").click()
                pw.expect(result).to_contain_text("원본 데이터는 함께 배포되지 않습니다")
                pw.expect(result).to_contain_text("Declared code revision")
                pw.expect(result).to_contain_text("Unsupported")
                assert page.locator("#asset-count").inner_text() == "0"
                assert page.locator("#analysis-count").inner_text() == "0"
                page.go_back(wait_until="networkidle")
                pw.expect(page.locator("#view-title")).to_have_text("설비 모니터링")
                page.get_by_role("link", name="실제 데이터 연결하기").click()
                pw.expect(page.locator("#view-title")).to_have_text("데이터 연결")
                pw.expect(page.locator("#file-form")).to_be_visible()
                pw.expect(page.locator("#monitor")).to_be_hidden()
                page.reload(wait_until="networkidle")
                pw.expect(page.locator("#view-title")).to_have_text("데이터 연결")
                page.locator('nav a[href="#monitor"]').click()
                page.route("**/api/v1/monitor", lambda route: route.abort())
                page.locator("#refresh").click()
                pw.expect(page.locator("#workspace-state")).to_contain_text("조회 미확인")
                pw.expect(page.locator("#workspace-start")).to_be_hidden()
                pw.expect(page.locator("#asset-count")).to_have_text("—")
                page.unroute("**/api/v1/monitor")
                page.locator("#refresh").click()
                pw.expect(page.locator("#workspace-state")).to_have_text("빈 작업공간")
                page.goto(base + "#unknown", wait_until="networkidle")
                pw.expect(page.locator("#view-title")).to_have_text("설비 모니터링")
                assert page.evaluate("location.hash") == "#monitor"
                assert not errors, errors
                assert not workspace.source_registry_path.exists()
                assert not workspace.history_catalog_path.exists()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()
