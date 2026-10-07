"""Interactive Monitor browser gate for a prepared, populated Operations workspace.

Run with ``uv run --no-sync --with playwright python -m tools.opcua.monitor_browser``.
The server lifecycle remains owned by the caller. This checks stored-data interaction,
not live fault/recovery behavior; fault_harness.py owns that separate protocol.
"""

from __future__ import annotations

import argparse
import json
import math
import re
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
                chart = page.locator(".mw-plot")
                expect(chart.locator("svg")).to_be_visible(timeout=30000)
                expect(page.get_by_role("button", name="Monitor", exact=True)).to_have_attribute(
                    "aria-current", "page"
                )
                initial_asset = page.locator(".mw-asset h1").inner_text()
                bounds = chart.bounding_box()
                assert bounds is not None and bounds["y"] < 600, bounds
                assert page.locator(".mw-shell select").count() == 0
                assert chart.locator("circle").count() > 0
                page.screenshot(path=str(args.output / f"monitor-{width}-fold.png"))
                assert chart.locator('rect[role="button"]').evaluate_all("""rects =>
                    rects.every(rect => {
                        const svg = rect.ownerSVGElement;
                        const x = Number(rect.getAttribute('x'));
                        const width = Number(rect.getAttribute('width'));
                        return x >= 54 && x + width <= svg.viewBox.baseVal.width - 16;
                    })""")
                for period in ("15m", "24h", "7d", "1h"):
                    page.get_by_role("button", name=period, exact=True).click()
                    expect(page.get_by_role("button", name=period, exact=True)).to_have_attribute(
                        "aria-pressed", "true", timeout=30000
                    )
                    if period in {"24h", "7d"}:
                        assert (
                            chart.locator(".mw-axis")
                            .filter(
                                has_text=re.compile(
                                    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\b"
                                )
                            )
                            .count()
                            > 0
                        )

                search = page.get_by_role("searchbox", name="Find a signal")
                search.fill(args.focus)
                focus = page.get_by_role("button", name=f"Inspect {args.focus}", exact=True)
                focus.click()
                expect(focus).to_have_attribute("aria-pressed", "true", timeout=30000)
                expect(
                    page.locator(".mw-reading-label").filter(has_text=args.focus)
                ).to_be_visible()
                search.fill(args.compare)
                comparison = page.get_by_role("button", name=f"Compare {args.compare}", exact=True)
                if comparison.get_attribute("aria-pressed") != "true":
                    comparison.click()
                expect(comparison).to_have_attribute("aria-pressed", "true", timeout=30000)
                expect(
                    page.locator(".mw-reading-label").filter(has_text=args.compare)
                ).to_be_visible()
                search.fill("")
                box = chart.bounding_box()
                assert box is not None
                page.mouse.move(box["x"] + box["width"] * 0.85, box["y"] + 80)
                expect(page.locator(".mw-tooltip")).to_be_visible()
                expect(page.locator(".mw-tooltip")).to_contain_text("BUCKET SUMMARY")
                expect(page.locator(".mw-tooltip-window").first).to_contain_text("UTC")
                expect(page.locator(".mw-tooltip-range").first).to_contain_text("Min")
                expect(page.locator(".mw-assessment")).to_contain_text("Manual snapshot")
                page.mouse.move(0, 0)
                page.get_by_role("button", name="Choose asset").click()
                expect(page.get_by_role("dialog", name="Choose an asset")).to_be_visible()
                page.get_by_role("button", name="Close asset picker").click()
                page.get_by_role("button", name="Inspect selected signal", exact=True).click()
                expect(page.get_by_role("button", name="Assets", exact=True)).to_have_attribute(
                    "aria-current", "page", timeout=30000
                )
                expect(page.get_by_label("Signal", exact=True)).to_have_value(args.focus)
                page.get_by_role("button", name="Monitor", exact=True).click()
                expect(page.locator(".mw-reading-label").filter(has_text=args.focus)).to_be_visible(
                    timeout=30000
                )
                expect(
                    page.locator(".mw-reading-label").filter(has_text=args.compare)
                ).to_be_visible()
                expect(page.locator(".mw-asset h1")).to_have_text(initial_asset)
                expect(page.get_by_role("button", name="1h", exact=True)).to_have_attribute(
                    "aria-pressed", "true"
                )
                evidence_rows = page.locator(".mw-evidence-row")
                evidence_count = evidence_rows.count()
                evidence_routing = None
                if evidence_rows.count():
                    expected_id = evidence_rows.last.get_attribute("data-evidence-id")
                    evidence_rows.last.click()
                    expect(
                        page.get_by_role("button", name="Investigations", exact=True)
                    ).to_have_attribute("aria-current", "page", timeout=30000)
                    expect(page.locator(".mw-shell")).to_have_attribute(
                        "data-current-investigation", expected_id
                    )
                    page.get_by_role("button", name="Monitor", exact=True).click()
                    expect(page.locator(".mw-plot svg")).to_be_visible(timeout=30000)
                    evidence_routing = expected_id
                page.get_by_role("button", name="Refresh observations").click()
                expect(page.locator(".mw-shell")).not_to_have_class(
                    "mw-shell mw-pending", timeout=30000
                )
                navigation_checks = []
                for destination in (
                    "Assets",
                    "Investigations",
                    "Maintenance",
                    "System",
                    "Setup",
                    "Monitor",
                ):
                    page.get_by_role("button", name=destination, exact=True).click()
                    expect(
                        page.get_by_role("button", name=destination, exact=True)
                    ).to_have_attribute("aria-current", "page", timeout=30000)
                    expect(page.locator(".mw-shell")).not_to_have_class(
                        "mw-shell mw-pending", timeout=30000
                    )
                    if destination != "Monitor":
                        expect(
                            page.get_by_role(
                                "heading",
                                name={
                                    "Assets": initial_asset,
                                    "Investigations": "Analysis evidence",
                                    "Maintenance": "Review workload",
                                    "System": "Advanced diagnostics",
                                    "Setup": "Setup",
                                }[destination],
                                exact=True,
                            ).first
                        ).to_be_visible(timeout=30000)
                    overflow = page.locator(".mw-shell").evaluate("""shell =>
                        [...document.querySelectorAll('.output-area *'),
                         ...shell.querySelectorAll('*')]
                    .filter(e => { const r = e.getBoundingClientRect();
                        if (!r.width || r.right <= innerWidth + 1) return false;
                        const svg = e.ownerSVGElement;
                        if (svg && svg.getBoundingClientRect().right <= innerWidth + 1)
                            return false;
                        for (let a=e.parentElement; a; a=a.parentElement) {
                            if (['auto','scroll'].includes(getComputedStyle(a).overflowX)
                                && a.getBoundingClientRect().right <= innerWidth + 1)
                                return false;
                        }
                        return getComputedStyle(e).visibility !== 'hidden';
                    }).map(e => e.tagName + '.' + String(e.className).slice(0,40))""")
                    assert not overflow, (destination, overflow)
                    navigation_checks.append({"page": destination, "overflow": overflow})
                shell_bounds = page.locator(".mw-shell").bounding_box()
                assert shell_bounds is not None
                # Marimo scrolls its app viewport internally. Expand the capture height
                # so an element screenshot cannot silently contain a clipped lower half.
                page.set_viewport_size(
                    {"width": width, "height": math.ceil(shell_bounds["height"]) + 150}
                )
                expect(page.locator(".mw-evidence-list")).to_be_in_viewport()
                page.screenshot(path=str(args.output / f"monitor-{width}-full.png"), full_page=True)
                page.set_viewport_size({"width": width, "height": 1000})
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
                        "cursor_bucket_summary": True,
                        "asset_picker": True,
                        "native_select_count": 0,
                        "exact_evidence_routing": evidence_routing,
                        "evidence_count": evidence_count,
                        "navigation_pages": navigation_checks,
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
