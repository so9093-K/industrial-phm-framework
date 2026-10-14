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
                pw.expect(spectrum.locator("svg.explore-spectrum-chart")).to_be_visible()
                pw.expect(spectrum.locator(".explore-band-changes li").first).to_contain_text(
                    "구간 B가 A보다 +"
                )
                pw.expect(spectrum).to_contain_text("구간 A 획득 #1 #2 #3 #4")

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
