"""Two saved acquisition features are paired only at the same recorded ordinal and binding."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


@pytest.mark.parametrize("width", [390, 1024])
def test_acquisition_relationship_retains_exact_binding_and_fails_closed(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    workspace = OperationsWorkspace(tmp_path / "acq-relation")
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
                page.route(
                    "**/api/v1/explore/sources?**",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "schema_version": 1,
                                "asset_id": "bearing-a",
                                "history": None,
                                "acquisition": {
                                    "source_id": "recorded-source",
                                    "binding_id": "binding-a",
                                    "first": 1,
                                    "last": 20,
                                    "count": 20,
                                    "features": [
                                        {"key": "rms", "label": "진동 RMS"},
                                        {"key": "peak", "label": "진동 첨두"},
                                    ],
                                },
                            }
                        ),
                    ),
                )
                response = {"binding": "binding-a", "failed": False}

                def relation(route):
                    query = parse_qs(urlsplit(route.request.url).query)
                    assert query == {
                        "asset_id": ["bearing-a"],
                        "kind": ["acquisition"],
                        "x": ["rms"],
                        "y": ["peak"],
                        "a_from": ["1"],
                        "a_to": ["10"],
                        "b_from": ["11"],
                        "b_to": ["20"],
                    }
                    if response["failed"]:
                        route.fulfill(
                            status=503,
                            content_type="application/json",
                            body=json.dumps({"error": "storage_unavailable"}),
                        )
                        return
                    groups = []
                    for period, position in [("a", 1), ("b", 20)]:
                        groups.append(
                            {
                                "period": period,
                                "source_id": "recorded-source",
                                "binding_id": response["binding"],
                                "measurement_point_id": None,
                                "analyzed_count": 10,
                                "x_usable_count": 1,
                                "y_usable_count": 1,
                                "pair_count": 1,
                                "pearson": None,
                                "spearman": None,
                                "sampled": True,
                                "points": [[position, 2.0, 4.0]],
                            }
                        )
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps(
                            {
                                "schema_version": 1,
                                "asset_id": "bearing-a",
                                "kind": "acquisition",
                                "pairing": "same-acquisition",
                                "x": "rms",
                                "y": "peak",
                                "groups": groups,
                            }
                        ),
                    )

                page.route("**/api/v1/explore/relation?**", relation)
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web-next/"
                    "?view=acq-relation&monitor_asset=bearing-a",
                    wait_until="networkidle",
                )
                pw.expect(
                    page.get_by_role("heading", name="획득 회차 두 특징 관계 비교")
                ).to_be_visible()
                pw.expect(page.get_by_text("binding-a", exact=True)).to_be_visible()
                pw.expect(page.locator("table")).to_have_count(2)
                pw.expect(page.get_by_role("status").filter(has_text="관계 없음(0)")).to_have_count(
                    2
                )
                assert "acq_a_from=1" in page.url
                assert "acq_b_to=20" in page.url
                page.reload(wait_until="networkidle")
                pw.expect(page.get_by_label("X 특징")).to_have_value("rms")
                response["binding"] = "binding-other"
                page.get_by_role("button", name="동일 획득의 특징 짝 비교").click()
                pw.expect(
                    page.get_by_role("heading", name="획득 특징 관계 확인 실패")
                ).to_be_visible()
                assert page.get_by_role("table").count() == 0
                response["binding"] = "binding-a"
                response["failed"] = True
                page.get_by_role("button", name="같은 조건 다시 조회").click()
                pw.expect(
                    page.get_by_role("heading", name="획득 특징 관계 확인 실패")
                ).to_be_visible()
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
