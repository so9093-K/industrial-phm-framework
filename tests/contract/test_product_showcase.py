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


def test_walkthrough_exposes_named_assets_and_real_baseline_analysis() -> None:
    responses = json.loads((FIXTURES / "responses.json").read_text())["responses"]
    assets = responses["/api/v1/monitor"]["body"]["assets"]["items"]
    changed = next(asset for asset in assets if asset["asset_id"] == "demo-pump-change")
    assert changed["asset_display_name"] == "순환 펌프 2호기 · 변화 기록"
    for asset_id in ("demo-pump-change", "demo-pump-stable"):
        key = "/api/v1/explore/anomaly?asset_id=" + asset_id + "&baseline=first-30&series=current_a"
        assert responses[key]["status"] == 200
        assert responses[key]["body"]["channels"][0]["state"] == "scored"
        if asset_id == "demo-pump-change":
            assert responses[key]["body"]["interval_count"] > 0
        else:
            assert responses[key]["body"]["interval_count"] == 0


def test_demo_media_matches_capture_manifest_and_includes_current_task_choice() -> None:
    """Published PNG and video files must match recorded actual Chromium evidence."""
    root = FIXTURES.parents[2] / "assets/showcase"
    evidence = json.loads((root / "capture.json").read_text())
    assert evidence["api_backend"] is False and evidence["data_kind"] == "synthetic"
    assert len(evidence["code_revision"]) == 40
    assert (
        evidence["snapshot_sha256"]
        == hashlib.sha256((FIXTURES / "responses.json").read_bytes()).hexdigest()
    )
    screens = evidence["screens"]
    assert [screen["name"] for screen in screens] == [
        "01-observe",
        "02-signals",
        "02a-choose-method",
        "03-anomaly",
        "04-compare",
        "05-outlook",
        "06-review",
    ]
    selected = screens[2]["path"]
    assert "tab=anomaly" in selected and "method=" not in selected
    for screen in screens:
        image = root / (screen["name"] + ".png")
        assert hashlib.sha256(image.read_bytes()).hexdigest() == screen["sha256"]
    for name in ("walkthrough.gif", "walkthrough.webm"):
        assert (
            hashlib.sha256((root / name).read_bytes()).hexdigest()
            == (evidence["media_sha256"][name])
        )


def test_csv_demo_media_matches_real_browser_recorded_files() -> None:
    """CSV onboarding/review photos must match the actual capture manifest."""
    root = FIXTURES.parents[2] / "assets/csv"
    evidence = json.loads((root / "capture.json").read_text())
    assert evidence["use_case"] == "csv"
    assert len(evidence["code_revision"]) == 40
    assert set(evidence["screens"]) == {
        "01-register.png",
        "02-attention.png",
        "03-departure.png",
        "04-summary.png",
        "05-outlook.png",
        "06-review.png",
    }
    for filename, digest in evidence["screens"].items():
        assert hashlib.sha256((root / filename).read_bytes()).hexdigest() == digest
    assert (root / "walkthrough.gif").stat().st_size > 0

