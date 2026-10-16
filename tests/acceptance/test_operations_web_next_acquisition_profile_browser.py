"""Acquisition A/B feature statistics respect ordinal, binding and sampling boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


@pytest.mark.parametrize("width", [390, 1024])
def test_acquisition_feature_profile_preserves_quality_and_binding(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "feature-profile")
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
                            {
                                "asset_id": "motor-a",
                                "data_flow_status": "stored-history",
                                "last_data_at": "2026-10-16T00:00:00Z",
                                "attention_count": 0,
                            }
                        ],
                        "total": 1,
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
                sources = {
                    "schema_version": 1,
                    "asset_id": "motor-a",
                    "history": None,
                    "acquisition": {
                        "source_id": "sensor-src",
                        "binding_id": "binding-a",
                        "first": 1,
                        "last": 20,
                        "count": 20,
                        "features": [
                            {"key": "feature.R.rms", "label": "R RMS"},
                            {"key": "feature.R.mean", "label": "R Mean"},
                        ],
                    },
                }
                page.route(
                    "**/api/v1/explore/sources?**",
                    lambda route: route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(sources)
                    ),
                )
                error = {"enabled": False}

                def profile(route):
                    query = parse_qs(urlsplit(route.request.url).query)
                    assert query["asset_id"] == ["motor-a"]
                    assert query["kind"] == ["acquisition"]
                    assert query["a_from"] == ["1"]
                    assert query["a_to"] == ["10"]
                    assert query["b_from"] == ["11"]
                    assert query["b_to"] == ["20"]
                    if error["enabled"]:
                        route.fulfill(
                            status=503,
                            content_type="application/json",
                            body=json.dumps({"error": "explore_store_unavailable"}),
                        )
                        return
                    feature = query["series"][0]

                    def stats(valid, first, last, sampled):
                        return {
                            "observation_count": 10,
                            "usable_count": valid,
                            "analyzed_count": 10,
                            "missing_count": 1,
                            "unanalyzed_count": 0,
                            "sampled": sampled,
                            "first_position": first,
                            "last_position": last,
                            "mean": 2.0,
                            "quantiles": [1, 1.5, 2, 2.5, 3],
                        }

                    payload = {
                        "schema_version": 1,
                        "asset_id": "motor-a",
                        "kind": "acquisition",
                        "meaning": "stored-measurements-compared-not-asset-health",
                        "periods": {
                            "a": {"from": 1, "to": 10},
                            "b": {"from": 11, "to": 20},
                        },
                        "series": [
                            {
                                "kind": "acquisition",
                                "key": feature,
                                "label": feature,
                                "source_id": "sensor-src",
                                "binding_id": "binding-a",
                                "periods": {
                                    "a": stats(10, 1, 10, False),
                                    "b": stats(8, 11, 20, True),
                                },
                                "comparison": {
                                    "median_change": 0,
                                    "b_outside_a_band_percent": 25,
                                },
                            }
                        ],
                    }
                    route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(payload)
                    )

                page.route("**/api/v1/explore/profile?**", profile)
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(
                    base + "/web-next/?view=features&monitor_asset=motor-a",
                    wait_until="networkidle",
                )
                pw.expect(
                    page.get_by_role("heading", name="획득 회차의 특징값 A/B 비교")
                ).to_be_visible()
                pw.expect(page.get_by_role("table")).to_have_count(1)
                pw.expect(page.get_by_role("table")).to_contain_text("중간 누락 회차")
                pw.expect(page.get_by_role("table")).to_contain_text("샘플링됨")
                assert "acquisition_feature=feature.R.rms" in page.url
                assert "feature_b_from=11" in page.url
                page.get_by_label("비교할 획득 특징").select_option("feature.R.mean")
                pw.expect(
                    page.get_by_role("heading", name="feature.R.mean · feature.R.mean")
                ).to_be_visible()
                page.reload(wait_until="networkidle")
                pw.expect(page.get_by_label("비교할 획득 특징")).to_have_value("feature.R.mean")
                error["enabled"] = True
                page.get_by_role("button", name="특징값 분포와 분석 누락 비교").click()
                pw.expect(page.get_by_role("heading", name="획득 특징 비교 실패")).to_be_visible()
                assert page.get_by_role("table").count() == 0
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
