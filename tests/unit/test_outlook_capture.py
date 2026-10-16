"""An explicitly captured outlook is immutable, scoped and verifiable on read."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from industrial_phm.runtime.operations_web_outlook_capture import (
    OutlookCaptureCorrupted,
    OutlookCaptureStore,
)


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
