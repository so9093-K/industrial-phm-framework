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
@pytest.mark.parametrize("part", ["primary", "ai", "different-input"])
def test_review_evidence_failures_and_other_input_are_not_shown_as_absent(
    tmp_path: Path, width: int, part: str
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "review-read")
    for ordinal, scale in enumerate((0.5, 0.6, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    root = workspace.root.resolve()
    requested = execute_web_source_action(
        root,
        "/api/v1/phm/reviews/request",
        {"binding_id": "anomaly-a", "position": 3, "explanation_id": None},
    )
    running = start_web(root, writer=True)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = _open(browser, width)
                broken = {"yes": True}

                def result(route: Any) -> None:
                    binding = parse_qs(urlsplit(route.request.url).query)["binding_id"][0]
                    if broken["yes"] and part == "primary" and binding == "anomaly-a":
                        route.fulfill(status=503, json={"error": "unavailable"})
                    elif broken["yes"] and part == "different-input" and binding == "anomaly-b":
                        response = route.fetch()
                        body = response.json()
                        body["step"]["input_reference"]["sha256"] = "f" * 64
                        route.fulfill(json=body)
                    else:
                        route.continue_()

                def explanation(route: Any) -> None:
                    if broken["yes"] and part == "ai":
                        route.fulfill(status=503, json={"error": "unavailable"})
                    else:
                        route.continue_()

                page.route("**/api/v1/phm/result?**", result)
                page.route("**/api/v1/phm/explanations?**", explanation)
                page.goto(
                    f"http://127.0.0.1:{running[0].server_port}/web/?page=maintenance"
                    f"&monitor_asset=bearing-a&finding_id={requested['finding_id']}"
                )
                detail = page.get_by_role("region", name="고른 검토 항목")
                retry = detail.get_by_role("button", name="판단 근거 다시 읽기")
                pw.expect(retry).to_be_visible()
                if part == "ai":
                    pw.expect(detail).to_contain_text(
                        "해설을 읽지 못했습니다. 해설이 없다는 뜻은 아닙니다."
                    )
                    pw.expect(detail.get_by_text("아직 없습니다.", exact=False)).to_have_count(0)
                if part == "different-input":
                    pw.expect(detail).to_contain_text("같은 원본의 다른 모델")
                    pw.expect(detail.locator(".grounds dt", has_text="다른 모델")).to_have_count(0)
                broken["yes"] = False
                retry.click()
                pw.expect(detail.locator(".grounds")).to_be_visible()
                pw.expect(retry).to_have_count(0)
                pw.expect(detail).to_contain_text("아직 없습니다. 설비 화면에서")
                pw.expect(detail.locator(".grounds dt", has_text="다른 모델")).to_have_count(1)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
            finally:
                browser.close()
    finally:
        stop_web(*running)


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
                # Which model and what it scored, read from the stored result.
                pw.expect(detail).to_contain_text("3번째 측정 · 점수")
                pw.expect(detail).to_contain_text("/ 기준 2")

                # The first response is lost after the server recorded the confirmation; the same
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
                # A structured decision is enough: no free-text memo is requested.
                assert detail.get_by_role("textbox").count() == 0
                pw.expect(detail.get_by_role("button", name="확인함으로 표시")).to_be_disabled()
                detail.get_by_role("radio", name="추가 점검 필요").check()
                detail.get_by_role("button", name="확인함으로 표시").click()
                pw.expect(detail.get_by_role("status").last).to_contain_text("다시 시도해도")
                assert detail.get_by_role("alert").count() == 0
                detail.get_by_role("button", name="확인함으로 표시").click()
                pw.expect(detail.get_by_role("status").last).to_have_text("검토 기록을 남겼습니다.")
                pw.expect(detail.locator(".events li")).to_have_count(1)
                pw.expect(detail.locator(".events li").first).to_contain_text(
                    "확인 · 추가 점검 필요"
                )
                assert len(writes) == 2 and writes[0] == writes[1]
                assert set(writes[0]) == {"finding_id", "action", "note", "event_id", "decision"}
                assert writes[0]["decision"] == "inspect"
                assert writes[0]["finding_id"] == finding
                assert writes[0]["note"] == ""
                events = JsonFindingReviewRepository(
                    workspace.maintenance_review_state_path
                ).list_events()
                assert [
                    (event.action.value, event.note, event.decision and event.decision.value)
                    for event in events
                ] == [("acknowledge", "", "inspect")]
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
                    "다른 창이나 요청에서 검토 상태가 변경됐습니다"
                )
                pw.expect(detail.locator(".badge")).to_have_text("검토 종료")
                assert detail.get_by_role("button", name="검토 종료").count() == 0
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
                pw.expect(view.locator(".events li")).to_have_count(2)
                assert view.get_by_role("button", name="확인함으로 표시").count() == 0
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


@pytest.mark.parametrize("width", [390, 1280])
def test_review_closing_defaults_to_newer_persisted_decision(
    tmp_path: Path, width: int
) -> None:
    """A concurrent acknowledgement must not leave an obsolete choice preselected."""
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "decision-reload")
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
    server, thread = start_web(root, writer=True)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = _open(browser, width)
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/?page=maintenance"
                    f"&monitor_asset=bearing-a&finding_id={finding}"
                )
                detail = page.get_by_role("region", name="고른 검토 항목")
                detail.get_by_role("radio", name="추가 점검 필요").check()
                execute_web_source_action(
                    root,
                    "/api/v1/reviews/action",
                    {
                        "finding_id": finding,
                        "action": "acknowledge",
                        "note": "",
                        "decision": "observe",
                    },
                )
                detail.get_by_role("button", name="확인함으로 표시").click()
                pw.expect(detail).to_contain_text("다른 창이나 요청에서 검토 상태가 변경됐습니다")
                pw.expect(detail.locator(".badge")).to_have_text("확인함")
                detail.get_by_role("button", name="검토 종료").click()
                confirm = detail.get_by_role("group", name="검토를 종료할까요?")
                pw.expect(confirm.get_by_role("radio", name="계속 관찰")).to_be_checked()
                pw.expect(confirm.get_by_role("radio", name="추가 점검 필요")).not_to_be_checked()
            finally:
                browser.close()
    finally:
        stop_web(server, thread)
