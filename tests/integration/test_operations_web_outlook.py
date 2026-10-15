"""The condition outlook over a real workspace: stored history and analyzed acquisitions."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("prophet", reason="install the forecast extra")
pytest.importorskip("duckdb")

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from tests.integration.test_operations_web_forecast import _serve
from tests.support.phm import analyze, deliver, phm_workspace

BASE = datetime(2026, 10, 14, tzinfo=UTC)


def _motor(workspace_root: Path, workspace) -> None:  # type: ignore[no-untyped-def]
    DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    ).append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:motor:{'d' * 64}:{index}",
                source_id="motor-file",
                asset_id="motor-01",
                channel_id="current",
                source_file="motor.csv",
                source_sha256="d" * 64,
                source_size_bytes=10,
                sample_index=index,
                event_at=BASE + timedelta(minutes=index),
                # Steady for two hours, then 0.05 A a minute: 14.45 A at the last minute.
                value=10.0 + 0.001 * (index % 3) + 0.05 * max(0, index - 120),
                source_metadata_json='{"binding":{"definition":{"unit":"A"}}}',
            )
            for index in range(210)
        ),
        batch_id="motor",
    )


def test_stored_history_reports_its_change_and_margin_to_both_conditions(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    _motor(tmp_path, workspace)
    get, stop = _serve(workspace.root)
    query = {"asset_id": "motor-01", "kind": "history", "series": "current"}
    try:
        status, plain = get("/api/v1/outlook", **query)
        assert status == 200 and plain["scenarios"] == [] and plain["unit"] == "A"
        assert plain["anomaly_model"] is None and plain["rate_unit"] == "hour"
        status, body = get(
            "/api/v1/outlook", **query, management_limit="16", end_limit="18", direction="upper"
        )
        assert status == 200 and body["axis"] == "time" and body["offset_unit"] == "second"
        indicator = body["degradation"]
        assert indicator["baseline"]["median"] == pytest.approx(10.001, abs=0.002)
        assert indicator["change_ratio"] > 0.2
        # 0.05 A a minute is 3 A an hour.
        assert indicator["rate"] == pytest.approx(3.0, rel=0.05)
        since = datetime.fromisoformat(indicator["departure"]["since"])
        assert BASE + timedelta(minutes=120) <= since <= BASE + timedelta(minutes=125)
        assert [item["id"] for item in body["scenarios"]] == [
            "current",
            "recent",
            "responsive",
            "linear",
        ]
        # Half of the 209 minutes recorded: the search ends 104.5 minutes after the last value.
        assert body["search"]["seconds"] == pytest.approx(209 * 30)
        linear = body["scenarios"][-1]["limits"]
        # 1.55 A to go at 0.05 A a minute, and 3.55 A to the end condition.
        assert linear["management"]["expected"] == pytest.approx(31 * 60, rel=0.02)
        assert linear["end"]["expected"] == pytest.approx(71 * 60, rel=0.02)
        for scenario in body["scenarios"][:3]:
            assert scenario["limits"]["management"]["state"] in {"expected", "possible", "beyond"}
        assert body["conditions"] == {"direction": "upper", "management": 16.0, "end": 18.0}
        assert body["meaning"] == "remaining-margin-to-user-conditions-not-a-diagnosis"
        assert str(tmp_path) not in json.dumps(body)

        status, lower = get("/api/v1/outlook", **query, management_limit="12", direction="lower")
        assert status == 200
        assert lower["scenarios"][0]["limits"]["management"]["state"] == "beyond"

        assert get("/api/v1/outlook", **query, management_limit="nan")[0] == 400
        assert get("/api/v1/outlook", **query, direction="sideways")[0] == 400
        assert get("/api/v1/outlook", **query, training_points="10")[0] == 400
        assert get("/api/v1/outlook", **query, assumed_period_seconds="60")[0] == 400
        assert get("/api/v1/outlook", asset_id="motor-01", kind="history")[0] == 400
        assert get("/api/v1/outlook", **{**query, "asset_id": "nobody"})[0] == 404
    finally:
        stop()


def test_acquisitions_report_margins_in_acquisitions_with_the_anomaly_model(
    tmp_path: Path,
) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal in range(1, 65):
        # Horizontal RMS is 1.118 times the scale; the model's score passes 2.0 from #62 on.
        scale = 0.5 + 0.002 * (ordinal % 3) if ordinal <= 40 else 0.5 + 0.06 * (ordinal - 40)
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    get, stop = _serve(workspace.root)
    try:
        status, body = get(
            "/api/v1/outlook",
            asset_id="bearing-a",
            kind="acquisition",
            series="feature.Horizontal_vibration_signals.rms",
            management_limit="2.4",
            end_limit="3.0",
        )
        assert status == 200 and body["axis"] == "acquisition"
        assert body["offset_unit"] == "acquisition" and body["rate_unit"] == "acquisition"
        assert body["record"] == {"first": 1, "last": 64, "points": 64}
        # Half of the 63 acquisition intervals recorded, rounded down.
        assert body["search"] == {"seconds": 1860.0, "acquisitions": 31, "until": 95}
        indicator = body["degradation"]
        assert indicator["rate"] == pytest.approx(0.06 * 1.118, rel=0.02)
        assert 41 <= indicator["departure"]["since"] <= 43
        linear = body["scenarios"][-1]["limits"]
        # From 2.17 at #64, 0.067 an acquisition: 2.4 is 4 acquisitions on, 3.0 is 13.
        assert linear["management"] == {
            "state": "expected",
            "expected": 4,
            "earliest": None,
            "latest": None,
        }
        assert linear["end"]["expected"] == 13
        model = body["anomaly_model"]
        assert model["binding_id"] == "anomaly-a" and model["results"] == 64
        assert model["latest"]["position"] == 64 and model["latest"]["exceeds"] is True
        assert model["first_exceeding"]["position"] == 62
        assert model["recent"] == {"results": 10, "exceeding": 3}
        assert model["interval_count"] == 1 and model["intervals"][0]["open"] is True
        original_version = body["data_version"]
        # A long history is sampled by analyzed_between: tail and first crossing must
        # instead use exact database queries, including analyzed results past 2,000.
        with sqlite3.connect(workspace.phm_analysis_path) as connection:
            template = connection.execute(
                "SELECT * FROM step_result WHERE binding_id = 'anomaly-a' "
                "AND position = 64"
            ).fetchone()
            assert template is not None
            rows = []
            for position in range(65, 2106):
                row = list(template)
                row[1] = f"synthetic-{position}"
                row[2] = position
                output = json.loads(row[8])
                output["exceeds_threshold"] = position == 2104
                row[8] = json.dumps(output)
                rows.append(row)
            connection.executemany(
                "INSERT INTO step_result VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows
            )
        status, extended = get(
            "/api/v1/outlook",
            asset_id="bearing-a",
            kind="acquisition",
            series="feature.Horizontal_vibration_signals.rms",
        )
        assert status == 200
        evidence = extended["anomaly_model"]
        assert evidence["results"] == 2105 and evidence["read"] == 2105
        assert evidence["first_exceeding"]["position"] == 62
        assert evidence["recent"] == {"results": 10, "exceeding": 1}
        assert extended["data_version"] != original_version
        # A model for another source must never be attached to this signal's outlook.
        with sqlite3.connect(workspace.phm_analysis_path) as connection:
            connection.execute(
                "UPDATE binding SET source_id = 'unrelated' WHERE asset_id = 'bearing-a'"
            )
        status, other = get(
            "/api/v1/outlook",
            asset_id="bearing-a",
            kind="acquisition",
            series="feature.Horizontal_vibration_signals.rms",
        )
        assert status == 200 and other["anomaly_model"] is None
    finally:
        stop()
