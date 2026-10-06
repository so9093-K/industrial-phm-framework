"""Historical FILE backfill into the common Asset History boundary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isfinite
from pathlib import Path
from typing import Protocol, runtime_checkable

from industrial_phm.adapters import CsvSensorAdapter
from industrial_phm.application.asset_history import (
    HistoricalBatchCommit,
    HistoricalInputReference,
    HistoryIngestionMode,
)
from industrial_phm.application.source_registration import (
    FileSourceConfig,
    FileSourceMode,
    SourceRepository,
)


@dataclass(frozen=True, slots=True)
class FileBackfillEvent:
    """One validated FILE cell with explicit source-time provenance.

    ``raw_evidence_id`` is a deterministic identity of the source cell: two events with
    the same ID must have the same ``source_id``, ``source_sha256`` and
    ``sample_index``. Built-in producers derive it from those values, and Asset History
    relies on it to keep the duplicate check bounded by source and sample range.
    """

    raw_evidence_id: str
    source_id: str
    asset_id: str
    channel_id: str
    source_file: str
    source_sha256: str
    source_size_bytes: int
    sample_index: int
    event_at: datetime
    value: float | None
    measurement_point_id: str | None = None
    source_metadata_json: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "raw_evidence_id",
            "source_id",
            "asset_id",
            "channel_id",
            "source_file",
            "source_sha256",
        ):
            _validate_identifier(getattr(self, field_name), field_name)
        if len(self.source_sha256) != 64:
            raise ValueError("source_sha256 must be a SHA-256 hex digest")
        try:
            int(self.source_sha256, 16)
        except ValueError as error:
            raise ValueError("source_sha256 must be a SHA-256 hex digest") from error
        if self.measurement_point_id is not None:
            _validate_identifier(self.measurement_point_id, "measurement_point_id")
        _validate_non_negative_int(self.source_size_bytes, "source_size_bytes")
        if self.source_size_bytes < 1:
            raise ValueError("source_size_bytes must be at least 1")
        _validate_non_negative_int(self.sample_index, "sample_index")
        _validate_aware_datetime(self.event_at, "event_at")
        if self.value is not None and (
            isinstance(self.value, bool)
            or not isinstance(self.value, (int, float))
            or not isfinite(self.value)
        ):
            raise ValueError("value must be finite numeric or None")
        if self.source_metadata_json is not None:
            if not isinstance(self.source_metadata_json, str):
                raise ValueError("source_metadata_json must be a JSON object string")
            if not isinstance(json.loads(self.source_metadata_json), dict):
                raise ValueError("source_metadata_json must contain a JSON object")


@dataclass(frozen=True, slots=True)
class FileBackfillSegmentResult:
    source_file: str
    source_sha256: str
    batch_id: str
    event_count: int
    observed_start_at: datetime
    observed_end_at: datetime
    commit: HistoricalBatchCommit
    recovered_existing_commit: bool

    def __post_init__(self) -> None:
        for field_name in ("source_file", "source_sha256", "batch_id"):
            _validate_identifier(getattr(self, field_name), field_name)
        _validate_positive_int(self.event_count, "event_count")
        _validate_aware_datetime(self.observed_start_at, "observed_start_at")
        _validate_aware_datetime(self.observed_end_at, "observed_end_at")
        if self.observed_end_at < self.observed_start_at:
            raise ValueError("observed_end_at must not be before observed_start_at")
        if not isinstance(self.commit, HistoricalBatchCommit):
            raise ValueError("commit must be HistoricalBatchCommit")
        if self.commit.batch_id != self.batch_id:
            raise ValueError("commit batch_id must match batch_id")
        if self.commit.event_count != self.event_count:
            raise ValueError("commit event_count must match event_count")
        if not isinstance(self.recovered_existing_commit, bool):
            raise ValueError("recovered_existing_commit must be boolean")


@dataclass(frozen=True, slots=True)
class FileBackfillResult:
    source_id: str
    asset_id: str
    segments: Sequence[FileBackfillSegmentResult]
    history_snapshot_id: int
    input_reference: HistoricalInputReference

    def __post_init__(self) -> None:
        segments = tuple(self.segments)
        _validate_identifier(self.source_id, "source_id")
        _validate_identifier(self.asset_id, "asset_id")
        if not segments:
            raise ValueError("segments must not be empty")
        if any(not isinstance(item, FileBackfillSegmentResult) for item in segments):
            raise ValueError("segments must contain FileBackfillSegmentResult values")
        _validate_non_negative_int(self.history_snapshot_id, "history_snapshot_id")
        if not isinstance(self.input_reference, HistoricalInputReference):
            raise ValueError("input_reference must be HistoricalInputReference")
        if self.input_reference.snapshot_id != self.history_snapshot_id:
            raise ValueError("input_reference snapshot_id must match history_snapshot_id")
        if self.input_reference.asset_id != self.asset_id:
            raise ValueError("input_reference asset_id must match asset_id")
        object.__setattr__(self, "segments", segments)

    @property
    def event_count(self) -> int:
        return sum(segment.event_count for segment in self.segments)

    @property
    def recovered_segment_count(self) -> int:
        return sum(segment.recovered_existing_commit for segment in self.segments)


@runtime_checkable
class FileHistoricalBatchStore(Protocol):
    def get_file_batch_commit(
        self,
        events: Sequence[FileBackfillEvent],
        *,
        batch_id: str,
        ingestion_mode: HistoryIngestionMode = HistoryIngestionMode.BACKFILL,
    ) -> HistoricalBatchCommit | None: ...

    def append_file_batch(
        self,
        events: Sequence[FileBackfillEvent],
        *,
        batch_id: str,
        ingestion_mode: HistoryIngestionMode = HistoryIngestionMode.BACKFILL,
    ) -> HistoricalBatchCommit: ...

    def current_snapshot_id(self) -> int: ...


def backfill_registered_file_source(
    source_repository: SourceRepository,
    history: FileHistoricalBatchStore,
    source_id: str,
) -> FileBackfillResult:
    """Backfill one registered FILE source using stable per-file DuckLake checkpoints."""
    source = source_repository.get(source_id)
    config = source.config
    if not isinstance(config, FileSourceConfig):
        raise ValueError("historical backfill currently supports registered FILE sources only")
    if config.timestamp_column is None:
        raise ValueError("historical backfill requires an explicit timestamp_column")

    paths = _source_paths(config)
    adapter = CsvSensorAdapter(config.to_csv_sensor_layout())
    segment_results: list[FileBackfillSegmentResult] = []

    all_start: datetime | None = None
    all_end: datetime | None = None
    for path in paths:
        series_items = tuple(adapter.iter_series(path))
        if len(series_items) != 1:
            raise RuntimeError("CSV sensor adapter must yield exactly one series per file")
        series = series_items[0]
        timestamps = series.timestamps
        if timestamps is None:
            raise ValueError("historical backfill requires explicit source timestamps")
        if not timestamps:
            raise ValueError("historical backfill source must contain at least one sample")
        if any(timestamp.utcoffset() is None for timestamp in timestamps):
            raise ValueError("historical backfill timestamps must be timezone-aware")

        source_file = _require_metadata_str(series.metadata.get("source_file"), "source_file")
        source_sha256 = _require_metadata_str(
            series.metadata.get("source_sha256"),
            "source_sha256",
        )
        source_size_bytes = _require_metadata_int(
            series.metadata.get("source_size_bytes"),
            "source_size_bytes",
        )
        events = tuple(
            FileBackfillEvent(
                raw_evidence_id=_file_raw_evidence_id(
                    source_id=source.source_id,
                    source_file=source_file,
                    source_sha256=source_sha256,
                    sample_index=sample_index,
                    channel_id=channel_id,
                ),
                source_id=source.source_id,
                asset_id=source.asset_id,
                measurement_point_id=source.measurement_point_id,
                channel_id=channel_id,
                source_file=source_file,
                source_sha256=source_sha256,
                source_size_bytes=source_size_bytes,
                sample_index=sample_index,
                event_at=timestamp,
                value=float(series.values[sample_index][channel_index]),
            )
            for sample_index, timestamp in enumerate(timestamps)
            for channel_index, channel_id in enumerate(series.channels)
        )
        batch_id = _file_backfill_batch_id(
            source_id=source.source_id,
            source_file=source_file,
            source_sha256=source_sha256,
            asset_id=source.asset_id,
            measurement_point_id=source.measurement_point_id,
            channels=tuple(series.channels),
        )
        existing = history.get_file_batch_commit(
            events,
            batch_id=batch_id,
            ingestion_mode=HistoryIngestionMode.BACKFILL,
        )
        commit = (
            existing
            if existing is not None
            else history.append_file_batch(
                events,
                batch_id=batch_id,
                ingestion_mode=HistoryIngestionMode.BACKFILL,
            )
        )
        start_at = timestamps[0]
        end_at = timestamps[-1]
        segment_results.append(
            FileBackfillSegmentResult(
                source_file=source_file,
                source_sha256=source_sha256,
                batch_id=batch_id,
                event_count=len(events),
                observed_start_at=start_at,
                observed_end_at=end_at,
                commit=commit,
                recovered_existing_commit=existing is not None,
            )
        )
        all_start = start_at if all_start is None else min(all_start, start_at)
        all_end = end_at if all_end is None else max(all_end, end_at)

    if all_start is None or all_end is None:
        raise AssertionError("historical backfill unexpectedly produced no timestamp range")
    history_snapshot_id = history.current_snapshot_id()
    input_reference = HistoricalInputReference(
        snapshot_id=history_snapshot_id,
        asset_id=source.asset_id,
        start_at=all_start,
        end_at=all_end + timedelta(microseconds=1),
        measurement_point_id=source.measurement_point_id,
        channel_ids=tuple(config.channel_columns),
    )
    return FileBackfillResult(
        source_id=source.source_id,
        asset_id=source.asset_id,
        segments=tuple(segment_results),
        history_snapshot_id=history_snapshot_id,
        input_reference=input_reference,
    )


def _source_paths(config: FileSourceConfig) -> tuple[Path, ...]:
    path = Path(config.source_path)
    if config.mode == FileSourceMode.SNAPSHOT:
        if not path.is_file():
            raise ValueError(f"registered FILE source does not exist: {path}")
        return (path,)
    if not path.is_dir():
        raise ValueError(f"registered history-directory source does not exist: {path}")
    paths = tuple(
        sorted(
            (
                candidate
                for candidate in path.iterdir()
                if candidate.is_file() and candidate.suffix.lower() == ".csv"
            ),
            key=lambda candidate: candidate.name,
        )
    )
    if not paths:
        raise ValueError(f"registered history-directory contains no CSV files: {path}")
    return paths


def _file_raw_evidence_id(
    *,
    source_id: str,
    source_file: str,
    source_sha256: str,
    sample_index: int,
    channel_id: str,
) -> str:
    payload = json.dumps(
        [source_id, source_file, source_sha256, sample_index, channel_id],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "file:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_backfill_batch_id(
    *,
    source_id: str,
    source_file: str,
    source_sha256: str,
    asset_id: str,
    measurement_point_id: str | None,
    channels: tuple[str, ...],
) -> str:
    payload = json.dumps(
        [
            source_id,
            source_file,
            source_sha256,
            asset_id,
            measurement_point_id,
            list(channels),
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "file-backfill:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _require_metadata_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"CSV adapter metadata {field_name} must be a string")
    return value


def _require_metadata_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"CSV adapter metadata {field_name} must be an integer")
    return value


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")


def _validate_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")


def _validate_positive_int(value: int, field_name: str) -> None:
    _validate_non_negative_int(value, field_name)
    if value < 1:
        raise ValueError(f"{field_name} must be at least 1")
