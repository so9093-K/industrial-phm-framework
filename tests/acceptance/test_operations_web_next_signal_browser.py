"""Isolated signal investigation retains source semantics, without fabricating readings."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.web_next import choose_asset, expect_place


@pytest.mark.parametrize("width", [390, 1024])
def test_web_next_signal_history_preserves_context_and_quality(tmp_path: Path, width: int) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "signals")
    initialize_operations_workspace(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                monitor = {
                    "assessed_at": "2026-10-12T00:00:00Z",
                    "assets": {
                        "items": [
                            {
                                "asset_id": "motor-a",
                                "data_flow_status": "stored-history",
                                "last_data_at": "2026-10-12T00:00:00Z",
                                "attention_count": 0,
                            },
                            {
                                "asset_id": "motor-b",
                                "data_flow_status": "waiting",
                                "last_data_at": None,
                                "attention_count": None,
                            },
                        ],
                        "total": 2,
                        "truncated": False,
                    },
                    "system_error_scopes": [],
                }
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(monitor)
                    ),
                )

                def channels(route):
                    asset = parse_qs(urlsplit(route.request.url).query)["asset_id"][0]
                    result = {
                        "asset_id": asset,
                        "channels": {
                            "items": ["R"] if asset == "motor-a" else [],
                            "total": 1 if asset == "motor-a" else 0,
                            "truncated": False,
                        },
                    }
                    route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(result)
                    )

                def trend(route):
                    params = parse_qs(urlsplit(route.request.url).query)
                    assert params["asset_id"] == ["motor-a"]
                    assert params["channel_id"] == ["R"]
                    assert params["anchor"] == ["latest"]
                    start = "2026-10-11T23:00:00Z"
                    bucket = {
                        "channel_id": "R",
                        "source_id": "source-1",
                        "measurement_point_id": "motor-winding",
                        "interpretation_id": "interpreted-A",
                        "semantics": {"unit": "A", "observed_property": "current"},
                        "bucket_start": "2026-10-11T23:01:00Z",
                        "mean": 1.5,
                        "usable_count": 2,
                        "null_count": 0,
                        "non_good_count": 0,
                        "conflict_count": 0,
                    }
                    bad = {
                        **bucket,
                        "bucket_start": "2026-10-11T23:02:00Z",
                        "mean": None,
                        "usable_count": 0,
                        "null_count": 1,
                    }
                    other = {
                        **bucket,
                        "source_id": "source-2",
                        "interpretation_id": "interpreted-V",
                        "semantics": {"unit": "V", "observed_property": "voltage"},
                        "bucket_start": "2026-10-11T23:03:00Z",
                        "mean": 5.0,
                    }
                    payload = {
                        "asset_id": "motor-a",
                        "channel_ids": ["R"],
                        "start_at": start,
                        "end_at": "2026-10-12T00:00:00Z",
                        "assessed_at": "2026-10-16T03:00:00Z",
                        "buckets": [bucket, bad, other],
                        "latest_stored": [],
                    }
                    route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(payload)
                    )

                page.route("**/api/v1/history/channels?**", channels)
                page.route("**/api/v1/history/trend?**", trend)
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(
                    base + "/web/?view=signals&monitor_asset=motor-a", wait_until="networkidle"
                )
                expect_place(pw, page, "신호")
                # Without a chosen window the whole stored record is shown.
                pw.expect(page.get_by_label("조회 기간")).to_have_value("all")
                first, second = "R · 데이터 출처 source-1", "R · 데이터 출처 source-2"
                pw.expect(page.get_by_role("heading", name=first)).to_be_visible()
                pw.expect(page.get_by_role("heading", name=second)).to_be_visible()
                pw.expect(page.get_by_role("link", name="기준 구간 이탈 →")).to_have_attribute(
                    "href",
                    "/web/?page=assets&tab=anomaly&method=baseline"
                    "&monitor_asset=motor-a&monitor_channel=R",
                )
                # One mean mark per usable bucket; the unusable bucket is not drawn as a value.
                pw.expect(page.locator("svg line.mean")).to_have_count(2)
                assert page.locator(".x-axis .ticks").count() == 2
                assert page.locator(".x-axis .ticks").first.locator("span").count() >= 2
                page.get_by_text("시간별 평균·결측·원본 품질 확인").first.click()
                pw.expect(page.get_by_role("table").first).to_contain_text("결측")
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )
                page.get_by_label("조회 기간").select_option("15m")
                assert "monitor_range=15m" in page.url
                page.reload(wait_until="networkidle")
                pw.expect(page.get_by_label("조회 기간")).to_have_value("15m")
                pw.expect(page.get_by_role("heading", name=first)).to_be_visible()

                choose_asset(page, "motor-b")
                expect_place(pw, page, "신호")
                pw.expect(
                    page.get_by_role("heading", name="저장된 신호가 없습니다")
                ).to_be_visible()
                assert page.get_by_role("heading", name="R · 데이터 출처 source-1").count() == 0
                assert "motor-b" in page.url
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()
