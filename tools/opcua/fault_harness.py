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
import urllib.request
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
    """A metrics record just before each fault and another just after its recovery."""
    blind_before = [
        fault.label
        for fault in faults
        if not any(fault.started - margin <= at <= fault.started for at in metric_times)
    ]
    blind_after = [
        fault.label
        for fault in faults
        if fault.recovered_at is None
        or not any(fault.recovered_at <= at <= fault.recovered_at + margin for at in metric_times)
    ]
    return _check(
        bool(metric_times) and not blind_before and not blind_after,
        records=len(metric_times),
        no_record_before=blind_before,
        no_record_after_recovery=blind_after,
    )


def check_backlog(details: Sequence[dict[str, object]]) -> dict[str, object]:
    """The held lease built a backlog above the pre-fault baseline and it drained back."""
    failed = [
        item
        for item in details
        if not (
            int(item["peak_pending"]) > int(item["baseline_pending"]) + 100  # type: ignore[call-overload]
            and item["drained"]
        )
    ]
    return _check(bool(details) and not failed, per_fault=list(details), failed=failed)


def check_missing_phase(
    omitted_channel: str,
    windows: Sequence[dict[str, object]],
    skipped_in_omission: int,
) -> dict[str, object]:
    """Each omission window names the missing phase, and only current is unresolved."""
    wrong = [
        item
        for item in windows
        if not (
            omitted_channel in item["missing_channels"]  # type: ignore[operator]
            and item["current_selection"] == "unresolved"
            and str(item["current_note"]).startswith("Not evaluated: no complete R/S/T")
            and item["voltage_selection"] != "unresolved"
            and omitted_channel in str(item["provenance_missing_channels"])
        )
    ]
    return _check(
        bool(windows) and not wrong and skipped_in_omission == 0,
        omission_windows=len(windows),
        skipped_in_omission=skipped_in_omission,
        wrong=wrong[:5],
    )


def check_review_workflow(detail: dict[str, object]) -> dict[str, object]:
    """After the faults one result travels Investigation -> review request -> Maintenance."""
    return _check(
        detail.get("before_state") == "not-requested"
        and detail.get("after_state") == "open"
        and detail.get("maintenance_status") == "open"
        and detail.get("result_after_last_fault") is True,
        **detail,
    )


