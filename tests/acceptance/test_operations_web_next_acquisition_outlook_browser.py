"""Acquisition forecasts remain ordinal and fail closed on version/binding/time basis drift."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


@pytest.mark.parametrize("width", [390, 1024])
@pytest.mark.parametrize("spacing", ["recorded", "assumed", "ordinal"])
def test_acquisition_outlook_does_not_invent_clock_and_blocks_drift(
    tmp_path: Path, width: int, spacing: str
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "acq-outlook")
    initialize_operations_workspace(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": width, "height": 960}, locale="ko-KR")
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.route(
                    "**/api/v1/monitor",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "assessed_at": "2026-10-16T00:00:00Z",
                                "assets": {
                                    "items": [
                                        {
                                            "asset_id": "bearing-a",
                                            "data_flow_status": "stored-history",
                                            "last_data_at": None,
                                            "attention_count": 0,
                                        }
                                    ],
                                    "total": 1,
                                    "truncated": False,
                                },
                                "system_error_scopes": [],
                            }
                        ),
                    ),
                )
                recorded_period = None if spacing == "ordinal" else 60
                page.route(
                    "**/api/v1/forecast/options?**",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "schema_version": 1,
                                "asset_id": "bearing-a",
                                "history": None,
                                "acquisition": {
                                    "source_id": "wave-source",
                                    "binding_id": "binding-a",
                                    "first": 1,
                                    "last": 64,
                                    "count": 64,
                                    "period_seconds": recorded_period,
                                    "series": [
                                        {
                                            "key": "feature.rms",
                                            "label": "진동 RMS",
                                            "valid_points": 64,
                                            "count_forecast": True,
                                        }
                                    ],
                                },
                            }
                        ),
                    ),
                )
                selected = {
                    "binding": "binding-a",
                    "forecast_version": "a" * 64,
                    "outlook_version": "a" * 64,
                }
                basis = "assumed" if spacing == "assumed" else spacing
                interval = 120 if basis == "assumed" else 60 if basis == "recorded" else 1
                assumed = 120 if basis == "assumed" else None

                def matched_query(route):
                    query = parse_qs(urlsplit(route.request.url).query)
                    assert query["asset_id"] == ["bearing-a"]
                    assert query["kind"] == ["acquisition"]
                    assert query["series"] == ["feature.rms"]
                    assert query.get("assumed_period_seconds") == (
                        ["120"] if spacing == "assumed" else None
                    )
                    return query

                def base_body(version: str):
                    return {
                        "schema_version": 1,
                        "asset_id": "bearing-a",
                        "kind": "acquisition",
                        "axis": "acquisition",
                        "series": "feature.rms",
                        "source_id": "wave-source",
                        "binding_id": selected["binding"],
                        "measurement_point_id": None,
                        "measurement_version": version,
                        "time_basis": basis,
                        "period_seconds": interval,
                        "recorded_period_seconds": recorded_period,
                        "assumed_period_seconds": assumed,
                    }

                def forecast(route):
                    query = matched_query(route)
                    assert query["horizon"] == ["count"]
                    assert query["horizon_count"] == ["20"]
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                **base_body(selected["forecast_version"]),
                                "horizon": "count",
                                "horizon_count": 20,
                                "meaning": "stored-flow-continued-not-failure-time-or-remaining-life",
                                "forecast": [[64, 2.2, 2.0, 2.4], [84, 3.4, 3.2, 3.8]],
                            }
                        ),
                    )

                def outlook(route):
                    query = matched_query(route)
                    assert query["direction"] == ["upper"]
                    assert query["management_limit"] == ["2.4"]
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                **base_body(selected["outlook_version"]),
                                "offset_unit": "acquisition",
                                "data_version": "b" * 64,
                                "meaning": "remaining-margin-to-user-conditions-not-a-diagnosis",
                                "conditions": {
                                    "direction": "upper",
                                    "management": 2.4,
                                    "end": None,
                                },
                                "record": {"first": 1, "last": 64, "points": 64},
                                "scenarios": [
                                    {
                                        "id": "linear",
                                        "limits": {
                                            "management": {
                                                "state": "expected",
                                                "expected": 4,
                                                "earliest": None,
                                                "latest": None,
                                            }
                                        },
                                    }
                                ],
                            }
                        ),
                    )

                page.route("**/api/v1/forecast?**", forecast)
                page.route("**/api/v1/outlook?**", outlook)
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(
                    base + "/web-next/?view=acq-outlook&monitor_asset=bearing-a",
                    wait_until="networkidle",
                )
                pw.expect(page.get_by_role("heading", name="획득 특징의 조건부 전망")).to_be_visible()
                if spacing == "assumed":
                    page.get_by_label("가정한 획득 간격 (선택 · 초/회, 1~86400)").fill("120")
                page.get_by_label("관리 기준 (선택)").fill("2.4")
                page.get_by_role("button", name="같은 획득 근거로 전망 계산").click()
                pw.expect(page.get_by_role("heading", name="서버에 검증된 획득 전망 근거")
                          ).to_be_visible()
                pw.expect(page.get_by_text("추가 4회 획득 시 도달 예상")).to_be_visible()
                assert page.get_by_role("columnheader", name="획득 #").count() == 1
                assert page.get_by_role("columnheader", name="예측 시점").count() == 0
                if spacing == "ordinal":
                    pw.expect(page.get_by_text("획득 순번만 확인 가능", exact=False)).to_be_visible()
                elif spacing == "assumed":
                    pw.expect(page.get_by_text("사용자가 가정한 획득 간격", exact=False)).to_be_visible()
                else:
                    pw.expect(page.get_by_text("수집 메타데이터에 기록된 획득 간격", exact=False)).to_be_visible()
                assert "acq_forecast_count=20" in page.url
                # Even if the observed version is unchanged, a different
                # binding cannot inherit the prior result.
                selected["binding"] = "binding-changed"
                page.get_by_role("button", name="같은 획득 근거로 전망 계산").click()
                pw.expect(page.get_by_role("heading", name="획득 전망 근거 불일치")
                          ).to_be_visible()
                assert page.get_by_role("heading", name="서버에 검증된 획득 전망 근거").count() == 0
                selected["binding"] = "binding-a"
                selected["outlook_version"] = "c" * 64
                page.get_by_role("button", name="원본 목록 다시 조회").click()
                page.get_by_role("button", name="같은 획득 근거로 전망 계산").click()
                pw.expect(page.get_by_role("heading", name="획득 전망 근거 불일치")
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
