from __future__ import annotations

import re
from datetime import timedelta
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.application.observation_window_sqlite import SqliteObservationWindowRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.phm_runner import PackageCache, run_window_bindings
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.electrical_phm import electrical_window, electrical_workspace
from tests.support.window_analysis import START


@pytest.mark.parametrize("width", [1024, 1440])
def test_electrical_phm_has_linked_raw_signals_residual_contributions_and_live_refresh(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = electrical_workspace(tmp_path / "ws")
    windows = SqliteObservationWindowRepository(workspace.window_state_path)
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    for i, current in enumerate((10.0, 20.0, 20.0)):
        windows.record_window(electrical_window(f"w{i}", START + timedelta(minutes=i * 5), current))
    run_window_bindings(store, windows, PackageCache(workspace.models_path))
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/web/#anomaly")
                pw.expect(page.locator("#anomaly-cards")).to_contain_text("최신 이상 점수")
                pw.expect(page.locator("#anomaly-asset-title")).to_contain_text("pump-1")
                pw.expect(page.locator("#anomaly-cards")).not_to_contain_text("학습 범위")
                pw.expect(page.locator("#anomaly-score-chart .condition-curve")).to_be_visible()
                assert page.locator("#anomaly-score-chart").evaluate(
                    "(e) => (e.compareDocumentPosition("
                    + "document.getElementById('anomaly-feature-chart')) "
                    + "& Node.DOCUMENT_POSITION_FOLLOWING) !== 0"
                )
                pw.expect(page.locator("#anomaly-freshness")).to_contain_text("최신 수신")
                page.locator("#anomaly-intervals button").first.click()
                pw.expect(page.locator("#anomaly-detail")).to_contain_text("특징별 잔차 기여")
                # A window is named by its event time, not by its internal ordering key.
                pw.expect(page.locator("#anomaly-explanation h3")).to_have_text(
                    re.compile(r"^분석 윈도우 \d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC · AI 설명")
                )
                pw.expect(page.locator("#anomaly-detail .phm-raw svg")).to_have_count(7)
                assert (
                    page.locator("#anomaly-score-chart .axis").evaluate(
                        "e => getComputedStyle(e).fill"
                    )
                    == "none"
                )
                pw.expect(page.locator("#anomaly-features")).to_contain_text("R상 평균 전류 · A")
                pw.expect(page.locator("#notice")).not_to_be_visible()
                pw.expect(page.locator("#anomaly-detail")).to_contain_text("관측 5개")
                page.get_by_label("원본 신호 표시 방식").select_option("relative")
                pw.expect(page.locator("#anomaly-detail .phm-raw")).to_contain_text(
                    "첫 유효 값이 0"
                )
                pw.expect(page.locator("#anomaly-detail .phm-raw svg")).to_have_count(7)
                windows.record_window(electrical_window("w3", START + timedelta(minutes=15), 10.0))
                run_window_bindings(store, windows, PackageCache(workspace.models_path))
                page.locator("#refresh").click()
                pw.expect(page.locator("#anomaly-state")).to_contain_text(
                    "4개 step 분석", timeout=10_000
                )
                windows.record_window(
                    electrical_window(
                        "too-short", START + timedelta(minutes=20), duration_minutes=1
                    )
                )
                run_window_bindings(store, windows, PackageCache(workspace.models_path))
                pw.expect(page.locator("#anomaly-state")).to_contain_text(
                    "최근 입력은 분석되지 않았습니다", timeout=10_000
                )
                pw.expect(page.locator("#anomaly-freshness")).to_contain_text("입력 조건 불충족")
                page.locator('a[href="#rul"]').click()
                pw.expect(page.locator("#rul-state")).to_contain_text(
                    "근거가 없는 설비에는 표시하지 않습니다"
                )
                pw.expect(page.locator("#rul-cards>*")).to_have_count(0)
                assert not errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
