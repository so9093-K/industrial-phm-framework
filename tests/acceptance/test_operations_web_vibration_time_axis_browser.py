"""Vibration time labels use the recorded interval while tooltips retain acquisition identity."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.phm import analyze, deliver, phm_workspace
from tests.support.web_next import asset_list, start_web, stop_web


@pytest.mark.parametrize("width", [390, 1280])
@pytest.mark.parametrize("period", [60, None])
def test_vibration_time_axis_uses_measurement_interval(
    tmp_path: Path, width: int, period: int | None
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal in range(1, 7):
        deliver(workspace, tmp_path / "waves", ordinal, ordinal * 0.1, period_seconds=period)
    analyze(workspace)
    server, thread = start_web(workspace.root.resolve(), writer=False)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        status=200, content_type="application/json", body=asset_list("bearing-a")
                    ),
                )
                page.goto(
                    f"http://127.0.0.1:{server.server_port}"
                    "/web/?page=assets&tab=signals&monitor_asset=bearing-a"
                )
                panel = page.get_by_role("region", name="진동 측정", exact=True)
                pw.expect(panel.locator(".x-axis")).to_be_visible()
                labels = panel.locator(".ticks span").all_text_contents()
                assert len(labels) >= 2
                if period is None:
                    assert all(label.startswith("#") for label in labels)
                else:
                    assert labels[0] == "0분"
                    assert all("분" in label for label in labels)
                    pw.expect(panel.locator(".x-axis")).to_contain_text("측정 간격 60초")
                pw.expect(panel.locator("circle title").first).to_contain_text("1번째 측정")
                pw.expect(panel.locator("circle title").last).to_contain_text("6번째 측정")
                # Labels must fit their chart and remain readable on a phone as well as a desktop.
                assert panel.locator(".ticks").evaluate("""axis => {
                    const box = axis.getBoundingClientRect();
                    const labels = [...axis.querySelectorAll('span')]
                        .map(el => el.getBoundingClientRect());
                    return labels.every((label, i) => label.left >= box.left - 1
                        && label.right <= box.right + 1
                        && (!i || label.left >= labels[i - 1].right));
                }""")
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )
                assert not errors, errors
            finally:
                browser.close()
    finally:
        stop_web(server, thread)
