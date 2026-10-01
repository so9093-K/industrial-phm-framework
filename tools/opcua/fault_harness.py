"""Repeatable Phase 10 fault gate (#321): inject faults N times and judge by machine.

Runs the AI-Hub replay OPC UA server, the collection service and the analysis runner
as separate processes, injects each fault scenario ``--repeat`` times, then checks:

- publish-ledger audit: duplicate, value (null included), quality and unknown = 0
- every missing delivery lies inside an injected fault's documented loss boundary
  (fault start - margin .. recovery + margin, ADR-0010)
- already-dequeued loss = 0: per gracefully stopped collector process, notifications
  handed to the worker == notifications accepted into the spool
- finalized windows do not overlap or repeat (no coordinator cursor rollback)
- one analysis outcome per window/capability/algorithm/policy, none missing
- every fault recovered within the timeout (no permanent wedge)
- pipeline metrics existed around every fault
- Operations Monitor shows source stale, source unreachable, collector down and
  analysis stale as four different states

Wall-clock duration is not a pass criterion. Exit code 0 only when every check passes;
the full verdict is written as JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLI = [sys.executable, "-c", "from industrial_phm.cli import main; raise SystemExit(main())"]
SOURCE_ID = "aihub239-replay-boiler-2297"
OMITTED_CHANNEL = "T상전류"
SCENARIOS = (
    "collector_stall",
    "source_stall",
    "collector_kill",
    "runner_kill",
    "forced_overflow",
    "spool_backlog",
)

# --------------------------------------------------------------------------- checks


@dataclass(slots=True)
class Fault:
    label: str
    scenario: str
    started: datetime
    ended: datetime | None = None
    recovered_at: datetime | None = None
    loss_allowed: bool = True
    detail: dict[str, object] = field(default_factory=dict)


def _check(passed: bool, **detail: object) -> dict[str, object]:
    return {"passed": passed, **detail}


def check_missing_within_boundary(
    missing: Iterable[tuple[str, datetime]],
    faults: Sequence[Fault],
    *,
    pre_margin: timedelta,
    post_margin: timedelta,
) -> dict[str, object]:
    """Every missing delivery must fall inside a loss-allowed fault's boundary."""
    windows = [
        (
            fault.started - pre_margin,
            (fault.recovered_at or fault.ended or fault.started) + post_margin,
        )
        for fault in faults
        if fault.loss_allowed
    ]
    outside = [
        (channel, at.isoformat())
        for channel, at in missing
        if not any(start <= at <= end for start, end in windows)
    ]
    return _check(not outside, outside_count=len(outside), outside_examples=outside[:10])


def check_dequeued_loss(metric_records: Iterable[dict[str, object]]) -> dict[str, object]:
    """Per gracefully stopped process: handed-to-worker == accepted into the spool."""
    totals: dict[int, Counter[str]] = defaultdict(Counter)
    finished: set[int] = set()
    for record in metric_records:
        pid = int(record["pid"])  # type: ignore[call-overload]
        counts = record.get("counts", {})
        assert isinstance(counts, dict)
        totals[pid].update({k: int(v) for k, v in counts.items()})
        if record.get("final"):
            finished.add(pid)
    per_process = {
        str(pid): {
            "dequeued_data_change": totals[pid]["dequeued_data_change"],
            "spool_accepted": totals[pid]["spool_accepted"],
            "graceful": pid in finished,
        }
        for pid in sorted(totals)
    }
    mismatched = [
        pid
        for pid, item in per_process.items()
        if item["graceful"] and item["dequeued_data_change"] != item["spool_accepted"]
    ]
    graceful = [pid for pid, item in per_process.items() if item["graceful"]]
    return _check(
        bool(graceful) and not mismatched,
        graceful_processes=len(graceful),
        crashed_processes_excluded=len(per_process) - len(graceful),
        mismatched=mismatched,
        per_process=per_process,
    )


def check_windows(rows: Sequence[tuple[str, str, datetime, datetime]]) -> dict[str, object]:
    """Finalized windows are unique and non-overlapping per source."""
    ids = Counter(row[0] for row in rows)
    repeated = [window_id for window_id, count in ids.items() if count > 1]
    overlaps = []
    by_source: dict[str, list[tuple[datetime, datetime, str]]] = defaultdict(list)
    for window_id, source_id, start, end in rows:
        by_source[source_id].append((start, end, window_id))
    for items in by_source.values():
        items.sort()
        for (_, prev_end, prev_id), (start, _, window_id) in pairwise(items):
            if start < prev_end:
                overlaps.append((prev_id, window_id))
    return _check(
        bool(rows) and not repeated and not overlaps,
        windows=len(rows),
        repeated=repeated[:10],
        overlaps=overlaps[:10],
    )


