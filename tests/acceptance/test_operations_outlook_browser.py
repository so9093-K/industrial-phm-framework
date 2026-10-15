"""The condition outlook shows a vibration feature's margin to both limits and an AI briefing."""

from __future__ import annotations

from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.genai import outlook_answer
from industrial_phm.runtime import operations_web_outlook_briefing as briefing_runtime
from industrial_phm.runtime.operations_web_actions import execute_web_source_action
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.phm import ScriptedModel, analyze, deliver, phm_workspace


class _InProcessSupervisor:
    """Executes authorized actions the way the supervisor broker does, without IPC."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def execute(
        self, route: str, payload: dict[str, object], *, request_id: str | None = None
    ) -> dict[str, object]:
        return execute_web_source_action(self.root, route, payload)


@pytest.mark.parametrize("width", [390, 1280])
def test_margins_readings_evidence_and_a_checked_briefing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("prophet")
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal in range(1, 65):
        scale = 0.5 + 0.002 * (ordinal % 3) if ordinal <= 40 else 0.5 + 0.06 * (ordinal - 40)
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    good = {
        "summary": "최근 획득당 +0.067씩 오르고 있어 관리 상한 2.4까지의 여유가 줄고 있습니다.",
        "points": [{"text": "최근 획득당 +0.067씩 오릅니다.", "evidence": ["rate"]}],
    }
    # The first draft invents a margin; the user only sees the checked rewrite.
    model = ScriptedModel({**good, "summary": "관리 상한 2.4까지 777개 획득 남았습니다."}, good)
    monkeypatch.setattr(outlook_answer, "complete_json", model)
    monkeypatch.setattr(briefing_runtime, "_MANAGERS", {})
    root = workspace.root.resolve()
    server = create_operations_web_read_server(root, command_client=_InProcessSupervisor(root))  # type: ignore[arg-type]
    viewer = create_operations_web_read_server(root)
    threads = [Thread(target=s.serve_forever, daemon=True) for s in (server, viewer)]
    for thread in threads:
        thread.start()
    query = "?monitor_asset=bearing-a&forecast_threshold=2.4&forecast_end=3#forecast"
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/web/{query}")
                outlook = page.locator("#outlook")
                lead = outlook.locator(".outlook-lead")
                pw.expect(lead).to_contain_text("기준 구간의 범위를 계속 벗어나", timeout=30000)
                pw.expect(lead).to_contain_text("최근 획득당 +0.067씩")
                figures = outlook.locator(".outlook-figures")
                pw.expect(figures).to_contain_text("관리 상한 2.4까지")
                pw.expect(figures).to_contain_text("잔여수명 · 종료 기준 3")
                pw.expect(figures).to_contain_text("모델 기준 초과")
                details = page.locator("#outlook-evidence .outlook-details")
                pw.expect(details).to_contain_text("이상 탐지 모델")
                pw.expect(details).to_contain_text("처음 초과 #62")
                rows = page.locator("#outlook-more .outlook-scenarios tbody tr")
                pw.expect(rows).to_have_count(4)
                pw.expect(page.locator("#forecast-chart-section .forecast-chart")).to_be_visible(
                    timeout=30000
                )

                briefing = page.locator("#outlook-briefing")
                ask = briefing.get_by_role("button", name="기준까지 얼마나 남았어?")
                pw.expect(ask).to_be_enabled(timeout=10000)
                ask.click()
                answer = briefing.locator(".outlook-answer-summary")
                pw.expect(answer).to_have_text(good["summary"], timeout=30000)
                pw.expect(briefing.locator(".outlook-chip")).to_have_text(["변화 속도"])
                pw.expect(briefing.locator(".outlook-answer-source")).to_contain_text(
                    "수치는 계산 결과와 대조함"
                )
                assert "777" not in briefing.inner_text()
                # The rewrite was asked with the reason the draft failed.
                assert "'777'" in model.requests[1][-1]["content"]
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

                # A stored briefing of the same selection is there again after a reload.
                page.reload()
                pw.expect(answer).to_have_text(good["summary"], timeout=30000)

                # A Web without running operations shows the outlook but cannot ask.
                page.goto(f"http://127.0.0.1:{viewer.server_port}/web/{query}")
                pw.expect(lead).to_be_visible(timeout=30000)
                pw.expect(briefing.locator("#outlook-ask")).to_be_disabled()
                pw.expect(briefing).to_contain_text("운영이 실행 중이 아닌 화면입니다")
                assert not errors, errors
            finally:
                browser.close()
    finally:
        for running in (server, viewer):
            running.shutdown()
            running.server_close()
        for thread in threads:
            thread.join(timeout=10)
