"""AI explanation and human review buttons work on a stored PHM result in a real browser."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from typing import Any

import pytest

from industrial_phm.genai import phm_answer
from industrial_phm.runtime import operations_web_phm_explanation as explanation_runtime
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


@pytest.mark.parametrize("width", [390, 1024, 1440])
def test_question_gets_a_checked_answer_linked_to_signals_and_review_moves_through_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.6, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)

    rms = "feature.Horizontal_vibration_signals.rms"
    answer = {
        "summary": "이상 점수가 증가했고 수평 진동 RMS가 함께 커졌습니다.",
        "observations": [{"feature": rms, "change": "증가"}],
        "next_signals": ["feature.Horizontal_vibration_signals.peak_to_peak"],
        "next_step": "두 시점의 원본 파형에서 수평 진동의 진폭을 비교해 보세요.",
    }
    # The first draft overstates two results; the user only sees the checked rewrite.
    model = ScriptedModel(
        {
            **answer,
            "summary": "고장 확률 91.3%입니다. 수평 진동이 커졌기 때문에 점수가 올랐습니다.",
        },
        answer,
    )
    monkeypatch.setattr(phm_answer, "complete_json", model)
    received: list[dict[str, Any]] = []
    grounded = explanation_runtime.generate_grounded_answer

    def recording(context: dict[str, Any], provider: object) -> dict[str, Any]:
        received.append(context)
        return grounded(context, provider)  # type: ignore[arg-type]

    monkeypatch.setattr(explanation_runtime, "generate_grounded_answer", recording)
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
                card = assistant.locator(".phm-answer")
                pw.expect(card.locator(".phm-ai-text")).to_have_text(answer["summary"])
                pw.expect(assistant).to_contain_text("local-main")
                pw.expect(card).to_contain_text("수평 진동은 어떻게 달라졌나요?")
                pw.expect(card).not_to_contain_text("91.3")
                signal = card.locator(".phm-answer-signals li")
                pw.expect(signal).to_have_count(1)
                pw.expect(signal).to_contain_text("수평 진동 RMS")
                pw.expect(signal).to_contain_text("↑ 증가")
                pw.expect(signal).to_contain_text("%")
                pw.expect(card).to_contain_text("수평 진동의 진폭을 비교")
                mentioned = assistant.locator(".phm-comparison tr.phm-ai-mentioned")
                pw.expect(mentioned).to_have_count(1)
                pw.expect(mentioned.first).to_contain_text("수평 진동 RMS")
                assert received[-1]["signal_comparison"]["previous_position"] == 1
                assert received[-1]["question"] == "수평 진동은 어떻게 달라졌나요?"
                assert received[-1]["signal_comparison"]["original_current"]["available"]
                assert "'때문'" in model.requests[-1][-1]["content"]
                signal.get_by_role("button", name="수평 진동 RMS").click()
                pw.expect(page.locator("#anomaly-signal")).to_have_value(json.dumps([rms]))
                pw.expect(panel.locator("h3")).to_contain_text("분석 #4 · ")
                assistant.get_by_role("button", name="비교 시점의 원본 신호 보기").click()
                pw.expect(assistant.locator(".phm-comparison-original h4")).to_contain_text("#1")
                pw.expect(assistant.locator(".phm-comparison-original .phm-wave")).to_have_count(2)
                # An answer for the old comparison must disappear as soon as selection changes.
                assistant.get_by_label("비교 시점").select_option("2")
                pw.expect(assistant.locator(".phm-answer")).to_be_empty()
                assistant.get_by_role("button", name="AI에 질문").click()
                pw.expect(assistant.locator(".phm-ai-text")).to_have_text(answer["summary"])
                assert received[-1]["signal_comparison"]["previous_position"] == 2
                page.reload()
                pw.expect(assistant.get_by_label("비교 시점")).to_have_value("2")
                pw.expect(assistant.get_by_label("분석 질문")).to_have_value(
                    "수평 진동은 어떻게 달라졌나요?"
                )
                pw.expect(assistant.locator(".phm-ai-text")).to_have_text(answer["summary"])
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
