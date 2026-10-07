"""Live retention cost versus stored snapshot count N.

Prepares N live commits in one isolated catalog, then measures one retention run:
the dry run, each step's catalog lease hold, snapshots expired, catalog bytes and
catalog-inlined rows, and the same counts after a flush. Every prepared snapshot is
older than the cutoff, so the run is the worst case of an N-snapshot backlog.

State preparation copies one public live batch's raw/history row per commit with
the same commit metadata shape. It is diagnostic state, not an ingestion path. The
answer comes from a few N points in minutes, not from collecting for a week.
"""

from __future__ import annotations

import argparse
import json
import platform
import sqlite3
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from industrial_phm.application import (
    OpcUaEventTimePolicy,
    RegisteredOpcUaDataChangeEvent,
    project_opcua_persistent_data_change_event,
)
from industrial_phm.application.history_retention import RetentionProtection
from industrial_phm.connectors import OpcUaNodeObservation, OpcUaSubscriptionNotification
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.history import ducklake as ducklake_module

CATALOG = ducklake_module._CATALOG_NAME


def _event(index: int, event_at: datetime) -> Any:
    channel_id = f"channel-{index % 35:02d}"
    registered = RegisteredOpcUaDataChangeEvent(
        source_id="profile-source",
        asset_id="profile-asset",
        endpoint_url="opc.tcp://127.0.0.1:4840",
        measurement_point_id=None,
        collection_index=index,
        notification=OpcUaSubscriptionNotification(
            observation=OpcUaNodeObservation(
                channel_id=channel_id,
                node_id=f"ns=2;s={channel_id}",
                value=float(index % 100),
                status_code=0,
                status_good=True,
                status_text="Good",
                variant_type="Double",
                source_timestamp=event_at,
                server_timestamp=None,
                received_at=event_at + timedelta(milliseconds=20),
            ),
            replayed=False,
        ),
    )
    return project_opcua_persistent_data_change_event(
        registered,
        connection_epoch=1,
        event_index=index,
        ingested_at=event_at + timedelta(milliseconds=30),
        event_time_policy=OpcUaEventTimePolicy(allow_server_timestamp_fallback=True),
    )


def _prepare(
    history: DuckLakeAssetHistory,
    commits: int,
    base: datetime,
    rows_per_commit: int,
    old_every: int,
) -> float:
    """One public template batch, then ``rows_per_commit`` copied live rows per commit.

    Every ``old_every``-th commit carries an event time three days before ``base``,
    the rest one day after it, so a run with a cutoff just after preparation deletes
    that fraction of the rows.
    """
    history.append_opcua_batch(
        tuple(_event(index, base + timedelta(days=1)) for index in range(11)),
        batch_id="template",
    )
    started = time.perf_counter()
    connection = history._connect()
    try:
        history._ensure_initialized(connection)
        for commit in range(commits):
            batch_id = f"profile-{commit:07d}"
            index = 1_000 + commit * rows_per_commit
            # One commit per second of event time, close to measured live collection.
            event_at = (
                base
                + (timedelta(days=-3) if commit % old_every == 0 else timedelta(days=1))
                + timedelta(seconds=commit)
            )
            extra = json.dumps(
                {
                    "schema": "industrial-phm-history-batch-v1",
                    "batch_id": batch_id,
                    "ingestion_mode": "live",
                    "event_count": rows_per_commit,
                    "fingerprint": batch_id,
                    "fingerprint_version": "opcua-semantic-v2",
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            connection.execute("BEGIN TRANSACTION")
            connection.execute(
                f"INSERT INTO {CATALOG}.history.ingestion_batch VALUES (?, 'live', ?)",
                [batch_id, rows_per_commit],
            )
            connection.execute(
                f"""
                INSERT INTO {CATALOG}.raw.opcua_data_change
                SELECT o.* REPLACE (
                    'opcua:["profile-source",1,' || (? + r.i) || ']' AS raw_evidence_id,
                    ? AS batch_id, ? + r.i AS event_index,
                    ?::TIMESTAMPTZ + r.i * INTERVAL '1 millisecond' AS event_at,
                    ?::TIMESTAMPTZ + r.i * INTERVAL '1 millisecond' AS ingested_at)
                FROM {CATALOG}.raw.opcua_data_change o, range(?) r(i)
                WHERE o.batch_id = 'template' AND o.event_index = 0
                """,
                [index, batch_id, index, event_at, event_at, rows_per_commit],
            )
            connection.execute(
                f"""
                INSERT INTO {CATALOG}.history.measurement
                SELECT m.* REPLACE (
                    'opcua:["profile-source",1,' || (? + r.i) || ']' AS raw_evidence_id,
                    ? AS batch_id,
                    ?::TIMESTAMPTZ + r.i * INTERVAL '1 millisecond' AS event_at)
                FROM (
                    SELECT * FROM {CATALOG}.history.measurement
                    WHERE batch_id = 'template' AND event_at IS NOT NULL LIMIT 1
                ) m, range(?) r(i)
                """,
                [index, batch_id, event_at, rows_per_commit],
            )
            connection.execute(
                f"CALL {CATALOG}.set_commit_message('industrial-phm', ?, extra_info => ?)",
                [f"retention profile {batch_id}", extra],
            )
            connection.execute("COMMIT")
    finally:
        connection.close()
    return time.perf_counter() - started


def _catalog_state(catalog_path: Path) -> dict[str, int]:
    with sqlite3.connect(catalog_path) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name LIKE 'ducklake_inlined_data_%' AND name != 'ducklake_inlined_data_tables'"
            )
        ]
        inlined = sum(
            connection.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] for table in tables
        )
        snapshots = connection.execute("SELECT count(*) FROM ducklake_snapshot").fetchone()[0]
    return {
        "catalog_bytes": catalog_path.stat().st_size,
        "catalog_inlined_rows": int(inlined),
        "catalog_snapshot_rows": int(snapshots),
    }


