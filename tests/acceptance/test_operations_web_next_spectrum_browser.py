"""Verified acquisition waveform PSD is not a clock or equipment diagnosis."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.web_next import choose_asset, expect_place, mock_analysis_capabilities


@pytest.mark.parametrize("width", [390, 1024])
def test_acquisition_psd_keeps_ordinals_and_missing_waveform(tmp_path: Path, width: int) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "spectrum")
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
                    "assessed_at": "2026-10-16T00:00:00Z",
                    "assets": {
                        "items": [
                            {"asset_id": "motor-a", "data_flow_status": "stored-history"},
                            {"asset_id": "motor-b", "data_flow_status": "waiting"},
                        ],
                        "total": 2,
                        "truncated": False,
                    },
                    "system_error_scopes": [],
                }
                mock_analysis_capabilities(page, "motor-a", "spectrum")
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(monitor)
                    ),
                )

                def source(route):
                    query = parse_qs(urlsplit(route.request.url).query)
                    asset = query["asset_id"][0]
                    record = None
                    if asset == "motor-a":
                        record = {
                            "source_id": "bearing-src",
                            "binding_id": "bearing-binding",
                            "first": 1,
                            "last": 20,
                            "count": 20,
                            "features": [],
                        }
                    body = {
                        "schema_version": 1,
                        "asset_id": asset,
                        "history": None,
                        "acquisition": record,
                    }
                    route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(body)
                    )

                page.route("**/api/v1/explore/sources?**", source)
                error = {"missing": False}

                def spectrum(route):
                    if error["missing"]:
                        route.fulfill(
                            status=409,
                            content_type="application/json",
                            body=json.dumps({"error": "original_waveform_unavailable"}),
                        )
                        return
                    query = parse_qs(urlsplit(route.request.url).query)
                    assert query["asset_id"] == ["motor-a"]
                    body = {
                        "schema_version": 1,
                        "asset_id": "motor-a",
                        "kind": "acquisition",
                        "sampling_rate_hz": 12000,
                        "segment": 4096,
                        "frequencies": [0, 100, 200],
                        "acquisitions": {
                            "a": [int(query["a_from"][0])],
                            "b": [int(query["b_from"][0])],
                        },
                        "channels": [
                            {
                                "channel": "R",
                                "label": "bearing R",
                                "a": [0.1, 0.2, 0.3],
                                "b": [0.3, 0.2, 0.1],
                                "band_changes": [
                                    {
                                        "from_hz": 0,
                                        "to_hz": 100,
                                        "change_db": 3.2,
                                    }
                                ],
                            }
                        ],
                    }
                    route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(body)
                    )

                page.route("**/api/v1/explore/spectrum?**", spectrum)
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(
                    base + "/web/?view=spectrum&monitor_asset=motor-a",
                    wait_until="networkidle",
                )
                expect_place(pw, page, "변화 분석", "주파수 분석")
                pw.expect(page.get_by_role("heading", name="bearing R · R")).to_be_visible()
                pw.expect(page.locator(".spectra svg polyline")).to_have_count(2)
                assert "spectrum_a_from=1" in page.url
                assert "spectrum_b_from=11" in page.url
                page.reload(wait_until="networkidle")
                pw.expect(page.get_by_text("B/A 세기 변화")).to_be_visible()
                # A dB axis keeps the weaker bands readable; the same two traces are redrawn.
                linear = page.locator(".spectra svg polyline").first.get_attribute("points")
                page.get_by_label("세로축을 dB로 보기", exact=False).check()
                pw.expect(page.locator(".spectra .axis-note").first).to_contain_text("dB")
                pw.expect(page.locator(".spectra .tick").first).to_contain_text("dB")
                assert page.locator(".spectra svg polyline").first.get_attribute("points") != linear
                pw.expect(page.locator(".spectra svg polyline")).to_have_count(2)

                error["missing"] = True
                page.get_by_role("button", name="주파수 비교하기").click()
                pw.expect(
                    page.get_by_role("heading", name="원본 파형을 확인할 수 없습니다")
                ).to_be_visible()
                assert page.locator(".spectra svg polyline").count() == 0

                choose_asset(page, "motor-b")
                expect_place(pw, page, "변화 분석", "주파수 분석")
                pw.expect(
                    page.get_by_role(
                        "heading", name="선택한 분석을 이 데이터에서 사용할 수 없습니다"
                    )
                ).to_be_visible()
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()
