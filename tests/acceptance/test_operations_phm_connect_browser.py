"""An asset without a model gets one connected from its anomaly tab, and results follow."""

from __future__ import annotations

from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.runtime.operations_web_actions import execute_web_source_action
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.phm import analyze, deliver, phm_workspace


class _InProcessSupervisor:
    """Executes authorized actions the way the supervisor broker does, without IPC."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def execute(
        self, route: str, payload: dict[str, object], *, request_id: str | None = None
    ) -> dict[str, object]:
        return execute_web_source_action(self.root, route, payload)


@pytest.mark.parametrize("width", [390, 1440])
def test_connecting_a_model_from_the_anomaly_tab_shows_its_scores(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    for ordinal, scale in enumerate((0.5, 0.6, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    root = workspace.root.resolve()
    server = create_operations_web_read_server(root, command_client=_InProcessSupervisor(root))  # type: ignore[arg-type]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                base = f"http://127.0.0.1:{server.server_port}/web/?monitor_asset=bearing-a"
                page.goto(base + "#rul")
                rul = page.locator("#rul-connect")
                pw.expect(rul).to_contain_text("연결할 수 있는 RUL 모델")
                pw.expect(rul).to_contain_text("synthetic-rul-v1")

                page.goto(base + "#anomaly")
                panel = page.locator("#anomaly-connect")
                pw.expect(panel).to_contain_text("연결할 수 있는 이상 탐지 모델")
                pw.expect(panel).not_to_contain_text("synthetic-rul-v1")
                panel.get_by_role("button", name="이상 점수 모델 연결").click()
                pw.expect(page.locator("#anomaly-binding")).to_be_enabled()
                pw.expect(panel).to_be_empty()
                pw.expect(page.locator("#anomaly-state")).to_contain_text(
                    "아직 분석 결과가 없습니다"
                )

                analyze(workspace)
                pw.expect(page.locator("#anomaly-state")).to_contain_text("4개 step 분석")
                pw.expect(page.locator("#anomaly-cards > *").first).to_be_visible()
                assert errors == []
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
