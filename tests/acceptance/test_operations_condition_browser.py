"""The primary screen answers what changed, when, and what to inspect next."""

import json
from dataclasses import replace
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

from industrial_phm.application import (
    FileSourceConfig,
    JsonSourceRepository,
    backfill_registered_file_source,
)
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.electrical_condition import condition_workspace


@pytest.mark.parametrize("width", [1024, 1440])
def test_monitor_shows_load_change_and_actionable_time_without_review_diary(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    workspace = condition_workspace(tmp_path / "electrical")
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
                page.goto(f"http://127.0.0.1:{server.server_port}/web/", wait_until="networkidle")
                page.locator("#condition-disclosure > summary").click()
                pw.expect(page.locator("#condition-events")).to_contain_text("평가하지 않았습니다")
                page.locator("#condition-period").select_option("1h")
                pw.expect(page.locator("#condition-reference")).to_contain_text("2020-11-13")
                pw.expect(page.locator("#condition-cards")).to_contain_text("관측 평균 전류")
                value = (
                    page.locator("#condition-cards .condition-card")
                    .first.locator("strong")
                    .inner_text()
                )
                assert 80 < float(value.split()[0]) < 82
                pw.expect(page.locator("#condition-insights")).to_contain_text("기준 패턴")
                pw.expect(page.locator("#condition-chart .condition-curve")).to_be_visible()
                pw.expect(page.locator("#review")).to_be_hidden()
                pw.expect(page.locator("#monitor")).to_be_hidden()
                pw.expect(page.locator("#first-run")).to_be_hidden()
                page.locator("#condition-cards").scroll_into_view_if_needed()
                cards = page.locator("#condition-cards").bounding_box()
                assert cards and cards["y"] + cards["height"] <= 900
                page.locator("#condition-events button").first.click()
                pw.expect(page.locator("#condition-detail")).to_contain_text("측정값 확인")
                pw.expect(page.locator("#condition-detail")).to_contain_text("운전 스케줄")
                page.route("**/api/v1/condition?**", lambda route: route.abort())
                page.locator("#condition-run").click()
                pw.expect(page.locator("#condition-state")).to_contain_text("읽지 못했습니다")
                pw.expect(page.locator("#condition-cards>*")).to_have_count(0)
                pw.expect(page.locator("#condition-chart>*")).to_have_count(0)
                page.unroute("**/api/v1/condition?**")
                page.locator("#condition-run").click()
                pw.expect(page.locator("#condition-chart .condition-curve")).to_be_visible()
                page.route(
                    "**/api/v1/condition?**",
                    lambda route: route.fulfill(
                        json={
                            "schema_version": 1,
                            "asset_id": "another-asset",
                            "state": "analyzed",
                            "meaning": (
                                "measured-operating-change-and-reference-pattern-not-fault-diagnosis"
                            ),
                        }
                    ),
                )
                page.locator("#condition-run").click()
                pw.expect(page.locator("#condition-state")).to_contain_text(
                    "응답이 일치하지 않습니다"
                )
                pw.expect(page.locator("#condition-cards>*")).to_have_count(0)
                assert not errors, errors
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()


def test_condition_source_selection_survives_a_new_source_changing_list_order(
    tmp_path: Path,
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    workspace = condition_workspace(tmp_path / "multiple-sources")
    sources = JsonSourceRepository(workspace.source_registry_path)
    original = sources.get("synthetic-electrical")
    assert isinstance(original.config, FileSourceConfig)
    config = original.config
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )

    def add_source(source_id: str) -> None:
        sources.register(
            replace(
                original,
                source_id=source_id,
                config=replace(
                    config,
                    semantic_bindings=tuple(
                        replace(binding, source_id=source_id)
                        for binding in config.semantic_bindings
                    ),
                ),
            )
        )
        backfill_registered_file_source(sources, history, source_id)

    add_source("second-source")
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{server.server_port}/web/", wait_until="networkidle")
                page.locator("#condition-disclosure > summary").click()
                pw.expect(page.locator("#condition-state")).to_contain_text("소스·측정 지점")
                key = json.dumps(["synthetic-electrical", "meter"], separators=(",", ":"))
                page.locator("#condition-period").select_option("1h")
                page.locator("#condition-source").select_option(key)
                pw.expect(page.locator("#condition-method")).to_contain_text(
                    "데이터 소스: synthetic-electrical"
                )
                add_source("aaa-new-source")
                page.locator("#condition-run").click()
                pw.expect(page.locator("#condition-source")).to_have_value(key)
                pw.expect(page.locator("#condition-source option")).to_have_count(4)
                pw.expect(page.locator("#condition-method")).to_contain_text(
                    "데이터 소스: synthetic-electrical"
                )
                pw.expect(page.locator("#condition-method")).not_to_contain_text("aaa-new-source")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()


def test_kst_period_inputs_request_the_same_instant_in_any_browser_time_zone(
    tmp_path: Path,
) -> None:
    """A KST wall-clock choice must not be sent as UTC and silently move nine hours."""
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    # Stored observations span 2020-11-13 00:00 to 03:59 UTC, i.e. 09:00 to 12:59 KST.
    workspace = condition_workspace(tmp_path / "kst")
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            try:
                # The display policy is fixed KST, independent of the viewer's machine zone.
                page = browser.new_page(locale="ko-KR", timezone_id="America/New_York")
                requests: list[str] = []
                page.on(
                    "request",
                    lambda request: (
                        requests.append(request.url)
                        if "/api/v1/condition?" in request.url
                        else None
                    ),
                )
                page.goto(f"http://127.0.0.1:{server.server_port}/web/", wait_until="networkidle")
                page.locator("#condition-disclosure > summary").click()
                pw.expect(page.locator("#condition-method")).to_contain_text(
                    "마지막 관측: 2020-11-13 12:59:00 KST"
                )
                page.locator("#condition-period").select_option("1h")
                page.locator(".condition-period-details > summary").click()
                page.locator("#condition-end").fill("2020-11-13T12:30:15")
                page.locator("#condition-reference-start").fill("2020-11-13T10:00")
                page.locator("#condition-reference-end").fill("2020-11-13T11:00")
                requests.clear()
                page.locator("#condition-run").click()
                pw.expect(page.locator("#condition-state")).to_contain_text(
                    "2020-11-13 11:30:15 KST → 2020-11-13 12:30:15 KST"
                )
                pw.expect(page.locator("#condition-reference")).to_contain_text(
                    "2020-11-13 10:00:00 KST → 2020-11-13 11:00:00 KST"
                )
                pw.expect(page.locator("#condition-chart .condition-curve")).to_be_visible()
                query = parse_qs(urlsplit(requests[-1]).query)
                assert query["end_at"] == ["2020-11-13T12:30:15+09:00"]
                assert query["reference_start"] == ["2020-11-13T10:00:00+09:00"]
                assert query["reference_end"] == ["2020-11-13T11:00:00+09:00"]
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()
