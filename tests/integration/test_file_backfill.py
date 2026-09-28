from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from industrial_phm.application import (
    FileSourceConfig,
    FileSourceMode,
    HistoricalBatchCommit,
    HistoryIngestionMode,
    InMemorySourceRepository,
    RegisteredSource,
    backfill_registered_file_source,
)

BASE = datetime(2026, 9, 28, 8, 0, tzinfo=UTC)


class _History:
    def __init__(self) -> None:
        self.commits: dict[str, HistoricalBatchCommit] = {}
        self.events_by_batch: dict[str, tuple[object, ...]] = {}
        self.append_count = 0

    def get_file_batch_commit(
        self,
        events,
        *,
        batch_id,
        ingestion_mode=HistoryIngestionMode.BACKFILL,
    ):
        assert ingestion_mode == HistoryIngestionMode.BACKFILL
        existing = self.commits.get(batch_id)
        if existing is not None:
            assert self.events_by_batch[batch_id] == tuple(events)
        return existing

    def append_file_batch(
        self,
        events,
        *,
        batch_id,
        ingestion_mode=HistoryIngestionMode.BACKFILL,
    ):
        assert ingestion_mode == HistoryIngestionMode.BACKFILL
        self.append_count += 1
        batch = tuple(events)
        commit = HistoricalBatchCommit(
            batch_id=batch_id,
            snapshot_id=self.append_count,
            event_count=len(batch),
            committed_at=BASE + timedelta(seconds=self.append_count),
        )
        self.events_by_batch[batch_id] = batch
        self.commits[batch_id] = commit
        return commit

    def current_snapshot_id(self) -> int:
        return self.append_count


def _write_csv(path: Path, rows: tuple[tuple[str, float, float], ...]) -> None:
    path.write_text(
        "timestamp,vibration_x,temperature\n"
        + "".join(f"{ts},{vibration},{temperature}\n" for ts, vibration, temperature in rows),
        encoding="utf-8",
    )


def _registered_history_source(path: Path) -> tuple[InMemorySourceRepository, RegisteredSource]:
    source = RegisteredSource(
        source_id="file-history",
        name="Historical pump export",
        config=FileSourceConfig(
            source_path=str(path),
            asset_id="pump-01",
            measurement_point_id="drive-end",
            channel_columns=("vibration_x", "temperature"),
            mode=FileSourceMode.HISTORY_DIRECTORY,
            timestamp_column="timestamp",
        ),
        registered_at=BASE,
    )
    repository = InMemorySourceRepository()
    repository.register(source)
    return repository, source


def test_registered_file_backfill_uses_stable_segment_checkpoints(tmp_path: Path) -> None:
    source_dir = tmp_path / "history"
    source_dir.mkdir()
    _write_csv(
        source_dir / "a.csv",
        (
            ("2026-09-28T08:00:01+00:00", 1.0, 10.0),
            ("2026-09-28T08:00:02+00:00", 2.0, 11.0),
        ),
    )
    _write_csv(
        source_dir / "b.csv",
        (
            ("2026-09-28T08:00:03+00:00", 3.0, 12.0),
            ("2026-09-28T08:00:04+00:00", 4.0, 13.0),
        ),
    )
    repository, _ = _registered_history_source(source_dir)
    history = _History()

    first = backfill_registered_file_source(repository, history, "file-history")
    assert first.event_count == 8
    assert first.recovered_segment_count == 0
    assert first.history_snapshot_id == 2
    assert [segment.source_file for segment in first.segments] == ["a.csv", "b.csv"]
    assert first.input_reference.asset_id == "pump-01"
    assert first.input_reference.measurement_point_id == "drive-end"
    assert first.input_reference.channel_ids == ("vibration_x", "temperature")
    assert first.input_reference.start_at == BASE + timedelta(seconds=1)
    assert first.input_reference.end_at == BASE + timedelta(seconds=4, microseconds=1)

    raw_events = tuple(
        event
        for batch in history.events_by_batch.values()
        for event in batch
    )
    assert len({event.raw_evidence_id for event in raw_events}) == 8
    assert all(event.event_at.utcoffset() is not None for event in raw_events)

    repeated = backfill_registered_file_source(repository, history, "file-history")
    assert repeated.event_count == first.event_count
    assert repeated.recovered_segment_count == 2
    assert history.append_count == 2
    assert [segment.batch_id for segment in repeated.segments] == [
        segment.batch_id for segment in first.segments
    ]


def test_file_backfill_rejects_missing_or_naive_absolute_time(tmp_path: Path) -> None:
    no_time = tmp_path / "no-time.csv"
    no_time.write_text("vibration_x\n1.0\n2.0\n", encoding="utf-8")
    repository = InMemorySourceRepository()
    repository.register(
        RegisteredSource(
            source_id="no-time",
            name="No absolute time",
            config=FileSourceConfig(
                source_path=str(no_time),
                asset_id="pump-01",
                channel_columns=("vibration_x",),
                sampling_rate_hz=1.0,
            ),
            registered_at=BASE,
        )
    )

    with pytest.raises(ValueError, match="explicit timestamp_column"):
        backfill_registered_file_source(repository, _History(), "no-time")

    naive = tmp_path / "naive.csv"
    naive.write_text(
        "timestamp,vibration_x\n"
        "2026-09-28T08:00:01,1.0\n"
        "2026-09-28T08:00:02,2.0\n",
        encoding="utf-8",
    )
    repository = InMemorySourceRepository()
    repository.register(
        RegisteredSource(
            source_id="naive",
            name="Naive time",
            config=FileSourceConfig(
                source_path=str(naive),
                asset_id="pump-01",
                channel_columns=("vibration_x",),
                timestamp_column="timestamp",
            ),
            registered_at=BASE,
        )
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        backfill_registered_file_source(repository, _History(), "naive")
