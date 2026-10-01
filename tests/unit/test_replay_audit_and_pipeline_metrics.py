import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from industrial_phm.runtime.pipeline_metrics import PipelineMetrics
from tools.opcua.replay_audit import LedgerKeyCollisionError, audit, load_ledger

T0 = datetime(2026, 10, 1, tzinfo=UTC)


def _ledger(tmp_path: Path, rows) -> Path:
    path = tmp_path / "ledger.jsonl"
    path.write_text(
        "".join(
            json.dumps(
                {
                    "run": run,
                    "at": (T0 + timedelta(seconds=s)).isoformat(),
                    "values": v,
                    "good": {ch: value is not None for ch, value in v.items()},
                }
            )
            + "\n"
            for run, s, v in rows
        )
    )
    return path


def _at(seconds: int) -> datetime:
    return T0 + timedelta(seconds=seconds)


def test_audit_expects_changes_only_and_classifies_stored_events(tmp_path):
    truth = load_ledger(
        _ledger(
            tmp_path,
            [
                ("r1", 0, {"a": 1.0, "b": 5.0}),
                ("r1", 1, {"a": 1.0, "b": 6.0}),  # a unchanged: no notification expected
                ("r1", 2, {"a": 2.0, "b": 6.0}),
                ("r2", 3, {"a": 2.0, "b": 6.0}),  # new server run: first writes are changes
            ],
        )
    )
    observed = [
        ("a", _at(0), 1.0, True),
        ("b", _at(0), 5.0, True),
        ("b", _at(1), 6.0, True),
        ("b", _at(1), 6.0, True),  # duplicate
        ("a", _at(1), 1.0, True),  # re-delivered current value (subscription start)
        ("a", _at(3), 2.0, True),
        ("b", _at(3), 9.9, True),  # value mismatch
        ("c", _at(3), 0.0, True),  # not in the ledger
    ]
    report = audit(truth, observed)
    assert report["expected_deliveries"] == 6
    assert report["missing"] == 1  # ("a", t=2)
    assert report["gaps"] == [{"start": _at(2).isoformat(), "end": _at(2).isoformat(), "events": 1}]
    assert report["duplicate_keys"] == 1
    assert report["redelivered_current_values"] == 1
    assert (report["value_mismatches"], report["quality_mismatches"]) == (1, 0)
    assert report["unknown_events"] == 1


def test_audit_compares_null_and_quality_exactly(tmp_path):
    # A recorded null is published as a Null variant with Bad status; a stored 0.0
    # or a Good status for it is corruption, not a match.
    truth = load_ledger(_ledger(tmp_path, [("r1", 0, {"a": None}), ("r1", 1, {"a": 3.0})]))
    clean = audit(truth, [("a", _at(0), None, False), ("a", _at(1), 3.0, True)])
    assert (clean["value_mismatches"], clean["quality_mismatches"], clean["missing"]) == (0, 0, 0)
    corrupted = audit(truth, [("a", _at(0), 0.0, True), ("a", _at(1), 3.0, False)])
    assert corrupted["value_mismatches"] == 1
    assert corrupted["quality_mismatches"] == 2


def test_audit_refuses_one_key_published_by_two_runs(tmp_path):
    path = _ledger(tmp_path, [("r1", 0, {"a": 1.0}), ("r2", 0, {"a": 1.0})])
    with pytest.raises(LedgerKeyCollisionError, match="runs r1 and r2"):
        load_ledger(path)


def test_pipeline_metrics_report_one_interval_and_reset():
    metrics = PipelineMetrics()
    metrics.count("arrived", 3)
    metrics.queue_depth(7, 4096)
    metrics.queue_depth(2)
    for seconds in (0.001, 0.002, 0.050):
        metrics.observe("arrival_to_dequeue", seconds)
    report = metrics.take()
    assert report["counts"] == {"arrived": 3}
    assert report["queue"] == {"depth": 2, "high_watermark": 7, "maxsize": 4096}
    assert report["latency"]["arrival_to_dequeue"] == {"n": 3, "max_ms": 50.0, "p95_ms": 50.0}
    following = metrics.take()
    assert following["counts"] == {}
    assert following["queue"]["high_watermark"] == 2


def test_reporter_tags_records_with_pid_and_flushes_a_final_interval(tmp_path):
    import asyncio
    import os

    from industrial_phm.runtime.pipeline_metrics import run_pipeline_metrics_reporter

    metrics = PipelineMetrics()
    path = tmp_path / "metrics.jsonl"

    async def _run() -> None:
        stop = asyncio.Event()
        task = asyncio.create_task(
            run_pipeline_metrics_reporter(metrics, path, stop_event=stop, interval_seconds=60)
        )
        metrics.count("spool_accepted", 2)
        await asyncio.sleep(0.05)
        stop.set()
        await task

    asyncio.run(_run())
    (record,) = [json.loads(line) for line in path.read_text().splitlines()]
    assert record["final"] is True and record["pid"] == os.getpid()
    assert record["counts"]["spool_accepted"] == 2
