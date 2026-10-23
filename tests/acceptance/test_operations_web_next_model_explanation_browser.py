"""A stored model result is explained against an earlier one and handed to human review."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from industrial_phm.application.phm_explanation import PhmExplanationStore
from industrial_phm.genai import phm_answer
from industrial_phm.genai.analysis_explanation import AnalysisExplanationError
from industrial_phm.runtime import operations_web_phm_explanation as explanation_runtime
from tests.support.phm import ScriptedModel, analyze, deliver, phm_workspace
from tests.support.web_next import asset_list, expect_place, start_web, stop_web

RMS = "feature.Horizontal_vibration_signals.rms"
SUMMARY = "이상 점수가 증가했고 수평 진동 RMS가 함께 커졌습니다."


def _open(browser: Any, width: int) -> Any:
    page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
    page.route(
        "**/api/v1/monitor",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=asset_list("bearing-a")
        ),
    )
    return page


@pytest.mark.parametrize("width", [390, 1280])
def test_unavailable_model_answer_can_be_regenerated_without_continuing_the_fallback(
    tmp_path: Path, width: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "retry-ai")
    for ordinal, scale in enumerate((0.5, 0.6, 3.0), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)

    def unavailable(*args: Any, **kwargs: Any) -> Any:
        raise AnalysisExplanationError("temporary model outage")

    monkeypatch.setattr(phm_answer, "complete_json", unavailable)
    monkeypatch.setattr(explanation_runtime, "_MANAGERS", {})
    running = start_web(workspace.root.resolve(), writer=True)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = _open(browser, width)
                asked: list[dict[str, Any]] = []
                page.on(
                    "request",
                    lambda request: (
                        asked.append(request.post_data_json)
                        if request.method == "POST"
                        and request.url.endswith("/phm/explanations/request")
                        else None
                    ),
                )
                page.goto(
                    f"http://127.0.0.1:{running[0].server_port}/web/?page=assets&tab=anomaly"
                    "&method=model&monitor_asset=bearing-a&model_binding=anomaly-a&model_position=3"
                )
                explanation = page.get_by_role("region", name="AI 해설")
                explanation.get_by_text("직접 질문하기", exact=True).click()
                question = "두 측정 사이에 무엇이 달라졌는지 설명해 주세요."
                explanation.get_by_label("AI에게 물을 질문 (최대 600자)").fill(question)
                explanation.get_by_role("button", name="질문 보내기", exact=True).click()
                retry = explanation.get_by_role("button", name="AI로 다시 만들기")
                pw.expect(retry).to_be_visible(timeout=20_000)
                pw.expect(explanation).to_contain_text("AI 응답 없음 · 저장된 비교로 작성")
                model = ScriptedModel(
                    {
                        "summary": SUMMARY,
                        "observations": [{"feature": RMS, "change": "증가"}],
                        "next_signals": [],
                        "next_step": "두 측정의 원본 파형을 비교해 보세요.",
                    }
                )
                monkeypatch.setattr(phm_answer, "complete_json", model)
                retry.click()
                pw.expect(explanation.locator("p.summary")).to_have_text(SUMMARY, timeout=20_000)
                pw.expect(retry).to_have_count(0)
                assert len(asked) == 2
                assert asked[0] == asked[1]
                assert asked[1]["question"] == question and "continue_from" not in asked[1]
                records = PhmExplanationStore(workspace.phm_explanation_path).list_for(
                    "anomaly-a", 3
                )
                assert len(records) == 2 and all(item["status"] == "complete" for item in records)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
            finally:
                browser.close()
    finally:
        stop_web(*running)


@pytest.mark.parametrize("width", [390, 1280])
def test_model_result_explanation_and_review_request(
    tmp_path: Path, width: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.6, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    model = ScriptedModel(
        {
            "summary": SUMMARY,
            "observations": [{"feature": RMS, "change": "증가"}],
            "next_signals": [],
            "next_step": "두 측정의 원본 파형을 비교해 보세요.",
        }
    )
    monkeypatch.setattr(phm_answer, "complete_json", model)
    monkeypatch.setattr(explanation_runtime, "_MANAGERS", {})
    root = workspace.root.resolve()
    running = [start_web(root, writer=True), start_web(root, writer=False)]
    writer, viewer = running[0][0], running[1][0]
    address = "/web/?" + urlencode(
        {
            "page": "assets",
            "tab": "anomaly",
            "method": "model",
            "monitor_asset": "bearing-a",
            "model_binding": "anomaly-a",
            "model_position": "3",
        }
    )
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = _open(browser, width)
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                asked: list[dict[str, Any]] = []
                page.on(
                    "request",
                    lambda request: (
                        asked.append(request.post_data_json)
                        if request.method == "POST"
                        and request.url.endswith("/phm/explanations/request")
                        else None
                    ),
                )
                page.goto(f"http://127.0.0.1:{writer.server_port}{address}")
                expect_place(pw, page, "이상 징후", "모델 점수")
                pw.expect(page.get_by_label("측정 선택 (최근 64회)")).to_have_value("3")
                explanation = page.get_by_role("region", name="AI 해설")
                compare = explanation.get_by_label("비교할 이전 측정")
                pw.expect(compare).to_have_value("2")
                pw.expect(explanation).to_contain_text("아직 이 비교에 대한 해설이 없습니다")
                explanation.get_by_role("button", name="해설 만들기").click()
                pw.expect(explanation.get_by_text(SUMMARY)).to_be_visible(timeout=20000)
                pw.expect(explanation).to_contain_text("AI 해설 · 근거 확인됨 · local-main")
                table = explanation.get_by_role("table", name="해설이 짚은 측정값")
                row = table.get_by_role("row", name="수평 진동 RMS")
                pw.expect(row).to_contain_text("증가")
                pw.expect(explanation).to_contain_text("2번째 측정 → 3번째 측정")
                assert asked == [
                    {
                        "binding_id": "anomaly-a",
                        "position": 3,
                        "question": "이전 측정과 비교해 어떤 측정값이 함께 변했는지 설명해 주세요.",
                        "compare_position": 2,
                    }
                ]

                page.locator("details.optional-review > summary").click()
                review = page.get_by_role("region", name="사람 검토")
                pw.expect(review).to_contain_text("위의 AI 해설을 정비 검토함에 남깁니다")
                review.get_by_role("button", name="검토 요청").click()
                pw.expect(review).to_contain_text("정비 검토함에 남겼습니다")
                pw.expect(review).to_contain_text("정비 검토함에 있습니다 · 검토 대기")
                link = review.get_by_role("link", name="정비 검토함에서 보기")
                href = link.get_attribute("href") or ""
                finding = parse_qs(urlsplit(href).query)["finding_id"][0]
                (record,) = PhmExplanationStore(workspace.phm_explanation_path).list_for(
                    "anomaly-a", 3
                )
                assert record["finding_id"] == finding and record["status"] == "complete"
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )

                # Another comparison has no answer yet; the shown one never moves over.
                compare.select_option("1")
                pw.expect(explanation).to_contain_text("아직 이 비교에 대한 해설이 없습니다")
                assert explanation.get_by_text(SUMMARY).count() == 0
                compare.select_option("2")
                pw.expect(explanation.get_by_text(SUMMARY)).to_be_visible()

                link.click()
                detail = page.get_by_role("region", name="고른 검토 항목")
                pw.expect(detail.get_by_role("heading", level=2)).to_have_text(
                    "bearing-a · 이상 탐지 모델 결과"
                )

                observer = _open(browser, width)
                observer.goto(f"http://127.0.0.1:{viewer.server_port}{address}")
                watched = observer.get_by_role("region", name="AI 해설")
                pw.expect(watched.get_by_text(SUMMARY)).to_be_visible(timeout=20000)
                pw.expect(watched).to_contain_text("보기 전용이라 해설을 만들 수 없습니다")
                assert watched.get_by_role("button", name="해설 만들기").count() == 0
                observer.locator("details.optional-review > summary").click()
                pw.expect(observer.get_by_role("region", name="사람 검토")).to_contain_text(
                    "정비 검토함에 있습니다"
                )
                assert not errors, errors
            finally:
                browser.close()
    finally:
        for server, thread in running:
            stop_web(server, thread)


@pytest.mark.parametrize("width", [390, 1440])
def test_comparison_without_ai_and_range_point_question_keep_exact_scope(
    tmp_path: Path, width: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "flow")
    for ordinal, scale in enumerate((0.5, 0.5, 0.5, 3, 3, 3.1, 3.1, 3.2), 1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    model = ScriptedModel(
        {
            "summary": SUMMARY,
            "observations": [{"feature": RMS, "change": "증가"}],
            "next_signals": [],
            "next_step": "원본 파형을 비교해 보세요.",
        }
    )
    monkeypatch.setattr(phm_answer, "complete_json", model)
    monkeypatch.setattr(explanation_runtime, "_MANAGERS", {})
    running = [start_web(workspace.root, writer=False), start_web(workspace.root, writer=True)]
    suffix = (
        "/web/?page=assets&tab=anomaly&method=model&monitor_asset=bearing-a"
        "&model_binding=anomaly-a&model_position=8&model_compare=1"
    )
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                observer = _open(browser, width)
                observer.goto(f"http://127.0.0.1:{running[0][0].server_port}{suffix}")
                table = observer.get_by_role("table", name="측정 특징 비교")
                pw.expect(table.get_by_role("row", name="수평 진동 RMS")).to_be_visible()
                pw.expect(observer.get_by_role("table", name="구간 흐름")).to_be_visible()
                assert (
                    PhmExplanationStore(workspace.phm_explanation_path).list_for("anomaly-a", 8)
                    == []
                )
                assert observer.get_by_role("button", name="해설 만들기").count() == 0
                page = _open(browser, width)
                page.goto(f"http://127.0.0.1:{running[1][0].server_port}{suffix}")
                flow = page.get_by_role("table", name="구간 흐름")
                flow.get_by_role("row").first.get_by_role(
                    "button", name="가장 큰 변화", exact=False
                ).click()
                explanation = page.get_by_role("region", name="AI 해설")
                pw.expect(explanation).to_contain_text("질문 기준 지점 · 4번째 측정 · 모델 점수")
                pw.expect(
                    explanation.get_by_role("region", name="측정값 비교").get_by_role(
                        "heading", name="4번째 측정 원본 파형"
                    )
                ).to_be_visible()
                explanation.get_by_text("직접 질문하기", exact=True).click()
                explanation.get_by_role(
                    "button", name="이 지점 전후로 무엇이 달라졌어?", exact=True
                ).click()
                pw.expect(explanation.get_by_text("답변 기준 지점 · 4번째 측정")).to_be_visible(
                    timeout=20_000
                )
                (record,) = PhmExplanationStore(workspace.phm_explanation_path).list_for(
                    "anomaly-a", 8
                )
                assert record["context"]["focus"]["position"] == 4
                assert record["context"]["focus"]["series"] == "primary"
                assert record["context"]["signal_comparison"]["previous_position"] == 1
                explanation.get_by_role("button", name="질문 기준 지점 해제").click()
                assert explanation.get_by_text("답변 기준 지점 · 4번째 측정").count() == 0
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
            finally:
                browser.close()
    finally:
        for server, thread in running:
            stop_web(server, thread)


def test_recorded_acceptance_helpers_follow_current_review_ui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tools.phm.acceptance_common import Checks
    from tools.phm.acceptance_web import expect_saved_review, open_model, review_explained_result

    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.6, 3.0), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    monkeypatch.setattr(
        phm_answer,
        "complete_json",
        ScriptedModel(
            {
                "summary": SUMMARY,
                "observations": [{"feature": RMS, "change": "증가"}],
                "next_signals": [],
                "next_step": "두 측정의 원본 파형을 비교해 보세요.",
            }
        ),
    )
    monkeypatch.setattr(explanation_runtime, "_MANAGERS", {})
    running = start_web(workspace.root.resolve(), writer=True)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page()
                panel = open_model(
                    page, f"http://127.0.0.1:{running[0].server_port}/web/", "anomaly-a"
                )
                checks = Checks()
                answer = review_explained_result(page, panel, checks, "-helper", window=False)
                assert checks.passed
                expect_saved_review(page, answer)
            finally:
                browser.close()
    finally:
        stop_web(*running)
