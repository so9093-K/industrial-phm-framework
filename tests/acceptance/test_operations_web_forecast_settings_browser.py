"""Current forecast settings/bookmarks reach paired real Prophet computations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from tests.support.phm import analyze, deliver, phm_workspace
from tests.support.web_next import start_web, stop_web


def _store_history(
    workspace: Any,
    *,
    channel: str = "current",
    source: str = "motor-file",
    count: int = 180,
    minutes: int = 1,
) -> None:
    DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    ).append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:{source}:{channel}:{'b' * 64}:{index}",
                source_id=source,
                asset_id="motor-01",
                channel_id=channel,
                source_file="motor.csv",
                source_sha256="b" * 64,
                source_size_bytes=10,
                sample_index=index,
                event_at=datetime(2026, 10, 14, tzinfo=UTC) + timedelta(minutes=index * minutes),
                value=10.0 + 0.02 * index,
                source_metadata_json='{"binding":{"definition":{"unit":"A"}}}',
            )
            for index in range(count)
        ),
        batch_id=f"motor-{source}-{channel}",
    )


@pytest.mark.parametrize("kind", ["history", "acquisition"])
def test_current_forecast_settings_and_time_horizon_use_real_evidence(
    tmp_path: Path, kind: str
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("prophet")
    workspace = phm_workspace(tmp_path / "ws", bind=kind == "acquisition")
    feature = "feature.Horizontal_vibration_signals.rms"
    if kind == "history":
        _store_history(workspace)
    else:
        for ordinal in range(1, 65):
            deliver(workspace, tmp_path / "waves", ordinal, 0.5 + ordinal / 100)
        analyze(workspace)
    running = start_web(workspace.root, writer=False)
    server, _ = running
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 390, "height": 900})
                page.clock.install()
                briefing_reads: list[str] = []

                def pending_briefing(route: Any) -> None:
                    briefing_reads.append(route.request.url)
                    pairs = parse_qs(urlsplit(route.request.url).query)
                    selection = urlencode(sorted((key, value[0]) for key, value in pairs.items()))
                    route.fulfill(
                        json={
                            "schema_version": 1,
                            "selection": selection,
                            "briefings": [
                                {
                                    "id": "pending-test",
                                    "status": "pending",
                                    "question": "현재 상태는 어떤가요?",
                                    "requested_at": "2026-10-16T00:00:00Z",
                                    "finished_at": None,
                                    "model": "local-main",
                                    "answer": None,
                                }
                            ],
                        }
                    )

                page.route("**/api/v1/outlook/briefings?**", pending_briefing)

                def endpoint(name: str) -> Any:
                    return lambda response: response.url.split("?")[0].endswith("/" + name)

                query = {
                    "page": "assets",
                    "tab": "outlook",
                    "data": "history" if kind == "history" else "vibration",
                    "monitor_asset": "motor-01" if kind == "history" else "bearing-a",
                    "forecast_prior": "0.12",
                    "forecast_range": "0.8",
                    "forecast_training": "150" if kind == "history" else "50",
                    "forecast_seasonality": "off",
                    "forecast_backtest": "multi",
                }
                if kind == "history":
                    query.update(
                        monitor_channel="current",
                        projection_horizon="1h",
                        projection_management="12",
                    )
                else:
                    query.update(
                        acq_forecast_feature=feature,
                        acq_forecast_unit="time",
                        acq_forecast_horizon="1h",
                        acq_management="12",
                        acq_assumed_period="180",
                    )
                page.goto(f"http://127.0.0.1:{server.server_port}/web/?{urlencode(query)}")
                panel = page.get_by_role("region", name="추세·기준 도달 전망")
                result_heading = (
                    "기록 마지막 시점 기준 전망"
                    if kind == "history"
                    else "기록 마지막 측정 기준 전망"
                )
                panel.get_by_text("예측 계산 설정", exact=True).click()
                pw.expect(panel.get_by_label("추세 민감도")).to_have_value("0.12")
                pw.expect(panel.get_by_label("최근 학습 개수")).to_have_value(
                    query["forecast_training"]
                )
                # Wait for the two responses themselves: a response listener can still be reading
                # a body after the result is already on screen.
                with (
                    page.expect_response(endpoint("forecast"), timeout=60_000) as forecast,
                    page.expect_response(endpoint("outlook"), timeout=60_000) as outlook,
                ):
                    panel.get_by_role("button", name="계산하기", exact=True).click()
                results = {"forecast": forecast.value.json(), "outlook": outlook.value.json()}
                pw.expect(
                    panel.get_by_role("heading", name=result_heading, exact=True)
                ).to_be_visible(timeout=60_000)
                assert results["forecast"]["horizon"] == "1h"
                assert results["forecast"]["model"]["training_points"] == int(
                    query["forecast_training"]
                )
                assert results["forecast"]["model"]["changepoint_prior_scale"] == 0.12
                assert results["outlook"]["settings"]["seasonality"] == "off"
                assert (
                    results["forecast"]["measurement_version"]
                    == results["outlook"]["measurement_version"]
                )
                # Both outlook kinds stay idle while collapsed, poll only while open,
                # and resume from the stored server status when reopened.
                assert not briefing_reads
                ai = panel.locator("details.optional-ai")
                ai.get_by_text("AI 해설·추가 질문", exact=True).click()
                pw.expect(ai.get_by_role("button", name="결과 다시 확인")).to_be_visible(
                    timeout=30000
                )
                with page.expect_response("**/api/v1/outlook/briefings?**"):
                    page.clock.run_for(1600)
                pw.expect(ai.get_by_role("button", name="결과 다시 확인")).to_be_visible(
                    timeout=30000
                )
                assert len(briefing_reads) >= 2
                ai.get_by_text("AI 해설·추가 질문", exact=True).click()
                pw.expect(ai.locator(".briefings")).to_have_count(0)
                stopped = len(briefing_reads)
                page.clock.run_for(10000)
                page.wait_for_timeout(100)
                assert len(briefing_reads) == stopped
                ai.get_by_text("AI 해설·추가 질문", exact=True).click()
                pw.expect(ai.get_by_role("button", name="결과 다시 확인")).to_be_visible(
                    timeout=30000
                )
                assert len(briefing_reads) > stopped
                ai.get_by_text("AI 해설·추가 질문", exact=True).click()
                panel.get_by_text("과거 자료로 예측 확인", exact=True).click()
                pw.expect(
                    panel.get_by_role("table", name="첫 행은 최근 과거 검증", exact=False)
                ).to_be_visible()
                assert results["forecast"]["rolling_backtests"]
                panel.get_by_label("추세 민감도").fill("0.2")
                pw.expect(
                    panel.get_by_role("heading", name=result_heading, exact=True)
                ).to_have_count(0)
                stopped = len(briefing_reads)
                page.reload()
                pw.expect(
                    panel.get_by_role("heading", name=result_heading, exact=True)
                ).to_be_visible(timeout=60000)
                assert len(briefing_reads) == stopped
                panel.get_by_text("예측 계산 설정", exact=True).click()
                pw.expect(panel.get_by_label("추세 민감도")).to_have_value("0.2")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            finally:
                browser.close()
    finally:
        stop_web(*running)


def test_history_periods_follow_selected_signal_identity_and_training_window(
    tmp_path: Path,
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("prophet")
    workspace = phm_workspace(tmp_path / "different-records", bind=False)
    _store_history(workspace)
    _store_history(workspace, channel="few", count=10, minutes=60)
    _store_history(workspace, channel="tight", count=30)
    # This second identity extends the asset's calendar, but is not the current signal's
    # selected training record (180 observations beats 10). Never borrow its longer span.
    _store_history(workspace, source="other-source", count=10, minutes=1440)
    running = start_web(workspace.root, writer=False)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 390, "height": 900})
                forecasts: list[str] = []
                page.on(
                    "request",
                    lambda request: (
                        forecasts.append(request.url)
                        if urlsplit(request.url).path == "/api/v1/forecast"
                        else None
                    ),
                )
                query = {
                    "page": "assets",
                    "tab": "outlook",
                    "data": "history",
                    "monitor_asset": "motor-01",
                    "monitor_channel": "few",
                    "projection_horizon": "24h",
                }
                page.goto(f"http://127.0.0.1:{running[0].server_port}/web/?{urlencode(query)}")
                panel = page.get_by_role("region", name="추세·기준 도달 전망")
                button = panel.get_by_role("button", name="계산하기", exact=True)
                unsupported = "선택한 신호와 학습 범위로 전망할 수 있는 예측 기간이 없습니다."
                pw.expect(panel).to_contain_text(unsupported)
                pw.expect(button).to_be_disabled()
                assert not forecasts
                panel.get_by_text("계산 조건 변경", exact=True).click()
                selector = panel.locator("#projection-horizon")
                assert selector.locator("option:not([disabled])").count() == 0

                panel.locator("#projection-channel").select_option("current")
                pw.expect(
                    panel.get_by_role("heading", name="기록 마지막 시점 기준 전망", exact=True)
                ).to_be_visible(timeout=60000)
                assert selector.locator("option:not([disabled])").count() == 1
                pw.expect(selector).to_have_value("1h")
                assert len(forecasts) == 1
                if panel.locator("details.calculation-options").get_attribute("open") is None:
                    panel.get_by_text("계산 조건 변경", exact=True).click()
                panel.get_by_text("예측 계산 설정", exact=True).click()
                training = panel.get_by_label("최근 학습 개수", exact=False)
                training.fill("100")
                pw.expect(panel).to_contain_text(unsupported)
                pw.expect(button).to_be_disabled()
                assert len(forecasts) == 1
                training.fill("150")
                pw.expect(button).to_be_enabled()
                button.click()
                pw.expect(
                    panel.get_by_role("heading", name="기록 마지막 시점 기준 전망", exact=True)
                ).to_be_visible(timeout=60000)
                assert len(forecasts) == 2
                assert parse_qs(urlsplit(forecasts[-1]).query)["training_points"] == ["150"]
                panel.locator("#projection-channel").select_option("tight")
                pw.expect(panel).to_contain_text(unsupported)
                pw.expect(button).to_be_disabled()
                assert len(forecasts) == 2
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
            finally:
                browser.close()
    finally:
        stop_web(*running)


@pytest.mark.parametrize(
    ("requested", "recorded", "assumed"),
    [(1, 60.0, None), (4, 60.0, 180.0), (1, None, None), (5, None, None)],
)
def test_count_forecast_discloses_actual_validation_range(
    tmp_path: Path, requested: int, recorded: float | None, assumed: float | None
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("prophet")
    workspace = phm_workspace(tmp_path / "count-range")
    for ordinal in range(1, 31):
        deliver(
            workspace,
            tmp_path / "waves",
            ordinal,
            0.5 + ordinal / 100,
            period_seconds=recorded,
        )
    analyze(workspace)
    running = start_web(workspace.root, writer=False)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 390, "height": 900})
                query = {
                    "page": "assets",
                    "tab": "outlook",
                    "data": "vibration",
                    "monitor_asset": "bearing-a",
                    "acq_forecast_feature": "feature.Horizontal_vibration_signals.rms",
                    "acq_forecast_count": str(requested),
                    **({"acq_assumed_period": str(assumed)} if assumed is not None else {}),
                }
                with page.expect_response("**/api/v1/forecast?**", timeout=60000) as response:
                    page.goto(f"http://127.0.0.1:{running[0].server_port}/web/?{urlencode(query)}")
                body = response.value.json()
                assert body["backtest"]["points"] == 5
                assert body["backtest"]["hidden_seconds"] / body["period_seconds"] == 5
                panel = page.get_by_role("region", name="추세·기준 도달 전망")
                diagnostic = panel.get_by_role("region", name="예측 시작값과 검증 상태")
                pw.expect(diagnostic).to_contain_text(
                    f"요청한 예측 범위 {requested}회 · 과거 검증 5개 측정값, 약 5회 구간."
                )
                mismatch = diagnostic.get_by_text(
                    "과거 검증 범위가 요청한 예측 횟수와 다릅니다.", exact=False
                )
                if requested < 5:
                    pw.expect(mismatch).to_be_visible()
                    pw.expect(mismatch).to_contain_text(f"요청한 {requested}회 앞 예측")
                else:
                    pw.expect(mismatch).to_have_count(0)
                # An ordinal-only stream has no clock: do not show the internal one-second
                # spacing as a real validation duration.
                pw.expect(diagnostic.get_by_text("과거 검증은", exact=False)).to_have_count(0)
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
            finally:
                browser.close()
    finally:
        stop_web(*running)


@pytest.mark.parametrize(
    ("saved_horizon", "none_supported"), [("24h", False), ("1h", False), ("24h", True)]
)
def test_bookmarked_history_outlook_opens_a_supported_period_or_explains_unavailability(
    tmp_path: Path, saved_horizon: str, none_supported: bool
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("prophet")
    workspace = phm_workspace(tmp_path / "bookmark", bind=False)
    _store_history(workspace)
    running = start_web(workspace.root, writer=False)
    try:
        with pw.sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": 390, "height": 900})
                forecast_periods: list[str] = []
                errors: list[str] = []
                page.on("pageerror", lambda error: errors.append(str(error)))

                def forecast(route: Any) -> None:
                    forecast_periods.append(
                        parse_qs(urlsplit(route.request.url).query)["horizon"][0]
                    )
                    route.continue_()

                def options(route: Any) -> None:
                    response = route.fetch()
                    body = response.json()
                    if none_supported:
                        support = {key: "short-history" for key in ("1h", "24h", "7d", "30d")}
                        body["history"]["horizons"] = support
                        if "selection" in body:
                            body["selection"]["horizons"] = support
                    route.fulfill(json=body)

                page.route("**/api/v1/forecast?**", forecast)
                page.route("**/api/v1/forecast/options?**", options)
                query = {
                    "page": "assets",
                    "tab": "outlook",
                    "data": "history",
                    "monitor_asset": "motor-01",
                    "monitor_channel": "current",
                    "projection_horizon": saved_horizon,
                    "projection_management": "12",
                }
                page.goto(f"http://127.0.0.1:{running[0].server_port}/web/?{urlencode(query)}")
                panel = page.get_by_role("region", name="추세·기준 도달 전망")
                if none_supported:
                    pw.expect(panel).to_contain_text(
                        "선택한 신호와 학습 범위로 전망할 수 있는 예측 기간이 없습니다."
                    )
                    pw.expect(
                        panel.get_by_role("button", name="계산하기", exact=True)
                    ).to_be_disabled()
                    assert not forecast_periods
                else:
                    pw.expect(
                        panel.get_by_role("heading", name="기록 마지막 시점 기준 전망", exact=True)
                    ).to_be_visible(timeout=60000)
                    assert forecast_periods == ["1h"]
                    assert parse_qs(urlsplit(page.url).query)["projection_horizon"] == ["1h"]
                    assert parse_qs(urlsplit(page.url).query)["projection_management"] == ["12"]
                    if saved_horizon != "1h":
                        pw.expect(panel).to_contain_text(
                            "저장된 예측 기간 24시간은 선택한 신호와 학습 범위가 지원하지 않아 "
                            "1시간으로 변경했습니다."
                        )
                    else:
                        pw.expect(panel.get_by_text("저장된 예측 기간", exact=False)).to_have_count(
                            0
                        )
                assert panel.locator("details.calculation-options").get_attribute("open") is None
                assert not errors, errors
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
            finally:
                browser.close()
    finally:
        stop_web(*running)
