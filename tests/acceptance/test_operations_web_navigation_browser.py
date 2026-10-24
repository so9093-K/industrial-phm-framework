"""Current model bookmarks retain exact identity; invalid selections never pick another result."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.phm import analyze, deliver, phm_workspace
from tests.support.web_next import start_web, stop_web


def test_model_bookmark_and_result_outside_recent_trace(tmp_path: Path) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "bookmarks")
    for ordinal in range(1, 71):
        deliver(workspace, tmp_path / "waves", ordinal, 0.5 + ordinal / 100)
    analyze(workspace)
    server, thread = start_web(workspace.root, writer=False)
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 390, "height": 900})
                page.goto(
                    base + "/web/?page=assets&tab=anomaly&method=model&monitor_asset=bearing-a"\
                    + "&model_binding=anomaly-a&model_position=2&model_compare=1"
                )
                pw.expect(page.get_by_role("heading", name="모델 이상 점수")).to_be_visible()
                pw.expect(page.get_by_label("측정 선택 (최근 64회)")).to_have_value("2")
                assert "/web/?" in page.url and "model_binding=anomaly-a" in page.url
                assert "monitor_asset=bearing-a" in page.url
                page.reload()
                pw.expect(page.get_by_role("group", name="2번째 측정 모델 결과")).to_be_visible()
                for suffix in (
                    "?page=assets&tab=anomaly&method=model&monitor_asset=bearing-a&model_binding=absent",
                    "?page=assets&tab=anomaly&method=model&monitor_asset=bearing-a&model_binding=anomaly-a&model_position=999",
                ):
                    page.goto(base + "/web/" + suffix)
                    pw.expect(
                        page.get_by_text("다른 모델 결과로 대신하지 않습니다", exact=False)
                        if "absent" in suffix
                        else page.get_by_text("모델 결과를 읽지 못했습니다", exact=False)
                    ).to_be_visible()
                    assert page.get_by_role("group", name="70번째 측정 모델 결과").count() == 0
                page.goto(base + "/web/?page=assets&tab=signals&monitor_asset=bearing-a")
                feature = page.get_by_label("진동 특징", exact=False)
                pw.expect(feature).to_be_visible()
                feature.select_option("feature.Vertical_vibration_signals.rms")
                tabs = page.get_by_role("navigation", name="설비 화면")
                tabs.get_by_role("link", name="상태 요약", exact=True).click()
                tabs.get_by_role("link", name="상태 전망", exact=True).click()
                pw.expect(page.get_by_label("진동 특징", exact=False)).to_have_value(
                    "feature.Vertical_vibration_signals.rms"
                )
                page.goto(base + "/web/?page=system")
                pw.expect(page.get_by_role("heading", name="CSV 파일로 시작")).to_be_visible()
                assert "section=connections" in page.url
                page.goto(base + "/web/?page=system&section=status")
                pw.expect(page.get_by_role("heading", name="실행 상태")).to_be_visible()
                assert "section=status" in page.url
                page.get_by_role("link", name="본문으로 건너뛰기").focus()
                page.keyboard.press("Enter")
                pw.expect(page.locator("#main")).to_be_focused()
            finally:
                browser.close()
    finally:
        stop_web(server, thread)
