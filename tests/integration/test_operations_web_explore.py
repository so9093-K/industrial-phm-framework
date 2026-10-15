"""Signal exploration routes over a real workspace: acquisition features and stored history."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from http.client import HTTPConnection
from importlib.util import find_spec
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import urlencode

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.phm import analyze, deliver, phm_workspace

RMS = "feature.Horizontal_vibration_signals.rms"
BASE = datetime(2026, 10, 14, tzinfo=UTC)


def _serve(root: Path):
    server = create_operations_web_read_server(root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def get(path: str, **query: Any) -> tuple[int, dict[str, Any]]:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            url = path + ("?" + urlencode(query, doseq=True) if query else "")
            connection.request("GET", url, headers={"Host": f"127.0.0.1:{server.server_port}"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def stop() -> None:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)

    return get, stop


def test_acquisition_ranges_are_compared_by_their_stored_features(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.5, 0.55, 0.5, 3.0, 3.1, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    get, stop = _serve(workspace.root)
    try:
        status, sources = get("/api/v1/explore/sources", asset_id="bearing-a")
        assert status == 200 and sources["history"] is None
        acquisition = sources["acquisition"]
        assert (acquisition["first"], acquisition["last"], acquisition["count"]) == (1, 8, 8)
        assert {"key": RMS, "label": "수평 진동 RMS"} in acquisition["features"]
        assert [m["task"] for m in acquisition["models"]] == ["anomaly-score", "anomaly-score"]

        status, body = get(
            "/api/v1/explore/profile",
            asset_id="bearing-a",
            kind="acquisition",
            series=[RMS],
            a_from=1,
            a_to=4,
            b_from=5,
            b_to=8,
        )
        assert status == 200 and body["periods"] == {
            "a": {"from": 1, "to": 4},
            "b": {"from": 5, "to": 8},
        }
        (series,) = body["series"]
        a, b = series["periods"]["a"], series["periods"]["b"]
        assert (a["observation_count"], a["usable_count"], a["missing_count"]) == (4, 4, 0)
        assert b["quantiles"][2] > a["quantiles"][2]
        assert series["comparison"]["b_outside_a_band"] == 4
        assert series["comparison"]["b_outside_a_band_percent"] == 100
        assert sum(series["histogram"]["a"]) == 4 and sum(series["histogram"]["b"]) == 4
        assert str(tmp_path) not in json.dumps(body)

        ranges = {"a_from": 1, "a_to": 4, "b_from": 5, "b_to": 8}
        status, relation = get(
            "/api/v1/explore/relation",
            asset_id="bearing-a",
            kind="acquisition",
            x=RMS,
            y="feature.Horizontal_vibration_signals.peak_to_peak",
            **ranges,
        )
        assert status == 200 and relation["pairing"] == "same-acquisition"
        assert [g["pair_count"] for g in relation["groups"]] == [4, 4]
        assert relation["groups"][1]["points"][0][0] == 5

        status, spectrum = get("/api/v1/explore/spectrum", asset_id="bearing-a", **ranges)
        assert status == 200 and spectrum["sampling_rate_hz"] == 1000
        assert spectrum["acquisitions"] == {"a": [1, 2, 3, 4], "b": [5, 6, 7, 8]}
        horizontal = spectrum["channels"][0]
        assert len(horizontal["a"]) == len(horizontal["b"]) == len(spectrum["frequencies"])
        # B carries six times the amplitude of A: about 15 dB more power in its strongest band.
        assert max(band["change_db"] for band in horizontal["band_changes"]) > 10

        assert get("/api/v1/explore/profile", asset_id="bearing-a", kind="acquisition")[0] == 400
        bad = {"a_from": 4, "a_to": 1, "b_from": 5, "b_to": 8}
        query = {"asset_id": "bearing-a", "kind": "acquisition", "series": [RMS], **bad}
        assert get("/api/v1/explore/profile", **query)[0] == 400
        history = {"a_from": BASE.isoformat(), "a_to": BASE.isoformat()}
        query = {"asset_id": "bearing-a", "kind": "history", "series": ["x"], **history}
        assert get("/api/v1/explore/profile", **query)[0] == 404
    finally:
        stop()


def test_stored_history_periods_are_compared_from_raw_observations(tmp_path: Path) -> None:
    if find_spec("duckdb") is None:
        pytest.skip("DuckLake history runtime is not installed")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    events = [
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
            value=10.0 + (5.0 if index >= 30 else 0.0) + (index % 3) * 0.1,
            source_metadata_json='{"binding":{"definition":{"unit":"A"}}}',
        )
        for index in range(60)
    ]
    # The voltage mapping changes from V to kV halfway through the second period.
    events += [
        FileBackfillEvent(
            raw_evidence_id=f"file:motor:{'b' * 64}:v{index}",
            source_id="motor-file",
            asset_id="motor-01",
            channel_id="voltage",
            source_file="motor.csv",
            source_sha256="b" * 64,
            source_size_bytes=10,
            sample_index=100 + index,
            event_at=BASE + timedelta(minutes=index),
            value=(380.0 + index) / (1000 if index >= 45 else 1),
            source_metadata_json='{"binding":{"definition":{"unit":"%s"}}}'
            % ("kV" if index >= 45 else "V"),
        )
        for index in range(60)
    ]
    history.append_file_batch(tuple(events), batch_id="motor")
    get, stop = _serve(workspace.root)
    try:
        status, sources = get("/api/v1/explore/sources", asset_id="motor-01")
        assert status == 200 and sources["acquisition"] is None
        assert sources["history"]["channels"] == ["current", "voltage"]
        assert sources["history"]["measurement_count"] == 120
        middle = BASE + timedelta(minutes=30)
        status, body = get(
            "/api/v1/explore/profile",
            asset_id="motor-01",
            kind="history",
            series=["current"],
            a_from=BASE.isoformat(),
            a_to=middle.isoformat(),
            b_from=middle.isoformat(),
            b_to=(BASE + timedelta(hours=1)).isoformat(),
        )
        assert status == 200
        (series,) = body["series"]
        assert series["unit"] == "A" and series["source_id"] == "motor-file"
        a, b = series["periods"]["a"], series["periods"]["b"]
        assert (a["usable_count"], b["usable_count"]) == (30, 30)
        assert a["median_interval_seconds"] == 60 and a["largest_gap"]["seconds"] == 60
        assert series["comparison"]["median_change"] == pytest.approx(5.0)
        assert series["comparison"]["b_outside_a_band_percent"] == 100
        status, relation = get(
            "/api/v1/explore/relation",
            asset_id="motor-01",
            kind="history",
            x="current",
            y="voltage",
            a_from=BASE.isoformat(),
            a_to=middle.isoformat(),
            b_from=middle.isoformat(),
            b_to=(BASE + timedelta(hours=1)).isoformat(),
        )
        assert status == 200
        units = sorted((g["period"], g["y_unit"], g["pair_count"]) for g in relation["groups"])
        assert units == [("a", "V", 30), ("b", "V", 15), ("b", "kV", 15)]
        assert (
            get(
                "/api/v1/explore/spectrum", asset_id="motor-01", a_from=1, a_to=2, b_from=3, b_to=4
            )[0]
            == 404
        )
    finally:
        stop()