def check_analysis_outcomes(
    windows: Sequence[tuple[str, datetime]],
    analyzed_keys: Sequence[tuple[str, str, str, str]],
    skipped_keys: Sequence[tuple[str, str, str, str]],
    *,
    covered_before: datetime,
) -> dict[str, object]:
    """One outcome per window and policy; no finalized window left behind."""
    analyzed = Counter(analyzed_keys)
    skipped = Counter(skipped_keys)
    duplicated = [key for key, count in (analyzed + skipped).items() if count > 1]
    both = sorted(set(analyzed) & set(skipped))
    policies = {key[1:] for key in (*analyzed, *skipped)}
    outcome_windows = {key[0] for key in (*analyzed, *skipped)}
    uncovered = [
        window_id
        for window_id, window_end in windows
        if window_end < covered_before and window_id not in outcome_windows
    ]
    return _check(
        len(policies) == 1 and not duplicated and not both and not uncovered,
        policies=len(policies),
        analyzed=len(analyzed),
        skipped=len(skipped),
        duplicated=duplicated[:10],
        analyzed_and_skipped=both[:10],
        uncovered_windows=uncovered[:10],
    )


def check_recovered(faults: Sequence[Fault]) -> dict[str, object]:
    wedged = [fault.label for fault in faults if fault.recovered_at is None]
    return _check(not wedged, faults=len(faults), wedged=wedged)


def check_metrics_present(
    faults: Sequence[Fault], metric_times: Sequence[datetime], *, margin: timedelta
) -> dict[str, object]:
    blind = [
        fault.label
        for fault in faults
        if not any(
            fault.started - margin <= at <= (fault.recovered_at or fault.started) + margin
            for at in metric_times
        )
    ]
    return _check(bool(metric_times) and not blind, records=len(metric_times), blind=blind)


UI_EXPECTED: dict[str, Callable[[dict[str, object]], bool]] = {
    "source_stale": lambda s: (
        s["sources"] == "delayed" and s["collect"] == "running" and "No new data" in s["attention"]
    ),  # type: ignore[operator]
    "source_unreachable": lambda s: (
        s["collect"] in ("error", "delayed")
        and "heartbeat" not in str(s["collect_summary"])
        and bool(
            {"Collection needs attention", "Source connection lost"} & set(s["attention"])  # type: ignore[arg-type]
        )
    ),
    "collector_down": lambda s: (
        s["collect"] == "error"
        and "heartbeat" in str(s["collect_summary"])
        and "Collection service is not running" in s["attention"]
    ),  # type: ignore[operator]
    "analysis_stale": lambda s: (
        s["analyze"] == "delayed"
        and s["collect"] == "running"
        and "Analysis service is not updating" in s["attention"]
    ),  # type: ignore[operator]
}


def check_ui_states(snapshots: dict[str, dict[str, object]]) -> dict[str, object]:
    results = {
        name: bool(name in snapshots and expected(snapshots[name]))
        for name, expected in UI_EXPECTED.items()
    }
    signatures = {
        name: (snap["sources"], snap["collect"], snap["analyze"], tuple(snap["attention"]))  # type: ignore[arg-type]
        for name, snap in snapshots.items()
    }
    distinct = len(set(signatures.values())) == len(signatures) == len(UI_EXPECTED)
    return _check(
        all(results.values()) and distinct, expected=results, distinct=distinct, snapshots=snapshots
    )


# ---------------------------------------------------------------------- the stack


def _utc() -> datetime:
    return datetime.now(UTC)


