"""Discovery stays useful without changes; outlook controls describe the shown result."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.acceptance.test_operations_web_forecast_settings_browser import _store_history
from tests.support.phm import analyze, deliver, phm_workspace
from tests.support.web_next import InProcessSupervisor, asset_list, start_web, stop_web


@pytest.mark.parametrize("width", [390, 1280])
def test_asset_first_monitor_quiet_record_and_public_data_preparation(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    for asset in ("stable", "changing"):
        history.append_file_batch(
            tuple(
                FileBackfillEvent(
                    raw_evidence_id=f"file:{asset}:{i}",
                    source_id="aihub239-training-1306-1"
                    if asset == "changing"
                    else asset + "-source",
                    asset_id=asset,
                    channel_id="temperature",
                    source_file=asset + ".csv",
                    source_sha256="a" * 64,
                    source_size_bytes=10,
                    sample_index=i,
                    event_at=datetime(2020, 10, 22, tzinfo=UTC) + timedelta(minutes=i),
                    value=65.0 if asset == "changing" and i >= 100 else 40.0,
                    source_metadata_json='{"binding":{"definition":{"unit":"°C"}}}',
                )
                for i in range(180)
            ),
            batch_id=asset,
        )
    snapshot = json.loads(asset_list("stable", "changing"))
    # Three operating checks plus one pending model must not outrank an actual change.
    stable = snapshot["assets"]["items"][0]
    stable["attention_count"] = 3
    model = {
        "binding_id": "stable-model",
        "asset_id": "stable",
        "step_kind": "history-window",
        "recipe_id": None,
        "processing_state": "pending",
        "latest_analyzed": None,
        "latest_processed": None,
    }
    phm = {"schema_version": 1, "items": [model], "truncated": False}
    monitor_failed = False
    snapshot["attention"] = {
        "truncated": False,
        "items": [
            {
                "attention_id": f"service-{i}",
                "title": f"service {i}",
                "code": "analysis-service-not-running",
                "status": "open",
                "destination": "system",
                "asset_id": None,
                "source_id": None,
                "finding_id": None,
                "occurred_at": None,
            }
            for i in range(12)
        ],
    }
    running = start_web(workspace.root, writer=False)
    origin = f"http://127.0.0.1:{running[0].server_port}"
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/api/v1/monitor", lambda route: route.fulfill(json=snapshot))
                page.route(
                    "**/api/v1/phm/monitor",
                    lambda route: (
                        route.fulfill(status=503) if monitor_failed else route.fulfill(json=phm)
                    ),
                )
                page.route(
                    "**/api/v1/datasets",
                    lambda route: route.fulfill(
                        json={
                            "schema_version": 1,
                            "available": True,
                            "can_import": False,
                            "items": [],
                            "jobs": {},
                            "meaning": (
                                "public-datasets-found-in-the-datasets-folder-not-imported-evidence"
                            ),
                        }
                    ),
                )
                page.goto(origin + "/web/")
                assets = page.locator('section[aria-labelledby="asset-list-title"]')
                operations = page.locator("details.monitor-operations")
                pw.expect(assets.locator(".row").first).to_contain_text("changing", timeout=30000)
                pw.expect(assets.locator(".primary-reason").first).to_be_visible()
                rows = assets.locator(".row")
                pw.expect(rows.first).to_contain_text("확인할 항목 1건")
                pw.expect(rows.nth(1)).to_contain_text("확인할 항목 4건")
                pw.expect(rows.first).to_contain_text("과거 저장 기록")
                pw.expect(rows.first.locator(".primary-reason")).to_contain_text("temperature")
                pw.expect(page.locator(".meta").first).to_contain_text("목록 확인 시각")
                direct = rows.first.get_by_role("link", name="변화 구간 조사하기", exact=False)
                picked = parse_qs(
                    urlsplit(direct.get_attribute("href")).query, keep_blank_values=True
                )
                assert picked["tab"] == ["signals"] and picked["monitor_channel"] == ["temperature"]
                assert picked["monitor_source"] == ["aihub239-training-1306-1"]
                assert (
                    picked["monitor_point"] == [""]
                    and len(picked["monitor_interpretation"][0]) == 64
                )
                assert picked["monitor_range"] == ["window"]
                assert picked["monitor_pick"][0].startswith("2020-")
                assert operations.get_attribute("open") is None
                assert assets.bounding_box()["y"] < operations.bounding_box()["y"]
                assets.locator(".row-details summary").first.click()
                assets.locator(".reason-link").first.click()
                pw.expect(page.locator("#attention-changing")).to_be_visible()
                assert operations.get_attribute("open") is not None
                # At equal importance the larger count wins, then the server's original order.
                model.update(
                    processing_state="processed",
                    latest_analyzed={"position": 5, "output": {"exceeds_threshold": True}},
                    open_interval={"start_position": 3, "step_count": 3},
                )
                page.reload()
                pw.expect(rows.first).to_contain_text("stable")
                pw.expect(rows.first).to_contain_text("확인할 항목 4건")
                stable["attention_count"] = 0
                snapshot["assets"]["items"].reverse()
                page.reload()
                pw.expect(rows.first).to_contain_text("changing")
                pw.expect(rows.first).to_contain_text("확인할 항목 1건")
                pw.expect(rows.nth(1)).to_contain_text("확인할 항목 1건")
                # Server-confirmed operating checks without a primary note still count.
                operating = json.loads(asset_list("operating"))["assets"]["items"][0]
                operating["attention_count"] = 4
                snapshot["assets"]["items"].append(operating)
                page.reload()
                # The signal change and model crossing remain ahead of these four checks.
                pw.expect(rows.nth(2)).to_contain_text("operating")
                pw.expect(rows.nth(2)).to_contain_text("확인할 항목 4건")
                model["processing_state"] = "pending"
                page.reload()
                pw.expect(rows.first).to_contain_text("changing")
                pw.expect(rows.nth(1)).to_contain_text("operating")
                pw.expect(rows.nth(1)).to_contain_text("확인할 항목 4건")
                pw.expect(rows.nth(1).locator(".primary-reason")).to_have_count(0)
                pw.expect(rows.nth(2)).to_contain_text("stable")
                pw.expect(rows.nth(2)).to_contain_text("확인할 항목 1건")
                snapshot["assets"]["items"].pop()
                # A failed read clears old reasons; only counts and source order remain.
                monitor_failed = True
                stable["attention_count"] = 3
                page.reload()
                pw.expect(rows.first).to_contain_text("stable")
                pw.expect(rows.first).to_contain_text("일부 미확인")
                pw.expect(assets.locator(".primary-reason")).to_have_count(0)
                # A partial read keeps the importance of the reasons it actually returned.
                monitor_failed = False
                model["processing_state"] = "pending"
                phm["truncated"] = True
                page.reload()
                pw.expect(rows.first).to_contain_text("changing")
                pw.expect(rows.first).to_contain_text("최소 1건 · 일부 미확인")
                page.unroute("**/api/v1/phm/monitor")
                rows.first.get_by_role("link", name="변화 구간 조사하기", exact=False).click()
                series = page.locator(".series")
                pw.expect(series).to_have_count(1)
                pw.expect(series.locator("svg").first).to_be_visible()
                pw.expect(page.locator(".pick")).to_be_visible()
                restored_pick = parse_qs(urlsplit(page.url).query)["monitor_pick"]
                page.reload()
                pw.expect(page.locator(".pick")).to_be_visible()
                assert parse_qs(urlsplit(page.url).query)["monitor_pick"] == restored_pick
                pw.expect(series.locator(".source-name")).to_have_text(
                    "AI-Hub 239 공개 실측 데이터"
                )
                source_details = series.locator(".source-identity details")
                assert source_details.get_attribute("open") is None
                pw.expect(source_details.get_by_text("지정되지 않음", exact=True)).to_be_hidden()
                source_details.locator("summary").click()
                pw.expect(
                    source_details.get_by_text("aihub239-training-1306-1", exact=True)
                ).to_be_visible()
                pw.expect(source_details.get_by_text("지정되지 않음", exact=True)).to_be_visible()
                page.goto(origin + "/web/?page=assets&monitor_asset=stable")
                quiet = page.get_by_role("region", name="변화가 없는 기록 살펴보기")
                pw.expect(quiet).to_contain_text("마지막 구간 평균 40 °C")
                pw.expect(quiet).to_contain_text("구간별 평균의 범위 40 ~ 40 °C")
                link = quiet.get_by_role("link", name="원본 신호 추세 보기", exact=False)
                query = parse_qs(urlsplit(link.get_attribute("href")).query, keep_blank_values=True)
                assert query["monitor_source"] == ["stable-source"] and query["monitor_point"] == [
                    ""
                ]
                link.click()
                pw.expect(
                    page.get_by_role("region", name="측정 기록 · stable-source", exact=True)
                ).to_be_visible()
                snapshot["assets"]["items"] = []
                page.goto(origin + "/web/")
                assert page.locator("details.start-guide").get_attribute("open") is None
                pw.expect(page.locator(".guide")).to_be_hidden()
                pw.expect(
                    page.get_by_role("link", name="CSV 파일로 시작하기", exact=True)
                ).to_be_visible()
                page.get_by_role("link", name="공개 실측 데이터 준비 방법", exact=True).click()
                preparation = page.get_by_role("region", name="공개 실측 데이터로 시작", exact=True)
                pw.expect(preparation).to_contain_text("data/raw/aihub/239/archives/*/raw/*.zip")
                pw.expect(preparation).to_contain_text(
                    "data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets/"
                )
                pw.expect(
                    preparation.get_by_role("link", name="데이터 준비 방법", exact=False)
                ).to_have_attribute(
                    "href",
                    "https://github.com/so9093-K/industrial-phm-framework/blob/main/data/README.md",
                )
                pw.expect(
                    preparation.get_by_role("button", name="준비한 데이터 다시 찾기", exact=True)
                ).to_be_visible()
                assert not errors
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+2")
            finally:
                browser.close()
    finally:
        stop_web(*running)


@pytest.mark.parametrize("width", [390, 1280])
def test_outlook_primary_controls_and_one_primary_review_action(tmp_path: Path, width: int) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("prophet")
    workspace = phm_workspace(tmp_path / "ws")
    _store_history(workspace, minutes=120)
    for ordinal in range(1, 65):
        deliver(workspace, tmp_path / "waves", ordinal, 0.5 + ordinal / 100)
    analyze(workspace)
    client = InProcessSupervisor(workspace.root)
    server = create_operations_web_read_server(workspace.root, command_client=client)  # type: ignore[arg-type]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        json=json.loads(asset_list("motor-01", "bearing-a"))
                    ),
                )
                query = {
                    "page": "assets",
                    "monitor_asset": "motor-01",
                    "tab": "outlook",
                    "data": "history",
                    "monitor_channel": "current",
                }
                page.goto(origin + "/web/?" + urlencode(query))
                panel = page.get_by_role("region", name="추세·기준 도달 전망")
                result = panel.get_by_role("heading", name="기록 마지막 시점 기준 전망", exact=True)
                pw.expect(result).to_be_visible(timeout=60000)
                pw.expect(panel.locator("#projection-horizon")).to_be_visible()
                advanced = panel.locator("details.calculation-options")
                assert advanced.get_attribute("open") is None
                pw.expect(panel.get_by_label("추세 민감도", exact=False)).to_be_hidden()
                panel.locator("#projection-horizon").select_option("24h")
                pw.expect(result).to_have_count(0)
                with page.expect_response("**/api/v1/forecast?**", timeout=60000) as response:
                    panel.get_by_role("button", name="계산하기", exact=True).click()
                assert response.value.json()["horizon"] == "24h"
                pw.expect(result).to_be_visible(timeout=60000)
                pw.expect(panel.locator(".result-head")).to_contain_text("예측 24시간")
                headline = panel.locator(".outlook-summary").inner_text()
                pw.expect(panel.get_by_text(headline, exact=True)).to_have_count(1)
                pw.expect(panel.locator(".message .headline")).to_have_count(0)
                chart = panel.locator("figure.chart")
                fit = panel.get_by_role("region", name="예측 시작값과 검증 상태")
                assert chart.bounding_box()["y"] < fit.bounding_box()["y"]
                assert (
                    chart.bounding_box()["y"]
                    < panel.get_by_role("region", name="이 분석에서 알 수 있는 것").bounding_box()[
                        "y"
                    ]
                )
                panel.get_by_text("검토 기록에 남기기 (선택)", exact=True).click()
                review = panel.locator(".review-request")
                pw.expect(
                    review.get_by_role("button", name="판단 저장", exact=True)
                ).to_be_visible()
                pw.expect(review.locator("button.ui-button-primary")).to_have_count(1)
                assert "ui-button-primary" not in review.get_by_role(
                    "button", name="결과만 저장", exact=True
                ).get_attribute("class")
                review.get_by_role("radio", name="계속 관찰").check()
                review.get_by_role("button", name="판단 저장", exact=True).click()
                pw.expect(review).to_contain_text("현재 판단 · 계속 관찰", timeout=60000)
                page.reload()
                pw.expect(result).to_be_visible(timeout=60000)
                panel.get_by_text("검토 기록에 남기기 (선택)", exact=True).click()
                pw.expect(review).to_contain_text("현재 판단 · 계속 관찰", timeout=60000)
                query.update(monitor_asset="bearing-a", data="vibration", acq_forecast_count="3")
                query.pop("monitor_channel")
                page.goto(origin + "/web/?" + urlencode(query))
                result = panel.get_by_role("heading", name="기록 마지막 측정 기준 전망", exact=True)
                pw.expect(result).to_be_visible(timeout=60000)
                count = panel.get_by_label("앞으로 볼 측정 횟수", exact=False)
                pw.expect(count).to_be_visible()
                assert panel.locator("details.calculation-options").get_attribute("open") is None
                count.fill("5")
                with page.expect_response("**/api/v1/forecast?**", timeout=60000) as response:
                    panel.get_by_role("button", name="계산하기", exact=True).click()
                assert response.value.json()["horizon_count"] == 5
                pw.expect(result).to_be_visible(timeout=60000)
                pw.expect(panel.locator(".message .headline")).to_have_count(0)
                assert not errors
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+2")
            finally:
                browser.close()
    finally:
        stop_web(server, thread)
        shutil.rmtree(Path(client.socket_path).parent)


@pytest.mark.parametrize("width", [390, 1280])
@pytest.mark.parametrize("kind", ["history", "vibration"])
def test_less_accurate_forecast_warns_before_reach_tiles_and_chart(
    tmp_path: Path, width: int, kind: str
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("prophet")
    workspace = phm_workspace(tmp_path / "ws", bind=kind == "vibration")
    if kind == "history":
        _store_history(workspace)
    else:
        for ordinal in range(1, 65):
            deliver(workspace, tmp_path / "waves", ordinal, 0.5 + ordinal / 100)
        analyze(workspace)
    running = start_web(workspace.root, writer=False)
    origin = f"http://127.0.0.1:{running[0].server_port}"
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        json=json.loads(asset_list("motor-01", "bearing-a"))
                    ),
                )
                worse = True

                def forecast(route):
                    # Keep the real prediction; control only the error comparison for this UI case.
                    response = route.fetch(timeout=60000)
                    body = response.json()
                    body["backtest"]["mean_absolute_error"] = 2 if worse else 0.5
                    body["backtest"]["naive_mean_absolute_error"] = 1
                    route.fulfill(response=response, json=body)

                page.route("**/api/v1/forecast?**", forecast)
                query = {
                    "page": "assets",
                    "monitor_asset": "motor-01" if kind == "history" else "bearing-a",
                    "tab": "outlook",
                    "data": kind,
                    "monitor_channel": "current",
                    "acq_forecast_count": "3",
                }
                prefix = "projection" if kind == "history" else "acq"
                panel = page.get_by_role("region", name="추세·기준 도달 전망")
                for worse, limited in ((True, True), (True, False), (False, True)):
                    for name, value in (("management", "12"), ("end", "14")):
                        query.pop(f"{prefix}_{name}", None)
                        if limited:
                            query[f"{prefix}_{name}"] = value
                    page.goto(origin + "/web/?" + urlencode(query))
                    chart = panel.locator("figure.chart")
                    pw.expect(chart).to_be_visible(timeout=60000)
                    caution = panel.locator(".forecast-caution")
                    pw.expect(caution).to_have_count(1 if worse else 0)
                    if worse:
                        pw.expect(caution).to_contain_text("추세 판단을 보류하세요")
                        assert (
                            panel.locator(".result-head").bounding_box()["y"]
                            < caution.bounding_box()["y"]
                            < chart.bounding_box()["y"]
                        )
                        if limited:
                            assert (
                                caution.bounding_box()["y"]
                                < panel.locator(".tiles").bounding_box()["y"]
                            )
                        fit = panel.get_by_role("region", name="예측 시작값과 검증 상태")
                        pw.expect(fit).to_contain_text("모델의 오차가 더 컸습니다")
                        assert chart.bounding_box()["y"] < fit.bounding_box()["y"]
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+2")
            finally:
                browser.close()
    finally:
        stop_web(*running)


@pytest.mark.parametrize("width", [390, 1280])
def test_stored_reviews_stay_reachable_when_their_count_cannot_be_read(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    snapshot = json.loads(asset_list("motor-01"))
    index: dict[str, object] = {"status": 503}

    def reviews(route: object) -> None:
        if index["status"] != 200:
            route.fulfill(status=503)  # type: ignore[attr-defined]
            return
        ids = index["ids"]
        route.fulfill(  # type: ignore[attr-defined]
            json={
                "schema_version": 1,
                "meaning": "stored-human-review-asset-identities-not-health",
                "asset_ids": ids,
                "total_assets": len(ids),  # type: ignore[arg-type]
                "revision": "a" * 64,
                "next_after": None,
            }
        )

    running = start_web(workspace.root, writer=False)
    origin = f"http://127.0.0.1:{running[0].server_port}"
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                page.route("**/api/v1/monitor", lambda route: route.fulfill(json=snapshot))
                page.route("**/api/v1/review-inbox/assets**", reviews)
                entry = page.locator(".review-entry")
                # The list failed: the way in stays, and the count is unknown rather than zero.
                page.goto(origin + "/web/")
                pw.expect(entry).to_contain_text(
                    "저장한 검토 건수를 확인하지 못했습니다", timeout=30000
                )
                link = entry.get_by_role("link", name="정비 검토함 열기 →")
                assert parse_qs(urlsplit(link.get_attribute("href")).query)["page"] == [
                    "maintenance"
                ]
                index.update(status=200, ids=[])
                page.reload()
                pw.expect(entry).to_have_text("정비 검토함 열기 →", timeout=30000)
                pw.expect(entry.get_by_role("link", name="정비 검토함 열기 →")).to_be_visible()
                index.update(ids=["motor-01", "motor-02"])
                page.reload()
                pw.expect(entry).to_contain_text("저장한 검토가 있는 설비 2곳", timeout=30000)
            finally:
                browser.close()
    finally:
        stop_web(*running)


@pytest.mark.parametrize("width", [390, 1280])
def test_priority_stays_global_and_a_change_leads_to_its_operating_context(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    history.append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:conditions:{channel}:{i}",
                source_id="compressor-file",
                asset_id="공기압축기 1",
                channel_id=channel,
                source_file="conditions.csv",
                source_sha256="c" * 64,
                source_size_bytes=10,
                sample_index=offset * 1000 + i,
                event_at=datetime(2020, 10, 22, tzinfo=UTC) + timedelta(minutes=i),
                value=((60 if i < 90 else 30) + (i % 3) * 0.5)
                if channel == "전류"
                else ((0.95 if i < 40 else 0.6) + (i % 4) * 0.005),
                source_metadata_json=json.dumps(
                    {
                        "binding": {
                            "definition": {
                                "observed_property": "electric current"
                                if channel == "전류"
                                else "power factor",
                                "unit": "A" if channel == "전류" else None,
                            }
                        }
                    }
                ),
            )
            for offset, channel in enumerate(("전류", "역률"))
            for i in range(120)
        ),
        batch_id="conditions",
    )
    snapshot = json.loads(asset_list("공기압축기 3", "펌프 2", "공기압축기 1"))
    snapshot["assessed_at"] = "2026-11-16T00:00:00Z"
    snapshot["assets"]["items"][2]["last_observed_at"] = "2020-10-22T01:59:00Z"
    phm = {
        "schema_version": 1,
        "truncated": False,
        "items": [
            {
                "binding_id": asset,
                "asset_id": asset,
                "step_kind": "history-window",
                "recipe_id": None,
                "processing_state": state,
                "latest_analyzed": None,
                "latest_processed": None,
            }
            for asset, state in (("공기압축기 3", "pending"), ("펌프 2", "rejected"))
        ],
    }
    running = start_web(workspace.root, writer=False)
    origin = f"http://127.0.0.1:{running[0].server_port}"
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route("**/api/v1/monitor", lambda route: route.fulfill(json=snapshot))
                page.route("**/api/v1/phm/monitor", lambda route: route.fulfill(json=phm))
                page.goto(origin + "/web/")
                rows = page.locator(".table .row")
                pw.expect(rows.nth(0).locator(".asset")).to_contain_text("공기압축기 1")
                pw.expect(rows.nth(1).locator(".asset")).to_contain_text("펌프 2")
                pw.expect(rows.nth(2).locator(".asset")).to_contain_text("공기압축기 3")
                pw.expect(rows.first.locator(".finding")).to_contain_text("역률", timeout=30000)
                pw.expect(rows.first.locator(".bar")).to_be_hidden()
                rows.first.get_by_text("운전·확인 상세", exact=True).click()
                pw.expect(rows.first.locator(".bar")).to_be_visible()
                options = page.locator(".view-options")
                pw.expect(options).not_to_have_attribute("open", "")
                pw.expect(page.get_by_role("checkbox", name="종류별로 묶기")).to_be_hidden()
                options.locator("summary").focus()
                page.keyboard.press("Enter")
                page.get_by_role("checkbox", name="종류별로 묶기").check()
                pw.expect(rows.nth(1).locator(".asset")).to_contain_text("공기압축기 3")
                pw.expect(rows.nth(2).locator(".asset")).to_contain_text("펌프 2")
                page.get_by_role("checkbox", name="종류별로 묶기").uncheck()
                inspect = rows.first.locator(".finding")
                target = parse_qs(
                    urlsplit(inspect.get_attribute("href")).query, keep_blank_values=True
                )
                assert target["tab"] == ["signals"] and target["monitor_source"] == [
                    "compressor-file"
                ]
                inspect.click()
                pw.expect(page.locator(".series").first).to_be_visible(timeout=30000)
                assert parse_qs(urlsplit(page.url).query)["monitor_source"] == ["compressor-file"]
                with page.expect_response("**/api/v1/explore/findings?**") as response:
                    page.get_by_role("navigation", name="설비 화면").get_by_role(
                        "link", name="상태 요약", exact=True
                    ).click()
                finding = response.value.json()["intervals"][0]
                card = page.locator(".found > li").first
                pw.expect(card.get_by_role("heading", level=3)).to_contain_text("역률")
                context = card.get_by_role("complementary", name="이 변화의 해석과 다음 확인")
                pw.expect(context).to_contain_text("때의 측정끼리 비교해 찾은 변화")
                page.get_by_text("측정 현황·데이터 출처·계산 범위", exact=True).click()
                op = page.locator("details.operation-details")
                assert op.get_attribute("open") is None
                pw.expect(op.locator(".operation")).to_be_hidden()
                op.locator("summary").first.click()
                pw.expect(op.locator(".operation")).to_be_visible()
                assert card.bounding_box()["y"] < op.bounding_box()["y"]
                compare = context.get_by_role(
                    "link", name="같은 운전 수준으로 두 기간 비교", exact=False
                )
                scope = parse_qs(
                    urlsplit(compare.get_attribute("href")).query, keep_blank_values=True
                )
                assert scope["compare_level"] == [str(finding["band"])]
                assert scope["monitor_source"] == ["compressor-file"] and scope[
                    "monitor_point"
                ] == [""]
                assert len(scope["monitor_interpretation"][0]) == 64
                compare.click()
                pw.expect(
                    page.get_by_text("중에 측정된 값끼리 비교합니다", exact=False)
                ).to_be_visible()
                comparison = page.locator(".compare")
                pw.expect(comparison.locator(".primary-insight").first).to_contain_text(
                    "0.955 → 0.605"
                )
                pw.expect(comparison.get_by_role("group", name="현재 비교 기간")).to_be_visible()
                conditions = comparison.locator("details.conditions")
                if width < 1100:
                    assert conditions.get_attribute("open") is None
                else:
                    pw.expect(conditions.locator("input").first).to_be_visible()
                    assert (
                        comparison.locator(".analysis-sidebar").bounding_box()["x"]
                        > comparison.locator(".analysis-body").bounding_box()["x"]
                    )
                distribution = comparison.locator("details.operation-distribution")
                assert distribution.get_attribute("open") is None
                assert (
                    comparison.locator(".series").first.bounding_box()["y"]
                    < distribution.bounding_box()["y"]
                )
                assert not errors, errors
                assert not page.evaluate("document.documentElement.scrollWidth>innerWidth+2")
            finally:
                browser.close()
    finally:
        stop_web(*running)


@pytest.mark.parametrize("width", [390, 1280])
@pytest.mark.parametrize("flat", [False, True])
def test_relation_leads_with_the_change_at_the_same_input_level(
    tmp_path: Path, width: int, flat: bool
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    base = datetime(2020, 10, 1, tzinfo=UTC)
    history.append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:relation:{channel}:{period}:{i}",
                source_id="paired",
                asset_id="pump",
                channel_id=channel,
                source_file="paired.csv",
                source_sha256="d" * 64,
                source_size_bytes=10,
                sample_index=offset * 10000 + period * 1000 + i,
                event_at=base + timedelta(days=period, minutes=i),
                value=float(i % 10)
                if channel == "x"
                else float((2 if flat else 2 * (i % 10)) + period * 5),
                source_metadata_json="{}",
            )
            for offset, channel in enumerate(("x", "y"))
            for period in (0, 1)
            for i in range(400)
        ),
        batch_id="paired",
    )
    running = start_web(workspace.root, writer=False)
    origin = f"http://127.0.0.1:{running[0].server_port}"
    query = {
        "page": "assets",
        "monitor_asset": "pump",
        "tab": "change",
        "method": "relation",
        "data": "history",
        "relation_x": "x",
        "relation_y": "y",
        "compare_a": base.isoformat() + "~" + (base + timedelta(minutes=400)).isoformat(),
        "compare_b": (base + timedelta(days=1)).isoformat()
        + "~"
        + (base + timedelta(days=1, minutes=400)).isoformat(),
    }
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(json=json.loads(asset_list("pump"))),
                )
                page.goto(origin + "/web/?" + urlencode(query))
                group = page.locator(".relation .group")
                pw.expect(group.locator(".primary-insight")).to_contain_text("y ·", timeout=30000)
                pw.expect(group.locator(".primary-context")).to_contain_text("x")
                conditions = page.locator(".relation details.conditions")
                assert (conditions.get_attribute("open") is not None) == (width >= 1100)
                pw.expect(page.get_by_role("group", name="현재 관계 비교 기간")).to_be_visible()
                pw.expect(group.locator(".coefficients dl").first).to_be_hidden()
                if width < 1100:
                    conditions.locator("summary").first.click()
                else:
                    graph = group.locator("svg").first.bounding_box()
                    sidebar = page.locator(".relation .analysis-sidebar").bounding_box()
                    assert graph and sidebar and sidebar["x"] >= graph["x"] + graph["width"]
                    assert graph["y"] + graph["height"] <= 900
                page.locator("#relation-y").select_option("x")
                pw.expect(group).to_have_count(0)
                page.locator("#relation-y").select_option("y")
                page.get_by_role("button", name="관계 계산하기").click()
                pw.expect(group.locator(".primary-insight")).to_contain_text("y ·")
                if flat:
                    pw.expect(group.locator(".coefficient-summary")).to_have_count(0)
                    pw.expect(group.locator(".message")).to_contain_text(
                        "기간 A 40개 · 기간 B 40개"
                    )
                else:
                    assert group.locator(".coefficient-summary").get_attribute("open") is None
                    pw.expect(group.locator(".coefficient-summary p").first).to_be_hidden()
                    group.locator(".coefficient-summary summary").click()
                    pw.expect(group.locator(".coefficient-summary p").first).to_be_visible()
                assert not page.evaluate("document.documentElement.scrollWidth>innerWidth+2")
            finally:
                browser.close()
    finally:
        stop_web(*running)


@pytest.mark.parametrize("width", [390, 1280])
def test_waterfall_selection_uses_the_original_measurement_in_one_comparison_period(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal in (2, 7, 11):
        deliver(workspace, tmp_path / "waves", ordinal, 0.5 + ordinal / 10)
    analyze(workspace)
    running = start_web(workspace.root, writer=False)
    origin = f"http://127.0.0.1:{running[0].server_port}"
    query = {"page": "assets", "tab": "change", "method": "spectrum", "monitor_asset": "bearing-a"}
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(json=json.loads(asset_list("bearing-a"))),
                )
                page.goto(origin + "/web/?" + urlencode(query))
                selection = page.get_by_role("group", name="선택한 측정으로 주파수 비교")
                pw.expect(selection).to_be_visible(timeout=30000)
                canvas = page.locator(".waterfall canvas").first
                canvas.focus()
                canvas.press("ArrowDown")
                pw.expect(selection.locator("select")).to_have_value("7")
                with page.expect_response("**/api/v1/explore/spectrum?**") as response:
                    selection.get_by_role("button", name="기간 B로 사용").click()
                requested = parse_qs(urlsplit(response.value.url).query)
                assert requested["a_from"] == ["2"] and requested["a_to"] == ["4"]
                assert requested["b_from"] == ["7"] and requested["b_to"] == ["7"]
                assert response.value.ok
                pw.expect(page.locator(".spectra p[role=status]").first).to_contain_text(
                    "7번째 측정"
                )
                canvas.click(position={"x": 20, "y": 179})
                pw.expect(selection.locator("select")).to_have_value("11")
                with page.expect_response("**/api/v1/explore/spectrum?**") as response:
                    selection.get_by_role("button", name="기간 A로 사용").click()
                requested = parse_qs(urlsplit(response.value.url).query)
                assert requested["a_from"] == ["11"] and requested["a_to"] == ["11"]
                assert requested["b_from"] == ["7"] and requested["b_to"] == ["7"]
                assert response.value.ok
                pw.expect(page.locator(".spectra p[role=status]").first).to_contain_text(
                    "11번째 측정"
                )
                page.reload()
                pw.expect(selection).to_be_visible()
                saved = parse_qs(urlsplit(page.url).query)
                assert saved["spectrum_a_from"] == ["11"] and saved["spectrum_a_to"] == ["11"]
                assert saved["spectrum_b_from"] == ["7"] and saved["spectrum_b_to"] == ["7"]
                assert not errors, errors
                assert not page.evaluate("document.documentElement.scrollWidth>innerWidth+2")
            finally:
                browser.close()
    finally:
        stop_web(*running)


@pytest.mark.parametrize("width", [390, 1280])
def test_three_phases_can_be_added_without_opening_companion_settings(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    for channel in ("R상전류", "S상전류", "T상전류", "other-a", "other-b", "other-c", "other-d"):
        _store_history(workspace, channel=channel, count=60)
    running = start_web(workspace.root, writer=False)
    origin = f"http://127.0.0.1:{running[0].server_port}"
    query = {
        "page": "assets",
        "tab": "signals",
        "monitor_asset": "motor-01",
        "monitor_channel": "R상전류",
        "monitor_with": "other-a,other-b,other-c,other-d,S상전류",
    }
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900})
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(json=json.loads(asset_list("motor-01"))),
                )
                page.goto(origin + "/web/?" + urlencode(query))
                direct = page.get_by_role("button", name="R·S·T 3상 함께 보기", exact=True)
                pw.expect(direct).to_be_visible(timeout=30000)
                assert page.locator("details.with").get_attribute("open") is None
                direct.click()
                for phase in ("S상전류", "T상전류"):
                    pw.expect(page.locator(".companions h4").filter(has_text=phase)).to_be_visible()
                chosen = parse_qs(urlsplit(page.url).query)["monitor_with"][0].split(",")
                assert {"S상전류", "T상전류"}.issubset(chosen) and len(chosen) <= 5
                assert not page.evaluate("document.documentElement.scrollWidth>innerWidth+2")
            finally:
                browser.close()
    finally:
        stop_web(*running)
