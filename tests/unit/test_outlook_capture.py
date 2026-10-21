"""An explicitly captured outlook is immutable, scoped and verifiable on read."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from industrial_phm.application.maintenance_review import FindingReviewAction
from industrial_phm.runtime.operations_web_forecast import measurement_version
from industrial_phm.runtime.operations_web_outlook_capture import (
    OutlookCaptureCorrupted,
    OutlookCaptureStore,
    capture_outlook,
    handle_outlook_captures_read,
)
from industrial_phm.runtime.operations_web_review import WebReviewConflict, WebReviewNotFound
from industrial_phm.runtime.operations_workspace import OperationsWorkspace


def _snapshot(*, last: int = 64) -> dict[str, object]:
    return {
        "schema_version": 1,
        "identity": {
            "asset_id": "bearing-a",
            "kind": "acquisition",
            "series": "rms",
            "record_last": last,
        },
        "selection": {"asset_id": "bearing-a", "kind": "acquisition", "series": "rms"},
        "outlook": {
            "asset_id": "bearing-a",
            "kind": "acquisition",
            "axis": "acquisition",
            "record": {"first": 1, "last": last, "points": last},
            "measurement_version": "a" * 64,
            "data_version": "b" * 64,
            "conditions": {"management": 2.4, "end": 3.0, "direction": "upper"},
            "scenarios": [{"id": "current", "limits": {"management": {"state": "possible"}}}],
        },
        "meaning": "captured-condition-outlook-not-actual-failure-or-maintenance",
    }


def test_capture_is_idempotent_and_new_observation_has_another_identity(tmp_path: Path) -> None:
    store = OutlookCaptureStore(tmp_path / "outlook.sqlite")
    assert store.list_for("bearing-a") == []
    assert not store.path.exists()  # Read-only never initializes a writeable store.
    first = store.save(_snapshot())
    again = store.save(_snapshot())
    assert first == again
    changed = store.save(_snapshot(last=65))
    assert first["capture_id"] != changed["capture_id"]
    assert len(store.list_for("bearing-a")) == 2
    assert store.list_for("bearing-b") == []
    assert store.list_for("bearing-a", capture_id=first["capture_id"])[0]["snapshot"] == (
        _snapshot()
    )
    assert store.list_for("bearing-b", capture_id=first["capture_id"]) == []


def test_captured_content_digest_is_checked_instead_of_trusting_saved_bytes(tmp_path: Path) -> None:
    store = OutlookCaptureStore(tmp_path / "outlook.sqlite")
    result = store.save(_snapshot())
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE capture SET snapshot=? WHERE id=?",
            (json.dumps(_snapshot(last=66)), result["capture_id"]),
        )
    with pytest.raises(OutlookCaptureCorrupted, match="digest mismatch"):
        store.list_for("bearing-a")


def test_review_events_are_exact_scoped_idempotent_and_persisted(tmp_path: Path) -> None:
    path = tmp_path / "outlook.sqlite"
    store = OutlookCaptureStore(path)
    capture = store.save(_snapshot())["capture_id"]
    wrong_asset = "bearing-b"
    event = str(uuid4())
    with pytest.raises(WebReviewNotFound):
        store.write_review(wrong_asset, capture, FindingReviewAction.NOTE, "확인", event)
    first = store.write_review("bearing-a", capture, FindingReviewAction.NOTE, "확인", event)
    assert first["status"] == "open"
    assert store.write_review("bearing-a", capture, FindingReviewAction.NOTE, "확인", event) == (
        first
    )
    with pytest.raises(WebReviewConflict):
        store.write_review("bearing-a", capture, FindingReviewAction.NOTE, "수정", event)
    acknowledged = store.write_review(
        "bearing-a", capture, FindingReviewAction.ACKNOWLEDGE, "", str(uuid4())
    )
    assert acknowledged["status"] == "acknowledged"
    with pytest.raises(WebReviewConflict):
        store.write_review("bearing-a", capture, FindingReviewAction.ACKNOWLEDGE, "", str(uuid4()))
    closed = store.write_review("bearing-a", capture, FindingReviewAction.CLOSE, "", str(uuid4()))
    assert closed["status"] == "closed"
    with pytest.raises(WebReviewConflict):
        store.write_review("bearing-a", capture, FindingReviewAction.NOTE, "늦음", str(uuid4()))
    restored = OutlookCaptureStore(path).list_for("bearing-a", capture_id=capture)[0]
    assert restored["review"]["status"] == "closed"
    assert [row["action"] for row in restored["review"]["events"]] == [
        "note",
        "acknowledge",
        "close",
    ]
    assert restored["snapshot"] == _snapshot()


def test_captured_review_history_can_be_paginated_without_losing_old_entries(
    tmp_path: Path,
) -> None:
    store = OutlookCaptureStore(tmp_path / "outlook.sqlite")
    for ordinal in range(30, 55):
        store.save(_snapshot(last=ordinal))
    first = store.list_for("bearing-a", limit=20)
    assert len(first) == 20
    second = store.list_for("bearing-a", before_id=first[-1]["capture_id"], limit=20)
    assert len(second) == 5
    ids = [record["capture_id"] for record in first + second]
    assert len(set(ids)) == 25
    assert store.list_for("bearing-a", before_id=second[-1]["capture_id"]) == []
    assert store.list_for("bearing-b") == []
    with pytest.raises(LookupError, match="cursor"):
        store.list_for("bearing-b", before_id=first[-1]["capture_id"])


def test_outlook_capture_api_pages_after_exact_asset_scoped_cursor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = OperationsWorkspace(tmp_path)
    store = OutlookCaptureStore(workspace.outlook_capture_path)
    for ordinal in range(30, 55):
        store.save(_snapshot(last=ordinal))
    monkeypatch.setattr(
        "industrial_phm.runtime.operations_web_outlook_capture.current_measurement_recheck",
        lambda workspace, snapshot, **kwargs: "unavailable",
    )
    status, first = handle_outlook_captures_read(workspace, "asset_id=bearing-a")
    assert status == 200 and len(first["captures"]) == 20
    assert first["next_before"] == first["captures"][-1]["capture_id"]
    status, second = handle_outlook_captures_read(
        workspace, "asset_id=bearing-a&before_id=" + first["next_before"]
    )
    assert status == 200 and len(second["captures"]) == 5
    assert "next_before" not in second
    first_ids = {item["capture_id"] for item in first["captures"]}
    second_ids = {item["capture_id"] for item in second["captures"]}
    assert first_ids.isdisjoint(second_ids)
    old_id = second["captures"][-1]["capture_id"]
    direct_status, direct = handle_outlook_captures_read(
        workspace, "asset_id=bearing-a&capture_id=" + old_id
    )
    assert direct_status == 200
    assert len(direct["captures"]) == 1
    assert direct["captures"][0]["capture_id"] == old_id
    wrong_asset_status, _ = handle_outlook_captures_read(
        workspace, "asset_id=other&before_id=" + first["next_before"]
    )
    invalid_cursor_status, _ = handle_outlook_captures_read(
        workspace, "asset_id=bearing-a&before_id=not-a-capture"
    )
    assert wrong_asset_status == 404
    assert invalid_cursor_status == 400


def test_page_rechecks_each_distinct_measurement_projection_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = OperationsWorkspace(tmp_path)
    store = OutlookCaptureStore(workspace.outlook_capture_path)
    asset, kind, series = "bearing-a", "history", "rms"
    times = [datetime(2026, 10, 1, tzinfo=UTC) + timedelta(minutes=i) for i in range(25)]
    values = [float(i) for i in range(25)]
    meta = {"source_id": "bench", "measurement_point_id": None, "time_basis": "recorded"}
    version = measurement_version(asset, kind, series, times, values, meta)
    for last, expected_version in ((64, version), (65, "0" * 64)):
        snapshot = _snapshot(last=last)
        snapshot["identity"].update(
            {
                "kind": kind,
                "source_id": "bench",
                "measurement_point_id": None,
                "time_basis": "recorded",
                "measurement_version": expected_version,
            }
        )
        snapshot["selection"]["kind"] = kind
        snapshot["outlook"]["kind"] = kind
        store.save(snapshot)
    requests = []

    def history(workspace: OperationsWorkspace, asset_id: str, name: str):
        requests.append((asset_id, name))
        return times, values, meta

    monkeypatch.setattr(
        "industrial_phm.runtime.operations_web_outlook_capture.history_points", history
    )
    status, response = handle_outlook_captures_read(workspace, "asset_id=bearing-a")
    assert status == 200
    assert {item["source_recheck"] for item in response["captures"]} == {
        "same_measurement_projection",
        "changed",
    }
    assert requests == [(asset, series)]


def test_capture_rejects_changed_acquisition_provenance_before_saving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = OperationsWorkspace(tmp_path)
    recomputed = {
        "schema_version": 1,
        "asset_id": "bearing-a",
        "kind": "acquisition",
        "series": "rms",
        "source_id": "bench",
        "binding_id": "anomaly-a",
        "measurement_point_id": None,
        "axis": "acquisition",
        "time_basis": "recorded",
        "period_seconds": 60.0,
        "recorded_period_seconds": 60.0,
        "record": {"first": 1, "last": 64, "points": 64},
        "conditions": {"direction": "upper", "management": 2.4, "end": None},
        "settings": {
            "changepoint_prior_scale": 0.05,
            "changepoint_range": 0.8,
            "training_points": None,
            "seasonality": "off",
        },
        "measurement_version": "a" * 64,
        "data_version": "b" * 64,
    }
    monkeypatch.setattr(
        "industrial_phm.runtime.operations_web_outlook_capture.condition_outlook",
        lambda workspace, **arguments: dict(recomputed),
    )
    legacy = {
        "asset_id": "bearing-a",
        "kind": "acquisition",
        "series": "rms",
        "management_limit": "2.4",
        "measurement_version": "a" * 64,
        "data_version": "b" * 64,
    }
    store = OutlookCaptureStore(workspace.outlook_capture_path)
    for name, displayed in (
        ("binding_id", "anomaly-b"),
        ("source_id", "other-bench"),
        ("time_basis", "ordinal"),
        ("recorded_period_seconds", "30"),
    ):
        with pytest.raises(ValueError, match="evidence changed"):
            capture_outlook(workspace.root, {**legacy, name: displayed})
        assert store.list_for("bearing-a") == []
    exact = {
        **legacy,
        "source_id": "bench",
        "binding_id": "anomaly-a",
        "time_basis": "recorded",
        "recorded_period_seconds": "60",
    }
    with_provenance = capture_outlook(workspace.root, exact)
    # Provenance selectors are checks only: the legacy request names the same capture.
    assert capture_outlook(workspace.root, legacy)["capture_id"] == with_provenance["capture_id"]
    (saved,) = store.list_for("bearing-a")
    assert "binding_id" not in saved["snapshot"]["selection"]
    assert saved["snapshot"]["outlook"]["binding_id"] == "anomaly-a"
    with pytest.raises(ValueError, match="unexpected capture fields"):
        capture_outlook(workspace.root, {**exact, "package_id": "model-a"})


def test_capture_review_keeps_the_decision_and_reads_stores_from_before_it(
    tmp_path: Path,
) -> None:
    import sqlite3

    from industrial_phm.application.maintenance_review import ReviewDecision

    path = tmp_path / "outlook.sqlite"
    store = OutlookCaptureStore(path)
    capture = store.save(_snapshot())["capture_id"]
    store.write_review(
        "bearing-a",
        capture,
        FindingReviewAction.ACKNOWLEDGE,
        "",
        str(uuid4()),
        ReviewDecision.OBSERVE,
    )
    events = store.list_for("bearing-a", capture_id=capture)[0]["review"]["events"]
    assert [row["decision"] for row in events] == ["observe"]
    # A store written before decisions existed: no column until the next write, read as none.
    old = tmp_path / "old.sqlite"
    previous = OutlookCaptureStore(old)
    kept = previous.save(_snapshot())["capture_id"]
    previous.write_review("bearing-a", kept, FindingReviewAction.NOTE, "확인", str(uuid4()))
    with sqlite3.connect(old) as connection:
        connection.execute("ALTER TABLE review_event DROP COLUMN decision")
    assert [row["decision"] for row in previous.read_review(kept)["events"]] == [None]
