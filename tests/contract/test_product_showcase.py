"""A shareable walkthrough must remain tied to its synthetic inputs and real evidence."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from tools.showcase.prepare import csv_bytes, prepare

FIXTURES = Path(__file__).resolve().parents[2] / "examples/operations/showcase"


def test_showcase_inputs_and_stored_analysis_share_the_same_hash() -> None:
    manifest = json.loads((FIXTURES / "manifest.json").read_text())
    assert manifest["kind"] == "synthetic"
    assert (
        manifest["generator_sha256"]
        == hashlib.sha256(
            (FIXTURES.parents[2] / "tools/showcase/prepare.py").read_bytes()
        ).hexdigest()
    )
    for source in manifest["sources"]:
        raw = (FIXTURES / (source["asset_id"] + ".csv")).read_bytes()
        assert raw == csv_bytes(source["asset_id"] == "demo-pump-change")
        assert hashlib.sha256(raw).hexdigest() == source["sha256"]
        assert source["analysis"]["source_snapshot_sha256"] == source["sha256"]
        assert source["stored"]["event_count"] == 480
        rows = list(csv.DictReader(raw.decode().splitlines()))
        assert len(rows) == 240
    assert (
        manifest["review"]["analysis_run_id"]
        == manifest["sources"][1]["analysis"]["analysis_run_id"]
    )


def test_exported_session_is_read_only_and_has_no_token_or_host_path() -> None:
    raw = (FIXTURES / "responses.json").read_text()
    responses = json.loads(raw)["responses"]
    session = responses["/api/v1/session"]["body"]
    assert session["can_change"] is False and session["csrf_token"] is None
    assert session["write_scope"] == "read-only-synthetic-demo"
    assert "/Users/" not in raw and "/var/folders/" not in raw
    assert any(key.startswith("/api/v1/forecast?") for key in responses)
    assert any(key.startswith("/api/v1/outlook?") for key in responses)
    media = json.loads((FIXTURES.parents[2] / "assets/showcase/capture.json").read_text())
    assert media["snapshot_sha256"] == hashlib.sha256(raw.encode()).hexdigest()


def test_scenario_never_adopts_or_changes_an_existing_directory(tmp_path: Path) -> None:
    import pytest

    sentinel = tmp_path / "keep.txt"
    sentinel.write_text("existing user data")
    with pytest.raises(ValueError, match="new workspace"):
        prepare(tmp_path)
    assert sentinel.read_text() == "existing user data"
    assert list(tmp_path.iterdir()) == [sentinel]
