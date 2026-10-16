"""The condition outlook shows a vibration feature's margin to both limits and an AI briefing."""

from __future__ import annotations

from pathlib import Path
from threading import Event, Thread
from typing import Any

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
                pw.expect(lead).to_contain_text("이후 값의", timeout=30000)
                pw.expect(lead).to_contain_text("%가 초기 비교 범위 밖")
                pw.expect(lead).to_contain_text("최근 획득당 +0.067씩")
                figures = outlook.locator(".outlook-figures")
                pw.expect(figures).to_contain_text("관리 상한 2.4까지")
                pw.expect(figures).to_contain_text("조건부 잔여수명 · 종료 기준 3")
                pw.expect(outlook.locator(".outlook-observed")).to_have_text("마지막 획득 #64")
                pw.expect(figures).to_contain_text("모델 기준 초과")
                # An explicit operator request captures server-recomputed facts, not UI numbers.
                archive = page.locator("#outlook-saved")
                save = archive.get_by_role("button", name="현재 전망을 검토 대상으로 저장")
                pw.expect(save).to_be_enabled(timeout=15000)
                pw.expect(archive).to_contain_text("아직 저장한 전망이 없습니다.")
                save.click()
                pw.expect(archive.locator(".outlook-saved-entry")).to_have_count(1, timeout=30000)
                pw.expect(archive).to_contain_text("확정 저장한 전망")
                archive.locator(".outlook-saved-evidence summary").first.click()
                pw.expect(archive).to_contain_text("당시 서버가 계산한 설명")
                pw.expect(archive).to_contain_text("당시 계산 조건")
                pw.expect(archive).to_contain_text("분석 근거 버전")
                pw.expect(archive).to_contain_text("같은 측정 내용")
                pw.expect(archive).to_contain_text("현재 저장된 측정 투영과 동일합니다")
                # A captured outlook has its own exact human-review subject, not a
                # fabricated file/phase analysis ID.
                archive.get_by_role("textbox", name="이 전망의 검토 메모").fill(
                    "최초 획득의 기준과 모델 입력 확인"
                )
                submitted_events = []

                def uncertain_review_response(route: Any) -> None:
                    submitted_events.append(route.request.post_data_json["event_id"])
                    if len(submitted_events) == 1:
                        route.fulfill(
                            status=503,
                            content_type="application/json",
                            body='{"error":"temporary"}',
                        )
                    else:
                        route.continue_()

                review_route = "**/api/v1/outlook/captures/review/action"
                page.route(review_route, uncertain_review_response)
                archive.get_by_role("button", name="메모 남기기").click()
                pw.expect(archive).to_contain_text("검토 결과를 확인하지 못했습니다")
                archive.get_by_role("button", name="메모 남기기").click()
                pw.expect(archive).to_contain_text("최초 획득의 기준과 모델 입력 확인")
                assert len(submitted_events) == 2
                assert submitted_events[0] == submitted_events[1]
                page.unroute(review_route, uncertain_review_response)
                archive.get_by_role("button", name="확인함으로 표시").click()
                pw.expect(archive).to_contain_text("담당자 검토 · 확인함")
                page.once("dialog", lambda dialog: dialog.accept())
                archive.get_by_role("button", name="검토 완료로 표시").click()
                pw.expect(archive).to_contain_text("담당자 검토 · 완료")
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
                chip = briefing.get_by_role("button", name="변화 속도의 사용한 사실 확인")
                pw.expect(chip).to_have_count(1)
                chip.click()
                pw.expect(briefing.locator(".outlook-answer-facts")).to_have_attribute("open", "")
                fact_row = (
                    briefing.locator(".outlook-answer-facts .forecast-summary>div")
                    .filter(has_text="변화 속도")
                    .first
                )
                assert fact_row.evaluate("(element) => document.activeElement === element")
                pw.expect(briefing.locator(".outlook-answer-facts")).to_contain_text("변화 속도")
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

                # A pending question survives a reload for the same evidence version.
                started, release = Event(), Event()

                def delayed(
                    provider: object,
                    messages: list[dict[str, str]],
                    schema: dict[str, object],
                    *,
                    max_tokens: int = 1200,
                ) -> dict[str, object]:
                    started.set()
                    if not release.wait(20):
                        raise TimeoutError("delayed model did not resume")
                    return good

                monkeypatch.setattr(outlook_answer, "complete_json", delayed)
                briefing.get_by_role("button", name="최근 어떤 변화가 있었어?").click()
                assert started.wait(timeout=10)
                page.reload()
                pw.expect(briefing.locator(".outlook-briefing-status")).to_contain_text(
                    "AI가 계산 결과를 읽고 있습니다.", timeout=30000
                )
                release.set()
                pw.expect(answer).to_have_text(good["summary"], timeout=30000)

                # A new acquisition must be reflected by the global refresh action,
                # rather than leaving an old forecast and an old AI briefing visible.
                deliver(workspace, tmp_path / "waves", 65, 2.2)
                analyze(workspace)
                page.locator("#refresh").click()
                pw.expect(outlook.locator(".outlook-observed")).to_have_text(
                    "마지막 획득 #65", timeout=30000
                )
                pw.expect(page.locator("#forecast-chart-section .forecast-chart")).to_be_visible(
                    timeout=30000
                )
                pw.expect(briefing.locator(".outlook-answer-summary")).to_have_count(0)
                pw.expect(archive).to_contain_text("새로운 측정 내용", timeout=30000)
                pw.expect(archive).to_contain_text("현재 계산 입력이 저장 당시와 다릅니다")
                pw.expect(archive).to_contain_text("#64 → #65")
                pw.expect(archive).to_contain_text("관리 기준: 이전")

                # A corrected historical observation keeps the same last acquisition.
                # A differing measurement fingerprint must force a coherent re-read.
                replies = {"count": 0}

                def mismatch_once(route: Any) -> None:
                    replies["count"] += 1
                    if replies["count"] == 1:
                        response = route.fetch()
                        body = response.json()
                        body["measurement_version"] = "0" * 64
                        route.fulfill(response=response, json=body)
                    else:
                        route.continue_()

                page.route("**/api/v1/outlook?*", mismatch_once)
                page.locator("#refresh").click()
                pw.expect(outlook.locator(".outlook-observed")).to_have_text(
                    "마지막 획득 #65", timeout=30000
                )
                pw.expect(page.locator("#forecast-chart-section .forecast-chart")).to_be_visible(
                    timeout=30000
                )
                assert replies["count"] >= 2
                page.unroute("**/api/v1/outlook?*", mismatch_once)

                # A failed half of the pair must never leave the other half
                # presented as a newly synchronized forecast.
                def unavailable(route: Any) -> None:
                    route.fulfill(
                        status=503,
                        content_type="application/json",
                        body='{"error":"outlook_store_unavailable"}',
                    )

                page.route("**/api/v1/outlook?*", unavailable)
                page.locator("#refresh").click()
                pw.expect(page.locator("#forecast-state")).to_contain_text(
                    "상태 전망을 계산하지 못했습니다", timeout=30000
                )
                pw.expect(page.locator("#forecast-chart-section")).to_be_hidden()
                pw.expect(outlook.locator(".outlook-figures")).to_have_count(0)
                assert not page.locator("#forecast-detail-metrics").inner_text()
                # Neither resize nor leaving and returning may resurrect the stale forecast.
                page.set_viewport_size({"width": width + 24, "height": 900})
                pw.expect(page.locator("#forecast-chart-section")).to_be_hidden()
                page.evaluate("""() => {
                    location.hash = '#signals';
                    location.hash = '#forecast';
                }""")
                pw.expect(page.locator("#forecast-chart-section")).to_be_hidden()
                page.unroute("**/api/v1/outlook?*", unavailable)
                page.locator("#refresh").click()
                pw.expect(outlook.locator(".outlook-observed")).to_have_text(
                    "마지막 획득 #65", timeout=30000
                )

                # Readable lower-limit and bounded-horizon wording on the same screen.
                page.evaluate(
                    """async () => {
                        const outlook = await import('/web/outlook.js');
                        const data = structuredClone(outlook.currentOutlook());
                        data.conditions.direction = 'lower';
                        const reading = data.scenarios.find(item => item.id === 'current');
                        reading.limits.management = {
                            state: 'possible', expected: null, earliest: 4, latest: null
                        };
                        reading.limits.end = {
                            state: 'beyond', expected: null, earliest: null, latest: null
                        };
                        outlook.renderOutlook(data);
                    }"""
                )
                pw.expect(figures).to_contain_text("범위 하단만 도달")
                pw.expect(figures).to_contain_text("기간 내 미도달")
                pw.expect(page.locator(".outlook-scenarios")).to_contain_text("범위 하단만")
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                # At 320px, each reading identifies its limit without horizontal scrolling.
                page.set_viewport_size({"width": 320, "height": 900})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                pw.expect(page.locator(".outlook-scenarios td[data-condition]")).not_to_have_count(
                    0
                )
                assert page.evaluate("""() => {
                    const links = document.querySelector('#outlook-more .forecast-explore-links');
                    const briefing = document.querySelector('#outlook-briefing');
                    return !!links && !!briefing &&
                        !!(links.compareDocumentPosition(briefing) &
                           Node.DOCUMENT_POSITION_FOLLOWING);
                }""")

                # The current transient calculation has its own exact, inspectable evidence.
                page.locator("#outlook-more").get_by_role(
                    "button", name="이 전망의 계산 근거 확인"
                ).click()
                pw.expect(page.locator("#forecast-settings")).to_have_attribute("open", "")
                pw.expect(page.locator("#outlook-evidence")).to_be_focused()
                pw.expect(page.locator("#outlook-evidence")).to_contain_text("계산 관측 내용 버전")
                pw.expect(page.locator("#outlook-evidence")).to_contain_text(
                    "별도 저장 분석 결과가 아닙니다"
                )
                # Other saved AnalysisRun/Evidence objects are NOT this computed outlook.
                page.locator("#outlook-more").get_by_role(
                    "link", name="이 설비의 별도 저장 분석·검토 기록"
                ).click()
                pw.expect(page.locator("#evidence")).to_be_visible(timeout=30000)
                assert page.evaluate("location.hash") == "#evidence"

                # The existing read-only web keeps AI writes disabled.
                # A Web without running operations shows the outlook but cannot ask.
                page.goto(f"http://127.0.0.1:{viewer.server_port}/web/{query}")
                pw.expect(lead).to_be_visible(timeout=30000)
                pw.expect(archive.locator(".outlook-saved-entry")).to_have_count(1, timeout=30000)
                pw.expect(archive).to_contain_text("담당자 검토 · 완료")
                pw.expect(archive).to_contain_text("최초 획득의 기준과 모델 입력 확인")
                pw.expect(
                    archive.get_by_role("button", name="현재 전망을 검토 대상으로 저장")
                ).to_be_disabled()
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
