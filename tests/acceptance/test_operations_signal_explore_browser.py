"""Period comparison in the signal exploration, and the way to and from model results."""

# The screen writes acquisition ranges with an en dash between the numbers.
# ruff: noqa: RUF001

from __future__ import annotations

from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.phm import analyze, deliver, phm_workspace


@pytest.mark.parametrize("width", [390, 1280])
def test_two_acquisition_ranges_compare_and_link_to_the_anomaly_view(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.5, 0.55, 0.5, 3.0, 3.1, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
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
                base = f"http://127.0.0.1:{server.server_port}/web/?monitor_asset=bearing-a"
                page.goto(base + "#signals")
                panel = page.locator("#explore")
                state = panel.locator("#explore-state")
                pw.expect(state).to_contain_text("획득별 특징 · 구간 A #1–#4 · 구간 B #5–#8")
                guide = panel.locator("#explore-guide")
                heading = guide.get_by_role("heading", name="무엇을 확인하고 싶나요?")
                pw.expect(heading).to_be_visible()
                compare_goal = guide.get_by_role("button", name="과거와 최근이 어떻게 다른가요?")
                pw.expect(compare_goal).to_be_visible()
                pw.expect(panel.locator("#explore-result-intro")).to_contain_text(
                    "구간 A는 사용자가 고른 비교 구간"
                )
                pw.expect(panel.locator(".explore-interpretation").first).to_contain_text(
                    "중앙값"
                )
                cards = panel.locator(".explore-series")
                pw.expect(cards).to_have_count(2)
                horizontal = cards.filter(has_text="수평 진동 RMS")
                pw.expect(horizontal.locator(".explore-lead")).to_contain_text(
                    "B 값의 100%가 A의 5–95% 범위 밖"
                )
                pw.expect(horizontal.locator("svg.explore-chart")).to_be_visible()
                quality = panel.locator(".explore-quality-card")
                pw.expect(quality).to_have_count(2)
                pw.expect(quality.first).to_contain_text("전달된 획득")
                relation = panel.locator(".explore-relation")
                pw.expect(relation.locator("svg.explore-scatter circle")).to_have_count(8)
                pw.expect(relation.locator("table")).to_contain_text("4 / 4")
                pw.expect(relation).to_contain_text("같은 획득의 두 특징을 짝지었습니다")
                spectrum = panel.locator(".explore-spectrum")
                pw.expect(spectrum.locator("svg.explore-spectrum-chart")).to_have_count(0)
                spectrum.get_by_role("button", name="주파수 성분 계산").click()
                pw.expect(spectrum.locator("svg.explore-spectrum-chart")).to_be_visible()
                pw.expect(spectrum.locator(".explore-band-changes li").first).to_contain_text(
                    "구간 B가 A보다 +"
                )
                pw.expect(spectrum).to_contain_text("구간 A 획득 #1 #2 #3 #4")

                compare_goal.click()
                pw.expect(state).to_contain_text("구간 A #1–#3 · 구간 B #6–#8")
                panel.get_by_role("button", name="처음 1/4 · 마지막 1/4").click()
                pw.expect(state).to_contain_text("구간 A #1–#3 · 구간 B #6–#8")
                assert "explore_a=1%7E3" in page.url

                panel.get_by_role("link", name="이상 탐지에서 #3 → #8 비교 보기").click()
                assistant = page.locator("#anomaly-assistant")
                pw.expect(assistant.get_by_label("비교 시점")).to_have_value("3")

                # Back from the model view: the range splits at its level shift.
                assistant.get_by_label("비교 시점").select_option("1")
                assistant.get_by_text("측정값 비교·구간 흐름 자세히 보기").click()
                link = assistant.locator(".phm-explore-link")
                pw.expect(link).to_contain_text("A #1–#4 / B #5–#8")
                link.click()
                pw.expect(state).to_contain_text("구간 A #1–#4 · 구간 B #5–#8")
                pw.expect(page.locator(".asset-tabs a[data-tab='signals']")).to_have_attribute(
                    "aria-current", "page"
                )
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def test_the_signal_flow_hands_its_window_over_and_late_answers_are_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    import time
    from datetime import UTC, datetime, timedelta

    from industrial_phm.application.backfill import FileBackfillEvent
    from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
    from industrial_phm.runtime import operations_web_http

    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.5, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    base = datetime(2026, 10, 14, tzinfo=UTC)
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
                event_at=base + timedelta(minutes=index),
                value=10.0 + index,
            )
            for index in range(40)
        ),
        batch_id="motor",
    )
    original = operations_web_http.handle_explore_read

    def slow_for_the_bearing(workspace_arg, path, query):  # type: ignore[no-untyped-def]
        if path.endswith("/sources") and "bearing-a" in query:
            time.sleep(1.5)
        return original(workspace_arg, path, query)

    monkeypatch.setattr(operations_web_http, "handle_explore_read", slow_for_the_bearing)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/?monitor_asset=bearing-a#signals"
                )
                page.locator("#asset-switch").select_option("motor-01")
                state = page.locator("#explore-state")
                pw.expect(state).to_contain_text("측정 이력 · 구간 A")
                page.wait_for_timeout(2000)  # the bearing's late answer arrives meanwhile
                # Controls still read the motor's history, not the bearing's late answer.
                page.get_by_role("button", name="처음 1/4 · 마지막 1/4").click()
                pw.expect(state).to_contain_text("측정 이력 · 구간 A")
                pw.expect(page.locator("#explore-series")).to_contain_text("current")

                trend = page.locator("#trend-results")
                trend.get_by_role("button", name="이 기간을 두 구간으로 나눠 비교").click()
                pw.expect(state).to_contain_text("구간 A 2026-10-14 08:39 KST")
                assert "explore_series=current" in page.url
                card = page.locator(".explore-series").first
                pw.expect(card.locator(".explore-lead")).to_contain_text("중앙값")
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
