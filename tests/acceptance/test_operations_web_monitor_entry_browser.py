"""The PC entry screen remains actionable while loading and leads with a measured change."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from tests.support.phm import phm_workspace
from tests.support.web_next import asset_list, start_web, stop_web


@pytest.mark.parametrize("width", [1024, 1440])
def test_single_asset_entry_handles_wait_failure_change_and_quiet_records(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    for asset in ("공기압축기 1306", "quiet"):
        history.append_file_batch(
            tuple(
                FileBackfillEvent(
                    raw_evidence_id=f"file:{asset}:{i}",
                    source_id="measured-file",
                    asset_id=asset,
                    channel_id="temperature",
                    source_file="measurements.csv",
                    source_sha256="a" * 64,
                    source_size_bytes=10,
                    sample_index=i,
                    event_at=datetime(2020, 10, 22, tzinfo=UTC) + timedelta(minutes=i),
                    value=65.0 if asset != "quiet" and i >= 100 else 40.0,
                    source_metadata_json='{"binding":{"definition":{"unit":"°C"}}}',
                )
                for i in range(180)
                if asset != "quiet" or not 60 <= i < 120
            ),
            batch_id=asset,
        )
    snapshot = json.loads(asset_list("공기압축기 1306"))
    snapshot["assets"]["items"][0]["last_observed_at"] = "2020-10-22T02:59:00Z"
    mode = {"overview": "hold"}
    running = start_web(workspace.root, writer=False)
    origin = f"http://127.0.0.1:{running[0].server_port}"
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/api/v1/monitor", lambda route: route.fulfill(json=snapshot))
                held = []

                def overview(route):
                    if mode["overview"] == "fail":
                        route.fulfill(status=503)
                    elif mode["overview"] == "ready":
                        route.continue_()
                    else:
                        held.append(route)

                page.route("**/api/v1/explore/overview?**", overview)
                page.goto(origin + "/web/")
                focus = page.get_by_role("article", name="공기압축기 1306 기록 요약")
                pw.expect(focus.get_by_text("과거 저장 기록", exact=True)).to_be_visible()
                pw.expect(focus.get_by_role("status")).to_contain_text("달라진 값을 확인")
                pw.expect(page.get_by_role("heading", name="설비 기록 1개")).to_be_visible()
                pw.expect(page.get_by_role("table", name="설비 비교")).to_have_count(0)
                pw.expect(page.get_by_label("정렬", exact=True)).to_have_count(0)
                records = focus.get_by_role("link", name="신호 기록 보기", exact=False)
                pw.expect(records).to_be_visible()
                assert records.bounding_box()["y"] < 600
                for request in held:
                    request.abort()
                held.clear()
                records.click()
                pw.expect(page.locator(".series").first).to_be_visible(timeout=30000)
                mode["overview"] = "fail"
                page.goto(origin + "/web/")
                pw.expect(focus).to_contain_text("주요 변화를 불러오지 못했습니다", timeout=10000)
                pw.expect(
                    focus.get_by_role("link", name="신호 기록 보기", exact=False)
                ).to_be_visible()
                mode["overview"] = "ready"
                focus.get_by_role("button", name="변화 다시 확인", exact=True).click()
                pw.expect(focus.locator(".values")).to_have_text("40 → 65 °C", timeout=30000)
                pw.expect(focus.locator(".change-trend svg path.trace")).to_have_count(1)
                investigate = focus.get_by_role("link", name="변화 구간 조사하기", exact=False)
                assert investigate.bounding_box()["y"] < 750
                query = parse_qs(
                    urlsplit(investigate.get_attribute("href")).query, keep_blank_values=True
                )
                assert query["monitor_source"] == ["measured-file"]
                assert query["monitor_channel"] == ["temperature"]
                assert (
                    query["monitor_point"] == [""] and len(query["monitor_interpretation"][0]) == 64
                )
                assert "record_key" in query and "monitor_pick" in query
                investigate.click()
                pw.expect(page.locator(".series .pick")).to_be_visible()
                assert parse_qs(urlsplit(page.url).query)["monitor_source"] == ["measured-file"]
                snapshot["assets"]["items"] = json.loads(asset_list("quiet"))["assets"]["items"]
                page.goto(origin + "/web/")
                quiet = page.get_by_role("article", name="quiet 기록 요약")
                pw.expect(quiet).to_contain_text(
                    "크게 달라진 구간을 찾지 못했습니다", timeout=30000
                )
                pw.expect(quiet).to_contain_text("마지막 저장값 40 °C")
                pw.expect(quiet.locator("figure.overview-trend")).to_be_visible()
                assert (
                    quiet.locator("figure.overview-trend path").get_attribute("d").count("M") >= 2
                )
                pw.expect(
                    quiet.get_by_role("link", name="신호 기록 보기", exact=False)
                ).to_be_visible()
                snapshot["assets"]["items"] = []
                page.goto(origin + "/web/")
                start = page.get_by_role("navigation", name="데이터로 시작하는 방법")
                pw.expect(start.get_by_role("link")).to_have_count(3)
                pw.expect(
                    start.get_by_role("link", name="CSV 파일로 시작하기", exact=True)
                ).to_be_visible()
                start.get_by_role("link", name="설비 데이터 수집 연결", exact=True).click()
                pw.expect(page.get_by_label("OPC UA 서버 주소", exact=True)).to_be_visible()
                assert page.locator("#opcua-connect").get_attribute("open") is not None
                assert page.url.endswith("#opcua-connect")
                assert not errors, errors
                assert not page.evaluate("document.documentElement.scrollWidth > innerWidth + 2")
            finally:
                browser.close()
    finally:
        stop_web(*running)
