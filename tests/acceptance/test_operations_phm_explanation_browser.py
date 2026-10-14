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
                pw.expect(assistant.locator(".phm-comparison-details")).not_to_have_attribute(
                    "open", ""
                )
                page.locator("#anomaly-ask").click()
                pw.expect(assistant.get_by_label("분석 질문")).to_be_focused()
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
                flow = assistant.locator(".phm-range")
                pw.expect(
                    assistant.get_by_role(
                        "button", name="구간 전체에서 어떤 흐름을 보였어?", exact=True
                    )
                ).to_have_count(0)
                pw.expect(assistant.locator(".phm-question-scope")).to_contain_text(
                    "두 시점의 차이"
                )
                pw.expect(flow).to_contain_text("구간 흐름 · #1 → #4 · 분석 4개")
                pw.expect(flow.locator("tr").nth(1)).to_contain_text("모델 점수")
                pw.expect(flow.locator("tr").nth(1)).to_contain_text("기록 부족")
                related = card.locator(".phm-answer-related li")
                pw.expect(related).to_have_count(1)
                pw.expect(related).to_have_text("잔여수명 추정 · 34.41 → 4.223 · 입력 #4 한 입력")
                pw.expect(related).to_contain_text("입력 #4 한 입력")
                assert received[-1]["signal_comparison"]["previous_position"] == 1
                assert received[-1]["question"] == "수평 진동은 어떻게 달라졌나요?"
                assert received[-1]["signal_comparison"]["original_current"]["available"]
                assert "'때문'" in model.requests[-1][-1]["content"]
                # A suggested question continues the same comparison with the earlier answer.
                assistant.get_by_role("button", name="이전보다 어떤 측정값이 달라졌어?").click()
                pw.expect(card.locator(".phm-answer-question").first).to_have_text(
                    "이전보다 어떤 측정값이 달라졌어?"
                )
                pw.expect(card.locator(".phm-answer-thread summary")).to_have_text(
                    "이어서 답한 앞선 질문 1개"
                )
                sent = json.loads(model.requests[-1][1]["content"])
                assert sent["history"] == [
                    {"question": "수평 진동은 어떻게 달라졌나요?", "answer": answer["summary"]}
                ]
                signal.get_by_role("button", name="수평 진동 RMS").click()
                pw.expect(page.locator("#anomaly-signal")).to_have_value(json.dumps([rms]))
                pw.expect(panel.locator("h3")).to_contain_text("분석 #4 · ")
                original = assistant.locator(".phm-comparison-original")
                pw.expect(original.locator(".phm-original-context")).to_contain_text(
                    "선택한 특징: 수평 진동 RMS · 관련 원본: 수평 진동 파형 #4"
                )
                pw.expect(original.locator(".phm-original-selected")).to_have_count(1)
                pw.expect(original.locator(".phm-original-selected")).to_have_attribute(
                    "data-channel", "Horizontal_vibration_signals"
                )
                assistant.locator(".phm-comparison-details > summary").click()
                if width == 390:
                    table = assistant.locator(".phm-feature-comparison").first
                    assert table.locator("tr").nth(1).bounding_box()["width"] < width
                    pw.expect(table.locator(".phm-feature-span").first).to_be_visible()
                assistant.get_by_role("button", name="#1의 비교 원본 신호 확인").click()
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
                    "이전보다 어떤 측정값이 달라졌어?"
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