class Stack:
    """Owns the replay, collector and runner processes for one harness root."""

    def __init__(self, root: Path, endpoint: str, *, speed: float) -> None:
        self.root = root
        self.endpoint = endpoint
        self.speed = speed
        self.replay: subprocess.Popen[bytes] | None = None
        self.collector: subprocess.Popen[bytes] | None = None
        self.runner: subprocess.Popen[bytes] | None = None
        self.env = {k: v for k, v in os.environ.items() if k != "AIHUB_APIKEY"}

    def _spawn(self, name: str, command: list[str]) -> subprocess.Popen[bytes]:
        log = (self.root / f"harness-{name}.log").open("ab")
        return subprocess.Popen(command, cwd=REPO, env=self.env, stdout=log, stderr=log)

    def start_replay(self, *extra: str) -> None:
        self.replay = self._spawn(
            "replay",
            [
                sys.executable,
                "-m",
                "tools.opcua.aihub_replay",
                "server",
                "--root",
                str(self.root),
                "--speed",
                str(self.speed),
                "--loop",
                "--publish-ledger",
                str(self.root / "publish-ledger.jsonl"),
                *extra,
            ],
        )

    def start_collector(self, *, queue_maxsize: int | None = None) -> None:
        r = self.root
        command = [
            *CLI,
            "operations",
            "run-collection-service",
            "--registry",
            str(r / "sources.json"),
            "--control-state",
            str(r / "control.sqlite"),
            "--spool-state",
            str(r / "spool.sqlite"),
            "--telemetry-state",
            str(r / "telemetry.sqlite"),
            "--window-state",
            str(r / "windows.sqlite"),
            "--ducklake-catalog",
            str(r / "catalog.sqlite"),
            "--ducklake-data",
            str(r / "data"),
            "--window-duration-seconds",
            "30",
            "--allowed-lateness-seconds",
            "2",
            "--pipeline-metrics",
            str(r / "pipeline-metrics.jsonl"),
        ]
        if queue_maxsize is not None:
            command += ["--subscription-queue-maxsize", str(queue_maxsize)]
        self.collector = self._spawn("collector", command)

    def start_runner(self) -> None:
        r = self.root
        self.runner = self._spawn(
            "runner",
            [
                *CLI,
                "operations",
                "run-window-analysis",
                "--window-state",
                str(r / "windows.sqlite"),
                "--analysis-state",
                str(r / "phase-unbalance.json"),
                "--ledger-state",
                str(r / "window-analysis-ledger.sqlite"),
                "--interval-seconds",
                "2",
                "--alignment",
                "bounded-previous",
                "--max-carry-age-seconds",
                str(5 * 60 / self.speed),
                "--alignment-basis",
                "AI-Hub 239 replay: every channel is written once per recorded minute; "
                "unchanged values raise no DataChange; carry bounded to 5 recorded minutes",
            ],
        )

    @staticmethod
    def stop(process: subprocess.Popen[bytes] | None, *, timeout: float = 30.0) -> None:
        if process is None or process.poll() is not None:
            return
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)

    @staticmethod
    def kill(process: subprocess.Popen[bytes] | None) -> None:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)

    @staticmethod
    def pause(process: subprocess.Popen[bytes] | None, seconds: float) -> None:
        assert process is not None and process.poll() is None
        os.kill(process.pid, signal.SIGSTOP)
        try:
            time.sleep(seconds)
        finally:
            os.kill(process.pid, signal.SIGCONT)

    def stop_all(self) -> None:
        self.stop(self.collector)
        self.stop(self.runner)
        self.stop(self.replay)

    # ------------------------------------------------------------- observations

    def last_received_at(self) -> datetime | None:
        from industrial_phm.runtime.acquisition_telemetry import (
            SqliteAcquisitionTelemetryRepository,
        )

        path = self.root / "telemetry.sqlite"
        if not path.exists():
            return None
        try:
            return SqliteAcquisitionTelemetryRepository(path).get(SOURCE_ID).last_received_at
        except LookupError, sqlite3.Error, ValueError:
            return None

    def runner_heartbeat(self) -> datetime | None:
        from industrial_phm.application.window_analysis_runtime import (
            JsonWindowAnalysisRuntimeRepository,
        )

        path = self.root / "phase-unbalance-runtime.json"
        if not path.exists():
            return None
        runtime = JsonWindowAnalysisRuntimeRepository(path).load()
        return None if runtime is None else runtime.heartbeat_at

    def spool_pending(self) -> int:
        from industrial_phm.runtime.acquisition_spool import (
            SqliteAcquisitionSpool,
            SqliteAcquisitionSpoolConfig,
        )

        return SqliteAcquisitionSpool(
            SqliteAcquisitionSpoolConfig(self.root / "spool.sqlite")
        ).pending_event_count()

    def wait_until(
        self, probe: Callable[[], datetime | None], after: datetime, timeout: float
    ) -> datetime | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = probe()
            if value is not None and value > after:
                return value
            time.sleep(1.0)
        return None

    def ui_snapshot(self) -> dict[str, object]:
        """Evaluate the Operations V2 Monitor read model exactly as the app builds it."""
        script = (
            "import json, runpy\n"
            "app = runpy.run_path('apps/operations_v2.py')['app']\n"
            "_, defs = app.run()\n"
            "m = defs['monitor']\n"
            "stage = {s.kind.value: s for s in m.stages}\n"
            "print('UI-SNAPSHOT ' + json.dumps({\n"
            "  'sources': stage['source'].status.value,\n"
            "  'collect': stage['collection'].status.value,\n"
            "  'collect_summary': stage['collection'].summary,\n"
            "  'analyze': stage['analysis'].status.value,\n"
            "  'attention': sorted({a.title for a in m.attention}),\n"
            "}))\n"
        )
        r = self.root
        env = dict(self.env)
        env.update(
            {
                "INDUSTRIAL_PHM_OPERATIONS_SOURCE_REGISTRY": str(r / "sources.json"),
                "INDUSTRIAL_PHM_OPERATIONS_SOURCE_RUNTIME": str(r / "source-runtime.json"),
                "INDUSTRIAL_PHM_OPERATIONS_COLLECTION_CONTROL": str(r / "control.sqlite"),
                "INDUSTRIAL_PHM_OPERATIONS_ACQUISITION_SPOOL": str(r / "spool.sqlite"),
                "INDUSTRIAL_PHM_OPERATIONS_ACQUISITION_TELEMETRY": str(r / "telemetry.sqlite"),
                "INDUSTRIAL_PHM_OPERATIONS_WINDOW_STATE": str(r / "windows.sqlite"),
                "INDUSTRIAL_PHM_OPERATIONS_ANALYSIS_LEDGER": str(
                    r / "window-analysis-ledger.sqlite"
                ),
                "INDUSTRIAL_PHM_OPERATIONS_ANALYSIS_STATE": str(r / "field-analysis.json"),
                "INDUSTRIAL_PHM_OPERATIONS_PHASE_UNBALANCE_STATE": str(r / "phase-unbalance.json"),
                "INDUSTRIAL_PHM_OPERATIONS_FINDING_STATE": str(r / "findings.json"),
                "INDUSTRIAL_PHM_OPERATIONS_MAINTENANCE_REVIEW_STATE": str(
                    r / "finding-review.json"
                ),
                "INDUSTRIAL_PHM_HISTORY_CATALOG": str(r / "catalog.sqlite"),
                "INDUSTRIAL_PHM_HISTORY_DATA": str(r / "data"),
            }
        )
        output = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        for line in output.stdout.splitlines():
            if line.startswith("UI-SNAPSHOT "):
                return dict(json.loads(line.removeprefix("UI-SNAPSHOT ")))
        raise RuntimeError(f"Operations Monitor could not be evaluated: {output.stderr[-2000:]}")


