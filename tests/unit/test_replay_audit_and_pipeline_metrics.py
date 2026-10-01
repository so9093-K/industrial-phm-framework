import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from industrial_phm.runtime.pipeline_metrics import PipelineMetrics
from tools.opcua.replay_audit import audit, load_ledger

T0 = datetime(2026, 10, 1, tzinfo=UTC)


def _ledger(tmp_path: Path, rows) -> Path:
    path = tmp_path / "ledger.jsonl"
    path.write_text(
        "".join(
            json.dumps({"run": run, "at": (T0 + timedelta(seconds=s)).isoformat(), "values": v})
            + "\n"
            for run, s, v in rows
        )
    )
    return path


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
    at = lambda s: T0 + timedelta(seconds=s)  # noqa: E731
    observed = [
        ("a", at(0), 1.0),
        ("b", at(0), 5.0),
        ("b", at(1), 6.0),
        ("b", at(1), 6.0),  # duplicate
        ("a", at(1), 1.0),  # re-delivered current value (subscription start)
        ("a", at(3), 2.0),
        ("b", at(3), 9.9),  # value mismatch
        ("c", at(3), 0.0),  # not in the ledger
    ]
    report = audit(truth, observed)
    assert report["expected_deliveries"] == 6
    assert report["missing"] == 1  # ("a", t=2)
    assert report["gaps"] == [{"start": at(2).isoformat(), "end": at(2).isoformat(), "events": 1}]
    assert report["duplicate_keys"] == 1
    assert report["redelivered_current_values"] == 1
    assert report["value_mismatches"] == 1
    assert report["unknown_events"] == 1


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
