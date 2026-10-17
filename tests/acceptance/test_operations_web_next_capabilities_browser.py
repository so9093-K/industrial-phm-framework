"""An asset's summary says what its stored data supports and opens each analysis for that asset."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from tests.support.phm import analyze, deliver, phm_workspace
from tests.support.web_next import asset_list, start_web, stop_web

BASE = datetime(2026, 10, 14, tzinfo=UTC)


def _history(workspace: Any, asset_id: str, channels: tuple[str, ...], count: int) -> None:
    DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    ).append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:{asset_id}:{'e' * 64}:{channel}:{index}",
                source_id=f"{asset_id}-file",
                asset_id=asset_id,
                channel_id=channel,
                source_file=f"{asset_id}.csv",
                source_sha256="e" * 64,
                source_size_bytes=10,
                sample_index=index * len(channels) + position,
                event_at=BASE + timedelta(minutes=index),
                value=10.0 + index * (position + 1),
            )
            for position, channel in enumerate(channels)
            for index in range(count)
        ),
        batch_id=asset_id,
    )


def _page(runtime: Any, port: int, width: int, *assets: str) -> tuple[Any, Any, list[str]]:
    browser = runtime.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route(
        "**/api/v1/monitor",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=asset_list(*assets)
        ),
    )
    return browser, page, errors


@pytest.mark.parametrize("width", [390, 1280])
def test_the_summary_says_what_each_assets_data_supports_and_opens_it(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.5, 0.55, 0.5, 3.0, 3.1, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    _history(workspace, "motor-01", ("current", "temperature"), 40)
    server, thread = start_web(workspace.root.resolve(), writer=True)
    try:
        with pw.sync_playwright() as runtime:
            browser, page, errors = _page(
                runtime, server.server_port, width, "motor-01", "bearing-a"
            )
            try:
                base = f"http://127.0.0.1:{server.server_port}/web/?page=assets"
                page.goto(base + "&monitor_asset=motor-01")
                options = page.get_by_role("region", name="이 데이터로 할 수 있는 분석")
                rows = options.get_by_role("listitem")

                def row(capability: str) -> Any:
                    return options.locator(f'li[data-capability="{capability}"]')

                pw.expect(rows).to_have_count(6)
                pw.expect(row("measurements")).to_contain_text("시계열 신호 2개 ·")
                pw.expect(row("anomaly")).to_contain_text("모델 없이 기준 구간에서 벗어난 값 찾기")
                pw.expect(row("forecast")).to_contain_text("기록이 짧아 예측 그래프는 없음")
                pw.expect(row("ai-question")).to_contain_text("상태 전망을 근거로 해설")
                # What this data cannot support stays one quiet line, each with its reason.
                pw.expect(options).to_contain_text("주파수 분석 — 원본 진동 파형 없음")
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )
                page.screenshot(path=str(tmp_path / f"options-{width}.png"), full_page=True)

                # Ready analyses open for the same asset and data kind.
                options.get_by_role("link", name="두 기간 비교 열기").click()
                pw.expect(page).to_have_url(
                    base + "&tab=change&method=compare&data=history&monitor_asset=motor-01"
                )
                heading = page.get_by_role("heading", name="두 기간 비교", exact=True)
                pw.expect(heading).to_be_visible()
                page.go_back()
                options.get_by_role("link", name="신호 관계 열기").click()
                pw.expect(page).to_have_url(
                    base + "&tab=change&method=relation&data=history&monitor_asset=motor-01"
                )
                page.go_back()
                options.get_by_role("link", name="AI 해설 열기").click()
                pw.expect(page).to_have_url(base + "&tab=outlook&monitor_asset=motor-01")

                # Vibration with a connected model: every analysis but the outlook.
                page.goto(base + "&monitor_asset=bearing-a")
                pw.expect(rows).to_have_count(6)
                pw.expect(options).to_contain_text(
                    "상태 전망 — 기록이 짧음 (예측 기간의 2배 이상 필요)"
                )
                pw.expect(row("period-compare")).to_contain_text("측정 순서 #1~#8")
                options.get_by_role("link", name="주파수 분석 열기").click()
                pw.expect(page).to_have_url(
                    base + "&tab=change&method=spectrum&monitor_asset=bearing-a"
                )
                page.go_back()
                options.get_by_role("link", name="AI 해설 열기").click()
                pw.expect(page).to_have_url(
                    base + "&tab=anomaly&method=model&monitor_asset=bearing-a"
                )
                assert not errors, errors
            finally:
                browser.close()
    finally:
        stop_web(server, thread)


def test_a_fitting_model_that_is_not_connected_yet_is_one_link_away(tmp_path: Path) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    for ordinal in range(1, 4):
        deliver(workspace, tmp_path / "waves", ordinal, 0.5)
    # The bearing also has a stored temperature record, so it is listed before any model.
    _history(workspace, "bearing-a", ("temperature",), 10)
    server, thread = start_web(workspace.root.resolve(), writer=True)
    try:
        with pw.sync_playwright() as runtime:
            browser, page, errors = _page(runtime, server.server_port, 1280, "bearing-a")
            try:
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/"
                    "?page=assets&monitor_asset=bearing-a"
                )
                options = page.get_by_role("region", name="이 데이터로 할 수 있는 분석")
                anomaly = options.locator('li[data-capability="anomaly"]')
                pw.expect(anomaly).to_contain_text("맞는 모델 2개 연결 가능")
                anomaly.get_by_role("link", name="이상 징후 모델 연결하기").click()
                offer = page.get_by_role("region", name="연결할 수 있는 이상 탐지 모델")
                pw.expect(offer.get_by_role("listitem")).to_have_count(2)
                assert not errors, errors
            finally:
                browser.close()
    finally:
        stop_web(server, thread)
