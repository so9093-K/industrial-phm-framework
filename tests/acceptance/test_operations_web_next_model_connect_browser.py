"""An anomaly detection model is connected from the asset's anomaly tab and then scores."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from tests.support.phm import analyze, deliver, phm_workspace
from tests.support.web_next import asset_list, start_web, stop_web


@pytest.mark.parametrize("width", [390, 1280])
def test_model_is_connected_to_the_assets_own_stream(tmp_path: Path, width: int) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    for ordinal, scale in enumerate((0.5, 0.6, 3.0), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    root = workspace.root.resolve()
    running = [start_web(root, writer=True), start_web(root, writer=False)]
    writer, viewer = running[0][0], running[1][0]
    address = "/web/?page=assets&tab=anomaly&method=model&monitor_asset=bearing-a"
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page: Any = browser.new_page(
                    viewport={"width": width, "height": 900}, locale="ko-KR"
                )
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        status=200, content_type="application/json", body=asset_list("bearing-a")
                    ),
                )
                page.goto(f"http://127.0.0.1:{writer.server_port}{address}")
                pw.expect(page.get_by_text("적용한 이상 탐지 모델이 없습니다")).to_be_visible()
                offer = page.get_by_role("region", name="연결할 수 있는 이상 탐지 모델")
                rows = offer.get_by_role("listitem")
                pw.expect(rows).to_have_count(2)
                pw.expect(rows.first).to_contain_text("저장된 입력부터 분석합니다")
                rows.filter(has_text="synthetic-rms-score-v1").get_by_role("button").click()
                pw.expect(page.get_by_text("연결했습니다")).to_be_visible()
                (binding,) = SqlitePhmAnalysisStore(workspace.phm_analysis_path).list_bindings()
                assert binding.asset_id == "bearing-a" and binding.source_id == "bench"
                # Until the runner has analyzed, the connection shows no score.
                pw.expect(page.get_by_text("아직 모델이 분석한 측정이 없습니다")).to_be_visible()
                pw.expect(page.get_by_text("다른 모델 연결 (1)")).to_be_visible()

                analyze(workspace)
                page.reload()
                pw.expect(page.get_by_label("측정 선택 (최근 64회)")).to_have_value("3")
                pw.expect(page.get_by_role("group", name="3번째 측정 모델 결과")).to_contain_text(
                    "기준 초과"
                )
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )

                observer: Any = browser.new_page(
                    viewport={"width": width, "height": 900}, locale="ko-KR"
                )
                observer.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        status=200, content_type="application/json", body=asset_list("bearing-a")
                    ),
                )
                observer.goto(f"http://127.0.0.1:{viewer.server_port}{address}")
                observer.get_by_text("다른 모델 연결 (1)").click()
                pw.expect(observer.get_by_text("synthetic-vertical-score-v1")).to_be_visible()
                assert observer.get_by_role("button", name="연결").count() == 0
                assert not errors, errors
            finally:
                browser.close()
    finally:
        for server, thread in running:
            stop_web(server, thread)
