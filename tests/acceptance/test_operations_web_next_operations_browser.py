"""The operations page reports services, connections and stores without claiming more."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_actions import execute_web_source_action
from tests.support.web_next import start_web, stop_web


def _registered_csv(root: Path) -> None:
    folder = root / "inputs"
    folder.mkdir()
    (folder / "phases.csv").write_text(
        "timestamp,phase-R,phase-S,phase-T\n"
        "2026-10-08T12:00:00+00:00,220.5,219.0,221.0\n"
        "2026-10-08T12:00:01+00:00,220.6,219.1,221.1\n",
        encoding="utf-8",
    )
    execute_web_source_action(
        root,
        "/api/v1/sources/file",
        {
            "source_id": "registered-file-01",
            "name": "Three phase file",
            "asset_id": "pump-01",
            "file_path": "inputs/phases.csv",
            "channel_columns": ["phase-R", "phase-S", "phase-T"],
            "measurement_point_id": "panel",
            "timestamp_column": "timestamp",
        },
    )


@pytest.mark.parametrize("width", [390, 1280])
def test_operations_page_separates_registration_receipt_and_service_state(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "plant")
    initialize_operations_workspace(workspace)
    root = workspace.root.resolve()
    _registered_csv(root)
    server, thread = start_web(root, writer=False)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page: Any = browser.new_page(
                    viewport={"width": width, "height": 900}, locale="ko-KR"
                )
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                base = f"http://127.0.0.1:{server.server_port}/web/?page=system"
                page.goto(base)
                pw.expect(page.get_by_role("heading", name="운영 관리", level=1)).to_be_visible()
                connections = page.get_by_role("region", name="등록한 연결")
                card = connections.get_by_role("article", name="Three phase file")
                pw.expect(card.locator(".badge")).to_have_text("파일 확인 대기")
                pw.expect(card).to_contain_text("CSV 파일 · 설비 pump-01")
                pw.expect(card.get_by_role("link", name="측정 신호 보기")).to_have_attribute(
                    "href", "/web/?page=assets&tab=signals&monitor_asset=pump-01"
                )
                # A view-only page shows the next step without offering to take it.
                pw.expect(card).to_contain_text("이 연결을 사용하면 데이터를 읽을 수 있습니다")
                assert card.get_by_role("button").count() == 0
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )

                # A file read is shown only after the server accepted it.
                execute_web_source_action(
                    root,
                    "/api/v1/sources/lifecycle",
                    {"source_id": "registered-file-01", "target_state": "active"},
                )
                execute_web_source_action(
                    root, "/api/v1/sources/file/receive", {"source_id": "registered-file-01"}
                )
                page.get_by_role("button", name="다시 불러오기").click()
                pw.expect(card.locator(".badge")).to_have_text("파일 읽기 확인됨")
                pw.expect(card).to_contain_text("사용 중")
                pw.expect(card).to_contain_text("원래 측정 시각")

                page.goto(base + "&section=status")
                services = page.get_by_role("region", name="실행 상태")
                # No supervisor runs in this test; nothing claims that it does.
                pw.expect(services).to_contain_text("모두 준비됐는지 확인되지 않습니다")
                pw.expect(services.get_by_role("listitem")).to_have_count(4)
                pw.expect(page.get_by_role("region", name="저장소 조회")).to_contain_text(
                    "저장소를 모두 읽었습니다"
                )
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )

                # The page that explains failures still opens when the store read fails.
                failing: Any = browser.new_page(
                    viewport={"width": width, "height": 900}, locale="ko-KR"
                )
                failing.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        status=503,
                        content_type="application/json",
                        body='{"error":"history_or_snapshot_unavailable"}',
                    ),
                )
                failing.goto(base + "&section=status")
                pw.expect(
                    failing.get_by_role("heading", name="저장소를 읽지 못했습니다")
                ).to_be_visible()
                failing.goto(base)
                pw.expect(failing.get_by_role("region", name="등록한 연결")).to_contain_text(
                    "Three phase file"
                )
                assert not errors, errors
            finally:
                browser.close()
    finally:
        stop_web(server, thread)
