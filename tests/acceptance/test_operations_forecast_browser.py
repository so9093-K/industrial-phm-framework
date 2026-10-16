"""The outlook tab measures a stored signal's change, its margin to set limits, and its forecast."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.phm import analyze, deliver, phm_workspace

BASE = datetime(2026, 10, 14, tzinfo=UTC)
# The forecast's own numbers, folded with its settings under the outlook.
METRICS = "#forecast-detail-metrics > .forecast-summary"


@pytest.mark.parametrize("width", [390, 1280])
def test_a_stored_signal_is_forecast_with_its_level_and_its_own_check(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    pytest.importorskip("prophet")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    ).append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:motor:{'c' * 64}:{index}",
                source_id="motor-file",
                asset_id="motor-01",
                channel_id="current",
                source_file="motor.csv",
                source_sha256="c" * 64,
                source_size_bytes=10,
                sample_index=index,
                event_at=BASE + timedelta(minutes=index),
                value=10.0 + 0.02 * index,
                source_metadata_json='{"binding":{"definition":{"unit":"A"}}}',
            )
            for index in range(180)
        ),
        batch_id="motor",
    )
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
                base = f"http://127.0.0.1:{server.server_port}/web/?monitor_asset=motor-01"
                # From the overview's shortcuts straight to the forecast of the same asset.
                page.goto(base + "#monitor")
                page.locator("#asset-capabilities").get_by_role(
                    "button", name="상태 전망 열기"
                ).click()
                panel = page.locator("#forecast")
                pw.expect(panel.locator(".forecast-chart")).to_be_visible(timeout=30000)
                # Read the actual values without guessing from paths and the legend.
                pw.expect(panel.locator(".forecast-chart-reading")).to_contain_text("마지막 실측")
                pw.expect(panel.locator(".forecast-chart-reading")).to_contain_text(
                    "중심 예측 종료"
                )
                pw.expect(panel.locator(".forecast-interval-note")).to_contain_text(
                    "고장 확률을 뜻하지 않습니다"
                )
                table = panel.locator(".forecast-reading-table")
                table.locator("summary").click()
                pw.expect(table.locator("tbody tr")).to_have_count(3)
                pw.expect(table).to_contain_text("마지막 실측")
                pw.expect(table).to_contain_text("예측 종료")
                table.locator("summary").focus()
                page.set_viewport_size({"width": width + 12, "height": 900})
                pw.expect(table).to_have_attribute("open", "")
                pw.expect(table.locator("summary")).to_be_focused()
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                # The forecast's own numbers sit with the settings, folded under the outlook.
                summary = panel.locator("#forecast-detail-metrics > .forecast-summary")
                pw.expect(summary).to_contain_text("예측 종료값")
                pw.expect(summary).to_contain_text("마지막 측정")
                pw.expect(summary).to_contain_text("1시간 뒤")
                pw.expect(summary).to_contain_text("과거 자료로 확인")
                outlook = panel.locator("#outlook")
                figures = outlook.locator(".outlook-figures")
                pw.expect(figures).to_contain_text("기준 대비 변화", timeout=30000)
                pw.expect(figures).to_contain_text("관리·종료 기준을 입력하면 계산")
                details = panel.locator("#outlook-evidence .outlook-details")
                pw.expect(details).to_contain_text("변화 속도")
                pw.expect(details).to_contain_text("초기 비교 범위 이탈")
                pw.expect(panel.get_by_role("button", name="24시간")).to_be_disabled()
                pw.expect(panel.get_by_role("button", name="1시간")).to_have_attribute(
                    "aria-pressed", "true"
                )

                panel.get_by_label("관리 기준 (선택)").fill("14.3")
                panel.get_by_label("종료 기준 (선택)").fill("15")
                panel.get_by_role("button", name="기준 적용").click()
                # The margin is searched past the chart's horizon: 0.02 A a minute from 13.58 A.
                pw.expect(figures).to_contain_text("관리 상한 14.3까지", timeout=30000)
                pw.expect(figures).to_contain_text("조건부 잔여수명 · 종료 기준 15")
                pw.expect(figures).to_contain_text("분 뒤")
                pw.expect(outlook.locator(".outlook-lead")).to_contain_text("읽는 방법에 따라")
                pw.expect(panel.locator(".outlook-scenarios tbody tr")).to_have_count(4)
                scenarios = panel.locator(".outlook-scenarios")
                pw.expect(scenarios).to_contain_text("최근 변화 속도 유지")
                pw.expect(panel.locator("line.forecast-threshold")).to_have_count(1)
                assert "forecast_threshold=14.3" in page.url
                assert "forecast_end=15" in page.url
                panel.locator("#forecast-settings > summary").click()
                panel.get_by_label("추세 민감도 (0.001-0.5)").fill("0.1")
                panel.get_by_role("button", name="설정 적용").click()
                pw.expect(panel.locator("#forecast-detail-metrics")).to_contain_text(
                    "추세 민감도 0.1", timeout=30000
                )
                panel.get_by_label("최근 학습 획득·측정 수 (선택)").fill("100")
                panel.get_by_role("button", name="설정 적용").click()
                pw.expect(
                    panel.get_by_role("button", name="1시간", exact=True, include_hidden=True)
                ).to_be_disabled()
                pw.expect(
                    panel.get_by_role("button", name="24시간", exact=True, include_hidden=True)
                ).to_be_disabled()
                pw.expect(panel.locator("#forecast-state")).to_contain_text("2배 이상")
                panel.get_by_label("최근 학습 획득·측정 수 (선택)").fill("150")
                panel.get_by_role("button", name="설정 적용").click()
                pw.expect(
                    panel.get_by_role("button", name="1시간", exact=True, include_hidden=True)
                ).to_be_enabled()
                pw.expect(panel.locator("#forecast-detail-metrics")).to_contain_text(
                    "학습 150개", timeout=30000
                )
                panel.get_by_role("button", name="여러 과거 시점 비교").click()
                pw.expect(panel.locator("#forecast-detail-metrics")).to_contain_text(
                    "여러 과거 시점", timeout=30000
                )
                assert "forecast_prior=0.1" in page.url

                page.reload()
                pw.expect(figures).to_contain_text("관리 상한 14.3까지", timeout=30000)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                panel.get_by_label("기준 방향").select_option("lower")
                pw.expect(figures).to_contain_text("관리 하한 14.3까지", timeout=30000)
                pw.expect(figures).to_contain_text("이미 도달")
                # EDA-selected range is a reference in the forecast, not implicit training.
                page.goto(
                    base
                    + "&forecast_series=history%7Ccurrent"
                    + "&forecast_context_kind=eda"
                    + "&forecast_context_from=2026-10-14T00%3A00%3A00%2B00%3A00"
                    + "&forecast_context_to=2026-10-14T02%3A00%3A00%2B00%3A00"
                    + "#forecast"
                )
                evidence = panel.locator("#outlook-evidence")
                pw.expect(evidence).to_contain_text("구간 비교의 구간 B", timeout=30000)

                # Cross-tab EDA navigation retains the comparison window as context.
                page.goto(base + "#signals")
                link = page.get_by_role("link", name="선택 신호의 상태 전망 보기")
                pw.expect(link).to_be_visible(timeout=30000)
                link.click()
                pw.expect(evidence).to_contain_text("구간 비교의 구간 B", timeout=30000)

                page.goto(base + "#anomaly")
                anomaly_link = page.get_by_role("link", name="이 신호 상태 전망").first
                pw.expect(anomaly_link).to_be_visible(timeout=30000)
                anomaly_link.click()
                pw.expect(evidence).to_contain_text("이상 탐지에서 고른 구간", timeout=30000)
                # The evidence opens the baseline-versus-recent comparison of the same signal.
                panel.locator("#forecast-settings > summary").click()
                panel.locator("#outlook-more").get_by_role(
                    "link", name="기준 구간과 최근 구간 비교"
                ).click()
                pw.expect(page.locator("#explore-state")).to_contain_text("구간 A", timeout=30000)

                # An old remaining-life link opens its replacement.
                page.goto(base + "#rul")
                pw.expect(page.locator(".asset-tabs a[data-tab='forecast']")).to_have_attribute(
                    "aria-current", "page"
                )
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def test_count_only_acquisition_record_opens_forecast_from_overview(tmp_path: Path) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("prophet")
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal in range(1, 31):
        deliver(
            workspace, tmp_path / "waves", ordinal, 4.0 if ordinal == 30 else 0.5 + 0.01 * ordinal
        )
    analyze(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 390, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                base = f"http://127.0.0.1:{server.server_port}/web/?monitor_asset=bearing-a"
                page.goto(base + "#monitor")
                page.locator("#asset-capabilities").get_by_role(
                    "button", name="상태 전망 열기"
                ).click()
                panel = page.locator("#forecast")
                pw.expect(panel.locator(".forecast-chart")).to_be_visible(timeout=30000)
                # The outlook reads the acquisition axis too: changes per acquisition.
                pw.expect(panel.locator("#outlook-evidence .outlook-details")).to_contain_text(
                    "획득당", timeout=30000
                )
                pw.expect(panel.locator("#forecast-unit")).to_have_value("count")
                pw.expect(panel.locator("#forecast-count")).to_have_value("14")
                pw.expect(panel.locator(METRICS)).to_contain_text("14개 획득 뒤")
                panel.locator("#forecast-count").fill("10")
                with page.expect_response(
                    lambda response: "/api/v1/forecast?" in response.url
                ) as response:
                    panel.get_by_role("button", name="획득 수 적용").click()
                forecast = response.value.json()
                # A rising model forecast can still end below the latest observed spike.
                assert forecast["trend"]["change"] > 0
                assert forecast["trend"]["end"] < forecast["history"][-1][1]
                pw.expect(panel.locator(METRICS + " > div").first).not_to_contain_text("증가")
                pw.expect(panel.locator(METRICS)).to_contain_text("10개 획득 뒤", timeout=30000)
                pw.expect(panel.locator(".forecast-compare")).to_have_count(0)
                panel.locator("#forecast-settings > summary").click()
                panel.locator("#forecast-assumed-period").fill("120")
                panel.get_by_role("button", name="간격 적용").click()
                pw.expect(panel.locator("#forecast-detail-metrics")).to_contain_text(
                    "가정 획득 간격 2분", timeout=30000
                )
                pw.expect(
                    panel.get_by_role("button", name="1시간", exact=True, include_hidden=True)
                ).to_be_disabled()
                panel.locator("#forecast-assumed-period").fill("600")
                panel.get_by_role("button", name="간격 적용").click()
                pw.expect(
                    panel.get_by_role("button", name="1시간", exact=True, include_hidden=True)
                ).to_be_enabled()
                pw.expect(
                    panel.get_by_role("button", name="24시간", exact=True, include_hidden=True)
                ).to_be_disabled()
                panel.locator("#forecast-unit").select_option("time")
                pw.expect(panel.locator(METRICS)).to_contain_text("1시간 뒤", timeout=30000)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
