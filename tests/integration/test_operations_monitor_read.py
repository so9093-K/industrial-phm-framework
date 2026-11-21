"""The monitor list is not 'unreadable' because another screen is reading the history store."""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import filelock
import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime import operations_app_composition as composition
from tests.support.phm import phm_workspace

BASE = datetime(2026, 10, 1, tzinfo=UTC)


def test_the_monitor_keeps_its_assets_while_another_screen_holds_the_history_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    ).append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:meter:{'a' * 64}:voltage-{index}",
                source_id="meter",
                asset_id="compressor",
                channel_id="voltage",
                source_file="meter.csv",
                source_sha256="a" * 64,
                source_size_bytes=10,
                sample_index=index,
                event_at=BASE + timedelta(minutes=index),
                value=220.0,
                source_metadata_json='{"binding":{"definition":{"unit":"V"}}}',
            )
            for index in range(5)
        ),
        batch_id="part",
    )
    environ = {"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(workspace.root)}
    first = composition.load_operations_app_snapshot(environ=environ)
    assert [row.asset_id for row in first.history_assets] == ["compressor"]
    assert not first.system_errors

    # 전망 계산처럼 다른 연결이 저장소 잠금을 쥐고 있는 동안 관측 목록을 다시 읽는다.
    monkeypatch.setattr(composition, "LIST_BUSY_WAIT_SECONDS", 0.2)
    held = filelock.FileLock(str(workspace.history_catalog_path) + ".phm.lock")
    holding, release = threading.Event(), threading.Event()

    def hold() -> None:
        with held:
            holding.set()
            release.wait()

    other = threading.Thread(target=hold)
    other.start()
    holding.wait()
    try:
        busy = composition.load_operations_app_snapshot(environ=environ)
    finally:
        release.set()
        other.join()
    # 기다리다 놓친 것은 고장이 아니다: 목록은 그대로이고 '읽지 못함'으로 알리지 않는다.
    assert busy.history_assets == first.history_assets
    assert not busy.system_errors
    assert busy.history_reader is not None
