"""What an asset's stored data supports is decided from the stores, for each kind of data."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from http.client import HTTPConnection
from importlib.util import find_spec
from pathlib import Path
from threading import Thread
from typing import Any

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime.operations_web_capabilities import project_asset_capabilities
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from industrial_phm.runtime.operations_workspace import OperationsWorkspace
from tests.support.phm import analyze, deliver, phm_workspace

BASE = datetime(2026, 10, 14, tzinfo=UTC)


def _status(body: dict[str, Any]) -> dict[str, tuple[str, str]]:
    return {item["id"]: (item["status"], item["reason"]) for item in body["capabilities"]}


def _history(workspace: OperationsWorkspace, asset: str, channels: tuple[str, ...]) -> None:
    if find_spec("duckdb") is None:
        pytest.skip("DuckLake history runtime is not installed")
    DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    ).append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:{asset}:{'d' * 64}:{channel}:{index}",
                source_id=f"{asset}-file",
                asset_id=asset,
                channel_id=channel,
                source_file="m.csv",
                source_sha256="d" * 64,
                source_size_bytes=10,
                sample_index=index * len(channels) + position,
                event_at=BASE + timedelta(minutes=index),
                value=10.0 + index,
            )
            for position, channel in enumerate(channels)
            for index in range(20)
        ),
        batch_id=asset,
    )


def test_vibration_waveforms_without_a_model_say_a_model_connection_opens_everything(
    tmp_path: Path,
) -> None:
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    for ordinal in range(1, 4):
        deliver(workspace, tmp_path / "waves", ordinal, 0.5)
    body = project_asset_capabilities(workspace, "bearing-a", can_ask=True)
    status = _status(body)
    for name in ("measurements", "period-compare", "relation", "spectrum"):
        assert status[name] == ("needs-connection", "waveforms-need-model")
    assert status["anomaly"] == ("needs-connection", "compatible-model")
    assert "rul" not in status
    assert status["ai-question"] == ("unavailable", "needs-results")
    assert body["data"]["acquisition"]["analyzed_count"] == 0
    assert body["data"]["history"] is None


def test_connected_models_open_every_analysis_and_questions_follow_the_web_mode(
    tmp_path: Path,
) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.5, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    waiting = _status(project_asset_capabilities(workspace, "bearing-a", can_ask=True))
    assert waiting["anomaly"] == ("waiting", "waiting-results")
    assert waiting["ai-question"] == ("unavailable", "waiting-results")

    analyze(workspace)
    asked = project_asset_capabilities(workspace, "bearing-a", can_ask=True)
    status = _status(asked)
    assert {status[name][0] for name in status if name != "forecast"} == {"ready"}
    # Four acquisitions a minute apart are far shorter than twice the shortest horizon.
    assert status["forecast"] == ("unavailable", "short-history")
    question = next(item for item in asked["capabilities"] if item["id"] == "ai-question")
    assert question["target"] == {"view": "anomaly", "goal": "ask"}
    spectrum = next(item for item in asked["capabilities"] if item["id"] == "spectrum")
    assert spectrum["target"] == {"view": "signals", "goal": "spectrum"}
    anomaly = next(item for item in asked["capabilities"] if item["id"] == "anomaly")
    assert anomaly["facts"]["results"] == 4
    read_only = _status(project_asset_capabilities(workspace, "bearing-a", can_ask=False))
    assert read_only["ai-question"] == ("unavailable", "read-only")


def test_stored_csv_history_opens_signal_analyses_and_says_why_models_cannot_read_it(
    tmp_path: Path,
) -> None:
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    _history(workspace, "motor-01", ("current", "vibration"))
    _history(workspace, "fan-01", ("speed",))
    body = project_asset_capabilities(workspace, "motor-01", can_ask=True)
    status = _status(body)
    assert status["measurements"] == ("ready", "history")
    assert status["period-compare"] == ("ready", "history")
    assert status["relation"] == ("ready", "history")
    assert status["spectrum"] == ("unavailable", "no-waveform")
    # A CSV history is not a model input, but it can be searched for departures without one.
    assert status["anomaly"] == ("ready", "explore")
    # Twenty minutes carry an outlook (no chart horizon fits), and questions about it.
    assert status["forecast"] == ("ready", "outlook-only")
    assert status["ai-question"] == ("ready", "outlook")
    assert body["data"]["history"]["channel_count"] == 2
    assert body["data"]["history"]["measurement_count"] == 40

    assert _status(project_asset_capabilities(workspace, "fan-01", can_ask=True))["relation"] == (
        "unavailable",
        "single-signal",
    )
    empty = _status(project_asset_capabilities(workspace, "nothing-here", can_ask=True))
    assert empty["measurements"] == ("unavailable", "no-data")
    assert empty["spectrum"] == ("unavailable", "no-data")


def test_the_route_decides_question_access_from_the_web_mode(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    deliver(workspace, tmp_path / "waves", 1, 0.5)
    analyze(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def get(query: str) -> tuple[int, dict[str, Any]]:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            connection.request(
                "GET",
                "/api/v1/explore/capabilities" + query,
                headers={"Host": f"127.0.0.1:{server.server_port}"},
            )
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    try:
        status, body = get("?asset_id=bearing-a")
        assert status == 200 and body["asset_id"] == "bearing-a"
        assert _status(body)["ai-question"] == ("unavailable", "read-only")
        assert str(tmp_path) not in json.dumps(body)
        assert get("")[0] == 400
        assert get("?asset_id=a&asset_id=b")[0] == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