# ---------------------------------------------------------------------- scenarios


class Harness:
    def __init__(self, stack: Stack, *, stall_seconds: float, recovery_timeout: float) -> None:
        self.stack = stack
        self.stall = stall_seconds
        self.recovery_timeout = recovery_timeout
        self.faults: list[Fault] = []
        self.ui: dict[str, dict[str, object]] = {}
        self.omission: tuple[datetime, datetime] | None = None

    def _recover_data(self, fault: Fault) -> None:
        fault.ended = fault.ended or _utc()
        fault.recovered_at = self.stack.wait_until(
            self.stack.last_received_at, fault.ended, self.recovery_timeout
        )
        self.faults.append(fault)
        print(f"  {fault.label}: recovered_at={fault.recovered_at}", flush=True)

    def collector_stall(self, label: str) -> None:
        fault = Fault(label, "collector_stall", _utc())
        self.stack.pause(self.stack.collector, self.stall)
        self._recover_data(fault)

    def source_stall(self, label: str) -> None:
        fault = Fault(label, "source_stall", _utc())
        self.stack.pause(self.stack.replay, self.stall)
        self._recover_data(fault)

    def collector_kill(self, label: str) -> None:
        fault = Fault(label, "collector_kill", _utc())
        self.stack.kill(self.stack.collector)
        time.sleep(5)
        self.stack.start_collector()
        self._recover_data(fault)

    def runner_kill(self, label: str) -> None:
        fault = Fault(label, "runner_kill", _utc(), loss_allowed=False)
        self.stack.kill(self.stack.runner)
        time.sleep(5)
        self.stack.start_runner()
        fault.ended = _utc()
        fault.recovered_at = self.stack.wait_until(
            self.stack.runner_heartbeat, fault.ended, self.recovery_timeout
        )
        self.faults.append(fault)
        print(f"  {label}: runner heartbeat at {fault.recovered_at}", flush=True)

    def forced_overflow(self, label: str) -> None:
        # A queue smaller than one subscription's initial values (35 channels) overflows
        # deterministically on every session start: the worker must end explicitly and
        # restart with backoff (no wedge), then recover once the queue is restored. The
        # source's own publish batches are coalesced per monitored item (queue size 1),
        # so a source stall alone does not reliably exceed a moderate queue.
        fault = Fault(label, "forced_overflow", _utc())
        before = _overflow_rejections(self.stack.root)
        self.stack.stop(self.stack.collector)
        self.stack.start_collector(queue_maxsize=16)
        time.sleep(20)
        fault.detail["overflow_rejected"] = _overflow_rejections(self.stack.root) - before
        self.stack.stop(self.stack.collector)
        self.stack.start_collector()
        self._recover_data(fault)

    def spool_backlog(self, label: str) -> None:
        # Hold the DuckLake catalog lease: the writer cannot commit, the spool grows.
        from filelock import FileLock

        fault = Fault(label, "spool_backlog", _utc(), loss_allowed=False)
        lock = FileLock(str(self.stack.root / "catalog.sqlite") + ".phm.lock")
        with lock:
            time.sleep(self.stall)
            fault.detail["peak_pending"] = self.stack.spool_pending()
        fault.ended = _utc()
        deadline = time.monotonic() + self.recovery_timeout
        while time.monotonic() < deadline and self.stack.spool_pending() > 200:
            time.sleep(1)
        drained = self.stack.spool_pending() <= 200
        fault.detail["drained"] = drained
        fault.recovered_at = _utc() if drained else None
        self.faults.append(fault)
        print(
            f"  {label}: peak backlog {fault.detail['peak_pending']}, drained={drained}", flush=True
        )

    def missing_phase_and_ui(self) -> None:
        s = self.stack
        # Missing phase: replay omits one current phase for three windows.
        fault = Fault("missing_phase", "missing_phase", _utc())
        s.stop(s.replay)
        s.start_replay("--omit-channel", OMITTED_CHANNEL)
        omitted_from = _utc()
        time.sleep(95)
        self.omission = (omitted_from, _utc())
        s.stop(s.replay)
        s.start_replay()
        self._recover_data(fault)

        # Source stale: connected, values frozen.
        fault = Fault("ui_source_stale", "ui_source_stale", _utc())
        s.stop(s.replay)
        s.start_replay("--freeze-after-records", "3")
        time.sleep(50)
        self.ui["source_stale"] = s.ui_snapshot()
        s.stop(s.replay)
        s.start_replay()
        self._recover_data(fault)

        # Source unreachable.
        fault = Fault("ui_source_unreachable", "ui_source_unreachable", _utc())
        s.stop(s.replay)
        time.sleep(15)
        self.ui["source_unreachable"] = s.ui_snapshot()
        s.start_replay()
        self._recover_data(fault)

        # Collector down.
        fault = Fault("ui_collector_down", "ui_collector_down", _utc())
        s.kill(s.collector)
        time.sleep(25)
        self.ui["collector_down"] = s.ui_snapshot()
        s.start_collector()
        self._recover_data(fault)

        # Analysis stale.
        fault = Fault("ui_analysis_stale", "ui_analysis_stale", _utc(), loss_allowed=False)
        s.kill(s.runner)
        time.sleep(25)
        self.ui["analysis_stale"] = s.ui_snapshot()
        s.start_runner()
        fault.ended = _utc()
        fault.recovered_at = s.wait_until(s.runner_heartbeat, fault.ended, self.recovery_timeout)
        self.faults.append(fault)


