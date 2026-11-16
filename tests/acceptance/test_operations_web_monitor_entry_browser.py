"""The PC entry screen remains actionable while loading and leads with a measured change."""

from __future__ import annotations

import json
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from tests.support.phm import analyze, deliver, phm_workspace
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


def test_new_history_refreshes_only_its_asset_and_ignores_superseded_overviews(
    tmp_path: Path,
) -> None:
    """Real history/monitor revisions, a held response, and a backfill with the same end time."""
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "refresh", bind=False)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )

    def append(asset: str, source: str, first: int, last: int, value: float) -> None:
        history.append_file_batch(
            tuple(
                FileBackfillEvent(
                    raw_evidence_id=f"file:{asset}:{source}:{i}",
                    source_id=source,
                    asset_id=asset,
                    channel_id="temperature",
                    source_file="measurements.csv",
                    source_sha256="b" * 64,
                    source_size_bytes=10,
                    sample_index=i,
                    event_at=datetime(2020, 10, 22, tzinfo=UTC) + timedelta(minutes=i),
                    value=value,
                    source_metadata_json='{"binding":{"definition":{"unit":"°C"}}}',
                )
                for i in range(first, last)
            ),
            batch_id=f"{asset}:{source}:{first}",
        )

    append("pump-1", "original", 0, 100, 40)
    append("pump-1", "original", 130, 180, 65)
    append("pump-2", "original", 0, 180, 30)
    running = start_web(workspace.root, writer=False)
    origin = f"http://127.0.0.1:{running[0].server_port}"
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                reads: dict[str, int] = {}
                held: list = []
                mode = {"hold": False}

                def overview(route):
                    asset = parse_qs(urlsplit(route.request.url).query)["asset_id"][0]
                    reads[asset] = reads.get(asset, 0) + 1
                    if mode["hold"] and asset == "pump-1":
                        held.append((route, route.fetch().json()))
                    else:
                        route.continue_()

                page.route("**/api/v1/explore/overview?**", overview)
                page.goto(origin + "/web/")
                table = page.get_by_role("table", name="설비 비교")
                one = table.locator(".row").filter(
                    has=page.get_by_role("link", name="pump-1", exact=True)
                )
                two = table.locator(".row").filter(
                    has=page.get_by_role("link", name="pump-2", exact=True)
                )
                pw.expect(one.locator(".latest")).to_have_text("65 °C", timeout=30000)
                pw.expect(two.locator(".latest")).to_have_text("30 °C", timeout=30000)
                pw.expect(one.get_by_role("cell").nth(1)).to_contain_text("2020.")
                # The multi-asset graph uses the same gap rule as the single-asset graph.
                assert one.locator("svg path").get_attribute("d").count("M") >= 2
                initial_two_reads = reads["pump-2"]
                mode["hold"] = True
                append("pump-1", "original", 180, 190, 70)
                pw.expect(one.get_by_role("cell").nth(1)).to_contain_text(
                    "변화 확인 중", timeout=15000
                )
                pw.expect(one.locator(".latest")).to_have_count(0)
                # Let the held read capture the old 70°C result before another receipt arrives.
                for _ in range(100):
                    if held:
                        break
                    page.wait_for_timeout(50)
                assert held
                mode["hold"] = False
                append("pump-1", "original", 190, 200, 80)
                pw.expect(one.locator(".latest")).to_have_text("80 °C", timeout=20000)
                for route, older in held:
                    # The newer revision has already cancelled this request.
                    with suppress(pw.Error):
                        route.fulfill(json=older)
                pw.expect(one.locator(".latest")).to_have_text("80 °C")
                assert reads["pump-2"] == initial_two_reads
                before_backfill = reads["pump-1"]
                # A new source adds older measurements; last_observed_at stays unchanged.
                append("pump-1", "older-source", 0, 30, 20)
                for _ in range(300):
                    if reads["pump-1"] > before_backfill:
                        break
                    page.wait_for_timeout(50)
                assert reads["pump-1"] > before_backfill
                pw.expect(one.locator(".latest")).to_have_text("80 °C", timeout=15000)
                assert reads["pump-2"] == initial_two_reads
                assert not errors
            finally:
                browser.close()
    finally:
        stop_web(*running)


def test_vibration_entry_plots_the_changed_feature_not_the_representative_rms(
    tmp_path: Path,
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "vibration")
    for ordinal in range(1, 31):
        if 11 <= ordinal <= 15:
            continue
        deliver(
            workspace,
            tmp_path / "waves",
            ordinal,
            0.5,
            amplitude_unit="g",
            vertical_scale=1.0 if ordinal < 23 else 5.0,
        )
    analyze(workspace)
    running = start_web(workspace.root, writer=False)
    origin = f"http://127.0.0.1:{running[0].server_port}"
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        body=asset_list("bearing-a"), content_type="application/json"
                    ),
                )
                row = page.request.get(
                    origin + "/api/v1/explore/overview?asset_id=bearing-a"
                ).json()
                assert row["main"]["label"] == "수평 진동 RMS"
                change = row["vibration_interval"]
                assert change["feature"] == "feature.Vertical_vibration_signals.rms"
                assert change["binding_id"] == "anomaly-a" and change["source_id"] == "bench"
                page.goto(origin + "/web/")
                focus = page.get_by_role("article", name="bearing-a 기록 요약")
                pw.expect(focus.get_by_role("heading", level=4)).to_contain_text(
                    "수직 진동 RMS", timeout=30000
                )
                figure = focus.get_by_role("figure", name="수직 진동 RMS 기록 추이")
                pw.expect(figure).to_be_visible()
                pw.expect(figure.locator("svg circle")).to_have_count(len(change["trace"]))
                assert figure.locator("svg path").get_attribute("d").count("M") == 2
                assert float(figure.locator("svg rect.interval").get_attribute("width")) > 0
                investigate = focus.get_by_role("link", name="변화 구간 조사하기", exact=False)
                query = parse_qs(urlsplit(investigate.get_attribute("href")).query)
                assert query["vibration_feature"] == [change["feature"]]
                assert query["vibration_at"] == [str(change["from"])]
                investigate.click()
                pw.expect(page.get_by_label("진동 특징", exact=False)).to_have_value(
                    change["feature"], timeout=30000
                )
                pw.expect(page.get_by_role("region", name="선택한 측정")).to_contain_text(
                    "23번째 측정"
                )
                assert not errors
            finally:
                browser.close()
    finally:
        stop_web(*running)