@pytest.mark.parametrize("width", [390, 1024, 1440])
def test_a_point_picked_in_the_range_becomes_what_the_question_is_about(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.5, 0.55, 0.5, 3.0, 3.1, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    model = ScriptedModel(
        {
            "summary": "#5의 이상 점수 수준 변화를 기준으로 보면 이후 이상 점수가 증가했습니다.",
            "observations": [],
            "next_signals": [],
            "next_step": "#5 전후의 원본 파형을 비교해 보세요.",
        }
    )
    monkeypatch.setattr(phm_answer, "complete_json", model)
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
                assistant = page.locator("#anomaly-assistant")
                assistant.get_by_label("비교 시점").select_option("1")
                flow = assistant.locator(".phm-range")
                pw.expect(
                    assistant.get_by_role(
                        "button", name="구간 전체에서 어떤 흐름을 보였어?", exact=True
                    )
                ).to_be_visible()
                pw.expect(
                    assistant.get_by_role(
                        "button", name="어느 지점에서 수준이 달라졌어?", exact=True
                    )
                ).to_be_visible()
                assistant.locator(".phm-comparison-details > summary").click()
                if width == 390:
                    row = flow.locator(".phm-range-table tr").nth(1)
                    cells = row.locator("td").all()
                    boxes = [cell.bounding_box() for cell in cells]
                    assert boxes[1]["y"] >= boxes[0]["y"] + boxes[0]["height"]
                    assert boxes[2]["y"] >= boxes[1]["y"] + boxes[1]["height"]
                    points = cells[2].get_by_role("button").all()
                    assert len(points) >= 2
                    a, b = [point.bounding_box() for point in points[:2]]
                    assert b["y"] >= a["y"] + a["height"]
                flow.get_by_role("button", name="수준 변화 #5 ↑").first.click()
                chip = assistant.locator(".phm-focus")
                pw.expect(chip).to_contain_text("질문 기준 지점 · #5 · 모델 점수 수준 변화")
                assistant.get_by_role("button", name="이 지점 전후로 무엇이 달라졌어?").click()
                card = assistant.locator(".phm-answer")
                pw.expect(card).to_contain_text("기준 지점 · #5")
                pw.expect(card.locator(".phm-ai-text")).to_contain_text("#5의 이상 점수 수준 변화")
                sent = json.loads(model.requests[-1][1]["content"])
                assert sent["focus"]["at"] == "#5"
                assert sent["focus"]["selected_series"] == "이상 점수"
                assert "이상 점수 수준이 이 지점에서 높아짐" in sent["focus"]["events"]
                # The same moment in another row must retain which signal was clicked.
                flow.locator("tr").filter(has_text="수평 진동 RMS").get_by_role(
                    "button"
                ).first.click()
                assistant.get_by_role("button", name="이 지점 전후로 무엇이 달라졌어?").click()
                pw.expect(card).to_contain_text("수평 진동 RMS")
                sent = json.loads(model.requests[-1][1]["content"])
                assert sent["focus"]["selected_series"] == "수평 진동 RMS"
                chip.get_by_role("button", name="질문 기준 지점 해제").click()
                pw.expect(chip).to_be_hidden()
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


@pytest.mark.parametrize("width", [390, 1024, 1440])
@pytest.mark.parametrize("session_failed", [False, True])
def test_read_only_header_opens_comparison_and_rul_explains_evaluation_scope(
    tmp_path: Path, width: int, session_failed: bool
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws")
    for position, scale in enumerate((0.5, 0.6), start=1):
        deliver(workspace, tmp_path / "waves", position, scale)
    analyze(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                if session_failed:
                    page.route("**/api/v1/session", lambda route: route.abort())
                for view in ("anomaly", "rul"):
                    page.goto(f"http://127.0.0.1:{server.server_port}/web/#{view}")
                    assistant = page.locator(f"#{view}-assistant")
                    action = page.locator(f"#{view}-ask")
                    pw.expect(action).to_be_enabled()
                    pw.expect(action).to_have_text("측정값 비교 보기")
                    action.click()
                    pw.expect(
                        assistant.locator(".phm-comparison-details > summary")
                    ).to_be_focused()
                    pw.expect(assistant.locator(".phm-feature-comparison").first).to_be_visible()
                    pw.expect(assistant.get_by_label("분석 질문")).not_to_be_visible()
                    pw.expect(assistant.get_by_label("분석 질문")).to_be_disabled()
                    pw.expect(assistant.get_by_role("button", name="AI에 질문")).to_have_count(0)
                    pw.expect(assistant.locator("h3")).to_have_text("측정값 비교")
                    if session_failed:
                        pw.expect(assistant).to_contain_text("질문 권한을 확인하지 못했습니다")
                    assistant.get_by_label("비교 시점").select_option("1")
                    pw.expect(action).to_have_text("측정값 비교 보기")
                    if view == "rul":
                        note = page.locator("#rul-validation-note")
                        pw.expect(note).to_contain_text("평균 절대 오차")
                        pw.expect(note).to_contain_text("오차 범위나 신뢰구간은 아닙니다")
                        pw.expect(page.locator("#rul-cards")).to_contain_text(
                            "모델 추정값의 변화이며 실제 경과 시간이 아닙니다"
                        )
                        cards = page.locator("#rul-cards").inner_text()
                        note.get_by_role("button", name="평가 대상·적용 범위 보기").click()
                        model = page.locator("#rul-model")
                        pw.expect(model).to_be_focused()
                        pw.expect(model).to_have_attribute("open", "")
                        pw.expect(model).to_contain_text("등록된 평가 대상")
                        pw.expect(model).to_contain_text("bearing-a")
                        pw.expect(model).to_contain_text("적용 운전 조건")
                        pw.expect(page.locator("#rul-cards")).to_have_text(
                            cards, use_inner_text=True
                        )
                        pw.expect(page.locator("#rul-position")).to_have_value("2")
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


@pytest.mark.parametrize("width", [390, 1024, 1440])
def test_rul_answer_keeps_the_selected_feature_and_original_channel_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws")
    for position, scale in enumerate((0.5, 0.6, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", position, scale)
    analyze(workspace)
    rms = "feature.Horizontal_vibration_signals.rms"
    monkeypatch.setattr(
        phm_answer,
        "complete_json",
        ScriptedModel(
            {
                "summary": "잔여 구간 추정이 감소했고 수평 진동 RMS가 증가했습니다.",
                "observations": [{"feature": rms, "change": "증가"}],
                "next_signals": [],
                "next_step": "수평 진동 파형을 확인해 보세요.",
            }
        ),
    )
    monkeypatch.setattr(explanation_runtime, "_MANAGERS", {})
    root = workspace.root.resolve()
    server = create_operations_web_read_server(root, command_client=_InProcessSupervisor(root))  # type: ignore[arg-type]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/web/#rul")
                action = page.locator("#rul-ask")
                pw.expect(action).to_have_text("이 변화 질문하기")
                action.click()
                assistant = page.locator("#rul-assistant")
                pw.expect(assistant.get_by_label("분석 질문")).to_be_focused()
                assistant.get_by_label("비교 시점").select_option("1")
                assistant.get_by_role("button", name="AI에 질문").click()
                assistant.locator(".phm-answer-signals").get_by_role(
                    "button", name="수평 진동 RMS"
                ).click()
                original = assistant.locator(".phm-comparison-original")
                pw.expect(original.locator(".phm-original-context")).to_have_text(
                    "선택한 특징: 수평 진동 RMS · 관련 원본: 수평 진동 파형 #4"
                )
                pw.expect(original).to_contain_text("파형에서 계산한 값")
                pw.expect(original.locator(".phm-original-selected")).to_have_count(1)
                pw.expect(original.locator(".phm-original-selected")).to_have_attribute(
                    "data-channel", "Horizontal_vibration_signals"
                )
                pw.expect(original.locator(".phm-wave")).to_have_count(2)
                pw.expect(page.locator("#rul-position")).to_have_value("4")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
