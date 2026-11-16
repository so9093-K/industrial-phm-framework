"""A moment or a span of a stored signal can be picked without dragging (WCAG 2.5.7, 2.1.1)."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from tests.acceptance.test_operations_web_forecast_settings_browser import _store_history
from tests.support.phm import phm_workspace
from tests.support.web_next import asset_list, start_web, stop_web


@pytest.mark.parametrize("width", [390, 1280])
def test_a_span_is_picked_with_keys_and_handed_to_the_comparison(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    _store_history(workspace)
    snapshot = json.loads(asset_list("motor-01"))
    running = start_web(workspace.root, writer=False)
    origin = f"http://127.0.0.1:{running[0].server_port}"
    query = {"page": "assets", "tab": "signals", "monitor_asset": "motor-01"}
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/api/v1/monitor", lambda route: route.fulfill(json=snapshot))
                page.goto(f"{origin}/web/?{urlencode(query)}")
                sliders = page.get_by_role("group", name="시점·구간 고르기").locator(
                    "input[type=range]"
                )
                pw.expect(sliders).to_have_count(2, timeout=60000)
                card = page.locator("section.pick").first
                pw.expect(card).to_have_count(0)
                # Both handles use the entire graph axis and move independently.
                rail = page.locator(".time-range .rail").first.bounding_box()
                chart = page.locator(".series svg").first.bounding_box()
                assert abs(rail["x"] - chart["x"]) < 1 and abs(rail["width"] - chart["width"]) < 1
                sliders.nth(0).focus()
                for _ in range(3):
                    page.keyboard.press("ArrowRight")
                pw.expect(card.locator("h4")).to_have_text("선택한 구간")
                start = sliders.nth(0).input_value()
                sliders.nth(1).focus()
                for _ in range(2):
                    page.keyboard.press("ArrowLeft")
                assert sliders.nth(0).input_value() == start
                pw.expect(card.locator("h4")).to_have_text("선택한 구간")
                pw.expect(card).to_contain_text("평균")
                compare = page.get_by_role("link", name="두 기간 비교 →").first
                handed = parse_qs(urlsplit(compare.get_attribute("href")).query)
                a_from, a_to = handed["compare_a"][0].split("~")
                b_from, b_to = handed["compare_b"][0].split("~")
                assert a_to == b_from and a_from < a_to < b_to
                # Escape lets go of the pick from the keyboard as well.
                page.keyboard.press("Escape")
                pw.expect(card).to_have_count(0)
                # Repeated boundary keys cannot visually cross the other handle while the
                # selected span stays clamped to one bucket.
                for _ in range(2):
                    sliders.nth(0).press("End")
                pw.expect(sliders.nth(0)).to_have_value(str(int(sliders.nth(1).input_value()) - 1))
                for _ in range(2):
                    sliders.nth(1).press("Home")
                pw.expect(sliders.nth(1)).to_have_value(str(int(sliders.nth(0).input_value()) + 1))
                page.keyboard.press("Escape")
                pw.expect(card).to_have_count(0)
                assert not errors
            finally:
                browser.close()
    finally:
        stop_web(*running)