def _overflow_rejections(root: Path) -> int:
    path = root / "pipeline-metrics.jsonl"
    if not path.exists():
        return 0
    total = 0
    for line in path.read_text().splitlines():
        total += int(json.loads(line).get("counts", {}).get("overflow_rejected", 0))
    return total


# ------------------------------------------------------------------------ verdict


def judge(harness: Harness, *, audit_since: datetime, audit_until: datetime) -> dict[str, object]:
    from industrial_phm.application.phase_unbalance import ChannelSelection
    from industrial_phm.application.phase_unbalance_state import (
        JsonPhaseUnbalanceRepository,
        window_result_key,
    )
    from industrial_phm.application.window_analysis_ledger_sqlite import (
        SqliteWindowAnalysisLedger,
    )
    from tools.opcua.replay_audit import audit, load_ledger, observed_events

    root = harness.stack.root
    truth = load_ledger(root / "publish-ledger.jsonl")
    observed = observed_events(root, SOURCE_ID)
    report = audit(truth, observed, since=audit_since, until=audit_until)
    stored = {(channel, at) for channel, at, _, _ in observed if at is not None}
    missing = [
        key for key in truth.expected if audit_since <= key[1] < audit_until and key not in stored
    ]
    margin_pre, margin_post = timedelta(seconds=3), timedelta(seconds=2)

    metric_records = [
        json.loads(line) for line in (root / "pipeline-metrics.jsonl").read_text().splitlines()
    ]
    metric_times = [datetime.fromisoformat(record["at"]) for record in metric_records]

    connection = sqlite3.connect(f"file:{root / 'windows.sqlite'}?mode=ro", uri=True)
    window_rows = [
        (window_id, source_id, datetime.fromisoformat(start), datetime.fromisoformat(end))
        for window_id, source_id, start, end in connection.execute(
            "SELECT window_id, source_id, window_start, window_end FROM finalized_window"
        )
    ]
    connection.close()
    results = JsonPhaseUnbalanceRepository(root / "phase-unbalance.json").list_results()
    analyzed_keys = [key for key in (window_result_key(r) for r in results) if key is not None]
    skipped = SqliteWindowAnalysisLedger(root / "window-analysis-ledger.sqlite").list_skipped()
    skipped_keys = [outcome.key for outcome in skipped]

    missing_phase_seen = False
    if harness.omission is not None:
        start, end = harness.omission
        for result in results:
            reference = result.evidence.input_reference
            if start <= reference.end_at <= end + timedelta(seconds=40) and any(
                series.channel_selection == ChannelSelection.UNRESOLVED
                for series in result.evidence.results
            ):
                missing_phase_seen = True
        missing_phase_seen = missing_phase_seen or any(
            start <= outcome.recorded_at <= end + timedelta(seconds=60) for outcome in skipped
        )

    overflow_faults = [f for f in harness.faults if f.scenario == "forced_overflow"]
    checks = {
        "audit_exact": _check(
            report["duplicate_keys"] == 0
            and report["value_mismatches"] == 0
            and report["quality_mismatches"] == 0
            and report["unknown_events"] == 0,
            **{k: v for k, v in report.items() if k != "gaps"},
        ),
        "missing_within_loss_boundary": check_missing_within_boundary(
            missing, harness.faults, pre_margin=margin_pre, post_margin=margin_post
        ),
        "already_dequeued_loss_zero": check_dequeued_loss(metric_records),
        "windows_no_rollback": check_windows(window_rows),
        "analysis_once_and_complete": check_analysis_outcomes(
            [(row[0], row[3]) for row in window_rows],
            analyzed_keys,
            skipped_keys,
            covered_before=audit_until - timedelta(seconds=60),
        ),
        "no_permanent_wedge": check_recovered(harness.faults),
        "metrics_present_around_faults": check_metrics_present(
            harness.faults, metric_times, margin=timedelta(seconds=15)
        ),
        "forced_overflow_happened": _check(
            bool(overflow_faults)
            and all(int(f.detail.get("overflow_rejected", 0)) > 0 for f in overflow_faults),  # type: ignore[call-overload]
            per_fault=[f.detail for f in overflow_faults],
        ),
        "spool_backlog_drained": _check(
            all(f.detail.get("drained") for f in harness.faults if f.scenario == "spool_backlog"),
            per_fault=[f.detail for f in harness.faults if f.scenario == "spool_backlog"],
        ),
        "missing_phase_explained": _check(missing_phase_seen),
        "ui_states_distinct": check_ui_states(harness.ui),
    }
    return {
        "passed": all(bool(check["passed"]) for check in checks.values()),
        "checks": checks,
        "faults": [
            {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in asdict(f).items()}
            for f in harness.faults
        ],
    }


