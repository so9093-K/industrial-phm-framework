"""A model's score trend, its threshold-exceedance intervals and the raw input it scored."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from tests.support.phm import analyze, deliver, phm_workspace
from tests.support.web_next import asset_list, start_web, stop_web


@pytest.mark.parametrize("width", [390, 1280])
@pytest.mark.parametrize("period", [60, None])
def test_score_trend_intervals_and_raw_waveform(
    tmp_path: Path, width: int, period: int | None
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.6, 0.55, 3.0, 3.2, 0.6), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale, period_seconds=period)
    analyze(workspace)
    # A waveform changed after its result was stored cannot be shown as that input.
    (tmp_path / "waves" / "2.csv").write_text("changed after delivery", encoding="utf-8")
    server, thread = start_web(workspace.root.resolve(), writer=False)
    address = (
        "/web/?page=assets&tab=anomaly&method=model&monitor_asset=bearing-a"
        "&model_binding=anomaly-a&model_position=6"
    )
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
                page.goto(f"http://127.0.0.1:{server.server_port}{address}")
                trend = page.get_by_role("region", name="점수 추이")
                pw.expect(trend).to_contain_text(
                    "분석 6회 · 모델 기준 초과 2회 · 기준 초과 구간 1개"
                )
                pw.expect(trend.get_by_role("img")).to_be_visible()
                # The run of crossings is read first; #6 is below but within the allowed gap.
                onset = trend.get_by_label("기준 초과 상태", exact=True)
                pw.expect(onset).to_contain_text(
                    "측정 순서 #4부터 기준 초과 구간 · 2회 · 최근 측정은 기준 이하"
                )
                pw.expect(trend.locator("line.onset-line")).to_have_count(1)
                if period:
                    pw.expect(onset).to_contain_text("기록 시작 후 3분")
                else:
                    assert "기록 시작 후" not in onset.inner_text()
                intervals = trend.get_by_role("list", name="기준 초과 구간")
                pw.expect(intervals).to_contain_text("측정 순서 #4 ~ 측정 순서 #5 · 2회")

                raw = page.get_by_role("region", name="측정 순서 #6 원본 파형")
                pw.expect(raw.get_by_role("img")).to_have_count(2)
                pw.expect(raw).to_contain_text("표본")

                intervals.get_by_role("button", name="시작 측정 보기").click()
                pw.expect(page.get_by_label("측정 선택 (최근 64회)")).to_have_value("4")
                pw.expect(page.get_by_role("group", name="측정 순서 #4 모델 결과")).to_contain_text(
                    "기준 초과"
                )
                pw.expect(page.get_by_role("region", name="측정 순서 #4 원본 파형")).to_be_visible()

                page.get_by_label("측정 선택 (최근 64회)").select_option("2")
                changed = page.get_by_role("region", name="측정 순서 #2 원본 파형")
                pw.expect(changed).to_contain_text("원본을 보여 줄 수 없습니다")
                assert changed.get_by_role("img").count() == 0
                overlay = page.get_by_role("region", name="모델별 점수 비교", exact=True)
                pw.expect(overlay.locator("line.onset-line")).to_have_count(1)
                # Each model's row says its state in the same words; the graph marks its start.
                pw.expect(
                    overlay.get_by_role("button", name=re.compile("synthetic-rms-score-v1"))
                ).to_contain_text("측정 순서 #4부터 기준 초과 구간 · 2회")
                overlay.get_by_role(
                    "button", name=re.compile("synthetic-vertical-score-v1")
                ).click()
                pw.expect(overlay.locator("line.onset-line")).to_have_count(0)
                overlay.get_by_role("button", name=re.compile("synthetic-rms-score-v1")).click()
                pw.expect(overlay.locator("line.onset-line")).to_have_count(1)
                pw.expect(page).to_have_url(re.compile("model_binding=anomaly-a"))
                if period:

                    def foreign_timing(route):
                        response = route.fetch()
                        body = response.json()
                        body["acquisition"]["source_id"] = "another-stream"
                        route.fulfill(response=response, json=body)

                    page.route("**/api/v1/forecast/options?**", foreign_timing)
                    page.reload()
                    onset = page.get_by_role("region", name="점수 추이").get_by_label(
                        "기준 초과 상태", exact=True
                    )
                    pw.expect(onset).to_contain_text("측정 순서 #4")
                    assert "기록 시작 후" not in onset.inner_text()
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )
                assert not errors, errors
            finally:
                browser.close()
    finally:
        stop_web(server, thread)
