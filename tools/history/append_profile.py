"""Profile the live DuckLake OPC UA append path by semantic stage.

This is a #344 diagnostic tool. State preparation reuses one already initialized
connection and is not an operational throughput benchmark. The measured probe uses
the public append_opcua_batch() path, including connect/attach/init and the normal
catalog lease.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from industrial_phm.application import (
    OpcUaEventTimePolicy,
    RegisteredOpcUaDataChangeEvent,
    project_opcua_persistent_data_change_event,
)
from industrial_phm.application.opcua_persistent import OpcUaPersistentDataChangeEvent
from industrial_phm.connectors import OpcUaNodeObservation, OpcUaSubscriptionNotification
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _event(commit_index: int, event_index: int, *, channels: int) -> OpcUaPersistentDataChangeEvent:
    global_index = commit_index * 1_000 + event_index
    event_at = BASE + timedelta(seconds=commit_index, microseconds=event_index)
    received_at = event_at + timedelta(milliseconds=20)
    channel_id = f"channel-{event_index % channels:02d}"
    observation = OpcUaNodeObservation(
        channel_id=channel_id,
        node_id=f"ns=2;s={channel_id}",
        value=float(commit_index) + event_index / 1000,
        status_code=0,
        status_good=True,
        status_text="Good",
        variant_type="Double",
        source_timestamp=event_at,
        server_timestamp=event_at + timedelta(milliseconds=5),
        received_at=received_at,
    )
    registered = RegisteredOpcUaDataChangeEvent(
        source_id="append-profile",
        asset_id="append-profile-asset",
        endpoint_url="opc.tcp://127.0.0.1:4840/profile",
        measurement_point_id="append-profile-point",
        collection_index=global_index,
        notification=OpcUaSubscriptionNotification(observation=observation, replayed=False),
    )
    return project_opcua_persistent_data_change_event(
        registered,
        connection_epoch=1,
        event_index=global_index,
        ingested_at=received_at + timedelta(milliseconds=5),
        event_time_policy=OpcUaEventTimePolicy(allow_server_timestamp_fallback=True),
    )


def _batch(
    commit_index: int, *, events_per_commit: int, channels: int
) -> tuple[OpcUaPersistentDataChangeEvent, ...]:
    return tuple(
        _event(commit_index, index, channels=channels) for index in range(events_per_commit)
    )


def _process_memory() -> dict[str, int | None]:
    status = Path("/proc/self/status")
    if not status.is_file():
        return {"rss_bytes": None, "high_watermark_bytes": None}
    values: dict[str, int] = {}
    for line in status.read_text(encoding="utf-8").splitlines():
        name, separator, raw = line.partition(":")
        if not separator or name not in {"VmRSS", "VmHWM"}:
            continue
        parts = raw.strip().split()
        if len(parts) == 2 and parts[1] == "kB":
            values[name] = int(parts[0]) * 1024
    return {
        "rss_bytes": values.get("VmRSS"),
        "high_watermark_bytes": values.get("VmHWM"),
    }


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except OSError, subprocess.CalledProcessError:
        return "unknown"
    return result.stdout.strip() or "unknown"


def _stage_for_sql(sql: str) -> str:
    normalized = " ".join(sql.lower().split())
    if (
        normalized.startswith("create schema")
        or normalized.startswith("create table")
        or normalized.startswith("alter table")
        or "information_schema.columns" in normalized
    ):
        return "initialize"
    if "history.ingestion_batch" in normalized and "where batch_id = ?" in normalized:
        return "batch_identity_lookup"
    if "raw.opcua_data_change" in normalized and "where raw_evidence_id in" in normalized:
        return "raw_duplicate_lookup"
    if (
        normalized.startswith("begin transaction")
        or normalized.startswith("insert into")
        or normalized.startswith("commit")
        or normalized.startswith("rollback")
        or "set_commit_message" in normalized
    ):
        return "insert_commit"
    if "last_committed_snapshot()" in normalized or (
        ".snapshots()" in normalized and "where snapshot_id = ?" in normalized
    ):
        return "snapshot_provenance"
    if ".snapshots()" in normalized and "commit_extra_info" in normalized:
        return "retry_provenance_scan"
    return "other_sql"


class _ProfileCursor:
    def __init__(self, cursor: Any, stage: str, profile: _SqlProfile) -> None:
        self._cursor = cursor
        self._stage = stage
        self._profile = profile

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)

    def _fetch(self, method: str, *args: object) -> Any:
        started = time.perf_counter()
        try:
            return getattr(self._cursor, method)(*args)
        finally:
            self._profile.add(self._stage, time.perf_counter() - started)

    def fetchone(self) -> Any:
        return self._fetch("fetchone")

    def fetchall(self) -> Any:
        return self._fetch("fetchall")

    def fetchmany(self, size: int = 1) -> Any:
        return self._fetch("fetchmany", size)


class _ProfileConnection:
    def __init__(self, connection: Any, profile: _SqlProfile) -> None:
        self._connection = connection
        self._profile = profile

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def execute(self, sql: str, parameters: object | None = None) -> _ProfileCursor:
        stage = _stage_for_sql(sql)
        started = time.perf_counter()
        try:
            if parameters is None:
                cursor = self._connection.execute(sql)
            else:
                cursor = self._connection.execute(sql, parameters)
        finally:
            self._profile.add(stage, time.perf_counter() - started)
        return _ProfileCursor(cursor, stage, self._profile)

    def close(self) -> None:
        self._connection.close()


class _SqlProfile:
    def __init__(self) -> None:
        self.seconds: dict[str, float] = defaultdict(float)
        self.calls: dict[str, int] = defaultdict(int)

    def add(self, stage: str, seconds: float) -> None:
        self.seconds[stage] += seconds
        self.calls[stage] += 1

    def reset(self) -> None:
        self.seconds.clear()
        self.calls.clear()

    def snapshot(self) -> dict[str, object]:
        return {
            stage: {"seconds": self.seconds[stage], "calls": self.calls[stage]}
            for stage in sorted(self.seconds)
        }


class _ProfilingHistory(DuckLakeAssetHistory):
    def __init__(self, config: DuckLakeAssetHistoryConfig) -> None:
        super().__init__(config)
        self.profile = _SqlProfile()

    def _connect(self) -> Any:
        started = time.perf_counter()
        connection = super()._connect()
        self.profile.add("connect_attach", time.perf_counter() - started)
        return _ProfileConnection(connection, self.profile)


def _measure_append(
    history: _ProfilingHistory,
    events: tuple[OpcUaPersistentDataChangeEvent, ...],
    *,
    batch_id: str,
) -> dict[str, object]:
    history.profile.reset()
    before = _process_memory()
    started = time.perf_counter()
    commit = history.append_opcua_batch(events, batch_id=batch_id)
    total = time.perf_counter() - started
    after = _process_memory()
    stages = history.profile.snapshot()
    measured = sum(
        float(item["seconds"])
        for item in stages.values()
        if isinstance(item, dict) and isinstance(item.get("seconds"), int | float)
    )
    return {
        "total_seconds": total,
        "stage_seconds": stages,
        "unattributed_python_seconds": max(0.0, total - measured),
        "snapshot_id": commit.snapshot_id,
        "memory_before": before,
        "memory_after": after,
    }


def run_profile(
    root: Path,
    *,
    commit_count: int,
    events_per_commit: int,
    channels: int,
) -> dict[str, object]:
    if commit_count < 0:
        raise ValueError("commit_count must not be negative")
    if events_per_commit < 1 or channels < 1:
        raise ValueError("events_per_commit and channels must be positive")
    if root.exists() and any(root.iterdir()):
        raise ValueError(f"profile root must be empty: {root}")
    root.mkdir(parents=True, exist_ok=True)

    config = DuckLakeAssetHistoryConfig(root / "catalog.sqlite", root / "data")
    preload = DuckLakeAssetHistory(config)
    runtime = preload.runtime_fingerprint()

    started = time.perf_counter()
    connection = preload._connect()
    try:
        preload._ensure_initialized(connection)
        for index in range(commit_count):
            preload._append_opcua_batch_with_connection(
                connection,
                _batch(index, events_per_commit=events_per_commit, channels=channels),
                batch_id=f"profile-{index:06d}",
            )
    finally:
        connection.close()
    preload_seconds = time.perf_counter() - started

    before_storage = preload.inspect_storage()
    profiling = _ProfilingHistory(config)

    unique_before_events = _batch(
        commit_count, events_per_commit=events_per_commit, channels=channels
    )
    unique_before = _measure_append(
        profiling,
        unique_before_events,
        batch_id="probe-unique-before",
    )
    retry_before = _measure_append(
        profiling,
        unique_before_events,
        batch_id="probe-unique-before",
    )

    compaction = preload.compact_adjacent_files(
        max_compacted_files=32,
        target_file_size_bytes=1024 * 1024,
        max_file_size_bytes=256 * 1024,
    )

    unique_after_events = _batch(
        commit_count + 1, events_per_commit=events_per_commit, channels=channels
    )
    unique_after = _measure_append(
        profiling,
        unique_after_events,
        batch_id="probe-unique-after",
    )
    retry_after = _measure_append(
        profiling,
        unique_after_events,
        batch_id="probe-unique-after",
    )

    return {
        "schema": "industrial-phm-history-append-profile-v1",
        "environment": {
            "git_sha": _git_sha(),
            "python": platform.python_version(),
            "os": platform.platform(),
            "machine": platform.machine(),
            "duckdb_version": runtime.duckdb_version,
            "ducklake_extension_version": runtime.ducklake_extension_version,
        },
        "workload": {
            "commit_count": commit_count,
            "events_per_commit": events_per_commit,
            "channels": channels,
        },
        "preload_seconds": preload_seconds,
        "storage_before_probe": {
            "active_data_file_count": before_storage.active_data_file_count,
            "snapshot_count": before_storage.snapshot_count,
            "catalog_bytes": before_storage.catalog_bytes,
        },
        "unique_before_compaction": unique_before,
        "retry_before_compaction": retry_before,
        "compaction": {
            "files_processed": compaction.files_processed,
            "files_created": compaction.files_created,
            "active_files_after": compaction.storage_after.active_data_file_count,
        },
        "unique_after_compaction": unique_after,
        "retry_after_compaction": retry_after,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--commits", type=int, required=True)
    parser.add_argument("--events-per-commit", type=int, default=35)
    parser.add_argument("--channels", type=int, default=35)
    args = parser.parse_args()

    try:
        report = run_profile(
            args.root,
            commit_count=args.commits,
            events_per_commit=args.events_per_commit,
            channels=args.channels,
        )
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")
    output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (args.root / "append-profile.json").write_text(output, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
