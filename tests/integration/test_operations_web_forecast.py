"""Forecast routes over a real workspace: stored history on a clock, acquisitions on their axis."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import urlencode

import pytest

pytest.importorskip("prophet", reason="install the forecast extra")
pytest.importorskip("duckdb")

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime.operations_web_capabilities import (
    project_asset_capabilities,
)
from industrial_phm.runtime.operations_web_http import (
    create_operations_web_read_server,
)
from tests.support.phm import analyze, deliver, phm_workspace

BASE = datetime(2026, 10, 14, tzinfo=UTC)


def _serve(root: Path):
    server = create_operations_web_read_server(root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def get(path: str, **query: Any) -> tuple[int, dict[str, Any]]:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=60)
        try:
            connection.request(
                "GET",
                path + "?" + urlencode(query),
                headers={"Host": f"127.0.0.1:{server.server_port}"},
            )
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def stop() -> None:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)

    return get, stop


def test_stored_history_is_forecast_on_its_clock_with_a_level_and_a_check(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws", bind=False)
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
                event_at=BASE + timedelta(minutes=index),
                value=10.0 + 0.02 * index,
                source_metadata_json='{"binding":{"definition":{"unit":"A"}}}',
            )
            for index in range(180)
        ),
        batch_id="motor",
    )
    get, stop = _serve(workspace.root)
    try:
        status, options = get("/api/v1/forecast/options", asset_id="motor-01")
        assert status == 200 and options["acquisition"] is None
        assert options["history"]["series"] == [{"key": "current", "label": "current"}]
        assert options["history"]["horizons"]["1h"] is None
        assert options["history"]["horizons"]["24h"] == "short-history"

        status, body = get(
            "/api/v1/forecast",
            asset_id="motor-01",
            kind="history",
            series="current",
            horizon="1h",
            threshold="14.3",
        )
        assert status == 200 and body["axis"] == "time" and body["unit"] == "A"
        assert body["raw_count"] == 180 and len(body["history"]) == 180
        assert body["trend"]["direction"] == "up"
        assert body["threshold"]["state"] == "expected"
        assert body["threshold"]["limit_kind"] == "upper"
        assert (
            body["backtest"]["mean_absolute_error"] < body["backtest"]["naive_mean_absolute_error"]
        )
        assert body["meaning"] == "stored-flow-continued-not-failure-time-or-remaining-life"
        assert str(tmp_path) not in json.dumps(body)
        status, limited = get(
            "/api/v1/forecast/options",
            asset_id="motor-01",
            kind="history",
            series="current",
            training_points="100",
        )
        assert status == 200
        assert limited["selection"]["points"] == 100
        assert limited["selection"]["horizons"]["1h"] == "short-history"
        assert (
            get(
                "/api/v1/forecast/options",
                asset_id="motor-01",
                kind="history",
                series="current",
                training_points="10",
            )[0]
            == 400
        )
        status, custom = get(
            "/api/v1/forecast",
            **{
                "asset_id": "motor-01",
                "kind": "history",
                "series": "current",
                "horizon": "1h",
                "changepoint_prior_scale": "0.1",
                "changepoint_range": "0.8",
                "training_points": "150",
                "seasonality": "off",
                "backtest": "multi",
            },
        )
        assert status == 200
        assert custom["model"]["points"] == 150
        assert custom["model"]["changepoint_prior_scale"] == 0.1
        assert custom["model"]["changepoint_range"] == 0.8
        assert len(custom["rolling_backtests"]) == 3
        status, lower = get(
            "/api/v1/forecast",
            asset_id="motor-01",
            kind="history",
            series="current",
            horizon="1h",
            threshold="12",
            threshold_direction="lower",
        )
        assert status == 200
        assert lower["threshold"]["limit_kind"] == "lower"

        query = {"asset_id": "motor-01", "kind": "history", "series": "current"}
        assert get("/api/v1/forecast", **query, horizon="24h") == (
            422,
            {"error": "forecast_unavailable", "reason": "short-history"},
        )
        assert get("/api/v1/forecast", **query, horizon="2h")[0] == 400
        assert get("/api/v1/forecast", **query, horizon="1h", threshold="nan")[0] == 400
        assert get("/api/v1/forecast", **query, horizon="1h", changepoint_prior_scale="1")[0] == 400
        assert get("/api/v1/forecast", **query, horizon="1h", changepoint_range="0.1")[0] == 400
        assert get("/api/v1/forecast", **query, horizon="1h", training_points="10")[0] == 400
        assert get("/api/v1/forecast", **query, horizon="1h", backtest="unknown")[0] == 400
        assert (
            get("/api/v1/forecast", **query, horizon="1h", threshold_direction="sideways")[0] == 400
        )
        assert get("/api/v1/forecast", **query, horizon="count", horizon_count="30")[0] == 400
        assert get("/api/v1/forecast", **{**query, "asset_id": "nobody"}, horizon="1h")[0] == 404
    finally:
        stop()
    forecast = next(
        item
        for item in project_asset_capabilities(workspace, "motor-01", can_ask=True)["capabilities"]
        if item["id"] == "forecast"
    )
    assert (forecast["status"], forecast["facts"]) == ("ready", {"horizon": "1h"})


def test_vibration_features_are_forecast_on_the_acquisition_axis(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal in range(1, 126):
        deliver(workspace, tmp_path / "waves", ordinal, 0.5 + 0.01 * ordinal)
    analyze(workspace)
    get, stop = _serve(workspace.root)
    try:
        status, options = get("/api/v1/forecast/options", asset_id="bearing-a")
        acquisition = options["acquisition"]
        assert status == 200 and acquisition["period_seconds"] == 60
        assert (acquisition["first"], acquisition["last"], acquisition["count"]) == (1, 125, 125)
        assert acquisition["horizons"]["1h"] is None
        status, body = get(
            "/api/v1/forecast",
            asset_id="bearing-a",
            kind="acquisition",
            series="feature.Horizontal_vibration_signals.rms",
            horizon="1h",
        )
        assert status == 200 and body["axis"] == "acquisition"
        assert body["history"][0][0] == 1 and body["history"][-1][0] == 125
        # One hour at one acquisition a minute: sixty acquisitions ahead.
        assert body["forecast"][0][0] == 125 and body["forecast"][-1][0] == pytest.approx(185)
        assert body["trend"]["direction"] == "up"
        status, count = get(
            "/api/v1/forecast",
            asset_id="bearing-a",
            kind="acquisition",
            series="feature.Horizontal_vibration_signals.rms",
            horizon="count",
            horizon_count="30",
            assumed_period_seconds="120",
        )
        assert (
            get(
                "/api/v1/forecast",
                asset_id="bearing-a",
                kind="acquisition",
                series="feature.Horizontal_vibration_signals.rms",
                horizon="count",
            )[0]
            == 400
        )
        for assumed, training, reason in [
            (120, 30, "short-history"),
            (600, 30, None),
            (600, 10, "invalid"),
        ]:
            selection_status, selected = get(
                "/api/v1/forecast/options",
                asset_id="bearing-a",
                kind="acquisition",
                series="feature.Horizontal_vibration_signals.rms",
                assumed_period_seconds=str(assumed),
                training_points=str(training),
            )
            if reason == "invalid":
                assert selection_status == 400
            else:
                assert selection_status == 200
                assert selected["selection"]["horizons"]["1h"] == reason
        assert status == 200 and count["horizon_count"] == 30
        assert count["time_basis"] == "assumed"
        assert count["recorded_period_seconds"] == 60
        assert count["period_seconds"] == 120
        assert count["forecast"][-1][0] == pytest.approx(155)
        assert len(count["forecast"]) == 31
        assert [row[0] for row in count["forecast"]] == list(range(125, 156))
        assert (
            get(
                "/api/v1/forecast",
                asset_id="bearing-a",
                kind="acquisition",
                series="feature.Horizontal_vibration_signals.rms",
                horizon="count",
                horizon_count="0",
            )[0]
            == 400
        )
    finally:
        stop()


def test_short_acquisition_record_offers_count_forecast_in_asset_shortcuts(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal in range(1, 31):
        deliver(workspace, tmp_path / "short-waves", ordinal, 0.5 + 0.01 * ordinal)
    analyze(workspace)
    get, stop = _serve(workspace.root)
    try:
        status, options = get("/api/v1/forecast/options", asset_id="bearing-a")
        assert status == 200
        assert options["acquisition"]["horizons"]["1h"] == "short-history"
        assert options["acquisition"]["count_forecast"] is True
        capability = next(
            item
            for item in project_asset_capabilities(workspace, "bearing-a", can_ask=True)[
                "capabilities"
            ]
            if item["id"] == "forecast"
        )
        assert capability["status"] == "ready"
        assert capability["reason"] == "stored-flow-count"
        status, body = get(
            "/api/v1/forecast",
            asset_id="bearing-a",
            kind="acquisition",
            series="feature.Horizontal_vibration_signals.rms",
            horizon="count",
            horizon_count="5",
        )
        assert status == 200
        assert [point[0] for point in body["forecast"]] == [30, 31, 32, 33, 34, 35]
    finally:
        stop()


@pytest.mark.parametrize("all_features_sparse", [False, True])
def test_acquisition_readiness_uses_finite_points_in_selected_feature(
    tmp_path: Path, all_features_sparse: bool
) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal in range(1, 36):
        deliver(workspace, tmp_path / "waves", ordinal, 0.5 + 0.01 * ordinal)
    analyze(workspace)
    with sqlite3.connect(workspace.phm_analysis_path) as connection:
        for position, serialized in connection.execute(
            "SELECT position, features FROM step_result WHERE state = 'analyzed' "
            "ORDER BY position"
        ).fetchall():
            if position > 20:
                continue
            features = json.loads(serialized)
            if all_features_sparse:
                features = {}
            else:
                features.pop("feature.Horizontal_vibration_signals.rms", None)
            connection.execute(
                "UPDATE step_result SET features = ? WHERE state = 'analyzed' AND position = ?",
                (json.dumps(features), position),
            )
    get, stop = _serve(workspace.root)
    try:
        status, options = get("/api/v1/forecast/options", asset_id="bearing-a")
        assert status == 200
        acquisition = options["acquisition"]
        rms = next(
            item for item in acquisition["series"]
            if item["key"] == "feature.Horizontal_vibration_signals.rms"
        )
        assert acquisition["count"] == 35  # All analyzed steps, not usable RMS values.
        assert rms["valid_points"] == 15
        assert rms["count_forecast"] is False
        assert rms["horizons"]["1h"] == "few-points"
        assert acquisition["count_forecast"] is (not all_features_sparse)
        assert (
            get(
                "/api/v1/forecast/options",
                asset_id="bearing-a",
                kind="acquisition",
                series=rms["key"],
            )[1]["selection"]["points"]
            == 15
        )
        assert (
            get(
                "/api/v1/forecast",
                asset_id="bearing-a",
                kind="acquisition",
                series=rms["key"],
                horizon="count",
                horizon_count="5",
            )[0]
            == 422
        )
        forecast = next(
            item for item in project_asset_capabilities(
                workspace, "bearing-a", can_ask=True
            )["capabilities"]
            if item["id"] == "forecast"
        )
        assert forecast["status"] == ("unavailable" if all_features_sparse else "ready")
        if not all_features_sparse:
            other = next(
                item for item in acquisition["series"] if item["valid_points"] >= 20
            )
            status, result = get(
                "/api/v1/forecast",
                asset_id="bearing-a",
                kind="acquisition",
                series=other["key"],
                horizon="count",
                horizon_count="5",
            )
            assert status == 200
            assert result["model"]["points"] == 35
    finally:
        stop()
