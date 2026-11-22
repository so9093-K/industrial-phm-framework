"""Channel meanings pinned to one stored snapshot are read once; a new snapshot is read again."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from tests.support.phm import phm_workspace

BASE = datetime(2026, 10, 1, tzinfo=UTC)
CURRENT = json.dumps(
    {"semantics": {"definition": {"observed_property": "phase current", "unit": "A"}}}
)


def _append(history: DuckLakeAssetHistory, minutes: range, batch: str) -> None:
    history.append_file_batch(
        tuple(
            FileBackfillEvent(
                raw_evidence_id=f"file:boiler:{'c' * 64}:{batch}:{index}",
                source_id="boiler-file",
                asset_id="boiler-01",
                channel_id="전류",
                source_file="boiler.csv",
                source_sha256="c" * 64,
                source_size_bytes=10,
                sample_index=index,
                event_at=BASE + timedelta(minutes=index),
                value=9.0 + (index % 5) * 0.1,
                source_metadata_json=CURRENT,
            )
            for index in minutes
        ),
        batch_id=batch,
    )


def test_channel_meanings_at_one_snapshot_are_read_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("duckdb")
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    config = DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    history = DuckLakeAssetHistory(config)
    _append(history, range(30), "first")
    reads: list[int] = []
    real = DuckLakeAssetHistory._channel_semantics

    def counted(self: DuckLakeAssetHistory, *args: object) -> object:
        reads.append(1)
        return real(self, *args)  # type: ignore[arg-type]

    monkeypatch.setattr(DuckLakeAssetHistory, "_channel_semantics", counted)

    def ask(reader: DuckLakeAssetHistory) -> tuple[object, ...]:
        (stream,) = reader.list_history_streams("boiler-01")
        return reader.list_channel_semantics(
            "boiler-01",
            source_id=stream.source_id,
            start_at=stream.start_at,
            end_at=stream.end_at + timedelta(seconds=1),
            snapshot_id=reader.current_snapshot_id(),
        )

    first = ask(history)
    # 다른 화면이 새로 연 읽기도 같은 저장 시점이면 다시 읽지 않는다.
    assert ask(DuckLakeAssetHistory(config)) == first
    assert len(reads) == 1
    # 기록이 더해져 저장 시점이 바뀌면 새로 읽는다.
    _append(history, range(30, 60), "second")
    ask(history)
    assert len(reads) == 2
