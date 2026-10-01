"""Repeatable accumulated-state benchmark for DuckLake non-destructive compaction.

This tool deliberately never expires snapshots, cleans files, runs CHECKPOINT, or
vacuum. Run separate roots for N=0, N=2000, and N=10000 and compare the emitted
JSON reports.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

from industrial_phm.application import (
    OpcUaEventTimePolicy,
    RegisteredOpcUaDataChangeEvent,
    project_opcua_persistent_data_change_event,
)
from industrial_phm.application.asset_history import HistoricalBatchCommit
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
        source_id="compaction-benchmark",
        asset_id="benchmark-asset",
        endpoint_url="opc.tcp://127.0.0.1:4840/benchmark",
        measurement_point_id="benchmark-point",
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


def _measure[T](operation: Callable[[], T]) -> tuple[T, dict[str, float | int]]:
    tracemalloc.start()
    started = time.perf_counter()
    try:
        value = operation()
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return value, {"seconds": elapsed, "python_peak_bytes": peak}


def _process_memory() -> dict[str, int | None]:
    """Return Linux process RSS/high-watermark without adding a runtime dependency."""
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


def _query_metrics(
    history: DuckLakeAssetHistory,
    *,
    commit_count: int,
) -> dict[str, dict[str, float | int]]:
    if commit_count == 0:
        return {}
    end_at = BASE + timedelta(seconds=commit_count + 3)
    _, latest = _measure(
        lambda: history.query_latest_measurements(
            "benchmark-asset",
            channel_id="channel-00",
        )
    )
    _, page = _measure(
        lambda: history.query_measurement_page(
            "benchmark-asset",
            channel_id="channel-00",
            start_at=BASE,
            end_at=end_at,
            point_budget=2000,
            latest=True,
        )
    )
    _, aggregate = _measure(
        lambda: history.query_measurement_aggregation(
            "benchmark-asset",
            channel_id="channel-00",
            start_at=BASE,
            end_at=end_at,
            bucket_count=200,
        )
    )
    return {"latest": latest, "page": page, "aggregate": aggregate}


def run_benchmark(
    root: Path,
    *,
    commit_count: int,
    events_per_commit: int,
    channels: int,
    max_compacted_files: int,
    max_file_size_bytes: int,
) -> dict[str, object]:
    if commit_count < 0:
        raise ValueError("commit_count must not be negative")
    for value, name in (
        (events_per_commit, "events_per_commit"),
        (channels, "channels"),
        (max_compacted_files, "max_compacted_files"),
        (max_file_size_bytes, "max_file_size_bytes"),
    ):
        if value < 1:
            raise ValueError(f"{name} must be positive")
    if root.exists() and any(root.iterdir()):
        raise ValueError(f"benchmark root must be empty: {root}")
    root.mkdir(parents=True, exist_ok=True)

    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(
            catalog_path=root / "catalog.sqlite",
            data_path=root / "data",
        )
    )
    runtime = history.runtime_fingerprint()
    selected_commits: dict[int, HistoricalBatchCommit] = {}
    first_commit: HistoricalBatchCommit | None = None

    preload_started = time.perf_counter()
    for index in range(commit_count):
        batch = _batch(index, events_per_commit=events_per_commit, channels=channels)
        commit = history.append_opcua_batch(batch, batch_id=f"benchmark-{index:06d}")
        if first_commit is None:
            first_commit = commit
        if index in {0, commit_count // 2, commit_count - 1}:
            selected_commits[index] = commit
    history.flush_inlined_data()
    preload_seconds = time.perf_counter() - preload_started

    storage_at_n = history.inspect_storage()
    memory_at_n = _process_memory()
    fingerprints_before = {
        str(index): history.snapshot_evidence_fingerprint(commit.snapshot_id)
        for index, commit in selected_commits.items()
    }
    query_before = _query_metrics(history, commit_count=commit_count)

    probe_before_batch = _batch(
        commit_count,
        events_per_commit=events_per_commit,
        channels=channels,
    )
    probe_before_commit, append_before = _measure(
        lambda: history.append_opcua_batch(
            probe_before_batch,
            batch_id="probe-before-compaction",
        )
    )

    memory_before_compaction = _process_memory()
    compaction, compaction_measure = _measure(
        lambda: history.compact_adjacent_files(
            max_compacted_files=max_compacted_files,
            max_file_size_bytes=max_file_size_bytes,
        )
    )

    memory_after_compaction = _process_memory()
    fingerprints_after = {
        str(index): history.snapshot_evidence_fingerprint(commit.snapshot_id)
        for index, commit in selected_commits.items()
    }
    if fingerprints_after != fingerprints_before:
        raise RuntimeError("historical snapshot evidence changed after compaction")

    batch_recovery_preserved = True
    if first_commit is not None:
        first_batch = _batch(0, events_per_commit=events_per_commit, channels=channels)
        recovered = history.append_opcua_batch(first_batch, batch_id="benchmark-000000")
        batch_recovery_preserved = recovered == first_commit
        if not batch_recovery_preserved:
            raise RuntimeError("existing batch provenance changed after compaction")

    probe_after_batch = _batch(
        commit_count + 1,
        events_per_commit=events_per_commit,
        channels=channels,
    )
    probe_after_commit, append_after = _measure(
        lambda: history.append_opcua_batch(
            probe_after_batch,
            batch_id="probe-after-compaction",
        )
    )
    query_after = _query_metrics(history, commit_count=commit_count + 2)
    final_storage = history.inspect_storage()
    final_memory = _process_memory()

    report: dict[str, object] = {
        "schema": "industrial-phm-ducklake-compaction-benchmark-v1",
        "environment": {
            "git_sha": _git_sha(),
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "os": platform.platform(),
            "machine": platform.machine(),
            **asdict(runtime),
        },
        "workload": {
            "commit_count": commit_count,
            "events_per_commit": events_per_commit,
            "channels": channels,
            "max_compacted_files": max_compacted_files,
            "max_file_size_bytes": max_file_size_bytes,
        },
        "preload_seconds": preload_seconds,
        "storage_at_n": asdict(storage_at_n),
        "process_memory_at_n": memory_at_n,
        "append_before_compaction": {
            **append_before,
            "snapshot_id": probe_before_commit.snapshot_id,
        },
        "query_before_compaction": query_before,
        "snapshot_fingerprints_before": fingerprints_before,
        "process_memory_before_compaction": memory_before_compaction,
        "compaction": {
            **asdict(compaction),
            "measurement": compaction_measure,
        },
        "process_memory_after_compaction": memory_after_compaction,
        "snapshot_fingerprints_after": fingerprints_after,
        "batch_recovery_preserved": batch_recovery_preserved,
        "append_after_compaction": {
            **append_after,
            "snapshot_id": probe_after_commit.snapshot_id,
        },
        "query_after_compaction": query_after,
        "final_storage": asdict(final_storage),
        "final_process_memory": final_memory,
        "destructive_operations": {
            "expire_snapshots": 0,
            "cleanup_old_files": 0,
            "checkpoint": 0,
            "vacuum": 0,
        },
    }
    (root / "compaction-benchmark.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--commits", type=int, required=True)
    parser.add_argument("--events-per-commit", type=int, default=35)
    parser.add_argument("--channels", type=int, default=35)
    parser.add_argument("--max-compacted-files", type=int, required=True)
    parser.add_argument("--max-file-size-bytes", type=int, required=True)
    args = parser.parse_args()
    try:
        report = run_benchmark(
            args.root,
            commit_count=args.commits,
            events_per_commit=args.events_per_commit,
            channels=args.channels,
            max_compacted_files=args.max_compacted_files,
            max_file_size_bytes=args.max_file_size_bytes,
        )
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
