"""FILE backfill cost versus stored rows N (#316).

Grows one isolated DuckLake catalog and,
at each checkpoint N, measures per-operation cost: batch append, the scoped duplicate
check against the former unscoped lookup, latest/page/aggregate queries for one asset,
the Monitor reads (asset latest, multi-signal chart, asset discovery), catalog lock
hold/wait between a Monitor read and an append, and storage. State preparation uses
SQL bulk inserts by default; timed appends use the public path.
``--prepare-via-append`` also grows small-file/snapshot count. ``--queried-asset-rows``
holds the queried asset fixed so that N grows only in unrelated assets.
The question is whether each cost is constant or proportional to N; the
answer comes from a few N points in minutes, not from ingesting a full archive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from industrial_phm.application.asset_history import HistoryIngestionMode
from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.history import ducklake as ducklake_module

BASE = datetime(2020, 11, 1, tzinfo=UTC)
CHANNELS = 35
# The Monitor compares up to six selected signals over a one-hour default window.
MONITOR_CHANNELS = tuple(f"channel-{index:02d}" for index in range(6))


def _digest(source_index: int) -> str:
    return hashlib.sha256(f"bench-file-{source_index}".encode()).hexdigest()


def _event(source_index: int, sample_index: int, metadata: str) -> FileBackfillEvent:
    source_id = f"device-{source_index:02d}"
    digest = _digest(source_index)
    identity = f"{source_id}|{digest}|{sample_index}"
    return FileBackfillEvent(
        raw_evidence_id="bench:" + hashlib.sha256(identity.encode()).hexdigest(),
        source_id=source_id,
        asset_id=f"asset-{source_index:02d}",
        channel_id=f"channel-{sample_index % CHANNELS:02d}",
        source_file=f"archive.zip!/member-{source_index:02d}.json",
        source_sha256=digest,
        source_size_bytes=1,
        sample_index=sample_index,
        # One record per channel per minute, as in AI-Hub 239 raw members.
        event_at=BASE + timedelta(minutes=sample_index // CHANNELS),
        value=float(sample_index % 1000),
        source_metadata_json=metadata,
    )


def _batch(
    source_index: int, start: int, size: int, metadata: str
) -> tuple[FileBackfillEvent, ...]:
    return tuple(_event(source_index, start + offset, metadata) for offset in range(size))


def _preload(
    history: DuckLakeAssetHistory,
    next_sample: list[int],
    rows: int,
    metadata: str,
    *,
    seed_id: str,
    source_indexes: Sequence[int] | None = None,
) -> None:
    """Prepare row volume directly; seeded batches are not recovery evidence.

    This bypasses append/duplicate/fingerprint work only during state preparation.
    Timed probes always use the public append path. It intentionally creates fewer
    files/snapshots than repeated small commits, so both preparation modes are reported.
    Rows are spread over ``source_indexes`` (default: every source).
    """
    indexes = tuple(range(len(next_sample)) if source_indexes is None else source_indexes)
    sizes = {
        index: rows // len(indexes) + (position < rows % len(indexes))
        for position, index in enumerate(indexes)
    }
    connection = history._connect()
    catalog = ducklake_module._CATALOG_NAME
    try:
        history._ensure_initialized(connection)
        connection.execute("BEGIN TRANSACTION")
        for index, size in sizes.items():
            if not size:
                continue
            event = _event(index, 0, metadata)
            template = ducklake_module._file_raw_event_row(
                event, batch_id=seed_id, ingestion_mode=HistoryIngestionMode.BACKFILL
            )
            columns = ducklake_module._FILE_RAW_COLUMNS
            values = ", ".join(f"?::{sql_type} AS {name}" for name, sql_type in columns)
            connection.execute(
                f"CREATE OR REPLACE TEMP TABLE seed_template AS SELECT {values}", list(template)
            )
            connection.execute(
                f"""INSERT INTO {catalog}.raw.file_measurement
                SELECT 'bench:' || sha256(source_id || '|' || source_sha256 || '|' || r.i),
                    batch_id, ingestion_mode, source_id, asset_id, measurement_point_id,
                    source_file, source_sha256, source_size_bytes, r.i,
                    printf('channel-%02d', r.i % {CHANNELS}),
                    source_timestamp + (r.i // {CHANNELS}) * INTERVAL '1 minute',
                    (r.i % 1000)::DOUBLE, source_metadata_json
                FROM seed_template, range(?, ?) r(i)""",
                [next_sample[index], next_sample[index] + size],
            )
        connection.execute(
            f"""INSERT INTO {catalog}.history.measurement
            SELECT raw_evidence_id, batch_id, source_id, 'file', asset_id,
                measurement_point_id, channel_id, source_timestamp, 'source-timestamp',
                value, value IS NOT NULL, ingestion_mode
            FROM {catalog}.raw.file_measurement WHERE batch_id = ?""",
            [seed_id],
        )
        connection.execute(
            f"INSERT INTO {catalog}.history.ingestion_batch VALUES (?, 'backfill', ?)",
            [seed_id, rows],
        )
        connection.execute("COMMIT")
        for index, size in sizes.items():
            next_sample[index] += size
    finally:
        connection.close()


def _median_ms(operation: Any, repeats: int) -> float:
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        operation()
        samples.append(time.perf_counter() - started)
    return round(statistics.median(samples) * 1000, 2)


def _legacy_lookup(connection: Any, events: tuple[FileBackfillEvent, ...]) -> None:
    with ducklake_module._cache_absent_pandas_import():
        connection.execute(
            f"""
            SELECT raw_evidence_id
            FROM {ducklake_module._CATALOG_NAME}.raw.file_measurement
            WHERE raw_evidence_id IN (SELECT unnest(?::VARCHAR[]))
            LIMIT 1
            """,
            [[event.raw_evidence_id for event in events]],
        ).fetchone()


def _connect_and_close(history: DuckLakeAssetHistory) -> None:
    connection = history._connect()
    try:
        history._ensure_initialized(connection)
    finally:
        connection.close()


def _lock_contention(
    history: DuckLakeAssetHistory,
    append: Callable[[DuckLakeAssetHistory], None],
    repeats: int,
) -> dict[str, float]:
    """Catalog lease hold and wait between one Monitor read and one append.

    Every read and write holds the same local catalog lock, so a read's hold time is
    the longest a collector append can wait behind it. Each contended sample starts
    the append only after a Monitor read has acquired the lock in another thread.
    """
    config = history.config

    def instrumented(on_acquired: Callable[[], None] | None = None) -> tuple[Any, list, list]:
        holds: list[float] = []
        connects: list[float] = []
        instance = DuckLakeAssetHistory(config)

        def connect() -> Any:
            started = time.perf_counter()
            connection = DuckLakeAssetHistory._connect(instance)
            acquired = time.perf_counter()
            connects.append(acquired - started)
            if on_acquired is not None:
                on_acquired()
            close = connection.close

            def close_and_record() -> None:
                close()
                holds.append(time.perf_counter() - acquired)

            connection.close = close_and_record
            return connection

        instance._connect = connect  # type: ignore[method-assign]
        return instance, holds, connects

    reader_ready = threading.Event()
    reader, read_holds, _ = instrumented(reader_ready.set)
    writer, append_holds, append_connects = instrumented()
    for _ in range(repeats):
        reader.query_latest_asset_measurements("asset-00")
        append(writer)
    uncontended_connects = list(append_connects)
    contended_connects: list[float] = []
    for _ in range(repeats):
        reader_ready.clear()
        thread = threading.Thread(target=reader.query_latest_asset_measurements, args=("asset-00",))
        thread.start()
        reader_ready.wait()
        append_connects.clear()
        append(writer)
        thread.join()
        # The first connect of an append waits for the lease the reader holds.
        contended_connects.append(append_connects[0])

    def ms(values: list[float]) -> float:
        return round(statistics.median(values) * 1000, 2)

    return {
        "monitor_read_lock_hold_ms": ms(read_holds),
        "append_lock_hold_ms": ms(append_holds),
        "append_connect_uncontended_ms": ms(uncontended_connects),
        "append_connect_behind_monitor_read_ms": ms(contended_connects),
    }


def _storage(history: DuckLakeAssetHistory, root: Path) -> dict[str, int]:
    inspection = history.inspect_storage()
    return {
        "active_parquet_files": inspection.active_data_file_count,
        "active_parquet_bytes": inspection.active_data_file_bytes,
        "physical_parquet_files": inspection.physical_parquet_file_count,
        "physical_parquet_bytes": inspection.physical_parquet_bytes,
        "catalog_and_sidecar_bytes": sum(
            path.stat().st_size for path in root.iterdir() if path.is_file()
        ),
    }


def _measure_state(
    history: DuckLakeAssetHistory,
    root: Path,
    *,
    next_sample: list[int],
    batch_size: int,
    metadata: str,
    repeats: int,
) -> dict[str, Any]:
    probe = _batch(0, next_sample[0], batch_size, metadata)
    connection = history._connect()
    try:
        history._ensure_initialized(connection)
        scoped_ms = _median_ms(
            lambda: history._reject_existing_file_evidence(connection, probe), repeats
        )
        legacy_ms = _median_ms(lambda: _legacy_lookup(connection, probe), repeats)
    finally:
        connection.close()
    end_at = BASE + timedelta(minutes=next_sample[0] // CHANNELS + 1)
    window_start = max(BASE, end_at - timedelta(hours=1))
    return {
        "queried_asset_rows": next_sample[0],
        "connect_ms": _median_ms(lambda: _connect_and_close(history), repeats),
        "asset_discovery_ms": _median_ms(history.list_history_assets, repeats),
        "monitor_latest_asset_ms": _median_ms(
            lambda: history.query_latest_asset_measurements("asset-00"), repeats
        ),
        "monitor_chart_1h_ms": _median_ms(
            lambda: history.query_multi_signal_measurement_aggregation(
                "asset-00",
                channel_ids=MONITOR_CHANNELS,
                start_at=window_start,
                end_at=end_at,
                bucket_count=120,
            ),
            repeats,
        ),
        "duplicate_check_scoped_ms": scoped_ms,
        "duplicate_check_unscoped_ms": legacy_ms,
        "latest_ms": _median_ms(
            lambda: history.query_latest_measurements("asset-00", channel_id="channel-00"),
            repeats,
        ),
        "page_ms": _median_ms(
            lambda: history.query_measurement_page(
                "asset-00", start_at=BASE, end_at=end_at, channel_id="channel-00"
            ),
            repeats,
        ),
        "aggregate_ms": _median_ms(
            lambda: history.query_measurement_aggregation(
                "asset-00", channel_id="channel-00", start_at=BASE, end_at=end_at
            ),
            repeats,
        ),
        "fixed_window_aggregate_ms": _median_ms(
            lambda: history.query_measurement_aggregation(
                "asset-00", channel_id="channel-00", start_at=window_start, end_at=end_at
            ),
            repeats,
        ),
        **_storage(history, root),
    }


def _runtime() -> dict[str, str]:
    import duckdb

    revision = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    return {
        "git_revision": revision or "unknown",
        "python": platform.python_version(),
        "duckdb": duckdb.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
    }


def run(
    root: Path,
    *,
    checkpoints: list[int],
    sources: int,
    batch_size: int,
    metadata_bytes: int,
    repeats: int,
    compact_at_end: bool = False,
    prepare_via_append: bool = False,
    queried_asset_rows: int | None = None,
) -> dict[str, Any]:
    if not checkpoints or any(value < 0 for value in checkpoints):
        raise ValueError("checkpoints must be nonempty and nonnegative")
    for name, value in (("sources", sources), ("batch_size", batch_size), ("repeats", repeats)):
        if value < 1:
            raise ValueError(f"{name} must be positive")
    if metadata_bytes < 0:
        raise ValueError("metadata_bytes must be nonnegative")
    if queried_asset_rows is not None:
        if queried_asset_rows < 1 or sources < 2:
            raise ValueError("a fixed queried asset needs positive rows and other sources")
        if prepare_via_append:
            raise ValueError("a fixed queried asset is prepared with SQL")
    if root.exists() and any(root.iterdir()):
        raise ValueError("benchmark root must be empty")
    root.mkdir(parents=True, exist_ok=True)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(root / "catalog.sqlite", root / "data")
    )
    metadata = json.dumps({"padding": "x" * max(0, metadata_bytes - 16)})
    next_sample = [0] * sources
    # With a fixed queried asset, checkpoint rows and probes grow only unrelated assets.
    growing = tuple(range(0 if queried_asset_rows is None else 1, sources))
    if queried_asset_rows is not None:
        _preload(
            history,
            next_sample,
            queried_asset_rows,
            metadata,
            seed_id="seed-queried-asset",
            source_indexes=(0,),
        )
    stored = next_sample[0]
    batch_number = 0
    append_seconds: list[float] = []
    results = []

    def append_next(size: int = batch_size, target: DuckLakeAssetHistory = history) -> None:
        nonlocal stored, batch_number
        source_index = growing[batch_number % len(growing)]
        batch = _batch(source_index, next_sample[source_index], size, metadata)
        started = time.perf_counter()
        target.append_file_batch(batch, batch_id=f"bench-{batch_number}")
        append_seconds.append(time.perf_counter() - started)
        next_sample[source_index] += size
        stored += size
        batch_number += 1

    compaction_report = None
    phases = [(checkpoint, "accumulated") for checkpoint in sorted(checkpoints)]
    if compact_at_end:
        phases.append((max(checkpoints), "after-merge-only-compaction"))
    for checkpoint, phase in phases:
        if prepare_via_append:
            while stored < checkpoint:
                append_next(min(batch_size, checkpoint - stored))
        elif phase == "accumulated":
            if stored < checkpoint:
                _preload(
                    history,
                    next_sample,
                    checkpoint - stored,
                    metadata,
                    seed_id=f"seed-{checkpoint}",
                    source_indexes=growing,
                )
                stored = checkpoint
            append_seconds.clear()
            # Repeated public appends are measured separately from the prepared row count.
            for _ in range(repeats):
                append_next()
        contention = None
        if phase == "accumulated":
            recent_appends = list(append_seconds)
            # Before the row count is recorded, so compaction compares identical rows.
            contention = _lock_contention(
                history, lambda writer: append_next(target=writer), repeats
            )
            append_seconds[:] = recent_appends
        if phase != "accumulated":
            # #317-A tier-0 profile: merge files below 256 KiB toward 1 MiB, nothing deleted.
            compaction_report = asdict(
                history.compact_adjacent_files(
                    max_compacted_files=32,
                    target_file_size_bytes=1_048_576,
                    max_file_size_bytes=262_144,
                )
            )

        recent = append_seconds[-20:]
        results.append(
            {
                "phase": phase,
                "checkpoint_rows": checkpoint,
                "stored_rows": stored,
                "batches": batch_number,
                "append_recent_ms": (
                    round(statistics.median(recent) * 1000, 2)
                    if recent and phase == "accumulated"
                    else None
                ),
                "lock": contention,
                **_measure_state(
                    history,
                    root,
                    next_sample=next_sample,
                    batch_size=batch_size,
                    metadata=metadata,
                    repeats=repeats,
                ),
            }
        )
        print(json.dumps(results[-1]), flush=True)
    post_compaction_append = None
    if compaction_report is not None:
        before_probe_rows = stored
        append_seconds.clear()
        for _ in range(repeats):
            append_next()
        post_compaction_append = {
            "rows_before": before_probe_rows,
            "rows_after": stored,
            "median_ms": round(statistics.median(append_seconds) * 1000, 2),
            "samples_ms": [round(value * 1000, 2) for value in append_seconds],
        }
    return {
        "schema": "industrial-phm-file-append-scaling-v3",
        "post_compaction_append": post_compaction_append,
        "compaction": compaction_report,
        "runtime": _runtime(),
        "workload": {
            "preparation": "public-append" if prepare_via_append else "sql-preload",
            "queried_asset_rows": queried_asset_rows,
            "sources": sources,
            "batch_size": batch_size,
            "channels": CHANNELS,
            "metadata_bytes": metadata_bytes,
            "repeats": repeats,
        },
        "checkpoints": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="empty directory for this run")
    parser.add_argument(
        "--checkpoints",
        default="250000,500000,1000000,2000000",
        help="comma-separated stored-row counts N to measure at",
    )
    parser.add_argument("--sources", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=2000)
    parser.add_argument("--metadata-bytes", type=int, default=900)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument(
        "--compact-at-end",
        action="store_true",
        help="after the last checkpoint, run merge-only compaction and measure again",
    )
    parser.add_argument(
        "--prepare-via-append",
        action="store_true",
        help="build many small files via public appends; default prepares row volume with SQL",
    )
    parser.add_argument(
        "--queried-asset-rows",
        type=int,
        help="hold the queried asset at this many rows; checkpoints grow only other assets",
    )
    args = parser.parse_args()
    report = run(
        args.root,
        checkpoints=[int(value) for value in args.checkpoints.split(",")],
        sources=args.sources,
        batch_size=args.batch_size,
        metadata_bytes=args.metadata_bytes,
        repeats=args.repeats,
        compact_at_end=args.compact_at_end,
        prepare_via_append=args.prepare_via_append,
        queried_asset_rows=args.queried_asset_rows,
    )
    (args.root / "file-append-scaling.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
