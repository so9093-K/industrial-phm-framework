"""The analysis records screen shows stored results and hands one to human review."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from industrial_phm.application import (
    JsonOperationalFindingRepository,
    SqlitePhaseUnbalanceRepository,
)
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from tests.support.web_next import start_web, stop_web
from tests.support.window_analysis import phase_unbalance_analysis


@pytest.mark.parametrize("width", [390, 1280])
def test_stored_analysis_is_listed_and_review_requested_once(tmp_path: Path, width: int) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "plant")
    initialize_operations_workspace(workspace)
    analysis = phase_unbalance_analysis()
    SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path).record(analysis)
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
                page.goto(f"http://127.0.0.1:{writer.server_port}/web/?page=investigations")
                pw.expect(page.get_by_role("heading", name="분석 기록", level=1)).to_be_visible()
                results = page.get_by_role("region", name="분석 결과")
                record = results.get_by_role("article", name="3상 불평형 분석 · motor-7")
                assert record.locator(".badge").count() == 0
                pw.expect(record.get_by_role("table", name="3상 불평형률 (%)")).to_be_visible()
                pw.expect(record).to_contain_text("데이터 출처 site-opcua")
                pw.expect(record.get_by_text(analysis.run.analysis_run_id)).to_be_hidden()
                pw.expect(page.get_by_role("region", name="적용한 이상 탐지 모델")).to_contain_text(
                    "적용한 이상 탐지 모델이 없습니다"
                )
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )

                # An unavailable optional review lookup must not be mistaken for no prior record.
                page.route(
                    "**/api/v1/reviews?*",
                    lambda route: route.fulfill(status=503, body="{}"),
                )
                record.locator("details.optional-review > summary").click()
                pw.expect(record.get_by_text("기록이 없다는 뜻은 아닙니다.")).to_be_visible()
                assert record.get_by_role("button", name="검토 요청").count() == 0
                page.unroute("**/api/v1/reviews?*")
                # A bounded response is not proof that an older review is absent.
                page.route(
                    "**/api/v1/reviews?*",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body='{"schema_version":1,"asset_id":"motor-7",'
                        '"meaning":"human-review-records-not-maintenance-or-diagnosis",'
                        '"reviews":{"items":[],"total":101,"truncated":true}}',
                    ),
                )
                record.get_by_role("button", name="다시 확인").click()
                pw.expect(
                    record.get_by_text("이전 기록이 없다고 판단하지 않습니다.")
                ).to_be_visible()
                assert record.get_by_role("button", name="검토 요청").count() == 0
                page.unroute("**/api/v1/reviews?*")
                record.get_by_role("button", name="다시 확인").click()
                pw.expect(record.get_by_role("button", name="검토 요청")).to_be_enabled()
                record.get_by_role("button", name="검토 요청").click()
                link = record.get_by_role("link", name="정비 검토함에서 보기")
                pw.expect(link).to_be_visible()
                pw.expect(record.locator(".badge")).to_have_text("검토 대기")
                (finding,) = JsonOperationalFindingRepository(
                    workspace.finding_state_path
                ).list_findings()
                assert finding.analysis_run_id == analysis.run.analysis_run_id
                assert finding.evidence_refs == (analysis.evidence.evidence_id,)
                assert f"finding_id={finding.finding_id}" in (link.get_attribute("href") or "")

                link.click()
                detail = page.get_by_role("region", name="고른 검토 항목")
                pw.expect(detail.get_by_role("heading", level=2)).to_have_text(
                    "motor-7 · 3상 불평형 분석"
                )
                pw.expect(detail.locator(".evidence li").first).to_contain_text(
                    "데이터 출처 site-opcua"
                )

                observer: Any = browser.new_page(
                    viewport={"width": width, "height": 900}, locale="ko-KR"
                )
                observer.goto(
                    f"http://127.0.0.1:{viewer.server_port}/web/?page=investigations"
                    "&monitor_asset=motor-7"
                )
                watched = observer.get_by_role("article", name="3상 불평형 분석 · motor-7")
                pw.expect(watched.locator(".badge")).to_have_text("검토 대기")
                pw.expect(observer.get_by_label("설비")).to_have_value("motor-7")
                assert watched.get_by_role("button", name="검토 요청").count() == 0
                observer.get_by_label("설비").select_option("")
                assert "monitor_asset" not in observer.url
                assert not errors, errors
            finally:
                browser.close()
    finally:
        for server, thread in running:
            stop_web(server, thread)
