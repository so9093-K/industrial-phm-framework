"""An asset's summary says what its stored data supports and opens each analysis for that asset."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from tests.support.phm import analyze, deliver, phm_workspace
from tests.support.web_next import asset_list, expect_place, start_web, stop_web

BASE = datetime(2026, 10, 14, tzinfo=UTC)


def _history(workspace: Any, asset_id: str, channels: tuple[str, ...], count: int) -> None:
    DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    ).append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:{asset_id}:{'e' * 64}:{channel}:{index}",
                source_id=f"{asset_id}-file",
                asset_id=asset_id,
                channel_id=channel,
                source_file=f"{asset_id}.csv",
                source_sha256="e" * 64,
                source_size_bytes=10,
                sample_index=index * len(channels) + position,
                event_at=BASE + timedelta(minutes=index),
                value=10.0 + index * (position + 1),
            )
            for position, channel in enumerate(channels)
            for index in range(count)
        ),
        batch_id=asset_id,
    )


def _page(runtime: Any, port: int, width: int, *assets: str) -> tuple[Any, Any, list[str]]:
    browser = runtime.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": width, "height": 900}, locale="ko-KR")
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route(
        "**/api/v1/monitor",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=asset_list(*assets)
        ),
    )
    return browser, page, errors


@pytest.mark.parametrize("width", [390, 1280])
def test_the_summary_says_what_each_assets_data_supports_and_opens_it(
    tmp_path: Path, width: int
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.5, 0.55, 0.5, 3.0, 3.1, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    _history(workspace, "motor-01", ("current", "temperature"), 40)
    server, thread = start_web(workspace.root.resolve(), writer=True)
    try:
        with pw.sync_playwright() as runtime:
            browser, page, errors = _page(
                runtime, server.server_port, width, "motor-01", "bearing-a"
            )
            try:
                base = f"http://127.0.0.1:{server.server_port}/web/?page=assets"
                page.goto(base + "&monitor_asset=motor-01")
                page.get_by_text("추가 분석", exact=True).click()
                options = page.get_by_role("region", name="사용 가능한 분석")
                rows = options.get_by_role("listitem")

                def row(capability: str) -> Any:
                    return options.locator(f'li[data-capability="{capability}"]')

                pw.expect(rows).to_have_count(5)
                pw.expect(row("measurements")).to_contain_text("시계열 신호 2개 ·")
                pw.expect(row("anomaly")).to_contain_text("모델 없이 기준 구간에서 벗어난 값 찾기")
                pw.expect(row("forecast")).to_contain_text("기록이 짧아 예측 그래프는 없음")
                assert row("ai-question").count() == 0
                # Analyses use method names in the usual order; questions stay within each result.
                pw.expect(row("anomaly")).to_contain_text("기준 구간 이탈")
                pw.expect(rows.first).to_contain_text("시계열 신호")
                # What this data cannot support stays one quiet line, each with its reason.
                pw.expect(options).to_contain_text("주파수 분석 — 원본 진동 파형 없음")
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )

                # Ready analyses open for the same asset and data kind.
                options.get_by_role("link", name="두 기간 비교 열기").click()
                pw.expect(page).to_have_url(
                    base + "&tab=change&method=compare&data=history&monitor_asset=motor-01"
                )
                heading = page.get_by_role("heading", name="두 기간 비교", exact=True)
                pw.expect(heading).to_be_visible()
                page.go_back()
                page.get_by_text("추가 분석", exact=True).click()
                options.get_by_role("link", name="신호 관계 열기").click()
                pw.expect(page).to_have_url(
                    base + "&tab=change&method=relation&data=history&monitor_asset=motor-01"
                )
                page.go_back()
                page.get_by_text("추가 분석", exact=True).click()
                options.get_by_role("link", name="상태 전망 열기").click()
                expect_place(pw, page, "상태 전망")
                pw.expect(page.get_by_role("heading", name="추세·기준 도달 전망")).to_be_visible()

                # Vibration with a connected model: every analysis but the outlook.
                page.goto(base + "&monitor_asset=bearing-a")
                page.get_by_text("추가 분석", exact=True).click()
                pw.expect(rows).to_have_count(5)
                pw.expect(options).to_contain_text(
                    "상태 전망 — 기록이 짧음 (예측 기간의 2배 이상 필요)"
                )
                pw.expect(row("period-compare")).to_contain_text("1~8번째 측정")
                options.get_by_role("link", name="주파수 분석 열기").click()
                pw.expect(page).to_have_url(
                    base + "&tab=change&method=spectrum&monitor_asset=bearing-a"
                )
                page.go_back()
                page.get_by_text("추가 분석", exact=True).click()
                options.get_by_role("link", name="이상 징후 열기").click()
                pw.expect(page).to_have_url(
                    base + "&tab=anomaly&method=model&monitor_asset=bearing-a"
                )
                assert not errors, errors
            finally:
                browser.close()
    finally:
        stop_web(server, thread)


def test_a_fitting_model_that_is_not_connected_yet_is_one_link_away(tmp_path: Path) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    for ordinal in range(1, 4):
        deliver(workspace, tmp_path / "waves", ordinal, 0.5)
    # The bearing also has a stored temperature record, so it is listed before any model.
    _history(workspace, "bearing-a", ("temperature",), 10)
    server, thread = start_web(workspace.root.resolve(), writer=True)
    try:
        with pw.sync_playwright() as runtime:
            browser, page, errors = _page(runtime, server.server_port, 1280, "bearing-a")
            try:
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/"
                    "?page=assets&monitor_asset=bearing-a"
                )
                page.get_by_text("추가 분석", exact=True).click()
                options = page.get_by_role("region", name="사용 가능한 분석")
                anomaly = options.locator('li[data-capability="anomaly"]')
                pw.expect(anomaly).to_contain_text("맞는 모델 2개 연결 가능")
                anomaly.get_by_role("link", name="이상 징후 모델 연결하기").click()
                page.get_by_text("이상 탐지 모델 설정", exact=True).click()
                offer = page.get_by_role("region", name="연결할 수 있는 이상 탐지 모델")
                pw.expect(offer.get_by_role("listitem")).to_have_count(2)
                assert not errors, errors
            finally:
                browser.close()
    finally:
        stop_web(server, thread)


def test_change_default_uses_the_bookmarked_data_kind(tmp_path: Path) -> None:
    """History comparison availability must not select comparison for one vibration record."""
    pw = pytest.importorskip("playwright.sync_api")
    workspace = phm_workspace(tmp_path / "mixed")
    deliver(workspace, tmp_path / "waves", 1, 0.5)
    analyze(workspace)
    _history(workspace, "bearing-a", ("temperature",), 40)
    server, thread = start_web(workspace.root.resolve(), writer=True)
    try:
        with pw.sync_playwright() as runtime:
            browser, page, errors = _page(runtime, server.server_port, 390, "bearing-a")
            try:
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/"
                    "?page=assets&tab=change&data=vibration&monitor_asset=bearing-a"
                )
                pw.expect(
                    page.get_by_role("heading", name="주파수 분석", exact=True)
                ).to_be_visible()
                assert page.get_by_role("heading", name="진동 특징의 두 구간 비교").count() == 0
                assert not errors, errors
            finally:
                browser.close()
    finally:
        stop_web(server, thread)


@pytest.mark.parametrize("width", [390, 1024, 1440])
def test_same_user_tasks_across_history_vibration_and_mixed_inputs(
    tmp_path: Path, width: int
) -> None:
    """The task starts consistently, while the source of evidence remains explicit."""
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.6, 0.7, 0.8), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    _history(workspace, "motor-01", ("current", "temperature"), 40)
    _history(workspace, "bearing-a", ("temperature",), 40)
    server, thread = start_web(workspace.root.resolve(), writer=True)
    try:
        with pw.sync_playwright() as runtime:
            browser, page, errors = _page(
                runtime, server.server_port, width, "motor-01", "bearing-a"
            )
            try:
                base = f"http://127.0.0.1:{server.server_port}/web/?page=assets"
                # The anomaly tab opens on an answer: model-free departures for a stored
                # history alone, model scores when a model has results; the other method
                # stays one tab away.
                page.goto(base + "&tab=anomaly&monitor_asset=motor-01")
                pw.expect(
                    page.get_by_role("heading", name="기준 구간 이탈", exact=True)
                ).to_be_visible()
                methods = page.get_by_role("navigation", name="분석 방법")
                pw.expect(methods.get_by_role("link", name="모델 점수")).to_be_visible()
                page.goto(base + "&tab=anomaly&monitor_asset=bearing-a")
                pw.expect(page.get_by_role("heading", name="모델 이상 점수")).to_be_visible()
                pw.expect(methods.get_by_role("link", name="기준 구간 이탈")).to_be_visible()

                # On the one-signal history source, relation is not eligible;
                # the connected vibration features support it instead.
                page.goto(base + "&tab=change&method=relation&monitor_asset=bearing-a")
                pw.expect(
                    page.get_by_role("heading", name="진동 특징 관계", exact=True)
                ).to_be_visible()
                assert page.get_by_role("heading", name="분석할 데이터 선택").count() == 0
                page.goto(base + "&tab=change&method=relation&data=history&monitor_asset=bearing-a")
                pw.expect(
                    page.get_by_text("선택한 분석을 이 데이터에서 사용할 수 없습니다")
                ).to_be_visible()

                # Mixed-input assets must not silently pick history over vibration.
                page.goto(base + "&tab=outlook&monitor_asset=bearing-a")
                pw.expect(page.get_by_role("heading", name="분석할 데이터 선택")).to_be_visible()
                pw.expect(page.get_by_role("link", name="시계열 기록으로 확인")).to_be_visible()
                pw.expect(page.get_by_role("link", name="진동 측정으로 확인")).to_be_visible()

                page.get_by_role("link", name="진동 측정으로 확인").click()
                pw.expect(page).to_have_url(
                    base + "&tab=outlook&data=vibration&monitor_asset=bearing-a"
                )
                assert page.get_by_role("heading", name="분석할 데이터 선택").count() == 0
                assert page.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth + 2"
                )
                assert not errors, errors
            finally:
                browser.close()
    finally:
        stop_web(server, thread)


def test_cumulative_only_record_leads_with_its_values(tmp_path: Path) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    workspace = phm_workspace(tmp_path / "cumulative")
    _history(workspace, "meter-01", ("누적전력량",), 40)
    server, thread = start_web(workspace.root.resolve(), writer=False)
    try:
        with pw.sync_playwright() as runtime:
            browser, page, errors = _page(runtime, server.server_port, 390, "meter-01")
            try:
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/?page=assets&monitor_asset=meter-01"
                )
                records = page.get_by_role("list", name="누적 기록")
                pw.expect(records).to_be_visible()
                pw.expect(records).to_contain_text("누적전력량 · 10 → 49")
                assert (
                    page.get_by_text("변화가 있었는지 말할 수 없습니다", exact=False).count() == 0
                )
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
                assert not errors, errors
            finally:
                browser.close()
    finally:
        stop_web(server, thread)


def test_electrical_period_navigation_keeps_the_explicit_reference(tmp_path: Path) -> None:
    from datetime import UTC, datetime
    from urllib.parse import parse_qs, urlsplit

    from tests.support.electrical_condition import condition_workspace

    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("duckdb")
    workspace = condition_workspace(tmp_path / "fixed-reference")
    server, thread = start_web(workspace.root, writer=False)
    try:
        with pw.sync_playwright() as runtime:
            browser, page, errors = _page(runtime, server.server_port, 390, "condition-motor")
            try:
                page.goto(
                    f"http://127.0.0.1:{server.server_port}/web/?page=assets"
                    "&monitor_asset=condition-motor&tab=change&method=electrical"
                )
                panel = page.get_by_role("region", name="부하·불평형 변화", exact=True)
                panel.get_by_label("분석 기간").select_option("1h")
                panel.get_by_text("분석·기준 기간 직접 지정", exact=True).click()
                panel.get_by_label("분석 끝 시각 (KST)", exact=True).fill("2020-11-13T11:00")
                panel.get_by_label("비교 기준").select_option("fixed")
                panel.get_by_label("기준 기간 시작 (KST)", exact=True).fill("2020-11-13T09:00")
                panel.get_by_label("기준 기간 끝 (KST)", exact=True).fill("2020-11-13T10:00")
                panel.get_by_role("button", name="분석하기", exact=True).click()
                following = panel.get_by_role("button", name="다음 기간 →", exact=True)
                pw.expect(following).to_be_enabled()
                with page.expect_response("**/api/v1/condition?**") as moved:
                    following.click()
                params = parse_qs(urlsplit(moved.value.url).query)
                assert params["reference_start"] == ["2020-11-13T09:00:00+09:00"]
                assert params["reference_end"] == ["2020-11-13T10:00:00+09:00"]
                assert datetime.fromisoformat(moved.value.json()["target_end"]).astimezone(
                    UTC
                ) == datetime(2020, 11, 13, 3, tzinfo=UTC)
                pw.expect(following).to_be_enabled()
                with page.expect_response("**/api/v1/condition?**") as last:
                    following.click()
                assert last.value.json()["next_period_available"] is False
                pw.expect(following).to_be_disabled()
                assert not errors, errors
            finally:
                browser.close()
    finally:
        stop_web(server, thread)