# --------------------------------------------------------------------------- main


def _prepare(root: Path, endpoint: str, args: argparse.Namespace) -> None:
    from industrial_phm.adapters.aihub_power_history import PowerHistoryBinding
    from industrial_phm.application import (
        CollectionDesiredState,
        JsonSourceRepository,
        request_collection_state,
    )
    from industrial_phm.runtime import SqliteCollectionControlRepository
    from tools.opcua import aihub_replay

    selection = aihub_replay.ReplaySelection(
        archive=args.archive,
        member=args.member,
        binding=PowerHistoryBinding(**json.loads(args.binding.read_text())),
        start_local=args.start,
        end_local=args.end,
    )
    aihub_replay.prepare(root, endpoint, selection, name="AI-Hub 239 replay (fault harness)")
    sources = JsonSourceRepository(root / "sources.json")
    request_collection_state(
        sources,
        sources,
        SqliteCollectionControlRepository(root / "control.sqlite"),
        SOURCE_ID,
        CollectionDesiredState.RUNNING,
        requested_at=_utc(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="empty directory for this run")
    parser.add_argument("--repeat", type=int, default=3, help="injections per scenario (N)")
    parser.add_argument("--scenarios", nargs="+", choices=SCENARIOS, default=list(SCENARIOS))
    parser.add_argument("--port", type=int, default=4852)
    parser.add_argument("--speed", type=float, default=60.0)
    parser.add_argument("--stall-seconds", type=float, default=20.0)
    parser.add_argument("--recovery-timeout", type=float, default=120.0)
    parser.add_argument(
        "--archive",
        type=Path,
        default=Path("data/raw/aihub/239/archives/training/raw/5.보일러.zip"),
    )
    parser.add_argument("--member", default="5.보일러/SourceData_211.json")
    parser.add_argument(
        "--binding", type=Path, default=Path("tools/opcua/presets/aihub-boiler-2297-replay.json")
    )
    parser.add_argument("--start", type=datetime.fromisoformat, default=datetime(2020, 11, 14, 6))
    parser.add_argument(
        "--end", type=datetime.fromisoformat, default=datetime(2020, 11, 14, 12, 30)
    )
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    root = args.root.resolve()
    endpoint = f"opc.tcp://127.0.0.1:{args.port}/aihub-replay/"
    _prepare(root, endpoint, args)

    stack = Stack(root, endpoint, speed=args.speed)
    harness = Harness(
        stack, stall_seconds=args.stall_seconds, recovery_timeout=args.recovery_timeout
    )
    started = _utc()
    verdict: dict[str, object]
    try:
        stack.start_replay()
        stack.start_collector()
        stack.start_runner()
        first = stack.wait_until(stack.last_received_at, started, args.recovery_timeout)
        if first is None:
            raise RuntimeError("collector never received data from the replay")
        print(f"first delivery {first}; warming up", flush=True)
        time.sleep(40)
        for index in range(1, args.repeat + 1):
            for scenario in args.scenarios:
                label = f"{scenario}#{index}"
                print(f"[{_utc():%H:%M:%S}] {label}", flush=True)
                getattr(harness, scenario)(label)
                time.sleep(10)
        harness.missing_phase_and_ui()
        time.sleep(40)
        audit_until = _utc() - timedelta(seconds=20)
        stack.stop(stack.collector)
        time.sleep(15)  # let the runner finish windows finalized before the stop
        stack.stop(stack.runner)
        stack.stop(stack.replay)
        verdict = judge(harness, audit_since=first, audit_until=audit_until)
    finally:
        stack.stop_all()
    verdict["config"] = {
        "repeat": args.repeat,
        "scenarios": args.scenarios,
        "stall_seconds": args.stall_seconds,
        "speed": args.speed,
        "started": started.isoformat(),
        "finished": _utc().isoformat(),
    }
    (root / "harness-verdict.json").write_text(json.dumps(verdict, indent=2, default=str) + "\n")
    for name, check in verdict["checks"].items():  # type: ignore[union-attr]
        print(f"{'PASS' if check['passed'] else 'FAIL'}  {name}", flush=True)
    print(f"verdict: {'PASS' if verdict['passed'] else 'FAIL'} -> {root / 'harness-verdict.json'}")
    raise SystemExit(0 if verdict["passed"] else 1)


if __name__ == "__main__":
    main()
