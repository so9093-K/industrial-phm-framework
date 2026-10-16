"""Two-period Web-next EDA distinguishes evidence sources and unavailable data."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


@pytest.mark.parametrize("width", [390, 1024])
def test_two_period_profile_preserves_evidence_and_requery(tmp_path: Path, width: int) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "comparison")
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
                            },
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

                def sources(route):
                    params = parse_qs(urlsplit(route.request.url).query)
                    assert params["asset_id"] == ["motor-a"]
                    data = {
                        "schema_version": 1,
                        "asset_id": "motor-a",
                        "history": {
                            "channels": ["current", "voltage"],
                            "start_at": "2026-10-14T00:00:00Z",
                            "end_at": "2026-10-16T00:00:00Z",
                        },
                        "acquisition": None,
                    }
                    route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(data)
                    )

                def profile(route):
                    q = parse_qs(urlsplit(route.request.url).query)
                    assert q["asset_id"] == ["motor-a"]
                    assert q["kind"] == ["history"]
                    channel = q["series"][0]
                    def period(name):
                        return {"from": q[name + "_from"][0], "to": q[name + "_to"][0]}
                    def stats(n):
                        return {
                            "observation_count": n,
                            "usable_count": n,
                            "missing_count": 0,
                            "non_good_count": 0,
                            "conflict_count": 0,
                            "mean": float(n),
                            "quantiles": [1, 2, float(n), 4, 5],
                        }
                    data = {
                        "schema_version": 1,
                        "asset_id": "motor-a",
                        "kind": "history",
                        "meaning": "stored-measurements-compared-not-asset-health",
                        "periods": {"a": period("a"), "b": period("b")},
                        "series": [
                            {
                                "kind": "history", "key": channel,
                                "source_id": source, "source_type": "csv",
                                "measurement_point_id": source,
                                "interpretation_id": source + "-meaning",
                                "unit": "A" if source == "src-A" else "V",
                                "periods": {"a": stats(30), "b": stats(20)},
                                "comparison": {
                                    "median_change": -10,
                                    "b_outside_a_band_percent": 25,
                                },
                            }
                            for source in ["src-A", "src-B"]
                        ],
                    }
                    route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(data)
                    )

                page.route("**/api/v1/explore/sources?**", sources)
                page.route("**/api/v1/explore/profile?**", profile)
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(
                    base + "/web-next/?view=compare&monitor_asset=motor-a",
                    wait_until="networkidle",
                )
                pw.expect(page.get_by_role("heading", name="두 기간의 측정 비교")).to_be_visible()
                pw.expect(page.get_by_role("heading", name="current · src-A")).to_be_visible()
                pw.expect(page.get_by_role("heading", name="current · src-B")).to_be_visible()
                pw.expect(page.get_by_role("table")).to_have_count(2)
                assert "compare_a=" in page.url
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )
                page.get_by_label("비교할 측정 신호").select_option("voltage")
                pw.expect(page.get_by_role("heading", name="voltage · src-A")).to_be_visible()
                assert "monitor_channel=voltage" in page.url
                page.reload(wait_until="networkidle")
                pw.expect(page.get_by_label("비교할 측정 신호")).to_have_value("voltage")
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()
