"""Paired stored history must not merge distinct sources or infer causal diagnosis."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


@pytest.mark.parametrize("width", [390, 1024])
def test_relation_pairing_and_unknown_correlation(tmp_path: Path, width: int) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "relation")
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
                source_data = {
                    "schema_version": 1,
                    "asset_id": "motor-a",
                    "history": {
                        "channels": ["current", "voltage", "temperature"],
                        "start_at": "2026-10-14T00:00:00Z",
                        "end_at": "2026-10-16T00:00:00Z",
                    },
                    "acquisition": None,
                }
                page.route(
                    "**/api/v1/explore/sources?**",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(source_data),
                    ),
                )
                failure = {"enabled": False}

                def relation(route):
                    query = parse_qs(urlsplit(route.request.url).query)
                    assert query["asset_id"] == ["motor-a"]
                    assert query["kind"] == ["history"]
                    assert query["x"] != query["y"]
                    if failure["enabled"]:
                        route.fulfill(
                            status=503,
                            content_type="application/json",
                            body=json.dumps({"error": "explore_store_unavailable"}),
                        )
                        return
                    groups = []
                    if query["x"] == ["current"]:
                        for source, point, pearson in [
                            ("source-a", "motor-1", 0.8),
                            ("source-b", "motor-2", None),
                        ]:
                            groups.append({
                                "period": "a",
                                "source_id": source,
                                "measurement_point_id": point,
                                "meaning_id": source + "-meaning",
                                "x_unit": "A",
                                "y_unit": "V",
                                "x_usable_count": 4,
                                "y_usable_count": 4,
                                "pair_count": 2,
                                "pearson": pearson,
                                "spearman": pearson,
                                "sampled": False,
                                "points": [
                                    ["2026-10-15T00:00:00Z", 2.0, 9.0],
                                    ["2026-10-15T00:01:00Z", 3.0, 10.0],
                                ],
                            })
                    payload = {
                        "schema_version": 1,
                        "asset_id": "motor-a",
                        "kind": "history",
                        "x": query["x"][0],
                        "y": query["y"][0],
                        "pairing": "same-source-point-and-timestamp",
                        "groups": groups,
                    }
                    route.fulfill(
                        status=200, content_type="application/json", body=json.dumps(payload)
                    )

                page.route("**/api/v1/explore/relation?**", relation)
                base = f"http://127.0.0.1:{server.server_port}"
                page.goto(
                    base + "/web-next/?view=relation&monitor_asset=motor-a",
                    wait_until="networkidle",
                )
                pw.expect(
                    page.get_by_role("heading", name="동일 시각 신호 관계 조사")
                ).to_be_visible()
                pw.expect(
                    page.get_by_role("heading", name="구간 A · source-a / motor-1")
                ).to_be_visible()
                pw.expect(
                    page.get_by_role("heading", name="구간 A · source-b / motor-2")
                ).to_be_visible()
                pw.expect(page.get_by_text("미산출", exact=True)).to_have_count(2)
                assert "relation_x=current" in page.url
                assert "relation_y=voltage" in page.url
                page.reload(wait_until="networkidle")
                pw.expect(page.get_by_label("X 측정")).to_have_value("current")
                page.get_by_label("X 측정").select_option("temperature")
                page.get_by_role("button", name="같은 시각의 신호 짝 비교").click()
                pw.expect(
                    page.get_by_role("heading", name="조건에 맞는 측정 짝이 없습니다")
                ).to_be_visible()
                assert page.get_by_role("heading", name="구간 A · source-a / motor-1").count() == 0
                failure["enabled"] = True
                page.get_by_role("button", name="같은 시각의 신호 짝 비교").click()
                pw.expect(page.get_by_role("heading", name="관계 분석 조회 실패")).to_be_visible()
                assert (
                    page.get_by_role("heading", name="조건에 맞는 측정 짝이 없습니다").count()
                    == 0
                )
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
