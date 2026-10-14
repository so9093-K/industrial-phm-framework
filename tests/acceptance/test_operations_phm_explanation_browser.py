"""AI explanation and human review buttons work on a stored PHM result in a real browser."""

from __future__ import annotations

from pathlib import Path
from threading import Thread
from typing import Any

import pytest

from industrial_phm.runtime import operations_web_phm_explanation as explanation_runtime
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


@pytest.mark.parametrize("width", [390, 1024, 1440])
def test_explanation_is_marked_reference_text_and_review_moves_through_its_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.6, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)

    received = []

    def provider(context: dict[str, Any], _: object) -> str:
        received.append(context)
        return (
            "관측 사실\n점수가 임계값을 넘었습니다. 고장 확률 91.3%로 보입니다. "
            "설비는 정상 상태입니다."
        )

    monkeypatch.setattr(explanation_runtime, "generate_local_explanation", provider)
    monkeypatch.setattr(explanation_runtime, "_MANAGERS", {})
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
                page.goto(f"http://127.0.0.1:{server.server_port}/web/#anomaly")
                panel = page.locator("#anomaly-explanation")
                pw.expect(panel).to_contain_text("사람 검토")
                pw.expect(panel.get_by_role("button", name="검토 요청")).not_to_be_visible()
                pw.expect(page.locator("#anomaly-assistant")).to_be_visible()
                page.locator("#anomaly-review-options > summary").click()
                pw.expect(panel.get_by_role("button", name="검토 요청")).to_be_visible()
                pw.expect(panel.get_by_role("button", name="검토 확인")).to_have_count(0)
                assistant = page.locator("#anomaly-assistant")
                pw.expect(assistant).to_be_visible()
                assistant.get_by_label("비교 시점").select_option("1")
                assistant.get_by_label("분석 질문").fill("수평 진동은 어떻게 달라졌나요?")
                assistant.get_by_role("button", name="AI에 질문").click()
                pw.expect(assistant.locator(".phm-ai-text")).to_contain_text("임계값을 넘었습니다")
                pw.expect(assistant).to_contain_text("local-main")
                assert received[-1]["signal_comparison"]["previous_position"] == 1
                assert received[-1]["question"] == "수평 진동은 어떻게 달라졌나요?"
                assert received[-1]["signal_comparison"]["original_current"]["available"]
                pw.expect(assistant.locator(".phm-ai-warning")).to_contain_text("91.3")
                pw.expect(assistant.locator(".phm-ai-warning")).to_contain_text(
                    "판정 표현 경고: 설명이 '정상 상태'처럼"
                )
                pw.expect(assistant.locator(".phm-ai-warning")).to_be_visible()
                pw.expect(panel.locator("h3")).to_contain_text("분석 #4 · ")
                assistant.get_by_role("button", name="비교 시점의 원본 신호 보기").click()
                pw.expect(assistant.locator(".phm-comparison-original h4")).to_contain_text("#1")
                pw.expect(assistant.locator(".phm-comparison-original .phm-wave")).to_have_count(2)
                # An answer for the old comparison must disappear as soon as selection changes.
                assistant.get_by_label("비교 시점").select_option("2")
                pw.expect(assistant.locator(".phm-ai-text")).to_have_text("")
                assistant.get_by_role("button", name="AI에 질문").click()
                pw.expect(assistant.locator(".phm-ai-text")).to_contain_text("임계값을 넘었습니다")
                assert received[-1]["signal_comparison"]["previous_position"] == 2
                page.reload()
                pw.expect(assistant.get_by_label("비교 시점")).to_have_value("2")
                pw.expect(assistant.get_by_label("분석 질문")).to_have_value(
                    "수평 진동은 어떻게 달라졌나요?"
                )
                pw.expect(assistant.locator(".phm-ai-text")).to_contain_text("임계값을 넘었습니다")
                page.locator("#anomaly-review-options > summary").click()

                panel.get_by_role("button", name="검토 요청").click()
                pw.expect(panel.locator(".phm-review-history")).to_contain_text("검토 요청됨")
                pw.expect(panel.get_by_role("button", name="검토 요청")).to_have_count(0)
                pw.expect(panel.get_by_role("button", name="검토 확인")).to_be_visible()
                panel.get_by_label("검토 메모").first.fill("수평 진동 RMS 원본 확인")
                panel.get_by_role("button", name="검토 확인").click()
                pw.expect(panel.locator(".phm-review-history")).to_contain_text("검토 확인됨")
                pw.expect(panel.get_by_role("button", name="검토 확인")).to_have_count(0)
                pw.expect(panel.get_by_role("button", name="검토 종료")).to_be_visible()
                pw.expect(panel.locator(".phm-review-history")).to_contain_text("수평 진동 RMS")
                panel.get_by_role("button", name="검토 종료").click()
                pw.expect(panel.locator(".phm-review-history")).to_contain_text("검토 완료")
                pw.expect(panel.get_by_role("button", name="검토 종료")).to_have_count(0)
                pw.expect(panel.locator(".phm-review-status")).to_contain_text("검토 완료")
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (
                    "PHM review page overflows the viewport"
                )
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
