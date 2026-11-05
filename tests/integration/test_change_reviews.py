"""A source-owned change stays reviewable after the current record grows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime.operations_backup import (
    create_operations_backup,
    restore_operations_backup,
)
from industrial_phm.runtime.operations_web_change_review import (
    ChangeReviewStore,
    capture_change,
    handle_change_reviews_read,
    review_change,
)
from industrial_phm.runtime.operations_web_explore import record_findings
from industrial_phm.runtime.operations_web_review import WebReviewConflict, WebReviewNotFound
from industrial_phm.runtime.operations_workspace import OperationsWorkspace
from tests.support.phm import phm_workspace


def test_a_change_review_restores_its_judgment_and_accepts_follow_up_notes(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    base = datetime(2026, 10, 1, tzinfo=UTC)

    def append(start: int, end: int) -> None:
        history.append_file_batch(
            tuple(
                FileBackfillEvent(
                    raw_evidence_id=f"file:s:{'a' * 64}:{i}",
                    source_id="source",
                    measurement_point_id="bearing",
                    asset_id="motor",
                    channel_id="temperature",
                    source_file="s.csv",
                    source_sha256="a" * 64,
                    source_size_bytes=1,
                    sample_index=i,
                    event_at=base + timedelta(minutes=i),
                    value=0 if i < 60 else 1,
                )
                for i in range(start, end)
            ),
            batch_id=f"batch-{start}",
        )

    append(0, 120)
    finding = record_findings(workspace, "motor")["intervals"][0]
    selected = {"asset_id": "motor", "finding_id": finding["review_key"]}
    captured = capture_change(workspace.root, selected)
    store = ChangeReviewStore(workspace.change_review_path)
    original = store.list_for("motor")[0]["snapshot"]
    payload = {
        "asset_id": "motor",
        "capture_id": captured["capture_id"],
        "action": "acknowledge",
        "note": "부하 변경 확인",
        "decision": "observe",
        "event_id": str(uuid4()),
    }
    assert review_change(workspace.root, payload)["status"] == "acknowledged"
    # A retry of the first request appends no duplicate event.
    review_change(workspace.root, payload)
    note = {**payload, "action": "note", "note": "다음 측정에서도 관찰", "event_id": str(uuid4())}
    del note["decision"]
    assert review_change(workspace.root, note)["status"] == "acknowledged"
    status, restored = handle_change_reviews_read(workspace, urlencode(selected))
    assert status == 200
    saved = restored["captures"][0]
    assert saved["review"]["events"][0]["decision"] == "observe"
    assert len(saved["review"]["events"]) == 2
    append(120, 180)
    assert (
        record_findings(workspace, "motor")["intervals"][0]["review_key"] != finding["review_key"]
    )
    assert capture_change(workspace.root, selected)["capture_id"] == captured["capture_id"]
    assert store.list_for("motor")[0]["snapshot"] == original
    with pytest.raises(WebReviewConflict):
        capture_change(workspace.root, {**selected, "finding_id": "f" * 64})
    with pytest.raises(WebReviewNotFound):
        review_change(workspace.root, {**note, "asset_id": "other", "event_id": str(uuid4())})
    review_change(workspace.root, {**payload, "action": "close", "event_id": str(uuid4())})
    with pytest.raises(WebReviewConflict):
        review_change(workspace.root, {**note, "event_id": str(uuid4())})
    # The workspace's ordinary backup carries the saved observation and judgment together.
    backup = tmp_path / "backup"
    manifest = create_operations_backup(workspace, backup).manifest
    assert "change-reviews.sqlite" in {item.relative_path for item in manifest.files}
    restored_workspace = OperationsWorkspace(tmp_path / "restored")
    restore_operations_backup(backup, restored_workspace)
    restored_capture = ChangeReviewStore(restored_workspace.change_review_path).list_for("motor")[0]
    assert (
        restored_capture["snapshot"] == original
        and restored_capture["review"]["status"] == "closed"
    )
