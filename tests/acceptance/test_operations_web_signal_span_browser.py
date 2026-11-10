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
                sliders = page.locator("fieldset.scrub input[type=range]")
                pw.expect(sliders).to_have_count(2, timeout=60000)
                card = page.locator("section.pick").first
                pw.expect(card).to_have_count(0)
                # Moving the start alone picks one moment, as the single slider did.
                sliders.nth(0).focus()
                for _ in range(3):
                    page.keyboard.press("ArrowLeft")
                pw.expect(card.locator("h4")).to_have_text("선택한 시점")
                # Moving the end past it stretches the moment into a span.
                sliders.nth(1).focus()
                for _ in range(2):
                    page.keyboard.press("ArrowRight")
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
                assert not errors
            finally:
                browser.close()
    finally:
        stop_web(*running)
