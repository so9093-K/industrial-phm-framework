"""변화 분석의 부하·불평형 answers what changed, when, and what to check next."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from industrial_phm.application import (
    FileSourceConfig,
    JsonSourceRepository,
    backfill_registered_file_source,
)
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from tests.support.electrical_condition import condition_workspace
from tests.support.web_next import asset_list, start_web, stop_web

PLACE = "/web-next/?page=assets&tab=change&method=electrical&monitor_asset=condition-motor"


def _open(runtime: Any, port: int, **options: Any) -> tuple[Any, Any, list[str]]:
    browser = runtime.chromium.launch(headless=True)
    page = browser.new_page(locale="ko-KR", **options)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route(
        "**/api/v1/monitor",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=asset_list("condition-motor")
        ),
    )
    page.goto(f"http://127.0.0.1:{port}{PLACE}")
    return browser, page, errors


@pytest.mark.parametrize("width", [390, 1280])
def test_load_change_shows_values_times_and_never_keeps_a_failed_result(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    workspace = condition_workspace(tmp_path / "electrical")
    server, thread = start_web(workspace.root.resolve(), writer=False)
    try:
        with pw.sync_playwright() as runtime:
            browser, page, errors = _open(
                runtime, server.server_port, viewport={"width": width, "height": 900}
            )
            try:
                panel = page.get_by_role("region", name="부하·불평형 변화")
                first = panel.get_by_role("region", name="먼저 확인할 시각")
                # The default 24 hours has no earlier history, so nothing is scored against it.
                pw.expect(first).to_contain_text("벗어남을 평가하지 않았습니다")
                panel.get_by_label("분석 기간").select_option("1h")
                pw.expect(panel).to_contain_text("비교 기준 2020. 11. 13.")
                cards = panel.get_by_label("기준 기간과 비교한 값")
                current = cards.get_by_role("article").filter(has_text="관측 평균 전류")
                value = current.locator("strong").inner_text()
                assert 80 < float(value.split()[0]) < 82
                changed = panel.get_by_role("region", name="기준 기간과 달라진 점")
                pw.expect(changed).to_contain_text("기준 패턴의 99% 점수 범위")
                pw.expect(panel.locator("svg path.line").first).to_be_visible()
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )
                page.screenshot(path=str(tmp_path / f"condition-{width}.png"), full_page=True)

                first.get_by_role("button").first.click()
                chosen = panel.get_by_role("region", name="측정값")
                pw.expect(chosen).to_be_focused()
                pw.expect(chosen).to_contain_text("전압 R / S / T")
                pw.expect(chosen).to_contain_text("운전 일정")
                panel.get_by_label("그래프 값").select_option(label="기준 패턴과의 차이")
                pw.expect(panel.get_by_role("img", name="기준 패턴과의 차이")).to_be_visible()
                pw.expect(panel.locator(".axis-note")).to_contain_text("점선: 기준 기간 점수 99%")

                # A failed read clears the earlier result rather than leaving it as current.
                page.route("**/api/v1/condition?**", lambda route: route.abort())
                panel.get_by_role("button", name="분석하기").click()
                pw.expect(panel).to_contain_text("분석할 데이터를 읽지 못했습니다")
                assert cards.count() == 0
                page.unroute("**/api/v1/condition?**")
                panel.get_by_role("button", name="같은 조건으로 다시 분석하기").click()
                pw.expect(panel.locator("svg path.line").first).to_be_visible()

                # An answer about another asset is never shown.
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
                panel.get_by_role("button", name="분석하기").click()
                pw.expect(panel).to_contain_text("형식이 올바르지 않습니다")
                assert cards.count() == 0
                assert not errors, errors
            finally:
                browser.close()
    finally:
        stop_web(server, thread)


def test_chosen_source_survives_a_new_source_changing_the_list_order(tmp_path: Path) -> None:
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
    server, thread = start_web(workspace.root.resolve(), writer=False)
    try:
        with pw.sync_playwright() as runtime:
            browser, page, errors = _open(
                runtime, server.server_port, viewport={"width": 1280, "height": 900}
            )
            try:
                panel = page.get_by_role("region", name="부하·불평형 변화")
                pw.expect(panel).to_contain_text("분석할 출처와 측정 위치를 고르세요")
                choice = panel.get_by_label("데이터 출처 · 측정 위치")
                key = json.dumps(["synthetic-electrical", "meter"], separators=(",", ":"))
                panel.get_by_label("분석 기간").select_option("1h")
                pw.expect(choice.locator("option")).to_have_count(3)
                choice.select_option(key)
                details = panel.locator("details.tech")
                details.locator("summary").click()
                pw.expect(details).to_contain_text("synthetic-electrical")
                add_source("aaa-new-source")
                panel.get_by_role("button", name="분석하기").click()
                pw.expect(choice.locator("option")).to_have_count(4)
                pw.expect(choice).to_have_value(key)
                pw.expect(details).to_contain_text("synthetic-electrical")
                pw.expect(details).not_to_contain_text("aaa-new-source")
                assert not errors, errors
            finally:
                browser.close()
    finally:
        stop_web(server, thread)


def test_kst_inputs_request_the_same_instant_in_any_browser_time_zone(tmp_path: Path) -> None:
    """A KST wall-clock choice must not be sent as UTC and silently move nine hours."""
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    # Stored observations span 2020-11-13 00:00 to 03:59 UTC, i.e. 09:00 to 12:59 KST.
    workspace = condition_workspace(tmp_path / "kst")
    server, thread = start_web(workspace.root.resolve(), writer=False)
    try:
        with pw.sync_playwright() as runtime:
            browser, page, errors = _open(
                runtime, server.server_port, timezone_id="America/New_York"
            )
            requests: list[str] = []
            page.on(
                "request",
                lambda request: (
                    requests.append(request.url) if "/api/v1/condition?" in request.url else None
                ),
            )
            try:
                panel = page.get_by_role("region", name="부하·불평형 변화")
                details = panel.locator("details.tech")
                details.locator("summary").click()
                pw.expect(details).to_contain_text("2020. 11. 13. 오후 12:59:00")
                panel.get_by_label("분석 기간").select_option("1h")
                pw.expect(panel.locator("svg path.line").first).to_be_visible()
                panel.get_by_text("분석·기준 기간 직접 지정").click()
                panel.get_by_label("분석 끝 시각 (KST)").fill("2020-11-13T12:30:15")
                panel.get_by_label("기준 기간 시작 (KST)").fill("2020-11-13T10:00")
                panel.get_by_label("기준 기간 끝 (KST)").fill("2020-11-13T11:00")
                requests.clear()
                panel.get_by_role("button", name="분석하기").click()
                pw.expect(panel).to_contain_text(
                    "분석 기간 2020. 11. 13. 오전 11:30:15 → 2020. 11. 13. 오후 12:30:15"
                )
                pw.expect(panel).to_contain_text(
                    "비교 기준 2020. 11. 13. 오전 10:00:00 → 2020. 11. 13. 오전 11:00:00"
                )
                pw.expect(panel.locator("svg path.line").first).to_be_visible()
                query = parse_qs(urlsplit(requests[-1]).query)
                assert query["end_at"] == ["2020-11-13T12:30:15+09:00"]
                assert query["reference_start"] == ["2020-11-13T10:00:00+09:00"]
                assert query["reference_end"] == ["2020-11-13T11:00:00+09:00"]
                assert not errors, errors
            finally:
                browser.close()
    finally:
        stop_web(server, thread)
