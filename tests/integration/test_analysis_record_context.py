"""A selected source, point and meaning remains the subject of every analysis and review."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("prophet")
pytest.importorskip("duckdb")

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime.operations_web_explore import record_findings
from industrial_phm.runtime.operations_web_outlook_capture import (
    capture_outlook,
    handle_outlook_captures_read,
)
from tests.integration.test_operations_web_forecast import _serve
from tests.support.phm import phm_workspace


def test_analyses_and_saved_outlook_keep_the_selected_record(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    for version, (source, point, unit, count, changed) in enumerate(
        (
            ("a", None, "°C", 600, False),
            ("b", "end", "°C", 180, True),
            ("b", "end", "K", 300, True),
            ("b", None, "°C", 240, False),
        )
    ):
        token = f"{source}-{point}-{unit}"
        history.append_file_batch(
            tuple(
                FileBackfillEvent(
                    raw_evidence_id=f"file:{token}:{'c' * 64}:{i}",
                    source_id=source,
                    asset_id="motor",
                    measurement_point_id=point,
                    channel_id="temperature",
                    source_file="t.csv",
                    source_sha256="c" * 64,
                    source_size_bytes=10,
                    sample_index=version * 10000 + i,
                    event_at=datetime(2026, 10, 1, tzinfo=UTC) + timedelta(minutes=i),
                    value=float(65 if changed and i >= 60 else 40),
                    source_metadata_json=json.dumps({"binding": {"definition": {"unit": unit}}}),
                )
                for i in range(count)
            ),
            batch_id=token,
        )
    results = record_findings(workspace, "motor")
    assert results["intervals"], results
    found = next(row for row in results["intervals"] if row["unit"] == "°C")
    assert found["source_id"] == "b" and found["measurement_point_id"] == "end"
    assert 2 <= len(found["trace"]) <= 54
    assert {row[1] for row in found["trace"]} == {40.0, 65.0}
    query = {"asset_id": "motor", "kind": "history", "series": "temperature"}
    focus = {
        "monitor_source": "b",
        "monitor_point": "end",
        "monitor_interpretation": found["interpretation_id"],
    }
    get, stop = _serve(workspace.root)
    try:
        status, options = get("/api/v1/forecast/options", **query, **focus)
        assert status == 200 and options["selection"]["record_key"] == found["key"]
        assert len(options["selection"]["records"]) == 4
        selected = {**query, "record_key": found["key"]}
        for route, args in (
            ("/api/v1/explore/anomaly", selected),
            ("/api/v1/forecast", {**selected, "horizon": "1h"}),
            ("/api/v1/outlook", selected),
        ):
            status, body = get(route, **args)
            assert status == 200
            context = body["record"] if route.endswith("anomaly") else body
            assert context["source_id"] == "b"
            assert context["measurement_point_id"] == "end"
            if not route.endswith("anomaly"):
                assert body["record_key"] == found["key"] and body["unit"] == "°C"
        _, outlook = get("/api/v1/outlook", **selected)
        payload = {
            **selected,
            "source_id": "b",
            "measurement_version": outlook["measurement_version"],
            "data_version": outlook["data_version"],
        }
        saved = capture_outlook(workspace.root, payload)
        status, captures = handle_outlook_captures_read(workspace, "asset_id=motor")
        assert status == 200 and captures["captures"][0]["capture_id"] == saved["capture_id"]
        assert captures["captures"][0]["source_recheck"] == "same_measurement_projection"
        assert captures["captures"][0]["snapshot"]["identity"]["record_key"] == found["key"]
        for route in (
            "/api/v1/forecast/options",
            "/api/v1/forecast",
            "/api/v1/outlook",
            "/api/v1/explore/anomaly",
        ):
            assert get(route, **query, record_key="0" * 64, horizon="1h")[0] == 404
        # Null is a real point identity, not permission to select a different point.
        status, null_point = get(
            "/api/v1/forecast/options", **query, monitor_source="b", monitor_point=""
        )
        assert status == 200
        key = null_point["selection"]["record_key"]
        assert (
            next(row for row in null_point["selection"]["records"] if row["key"] == key)[
                "measurement_point_id"
            ]
            is None
        )
    finally:
        stop()
