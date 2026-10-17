"""관측 현황 keeps what needs a look current and opens the exact place to check it."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.support.phm import analyze, deliver, phm_workspace
from tests.support.web_next import asset_list, start_web, stop_web


@pytest.mark.parametrize("width", [390, 1280])
def test_attention_follows_new_results_without_reload(tmp_path: Path, width: int) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 3.0), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    server, thread = start_web(workspace.root.resolve(), writer=False)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page: Any = browser.new_page(
                    viewport={"width": width, "height": 900}, locale="ko-KR"
                )
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        status=200, content_type="application/json", body=asset_list("bearing-a")
                    ),
                )
                page.goto(f"http://127.0.0.1:{server.server_port}/web-next/")
                attention = page.get_by_role("region", name="확인이 필요한 설비")
                asset = attention.get_by_role("article", name="bearing-a")
                pw.expect(asset).to_contain_text("진동 변화 확인 필요")
                pw.expect(asset).to_contain_text("모델 기준 초과 1개")
                # The asset list counts the same items, so the two never disagree.
                listed = page.get_by_role("region", name="설비 1개").get_by_role(
                    "link", name="bearing-a"
                )
                pw.expect(listed).to_contain_text("확인할 항목 1건")
                trend = asset.get_by_role("link", name="점수 추이 보기")
                pw.expect(trend).to_have_attribute(
                    "href",
                    "/web-next/?page=assets&tab=anomaly"
                    "&method=model&monitor_asset=bearing-a&model_binding=anomaly-a&model_position=2",
                )

                # A refresh keeps the operator's focus on the same link.
                trend.focus()
                with page.expect_response("**/api/v1/phm/monitor"):
                    pass
                pw.expect(trend).to_be_focused()

                # A changed waveform and a new input appear without reloading the page.
                deliver(workspace, tmp_path / "waves", 3, 3.2)
                (tmp_path / "waves" / "3.csv").write_text("changed after delivery")
                analyze(workspace)
                pw.expect(asset).to_contain_text("최근 진동 파형을 분석하지 못함", timeout=10_000)
                pw.expect(asset).to_contain_text("전달 뒤 원본이 바뀜")
                deliver(workspace, tmp_path / "waves", 4, 0.6)
                pw.expect(asset).to_contain_text("새 입력 분석 대기", timeout=10_000)
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )

                # A failed read never leaves the earlier items looking current.
                page.route(
                    "**/api/v1/phm/monitor", lambda route: route.fulfill(status=503, json={})
                )
                pw.expect(attention).to_contain_text("다시 읽지 못했습니다", timeout=10_000)
                assert attention.get_by_role("article").count() == 0
                page.unroute("**/api/v1/phm/monitor")
                pw.expect(asset).to_be_visible(timeout=10_000)
                attention.get_by_role("button", name="자동 갱신 멈추기").click()
                pw.expect(attention).to_contain_text("자동 갱신을 멈췄습니다")
                assert not errors, errors
            finally:
                browser.close()
    finally:
        stop_web(server, thread)
