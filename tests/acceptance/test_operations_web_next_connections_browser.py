"""One CSV file becomes stored measurements from 운영 관리, and each connection moves forward."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from industrial_phm.application import JsonSourceRepository
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from tests.support.web_next import same_origin, start_web, stop_web


def _csv(rows: int = 40) -> bytes:
    start = datetime(2026, 10, 11, 0, 0, tzinfo=UTC)
    lines = ["timestamp,current_a,voltage_v,label"]
    for index in range(rows):
        at = (start + timedelta(seconds=index)).isoformat()
        lines.append(f"{at},{1.5 + 0.01 * index:.2f},{220 + index % 3},run")
    return ("\n".join(lines) + "\n").encode()


@pytest.mark.parametrize("width", [390, 1280])
def test_csv_first_data_and_connection_steps(tmp_path: Path, width: int) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "plant")
    initialize_operations_workspace(workspace)
    root = workspace.root.resolve()
    running = [start_web(root, writer=True), start_web(root, writer=False)]
    writer, viewer = running[0][0], running[1][0]
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page: Any = browser.new_page(
                    viewport={"width": width, "height": 900}, locale="ko-KR"
                )
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{writer.server_port}/web-next/?page=system")
                sections = page.get_by_role("navigation", name="운영 관리")
                pw.expect(sections.get_by_role("link", name="데이터 연결")).to_have_attribute(
                    "aria-current", "page"
                )
                connections = page.get_by_role("region", name="등록한 연결")
                pw.expect(connections).to_contain_text("아직 등록한 데이터 연결이 없습니다")

                start = page.get_by_role("region", name="CSV 파일로 시작")
                start.get_by_label("CSV 파일 (UTF-8 · 20MiB 이하)").set_input_files(
                    files=[{"name": "pump.csv", "mimeType": "text/csv", "buffer": _csv()}]
                )
                preview = start.get_by_role("region", name="파일 미리보기")
                pw.expect(preview.get_by_label("시간 컬럼")).to_have_value("0")
                current = preview.get_by_role("checkbox", name="current_a", exact=True)
                pw.expect(current).to_be_checked()
                text_column = preview.get_by_role("checkbox", name="label · 숫자가 아닌 값 40개")
                pw.expect(text_column).to_be_disabled()
                summary = preview.get_by_role("table", name="측정 컬럼 요약")
                pw.expect(summary).to_contain_text("1.5")
                pw.expect(preview.get_by_role("img")).to_be_visible()
                pw.expect(preview).to_contain_text("측정 간격 · 보통 1초")

                start.get_by_label("설비 이름·번호").fill("pump-01")
                start.get_by_role("button", name="서버에서 점검 (저장 안 함)").click()
                pw.expect(start.get_by_text("점검 통과")).to_be_visible()
                assert JsonSourceRepository(workspace.source_registry_path).list_sources() == ()

                # The registration commits but its answer is lost; the retry continues from
                # the server's state instead of registering the file a second time.
                lost = {"pending": True}

                def lose_once(route: Any) -> None:
                    response = route.fetch(headers=same_origin(route))
                    if lost["pending"]:
                        lost["pending"] = False
                        route.fulfill(
                            status=503,
                            content_type="application/json",
                            body=json.dumps({"error": {"code": "command_outcome_unknown"}}),
                        )
                        return
                    route.fulfill(response=response)

                page.route("**/api/v1/sources/file/upload", lose_once)
                save = start.get_by_role("region", name="등록하고 이력 저장")
                save.get_by_role("button", name="등록하고 이력 저장").click()
                pw.expect(save.get_by_role("listitem").first).to_contain_text("결과 확인 필요")
                save.get_by_role("button", name="실패한 단계부터 다시 시도").click()
                pw.expect(save).to_contain_text("저장했습니다", timeout=30_000)
                for item in save.get_by_role("listitem").all():
                    pw.expect(item).to_contain_text("완료")
                registered = JsonSourceRepository(workspace.source_registry_path).list_sources()
                assert [source.asset_id for source in registered] == ["pump-01"]
                done = start.get_by_role("region", name="다음 할 일")
                pw.expect(done.get_by_role("heading", name="다음 할 일")).to_be_focused()
                signals = done.get_by_role("link", name="설비 화면에서 신호 보기")
                pw.expect(signals).to_have_attribute(
                    "href", "/web-next/?page=assets&tab=signals&monitor_asset=pump-01"
                )
                # Where the data arrived: what it supports now, and what it cannot support.
                options = done.get_by_role("region", name="이 데이터로 할 수 있는 분석")
                pw.expect(options.get_by_role("link", name="두 기간 비교 열기")).to_be_visible()
                pw.expect(options).to_contain_text("주파수 분석 — 원본 진동 파형 없음")

                card = connections.get_by_role("article", name="pump.csv")
                pw.expect(card.locator(".badge")).to_have_text("파일 읽기 확인됨")
                pw.expect(card).to_contain_text("측정 이력 저장됨 · 측정값 80개")
                card.get_by_role("button", name="신호 통계 분석").click()
                pw.expect(card.get_by_role("status")).to_contain_text("분석을 저장했습니다")
                pw.expect(card.get_by_role("link", name="분석 기록에서 보기")).to_be_visible()
                pw.expect(card).to_contain_text("저장된 분석이 있습니다")

                card.get_by_text("다른 작업").click()
                card.get_by_role("button", name="일시정지").click()
                confirm = card.get_by_role("group", name="일시정지할까요?")
                pw.expect(confirm).to_be_focused()
                confirm.get_by_role("button", name="일시정지").click()
                pw.expect(card).to_contain_text("일시정지", timeout=10_000)
                pw.expect(card.get_by_role("button", name="이 연결 사용하기")).to_be_visible()
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )

                sections.get_by_role("link", name="시스템 상태").click()
                pw.expect(page.get_by_role("region", name="실행 상태")).to_be_visible()
                assert "section=status" in page.url

                observer: Any = browser.new_page(
                    viewport={"width": width, "height": 900}, locale="ko-KR"
                )
                observer.goto(f"http://127.0.0.1:{viewer.server_port}/web-next/?page=system")
                watched = observer.get_by_role("region", name="등록한 연결")
                pw.expect(watched.get_by_role("article", name="pump.csv")).to_be_visible()
                pw.expect(watched).to_contain_text("보기 전용이라")
                assert watched.get_by_role("button").count() == 0
                assert not errors, errors
            finally:
                browser.close()
    finally:
        for server, thread in running:
            stop_web(server, thread)
