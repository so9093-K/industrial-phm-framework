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
                    source_id=asset + "-source",
                    asset_id=asset,
                    channel_id="temperature",
                    source_file=asset + ".csv",
                    source_sha256="a" * 64,
                    source_size_bytes=10,
                    sample_index=i,
                    event_at=datetime(2026, 11, 1, tzinfo=UTC) + timedelta(minutes=i),
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
                assert operations.get_attribute("open") is None
                assert assets.bounding_box()["y"] < operations.bounding_box()["y"]
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
                        pw.expect(fit).to_contain_text("추세 판단을 보류하세요")
                        assert chart.bounding_box()["y"] < fit.bounding_box()["y"]
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+2")
            finally:
                browser.close()
    finally:
        stop_web(*running)