def _instrument_holds(history: DuckLakeAssetHistory) -> list[float]:
    holds: list[float] = []

    def connect() -> Any:
        connection = DuckLakeAssetHistory._connect(history)
        acquired = time.perf_counter()
        close = connection.close

        def close_and_record() -> None:
            close()
            holds.append(time.perf_counter() - acquired)

        connection.close = close_and_record
        return connection

    history._connect = connect  # type: ignore[method-assign]
    return holds


def _ms(seconds: float) -> float:
    return round(seconds * 1000, 1)


def run(
    root: Path, *, commits: int, rows_per_commit: int = 1, old_every: int = 2
) -> dict[str, Any]:
    if commits < 1 or rows_per_commit < 1 or old_every < 1:
        raise ValueError("commits, rows_per_commit and old_every must be positive")
    if root.exists() and any(root.iterdir()):
        raise ValueError("profile root must be empty")
    root.mkdir(parents=True, exist_ok=True)
    catalog_path = root / "catalog.sqlite"
    history = DuckLakeAssetHistory(DuckLakeAssetHistoryConfig(catalog_path, root / "data"))
    base = datetime.now(UTC)
    preparation_seconds = _prepare(history, commits, base, rows_per_commit, old_every)
    prepared = _catalog_state(catalog_path)
    probe = tuple(_event(900_000 + index, base + timedelta(days=1)) for index in range(11))
    started = time.perf_counter()
    history.append_opcua_batch(probe, batch_id="probe")
    append_seconds = time.perf_counter() - started
    # Snapshot times are real commit times. A cutoff taken after the last prepared
    # commit, as if the run happened seven days later, puts every snapshot before it.
    cutoff = datetime.now(UTC) + timedelta(milliseconds=1)

    started = time.perf_counter()
    preview = history.apply_live_retention(
        cutoff=cutoff, protection=RetentionProtection(), dry_run=True
    )
    dry_run_seconds = time.perf_counter() - started

    holds = _instrument_holds(history)
    started = time.perf_counter()
    result = history.apply_live_retention(cutoff=cutoff, protection=RetentionProtection())
    retention_seconds = time.perf_counter() - started
    retained = _catalog_state(catalog_path)
    history._connect = DuckLakeAssetHistory._connect.__get__(history)  # type: ignore[method-assign]

    started = time.perf_counter()
    history.flush_inlined_data()
    flush_seconds = time.perf_counter() - started
    flushed = _catalog_state(catalog_path)

    started = time.perf_counter()
    history.append_opcua_batch(
        tuple(_event(950_000 + index, base + timedelta(days=1)) for index in range(11)),
        batch_id="probe-after",
    )
    append_after_seconds = time.perf_counter() - started

    revision = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    import duckdb

    return {
        "schema": "industrial-phm-retention-profile-v1",
        "runtime": {
            "git_revision": revision or "unknown",
            "python": platform.python_version(),
            "duckdb": duckdb.__version__,
            "platform": platform.platform(),
        },
        "commits": commits,
        "rows_per_commit": rows_per_commit,
        "old_every": old_every,
        "preparation_seconds": round(preparation_seconds, 1),
        "prepared": prepared,
        "dry_run_ms": _ms(dry_run_seconds),
        "append_before_ms": _ms(append_seconds),
        "retention_ms": _ms(retention_seconds),
        "retention_lease_holds_ms": [_ms(value) for value in holds],
        "retention_max_lease_hold_ms": _ms(max(holds)),
        "deleted_observations": result.deleted_observation_count,
        "dry_run_deleted_observations": preview.deleted_observation_count,
        "deleted_batches": result.deleted_batch_count,
        "expired_snapshots": result.expired_snapshot_count,
        "removed_files": result.removed_file_count,
        "after_retention": retained,
        "flush_ms": _ms(flush_seconds),
        "after_flush": flushed,
        "append_after_ms": _ms(append_after_seconds),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="empty directory for this run")
    parser.add_argument("--commits", type=int, required=True, help="prepared live commits N")
    parser.add_argument(
        "--rows-per-commit",
        type=int,
        default=1,
        help="live rows per prepared commit; live collection measured about 90",
    )
    parser.add_argument(
        "--old-every",
        type=int,
        default=2,
        help="every k-th prepared commit is older than the cutoff (default: half)",
    )
    args = parser.parse_args()
    report = run(
        args.root,
        commits=args.commits,
        rows_per_commit=args.rows_per_commit,
        old_every=args.old_every,
    )
    (args.root / "retention-profile.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
