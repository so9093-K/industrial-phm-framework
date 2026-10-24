"""Current forecast settings/bookmarks reach paired real Prophet computations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from tests.support.phm import analyze, deliver, phm_workspace
from tests.support.web_next import start_web, stop_web


@pytest.mark.parametrize("kind", ["history", "acquisition"])
def test_current_forecast_settings_and_time_horizon_use_real_evidence(
    tmp_path: Path, kind: str
) -> None:
    pw = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("prophet")
    workspace = phm_workspace(tmp_path / "ws", bind=kind == "acquisition")
    feature = "feature.Horizontal_vibration_signals.rms"
    if kind == "history":
        DuckLakeAssetHistory(
            DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
        ).append_file_batch(
            tuple(
                FileBackfillEvent(
                    raw_evidence_id=f"file:motor:{'b' * 64}:{index}",
                    source_id="motor-file",
                    asset_id="motor-01",
                    channel_id="current",
                    source_file="motor.csv",
                    source_sha256="b" * 64,
                    source_size_bytes=10,
                    sample_index=index,
                    event_at=datetime(2026, 10, 14, tzinfo=UTC) + timedelta(minutes=index),
                    value=10.0 + 0.02 * index,
                    source_metadata_json='{"binding":{"definition":{"unit":"A"}}}',
                )
                for index in range(180)
            ),
            batch_id="motor",
        )
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
                    query.update(monitor_channel="current", projection_horizon="1h", projection_management="12")
                else:
                    query.update(acq_forecast_feature=feature, acq_forecast_unit="time",
                                 acq_forecast_horizon="1h", acq_management="12", acq_assumed_period="180")
                page.goto(f"http://127.0.0.1:{server.server_port}/web/?{urlencode(query)}")
                panel = page.get_by_role("region", name="기준 도달 전망")
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
                pw.expect(panel.get_by_role("heading", name="결과", exact=True)).to_be_visible(
                    timeout=60_000
                )
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
                panel.get_by_text("과거 자료로 예측 확인", exact=True).click()
                pw.expect(
                    panel.get_by_role("table", name="첫 행은 최근 과거 검증", exact=False)
                ).to_be_visible()
                assert results["forecast"]["rolling_backtests"]
                panel.get_by_label("추세 민감도").fill("0.2")
                pw.expect(panel.get_by_role("heading", name="결과", exact=True)).to_have_count(0)
                page.reload()
                panel.get_by_text("예측 계산 설정", exact=True).click()
                pw.expect(panel.get_by_label("추세 민감도")).to_have_value("0.2")
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            finally:
                browser.close()
    finally:
        stop_web(*running)
