"""Anomaly and RUL screens show stored model results, follow new steps, and keep their limits."""

from __future__ import annotations

from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from industrial_phm.runtime.operations_workspace import (
    OperationsWorkspace,
    initialize_operations_workspace,
)
from tests.support.phm import analyze, deliver, phm_workspace


@pytest.mark.parametrize("width", [1024, 1440])
def test_anomaly_and_rul_screens_follow_new_steps_with_linked_evidence(
    tmp_path: Path, width: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    from industrial_phm.application import phm_read

    monkeypatch.setattr(phm_read, "_SERIES_PAGE_SIZE", 2)
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws")
    waveforms = tmp_path / "waveforms"
    for ordinal, scale in enumerate((0.5, 0.6, 3.0, 3.2, 0.5, 0.5), start=1):
        deliver(workspace, waveforms, ordinal, scale)
    analyze(workspace)
    server = create_operations_web_read_server(workspace.root)
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
                pw.expect(page.locator("#view-title")).to_have_text("이상 탐지")
                pw.expect(page.locator("#anomaly-cards")).to_contain_text("최신 이상 점수")
                pw.expect(page.locator("#anomaly-cards")).to_contain_text("1개")
                pw.expect(page.locator("#anomaly-replay")).to_be_visible()
                pw.expect(page.locator("#anomaly-state")).to_contain_text(
                    "고장 확률이나 진단이 아닙니다"
                )
                pw.expect(page.locator("#anomaly-score-chart .reference-line")).to_have_count(1)
                pw.expect(page.locator("#anomaly-score-chart .phm-interval")).to_have_count(1)
                assert page.locator("#anomaly-feature-chart .phm-svg").count() >= 2
                pw.expect(page.locator("#anomaly-freshness")).to_contain_text("최신 분석 #6")

                page.locator("#anomaly-intervals button").first.click()
                pw.expect(page.locator("#anomaly-score-chart button")).to_have_text(
                    "전체 기간 보기"
                )
                pw.expect(page.locator("#anomaly-detail")).to_contain_text("입력과 모델 출력")
                pw.expect(page.locator("#anomaly-detail .phm-wave")).to_have_count(2)
                pw.expect(page.locator("#anomaly-detail")).to_contain_text(
                    "변수별 기여도를 제공하지 않습니다"
                )
                # The selected interval moves every chart to the same range.
                focused = page.locator(
                    "#anomaly-feature-chart .phm-focus, #anomaly-score-chart .phm-focus"
                )
                assert (
                    focused.count() == 1 + page.locator("#anomaly-feature-chart .phm-svg").count()
                )

                deliver(workspace, waveforms, 7, 0.4)
                analyze(workspace)
                pw.expect(page.locator("#anomaly-freshness")).to_contain_text(
                    "최신 분석 #7", timeout=10_000
                )

                page.locator('a[href="#rul"]').click()
                pw.expect(page.locator("#view-title")).to_have_text("RUL 모니터링")
                pw.expect(page.locator("#rul-cards")).to_contain_text("마지막 RUL 추정")
                pw.expect(page.locator("#rul-cards")).to_contain_text("획득 간격")
                pw.expect(page.locator("#rul-cards")).to_contain_text("이 설비 검증 MAE 10")
                pw.expect(page.locator("#rul-state")).to_contain_text("물리 고장 시각 아님")
                pw.expect(page.locator("#rul-state")).to_contain_text("신뢰구간은 검증되지 않아")
                pw.expect(page.locator("#rul-chart .condition-curve")).to_be_visible()
                pw.expect(page.locator("#rul-recent tr")).to_have_count(8)
                page.locator("#rul-model summary").click()
                pw.expect(page.locator("#rul-model")).to_contain_text("synthetic-test-evidence")
                page.locator('a[href="#anomaly"]').click()
                pw.expect(page.locator("#anomaly-cards")).to_contain_text("최신 이상 점수")
                page.route(
                    "**/api/v1/phm/series?*",
                    lambda route: route.fulfill(status=503, json={"error": "test-read-failed"}),
                )
                pw.expect(page.locator("#anomaly-state")).to_contain_text(
                    "읽지 못했습니다", timeout=10_000
                )
                for selector in (
                    "#anomaly-detail",
                    "#anomaly-features",
                    "#anomaly-cards",
                    "#anomaly-score-chart",
                ):
                    pw.expect(page.locator(selector + ">*")).to_have_count(0)
                pw.expect(page.locator("#anomaly-freshness")).to_be_empty()
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def test_phm_screens_explain_missing_models_instead_of_inventing_results(tmp_path: Path) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "empty")
    initialize_operations_workspace(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900}, locale="ko-KR")
                page.goto(f"http://127.0.0.1:{server.server_port}/web/#anomaly")
                pw.expect(page.locator("#anomaly-state")).to_contain_text("연결된 설비가 없습니다")
                pw.expect(page.locator("#anomaly-cards>*")).to_have_count(0)
                page.goto(f"http://127.0.0.1:{server.server_port}/web/#rul")
                pw.expect(page.locator("#rul-state")).to_contain_text(
                    "근거가 없는 설비에는 표시하지 않습니다"
                )
                pw.expect(page.locator("#rul-chart>*")).to_have_count(0)
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
