"""A requested review of a stored model result is noted, acknowledged and kept exact."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from industrial_phm.application import JsonFindingReviewRepository
from industrial_phm.runtime.operations_web_actions import execute_web_source_action
from tests.support.phm import analyze, deliver, phm_workspace
from tests.support.web_next import asset_list, same_origin, start_web, stop_web


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
def test_model_result_review_is_written_once_and_opens_its_exact_result(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.6, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    root = workspace.root.resolve()
    requested = execute_web_source_action(
        root,
        "/api/v1/phm/reviews/request",
        {"binding_id": "anomaly-a", "position": 3, "explanation_id": None},
    )
    finding = requested["finding_id"]
    running = [start_web(root, writer=True), start_web(root, writer=False)]
    writer, viewer = running[0][0], running[1][0]
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = _open(browser, width)
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                writes: list[dict[str, Any]] = []
                page.on(
                    "request",
                    lambda request: (
                        writes.append(request.post_data_json)
                        if request.method == "POST" and request.url.endswith("/reviews/action")
                        else None
                    ),
                )
                page.goto(f"http://127.0.0.1:{writer.server_port}/web/?page=maintenance")
                queue = page.get_by_role("region", name="검토함")
                detail = page.get_by_role("region", name="고른 검토 항목")
                pw.expect(queue.get_by_role("listitem")).to_have_count(1)
                pw.expect(queue.get_by_role("listitem").first).to_contain_text(
                    "분석 결과 · 이상 탐지 모델 · 검토 대기"
                )
                pw.expect(detail.get_by_role("heading", level=2)).to_have_text(
                    "bearing-a · 이상 탐지 모델 결과"
                )
                pw.expect(detail.get_by_text("모델 입력 #3에서 계산한 점수")).to_be_visible()

                # The first response is lost after the server recorded the note; the same
                # click again is answered from that record instead of adding a second one.
                lost = {"pending": True}

                def lose_once(route: Any) -> None:
                    response = route.fetch(headers=same_origin(route))
                    if lost["pending"]:
                        lost["pending"] = False
                        route.fulfill(
                            status=503,
                            content_type="application/json",
                            # The server's own write error shape.
                            body=json.dumps({"error": {"code": "command_outcome_unknown"}}),
                        )
                        return
                    route.fulfill(response=response)

                page.route("**/api/v1/reviews/action", lose_once)
                detail.get_by_label("메모 (최대 1000자)").fill("베어링 하우징 진동 확인 예정")
                detail.get_by_role("button", name="메모 남기기").click()
                pw.expect(detail.get_by_role("status").last).to_contain_text("다시 시도해도")
                assert detail.get_by_role("alert").count() == 0
                detail.get_by_role("button", name="메모 남기기").click()
                pw.expect(detail.get_by_role("status").last).to_have_text("검토 기록을 남겼습니다.")
                pw.expect(detail.locator(".events li")).to_have_count(1)
                pw.expect(detail.locator(".events li").first).to_contain_text(
                    "메모 · 베어링 하우징 진동 확인 예정"
                )
                assert len(writes) == 2 and writes[0] == writes[1]
                assert set(writes[0]) == {"finding_id", "action", "note", "event_id"}
                assert writes[0]["finding_id"] == finding
                events = JsonFindingReviewRepository(
                    workspace.maintenance_review_state_path
                ).list_events()
                assert [event.action.value for event in events] == ["note"]

                detail.get_by_role("button", name="확인함으로 표시").click()
                pw.expect(detail.locator(".badge")).to_have_text("확인함")
                # Someone else closes it first; this screen reloads instead of overwriting.
                execute_web_source_action(
                    root,
                    "/api/v1/reviews/action",
                    {"finding_id": finding, "action": "close", "note": "현장 확인 완료"},
                )
                detail.get_by_role("button", name="검토 종료").click()
                confirm = detail.get_by_role("group", name="검토를 종료할까요?")
                pw.expect(confirm).to_be_focused()
                confirm.get_by_role("button", name="종료하기").click()
                pw.expect(detail.get_by_role("status").last).to_contain_text(
                    "다른 사람이 먼저 검토 상태를 바꿨습니다"
                )
                pw.expect(detail.locator(".badge")).to_have_text("검토 종료")
                assert detail.get_by_role("button", name="메모 남기기").count() == 0
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )

                # The link opens exactly the stored model result under review.
                link = detail.get_by_role("link", name="설비 화면에서 이 모델 결과 보기")
                query = parse_qs(urlsplit(link.get_attribute("href") or "").query)
                assert query["model_binding"] == ["anomaly-a"] and query["model_position"] == ["3"]
                link.click()
                pw.expect(page.get_by_role("heading", name="모델 이상 점수")).to_be_visible()
                pw.expect(page.get_by_label("측정 선택 (최근 64회)")).to_have_value("3")

                read_only = _open(browser, width)
                read_only.goto(
                    f"http://127.0.0.1:{viewer.server_port}/web/?page=maintenance"
                    f"&monitor_asset=bearing-a&finding_id={finding}"
                )
                view = read_only.get_by_role("region", name="고른 검토 항목")
                pw.expect(view.locator(".badge")).to_have_text("검토 종료")
                pw.expect(view.locator(".events li")).to_have_count(3)
                assert view.get_by_role("button", name="메모 남기기").count() == 0
                missing = _open(browser, width)
                missing.goto(
                    f"http://127.0.0.1:{viewer.server_port}/web/?page=maintenance"
                    "&monitor_asset=bearing-a&finding_id=finding-phm-unknown"
                )
                pw.expect(
                    missing.get_by_role("heading", name="검토 항목을 찾을 수 없습니다")
                ).to_be_visible()
                assert not errors, errors
            finally:
                browser.close()
    finally:
        for server, thread in running:
            stop_web(server, thread)
