"""Interactive Monitor browser gate for a prepared, populated Operations workspace.

Run with ``uv run --no-sync --with playwright python -m tools.opcua.monitor_browser``.
The server lifecycle remains owned by the caller. This checks stored-data interaction,
not live fault/recovery behavior; fault_harness.py owns that separate protocol.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    from playwright.sync_api import expect, sync_playwright

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--focus", required=True, help="another populated channel ID")
    parser.add_argument("--compare", required=True, help="a populated comparison channel ID")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {"url": args.url, "focus": args.focus, "compare": args.compare, "viewports": []}
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        try:
            for width in (1440, 1024):
                page = browser.new_page(viewport={"width": width, "height": 1000})
                errors = []
                page.on("pageerror", lambda error, sink=errors: sink.append(str(error)))
                page.goto(args.url)
                chart = page.locator(".phm-chart-workspace")
                expect(chart.locator("svg")).to_be_visible(timeout=30000)
                expect(page.get_by_role("tab", name="Monitor", exact=True)).to_have_attribute(
                    "aria-selected", "true"
                )
                initial_asset = page.get_by_label("Asset", exact=True).input_value()
                # Test the first fold before Playwright scrolls any control into view.
                bounds = chart.bounding_box()
                assert bounds is not None and bounds["y"] < 750, bounds
                assert chart.locator("svg text").count() > 5
                page.screenshot(path=str(args.output / f"monitor-{width}-fold.png"))
                before = chart.inner_html()
                page.get_by_role("tab", name="15m", exact=True).click()
                expect(page.get_by_role("tab", name="15m", exact=True)).to_have_attribute(
                    "aria-selected", "true"
                )
                page.wait_for_function(
                    "old => document.querySelector('.phm-chart-workspace')?.innerHTML !== old",
                    arg=before,
                )
                for period in ("24h", "7d", "1h"):
                    previous_chart = chart.inner_html()
                    page.get_by_role("tab", name=period, exact=True).click()
                    expect(page.get_by_role("tab", name=period, exact=True)).to_have_attribute(
                        "aria-selected", "true"
                    )
                    page.wait_for_function(
                        "old => document.querySelector('.phm-chart-workspace')?.innerHTML !== old",
                        arg=previous_chart,
                    )
                focus = page.get_by_label("Signal", exact=True)
                focus.select_option(args.focus)
                expect(focus).to_have_value(args.focus)
                expect(chart).to_contain_text(args.focus, timeout=30000)
                comparison = page.get_by_label("Compare signals", exact=True)
                comparison.click()
                option = page.get_by_role("listbox", name="Suggestions").get_by_role(
                    "option", name=args.compare, exact=True
                )
                if option.get_attribute("aria-selected") != "true":
                    option.click()
                page.keyboard.press("Escape")
                expect(chart).to_contain_text(args.compare, timeout=30000)
                page.get_by_role("button", name="Open signal details", exact=True).click()
                expect(page.get_by_role("tab", name="Assets", exact=True)).to_have_attribute(
                    "aria-selected", "true"
                )
                expect(page.get_by_label("Signal", exact=True)).to_have_value(args.focus)
                page.get_by_role("tab", name="Monitor", exact=True).click()
                expect(chart).to_contain_text(args.focus, timeout=30000)
                expect(chart).to_contain_text(args.compare, timeout=30000)
                expect(page.get_by_label("Asset", exact=True)).to_have_value(initial_asset)
                expect(page.get_by_role("tab", name="1h", exact=True)).to_have_attribute(
                    "aria-selected", "true"
                )
                overflow = page.evaluate("""() => [...document.querySelectorAll('.output-area *')]
                    .filter(e => { const r = e.getBoundingClientRect();
                        if (!r.width || r.right <= innerWidth + 1) return false;
                        for (let a=e.parentElement; a; a=a.parentElement) {
                            if (['auto','scroll'].includes(getComputedStyle(a).overflowX)
                                && a.getBoundingClientRect().right <= innerWidth + 1)
                                return false;
                        }
                        return getComputedStyle(e).visibility !== 'hidden';
                    }).map(e => e.tagName + '.' + String(e.className).slice(0,40))""")
                assert not overflow, overflow
                assert not errors, errors
                chart.screenshot(path=str(args.output / f"monitor-{width}-chart.png"))
                report["viewports"].append(
                    {
                        "width": width,
                        "asset_id": initial_asset,
                        "chart_initial_y": bounds["y"],
                        "overflow": overflow,
                        "page_errors": errors,
                        "range_changes": ["15m", "24h", "7d", "1h"],
                        "focus_and_comparison": True,
                        "detail_return_context": True,
                    }
                )
                page.close()
        finally:
            browser.close()
    report["passed"] = True
    (args.output / "monitor-browser.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
