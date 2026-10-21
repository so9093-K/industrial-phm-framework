"""Render assets/system-architecture.png from its HTML source (assets/source/).

Run from the repository root with Playwright's Chromium installed:
    uv run --no-sync python -m tools.assets.render_architecture
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "assets" / "source" / "system-architecture.html"
TARGET = ROOT / "assets" / "system-architecture.png"


def main() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        page = browser.new_page(viewport={"width": 1672, "height": 941}, locale="ko-KR")
        page.goto(SOURCE.as_uri())
        page.wait_for_load_state("networkidle")
        page.screenshot(path=str(TARGET), full_page=False)
        browser.close()
    print(TARGET.relative_to(ROOT))


if __name__ == "__main__":
    main()