def check_first_render(renders: dict[str, dict[str, object]]) -> dict[str, object]:
    """In a real browser each state is readable within five seconds of opening."""
    slow = {name: r for name, r in renders.items() if not r.get("within_5s")}
    return _check(len(renders) == 4 and not slow, renders=renders, slow=slow)


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
        self.ui_server: subprocess.Popen[bytes] | None = None
        self.ui_url: str | None = None
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
        self.stop(self.ui_server)
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

    def last_metrics_at(self) -> datetime | None:
        path = self.root / "pipeline-metrics.jsonl"
        if not path.exists():
            return None
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in reversed(lines):
            try:
                return datetime.fromisoformat(json.loads(line)["at"])
            except ValueError, KeyError:
                continue  # a line still being appended
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
        return self.app_probe(
            "m = defs['monitor']\n"
            "stage = {s.kind.value: s for s in m.stages}\n"
            "out = {\n"
            "  'sources': stage['source'].status.value,\n"
            "  'collect': stage['collection'].status.value,\n"
            "  'collect_summary': stage['collection'].summary,\n"
            "  'analyze': stage['analysis'].status.value,\n"
            "  'attention': sorted({a.title for a in m.attention}),\n"
            "}\n"
        )

    def app_env(self) -> dict[str, str]:
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
        return env

    def app_probe(self, body: str) -> dict[str, object]:
        """Run Operations V2 in script mode against this root; ``body`` sets ``out``."""
        script = (
            "import json, runpy\n"
            "app = runpy.run_path('apps/operations_v2.py')['app']\n"
            "_, defs = app.run()\n"
            f"{body}"
            "print('UI-SNAPSHOT ' + json.dumps(out, default=str))\n"
        )
        output = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPO,
            env=self.app_env(),
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        for line in output.stdout.splitlines():
            if line.startswith("UI-SNAPSHOT "):
                return dict(json.loads(line.removeprefix("UI-SNAPSHOT ")))
        raise RuntimeError(f"Operations V2 could not be evaluated: {output.stderr[-2000:]}")

    # ----------------------------------------------------------- real browser

    def start_ui_server(self, port: int) -> None:
        log = (self.root / "harness-ui.log").open("ab")
        self.ui_server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "marimo",
                "run",
                "apps/operations_v2.py",
                "--headless",
                "--no-token",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=REPO,
            env=self.app_env(),
            stdout=log,
            stderr=log,
        )
        self.ui_url = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                urllib.request.urlopen(self.ui_url, timeout=1)
                return
            except OSError:
                time.sleep(0.5)
        raise RuntimeError("marimo UI server did not start")

    def browser_render(self, name: str, expected_attention: str) -> dict[str, object]:
        """Open Monitor in Chromium; time until the data flow and the attention item show."""
        assert self.ui_url is not None, "start_ui_server first"
        output = subprocess.run(
            [
                "uv",
                "run",
                "--no-sync",
                "--with",
                "playwright",
                "python",
                "-c",
                _BROWSER_SCRIPT,
                self.ui_url,
                expected_attention,
                str(self.root / f"ui-{name}.png"),
            ],
            cwd=REPO,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        for line in output.stdout.splitlines():
            if line.startswith("BROWSER "):
                render = dict(json.loads(line.removeprefix("BROWSER ")))
                render["within_5s"] = bool(
                    render["attention_seen"] and float(render["seconds"]) <= 5.0  # type: ignore[arg-type]
                )
                return render
        return {"within_5s": False, "error": output.stderr[-1500:]}


# Opens a fresh page (a fresh marimo session reads current runtime files), waits for
# the Monitor data flow and the expected attention title, and reports the elapsed time.
_BROWSER_SCRIPT = """
import json, sys, time
from playwright.sync_api import sync_playwright
url, attention, shot = sys.argv[1:4]
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1100})
    started = time.monotonic()
    page.goto(url)
    page.get_by_text("Data flow", exact=True).first.wait_for(timeout=30000)
    flow = time.monotonic() - started
    seen = True
    try:
        page.get_by_text(attention).first.wait_for(timeout=30000)
    except Exception:
        seen = False
    seconds = time.monotonic() - started
    cards = page.locator(".phm-flow > *").all_inner_texts()
    page.screenshot(path=shot, full_page=True)
    browser.close()
print("BROWSER " + json.dumps({
    "data_flow_seconds": round(flow, 2), "seconds": round(seconds, 2),
    "attention": attention, "attention_seen": seen,
    "stages": [" | ".join(c.split()) for c in cards],
}))
"""


# ---------------------------------------------------------------------- scenarios


class Harness:
    def __init__(
        self,
        stack: Stack,
        *,
        stall_seconds: float,
        recovery_timeout: float,
        browser: bool = False,
    ) -> None:
        self.stack = stack
        self.stall = stall_seconds
        self.recovery_timeout = recovery_timeout
        self.browser = browser
        self.faults: list[Fault] = []
        self.ui: dict[str, dict[str, object]] = {}
        self.renders: dict[str, dict[str, object]] = {}
        self.omission: tuple[datetime, datetime] | None = None
        self.workflow: dict[str, object] = {}

    def _record(self, fault: Fault) -> None:
        """Keep the fault and do not start the next one before metrics resume after it.

        Faults run back to back; without this, a fault that kills the collector right
        after another one recovers would leave the earlier fault with no metrics record
        after its recovery and the later fault with none before it.
        """
        self.faults.append(fault)
        if fault.recovered_at is not None:
            fault.detail["metrics_resumed_at"] = self.stack.wait_until(
                self.stack.last_metrics_at, fault.recovered_at, 45.0
            )

    def _observe_ui(self, name: str) -> None:
        snapshot = self.stack.ui_snapshot()
        self.ui[name] = snapshot
        if self.browser:
            titles = list(snapshot["attention"])  # type: ignore[call-overload]
            wanted = [t for t in _UI_ATTENTION[name] if t in titles]
            render = self.stack.browser_render(name, (wanted or _UI_ATTENTION[name])[0])
            self.renders[name] = render
            print(f"  {name}: browser {render.get('seconds')}s", flush=True)

    def _recover_data(self, fault: Fault) -> None:
        fault.ended = fault.ended or _utc()
        fault.recovered_at = self.stack.wait_until(
            self.stack.last_received_at, fault.ended, self.recovery_timeout
        )
        self._record(fault)
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
        self._record(fault)
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

        samples = []
        for _ in range(3):
            samples.append(self.stack.spool_pending())
            time.sleep(1)
        baseline = max(samples)
        fault = Fault(label, "spool_backlog", _utc(), loss_allowed=False)
        fault.detail["baseline_pending"] = baseline
        lock = FileLock(str(self.stack.root / "catalog.sqlite") + ".phm.lock")
        with lock:
            time.sleep(self.stall)
            fault.detail["peak_pending"] = self.stack.spool_pending()
        fault.ended = _utc()
        # Drained = back to the pre-fault baseline plus one in-flight writer batch.
        limit = baseline + 50
        deadline = time.monotonic() + self.recovery_timeout
        while time.monotonic() < deadline and self.stack.spool_pending() > limit:
            time.sleep(1)
        drained = self.stack.spool_pending() <= limit
        fault.detail["drained"] = drained
        fault.detail["final_pending"] = self.stack.spool_pending()
        fault.recovered_at = _utc() if drained else None
        self._record(fault)
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
        self._observe_ui("source_stale")
        s.stop(s.replay)
        s.start_replay()
        self._recover_data(fault)

        # Source unreachable.
        fault = Fault("ui_source_unreachable", "ui_source_unreachable", _utc())
        s.stop(s.replay)
        time.sleep(15)
        self._observe_ui("source_unreachable")
        s.start_replay()
        self._recover_data(fault)

        # Collector down.
        fault = Fault("ui_collector_down", "ui_collector_down", _utc())
        s.kill(s.collector)
        time.sleep(25)
        self._observe_ui("collector_down")
        s.start_collector()
        self._recover_data(fault)

        # Analysis stale.
        fault = Fault("ui_analysis_stale", "ui_analysis_stale", _utc(), loss_allowed=False)
        s.kill(s.runner)
        time.sleep(25)
        self._observe_ui("analysis_stale")
        s.start_runner()
        fault.ended = _utc()
        fault.recovered_at = s.wait_until(s.runner_heartbeat, fault.ended, self.recovery_timeout)
        self._record(fault)

    def review_workflow(self) -> None:
        """After every fault, request review of the newest result and follow it to Maintenance.

        Both steps read the queues the app itself builds; the review request is the
        same domain call the Investigations "Request review" button makes.
        """
        before = self.stack.app_probe(
            "from industrial_phm.application import PHASE_UNBALANCE_CAPABILITY_ID as CAP\n"
            "from industrial_phm.application.finding_review import (\n"
            "    JsonOperationalFindingRepository, create_human_review_finding)\n"
            "import os\n"
            "from pathlib import Path\n"
            "queue = defs['investigation_queue']\n"
            "latest = [g.latest for g in queue.groups() if g.capability_id == CAP\n"
            "          and g.review_state.value == 'not-requested']\n"
            "item = max(latest, key=lambda i: i.completed_at)\n"
            "result = next(r for r in defs['current_analysis_results']\n"
            "              if r.run.analysis_run_id == item.analysis_run_id)\n"
            "finding = create_human_review_finding(result)\n"
            "JsonOperationalFindingRepository(\n"
            "    Path(os.environ['INDUSTRIAL_PHM_OPERATIONS_FINDING_STATE'])).record(finding)\n"
            "out = {'analysis_run_id': item.analysis_run_id, 'finding_id': finding.finding_id,\n"
            "       'observed_end_at': result.run.observed_end_at.isoformat(),\n"
            "       'before_state': item.review_state.value}\n"
        )
        after = self.stack.app_probe(
            f"run_id = {before['analysis_run_id']!r}\n"
            f"finding_id = {before['finding_id']!r}\n"
            "states = [g.review_state.value for g in defs['investigation_queue'].groups()\n"
            "          if any(i.analysis_run_id == run_id for i in g.items)]\n"
            "items = [i for i in defs['maintenance_queue'].items if i.finding_id == finding_id]\n"
            "out = {'after_state': states[0] if len(states) == 1 else states,\n"
            "       'maintenance_status': items[0].status.value if len(items) == 1 else None}\n"
        )
        last_fault = max(fault.started for fault in self.faults)
        self.workflow = {
            **before,
            **after,
            "result_after_last_fault": datetime.fromisoformat(str(before["observed_end_at"]))
            > last_fault,
        }
        print(f"  review workflow: {self.workflow}", flush=True)


_UI_ATTENTION = {
    "source_stale": ("No new data",),
    "source_unreachable": ("Collection needs attention", "Source connection lost"),
    "collector_down": ("Collection service is not running",),
    "analysis_stale": ("Analysis service is not updating",),
}


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
    from industrial_phm.application import WindowInputReference
    from industrial_phm.application.observation_window_sqlite import (
        SqliteObservationWindowRepository,
    )
    from industrial_phm.application.phase_unbalance import UnbalanceQuantity
    from industrial_phm.application.phase_unbalance_state import (
        JsonPhaseUnbalanceRepository,
        window_result_key,
    )
    from industrial_phm.application.window_analysis_ledger_sqlite import (
        SqliteWindowAnalysisLedger,
    )
    from industrial_phm.presentation.phase_unbalance import (
        phase_unbalance_provenance_rows,
        phase_unbalance_summary_rows,
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

    # Windows lying wholly inside the omission: the window names the missing phase, the
    # result leaves only current unresolved, and the Investigation tables (summary note
    # and provenance) carry that exact reason. A skip there is a failure.
    omission_windows: list[dict[str, object]] = []
    skipped_in_omission = 0
    if harness.omission is not None:
        omitted_from, omitted_until = harness.omission
        inside = {
            row[0]
            for row in window_rows
            if row[2] >= omitted_from + timedelta(seconds=5) and row[3] <= omitted_until
        }
        by_window = {
            r.evidence.input_reference.window_id: r
            for r in results
            if isinstance(r.evidence.input_reference, WindowInputReference)
        }
        window_repository = SqliteObservationWindowRepository(root / "windows.sqlite")
        skipped_in_omission = sum(1 for outcome in skipped if outcome.window_id in inside)
        for window_id in sorted(inside):
            window = window_repository.get(window_id)
            result = by_window.get(window_id)
            item: dict[str, object] = {
                "window_id": window_id,
                "missing_channels": list(window.missing_channel_ids),
                "current_selection": None,
                "voltage_selection": None,
                "current_note": "",
                "provenance_missing_channels": None,
            }
            if result is not None:
                selections = {
                    series.quantity: series.channel_selection for series in result.evidence.results
                }
                # Summary rows follow evidence order; quantity labels are display text.
                notes = {
                    series.quantity: row["note"]
                    for series, row in zip(
                        result.evidence.results, phase_unbalance_summary_rows(result), strict=True
                    )
                }
                provenance = {
                    row["field"]: row["value"] for row in phase_unbalance_provenance_rows(result)
                }
                item.update(
                    current_selection=selections[UnbalanceQuantity.CURRENT].value,
                    voltage_selection=selections[UnbalanceQuantity.VOLTAGE].value,
                    current_note=notes[UnbalanceQuantity.CURRENT],
                    provenance_missing_channels=provenance.get("missing_channels"),
                )
            omission_windows.append(item)

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
        "missing_phase_explained": check_missing_phase(
            OMITTED_CHANNEL, omission_windows, skipped_in_omission
        ),
        "ui_states_distinct": check_ui_states(harness.ui),
        "review_workflow_continues": check_review_workflow(harness.workflow),
    }
    # Scenario-specific checks only for scenarios that ran (a diagnostic run may filter).
    if overflow_faults:
        checks["forced_overflow_happened"] = _check(
            all(int(f.detail.get("overflow_rejected", 0)) > 0 for f in overflow_faults),  # type: ignore[call-overload]
            per_fault=[f.detail for f in overflow_faults],
        )
    backlog_faults = [f.detail for f in harness.faults if f.scenario == "spool_backlog"]
    if backlog_faults:
        checks["spool_backlog_drained_to_baseline"] = check_backlog(backlog_faults)
    if harness.browser:
        checks["browser_readable_within_5s"] = check_first_render(harness.renders)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="empty directory for this run")
    parser.add_argument("--repeat", type=int, default=3, help="injections per scenario (N)")
    parser.add_argument("--scenarios", nargs="+", choices=SCENARIOS, default=list(SCENARIOS))
    parser.add_argument("--port", type=int, default=4852)
    parser.add_argument("--speed", type=float, default=60.0)
    parser.add_argument("--stall-seconds", type=float, default=20.0)
    parser.add_argument("--recovery-timeout", type=float, default=120.0)
    parser.add_argument(
        "--browser",
        action="store_true",
        help="also open Monitor in Chromium (Playwright) for each UI state; required for 'full'",
    )
    parser.add_argument("--ui-port", type=int, default=27190)
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
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    root = args.root.resolve()
    endpoint = f"opc.tcp://127.0.0.1:{args.port}/aihub-replay/"
    _prepare(root, endpoint, args)

    stack = Stack(root, endpoint, speed=args.speed)
    harness = Harness(
        stack,
        stall_seconds=args.stall_seconds,
        recovery_timeout=args.recovery_timeout,
        browser=args.browser,
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
        if args.browser:
            stack.start_ui_server(args.ui_port)
        for index in range(1, args.repeat + 1):
            for scenario in args.scenarios:
                label = f"{scenario}#{index}"
                print(f"[{_utc():%H:%M:%S}] {label}", flush=True)
                getattr(harness, scenario)(label)
                time.sleep(10)
        harness.missing_phase_and_ui()
        time.sleep(40)
        harness.review_workflow()
        audit_until = _utc() - timedelta(seconds=20)
        stack.stop(stack.collector)
        time.sleep(15)  # let the runner finish windows finalized before the stop
        stack.stop(stack.runner)
        stack.stop(stack.replay)
        verdict = judge(harness, audit_since=first, audit_until=audit_until)
    finally:
        stack.stop_all()
    # Only an unfiltered N>=3 run with the browser check can stand in for the #321 gate.
    full = set(args.scenarios) == set(SCENARIOS) and args.repeat >= 3 and args.browser
    verdict["gate"] = "full" if full else "diagnostic"
    verdict["config"] = {
        "repeat": args.repeat,
        "scenarios": args.scenarios,
        "browser": args.browser,
        "stall_seconds": args.stall_seconds,
        "speed": args.speed,
        "started": started.isoformat(),
        "finished": _utc().isoformat(),
    }
    (root / "harness-verdict.json").write_text(json.dumps(verdict, indent=2, default=str) + "\n")
    for name, check in verdict["checks"].items():  # type: ignore[union-attr]
        print(f"{'PASS' if check['passed'] else 'FAIL'}  {name}", flush=True)
    outcome = "PASS" if verdict["passed"] else "FAIL"
    print(f"verdict ({verdict['gate']}): {outcome} -> {root / 'harness-verdict.json'}")
    if verdict["gate"] == "diagnostic":
        print("note: partial scenarios, repeat < 3 or no --browser; this is not the #321 gate")
    raise SystemExit(0 if verdict["passed"] else 1)


if __name__ == "__main__":
    main()
