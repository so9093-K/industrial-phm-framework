"""An explicitly captured outlook is immutable, scoped and verifiable on read."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from industrial_phm.application.maintenance_review import FindingReviewAction
from industrial_phm.runtime.operations_web_outlook_capture import (
    OutlookCaptureCorrupted,
    OutlookCaptureStore,
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
        lambda workspace, snapshot: "unavailable",
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
