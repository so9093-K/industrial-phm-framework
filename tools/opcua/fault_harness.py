"""Repeatable AI-Hub boiler 2297 replay fault/recovery gate.

This harness is intentionally scoped to the bundled AI-Hub 239 boiler device 2297
replay profile and its explicit phase-current identities; it is not a generic
live-source fault harness.

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

from industrial_phm.apps import operations_app_path

REPO = Path(__file__).resolve().parents[2]
OPERATIONS_APP = operations_app_path()
CLI = [sys.executable, "-c", "from industrial_phm.cli import main; raise SystemExit(main())"]
# Deliberately fixed identities for the bundled boiler-2297 replay gate.
AIHUB_BOILER_2297_SOURCE_ID = "aihub239-replay-boiler-2297"
AIHUB_BOILER_2297_OMITTED_CHANNEL = "T상전류"
AIHUB_BOILER_2297_PEER_CHANNEL = "R상전류"
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


# Monitor states captured in Chromium. Normal receiving and a missing phase have no
# expected attention: they show whether observations, not workflow, lead the screen.
MONITOR_RENDER_STATES = (
    "normal",
    "missing_phase",
    "source_stale",
    "source_unreachable",
    "collector_down",
    "analysis_stale",
)
_MONITOR_STATES_WITHOUT_ATTENTION = frozenset({"normal", "missing_phase"})


def check_first_render(renders: dict[str, dict[str, object]]) -> dict[str, object]:
    """Require the observation-first Monitor surface to be readable within five seconds."""

    missing = [name for name in MONITOR_RENDER_STATES if name not in renders]
    slow = {name: r for name, r in renders.items() if not r.get("within_5s")}
    incomplete = {
        name: r
        for name, r in renders.items()
        if not r.get("monitor_ready")
        or (name not in _MONITOR_STATES_WITHOUT_ATTENTION and not r.get("attention_seen"))
        or int(r.get("signal_value_count", 0)) < 1
        or not r.get("system_data_flow_absent")
        or int(r.get("overflow_count", 0)) > 0
    }
    return _check(
        not missing and not slow and not incomplete,
        renders=renders,
        missing=missing,
        slow=slow,
        incomplete=incomplete,
    )


def check_live_replay_sequence(states: dict[str, dict[str, object]]) -> dict[str, object]:
    """Judge the observation journey without inventing channel cadence semantics."""

    required = {
        "before_missing",
        "before_missing_peer",
        "during_missing",
        "during_missing_peer",
        "paused",
        "reconnecting",
        "recovered",
    }
    missing = sorted(required - set(states))
    if missing:
        return _check(False, missing_states=missing, states=states)

    def event_at(name: str) -> datetime | None:
        value = states[name].get("channel_event_at")
        return None if value is None else datetime.fromisoformat(str(value))

    before = event_at("before_missing")
    before_peer = event_at("before_missing_peer")
    during = event_at("during_missing")
    during_peer = event_at("during_missing_peer")
    recovered = event_at("recovered")
    reconnect_flow = str(states["reconnecting"].get("source_flow"))

    passed = (
        states["before_missing"].get("source_flow") == "Receiving"
        and before is not None
        and before_peer is not None
        and states["during_missing"].get("source_flow") == "Receiving"
        and during == before
        and during_peer is not None
        and during_peer > before_peer
        and "behind latest source timestamp"
        in str(states["during_missing"].get("channel_event_lag"))
        and states["paused"].get("source_flow") == "No recent source data"
        and reconnect_flow in {"Connecting", "Reconnecting", "Disconnected"}
        and states["recovered"].get("source_flow") == "Receiving"
        and recovered is not None
        and during is not None
        and recovered > during
        and int(states["recovered"].get("history_count", 0))
        > int(states["before_missing"].get("history_count", 0))
    )
    return _check(passed, states=states)


def check_live_browser_journey(renders: dict[str, dict[str, object]]) -> dict[str, object]:
    """Require the core live states to become readable within five seconds."""

    required = ("before_missing", "paused", "reconnecting", "recovered")
    missing = [name for name in required if name not in renders]
    slow = {
        name: renders[name]
        for name in required
        if name in renders and not renders[name].get("within_5s")
    }
    unmatched = {
        name: renders[name]
        for name in required
        if name in renders and not renders[name].get("matched")
    }
    incomplete = {
        name: renders[name]
        for name in required
        if name in renders
        and (
            not renders[name].get("current_observation_seen")
            or int(renders[name].get("value_count", 0)) < 1
        )
    }
    return _check(
        not missing and not slow and not unmatched and not incomplete,
        missing=missing,
        slow=slow,
        unmatched=unmatched,
        incomplete=incomplete,
        renders=renders,
    )


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
    # Only the fault states must differ; normal/missing-phase snapshots are screenshots.
    signatures = {
        name: (snap["sources"], snap["collect"], snap["analyze"], tuple(snap["attention"]))  # type: ignore[arg-type]
        for name, snap in snapshots.items()
        if name in UI_EXPECTED
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
            "internal",
            "collection-service",
            "--workspace",
            str(r),
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
                "internal",
                "window-analysis",
                "--workspace",
                str(r),
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
            return (
                SqliteAcquisitionTelemetryRepository(path)
                .get(AIHUB_BOILER_2297_SOURCE_ID)
                .last_received_at
            )
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

    def live_snapshot(self, channel_id: str) -> dict[str, object]:
        """Read the same bounded live projection used by Assets -> Signals."""

        from industrial_phm.application.operations_assets import AssetWorkspaceSource
        from industrial_phm.application.operations_monitor import OperationsMonitorStatus
        from industrial_phm.presentation.operations_live import (
            channel_event_lag_label,
            live_source_flow_label,
        )
        from industrial_phm.runtime.operations_app_context import load_operations_app_context
        from industrial_phm.runtime.operations_live import load_operations_live_observation

        sampled_at = _utc()
        context = load_operations_app_context(
            environ=self.app_env(),
            assessed_at=sampled_at,
        )
        source = next(
            item
            for item in context.snapshot.registered_sources
            if item.source_id == AIHUB_BOILER_2297_SOURCE_ID
        )
        source_view = AssetWorkspaceSource(
            source_id=source.source_id,
            name=source.name,
            source_type=source.source_type,
            status=OperationsMonitorStatus.RUNNING,
            last_data_at=None,
            measurement_point_id=source.measurement_point_id,
            channel_count=len(source.channel_identities),
        )
        view = load_operations_live_observation(
            context.snapshot.paths,
            asset_id=source.asset_id,
            channel_id=channel_id,
            registered_sources=context.snapshot.registered_sources,
            asset_sources=(source_view,),
            sampled_at=sampled_at,
            lookback_seconds=60.0,
            point_budget=600,
        )
        series = next(item for item in view.series if item.source_id == AIHUB_BOILER_2297_SOURCE_ID)
        latest = series.latest_point
        history = next(
            (item for item in context.snapshot.history_assets if item.asset_id == source.asset_id),
            None,
        )
        return {
            "source_flow": live_source_flow_label(
                series,
                sampled_at=sampled_at,
                silence_limit_seconds=context.snapshot.live_flow_timing.max_silence.total_seconds(),
            ),
            "channel_event_at": (
                None
                if latest is None or latest.measurement.event_at is None
                else latest.measurement.event_at.isoformat()
            ),
            "last_source_timestamp": (
                None
                if series.last_source_timestamp is None
                else series.last_source_timestamp.isoformat()
            ),
            "channel_event_lag": channel_event_lag_label(series),
            "source_quality": None if latest is None else latest.measurement.source_quality.value,
            "recent_points": len(series.recent_points),
            "history_count": 0 if history is None else history.measurement_count,
        }

    def app_env(self) -> dict[str, str]:
        env = dict(self.env)
        env["INDUSTRIAL_PHM_OPERATIONS_WORKSPACE"] = str(self.root)
        return env

    def app_probe(self, body: str) -> dict[str, object]:
        """Run Operations V2 in script mode against this root; ``body`` sets ``out``."""
        script = (
            "import json, runpy\n"
            f"app = runpy.run_path({str(OPERATIONS_APP)!r})['app']\n"
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
                str(OPERATIONS_APP),
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

    def browser_render(self, name: str, expected_attention: str | None) -> dict[str, object]:
        """Open Monitor in Chromium; time until observation data and attention are readable."""
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
                expected_attention or "",
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
                    render.get("monitor_ready")
                    and (expected_attention is None or render.get("attention_seen"))
                    and float(render["seconds"]) <= 5.0  # type: ignore[arg-type]
                )
                return render
        return {"within_5s": False, "error": output.stderr[-1500:]}

    def browser_live_render(
        self,
        name: str,
        expected: Sequence[str],
    ) -> dict[str, object]:
        """Open Assets -> Signals and wait for one expected live observation state."""

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
                _BROWSER_LIVE_SCRIPT,
                self.ui_url,
                json.dumps(list(expected)),
                str(self.root / f"ui-live-{name}.png"),
            ],
            cwd=REPO,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        for line in output.stdout.splitlines():
            if line.startswith("LIVE-BROWSER "):
                render = dict(json.loads(line.removeprefix("LIVE-BROWSER ")))
                render["within_5s"] = bool(
                    render.get("current_observation_seen")
                    and int(render.get("value_count", 0)) >= 1
                    and render.get("matched")
                    and int(render.get("overflow_count", 0)) == 0
                    and float(render["seconds"]) <= 5.0
                )
                return render
        return {"within_5s": False, "error": output.stderr[-1500:]}


# Visible elements whose right edge passes the viewport, outside intended horizontal
# scroll containers. Content clipped by the page is unreadable even when it "renders".
_OVERFLOW_JS = """() => {
  const limit = window.innerWidth + 1;
  const scrolls = (e) => {
    for (let a = e.parentElement; a; a = a.parentElement) {
      const x = getComputedStyle(a).overflowX;
      if ((x === 'auto' || x === 'scroll') && a.getBoundingClientRect().right <= limit) return true;
    }
    return false;
  };
  const out = [];
  for (const e of document.querySelectorAll('body *')) {
    const r = e.getBoundingClientRect();
    if (r.width === 0 || r.height === 0 || r.right <= limit) continue;
    if (getComputedStyle(e).visibility === 'hidden' || scrolls(e)) continue;
    out.push(e.tagName + '.' + String(e.className).slice(0, 40) + ':' + Math.round(r.right));
  }
  return out;
}"""

# Opens a fresh page (a fresh marimo session reads current runtime files), waits for
# the observation-first Monitor surface and the expected attention title, and reports
# the elapsed time. Runtime/System flow is deliberately not a Monitor readiness signal.
_BROWSER_SCRIPT = """
import json, sys, time
from playwright.sync_api import sync_playwright
url, attention, shot = sys.argv[1:4]
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1100})
    started = time.monotonic()
    page.goto(url)
    observed_asset_seen = latest_seen = trends_seen = False
    try:
        page.get_by_text("Observed asset", exact=True).first.wait_for(timeout=30000)
        observed_asset_seen = True
        page.get_by_text("Latest stored observations", exact=True).first.wait_for(timeout=30000)
        latest_seen = True
        page.get_by_text("Recent signal trends", exact=True).first.wait_for(timeout=30000)
        trends_seen = True
        page.locator(".phm-signal-value").first.wait_for(timeout=30000)
    except Exception:
        pass
    observation_seconds = time.monotonic() - started
    attention_seen = None
    if attention:
        attention_seen = True
        try:
            # Exact text: the attention selector's hidden <option> also contains it.
            page.get_by_text(attention, exact=True).first.wait_for(timeout=30000)
        except Exception:
            attention_seen = False
    seconds = time.monotonic() - started
    signal_values = page.locator(".phm-signal-value").all_inner_texts()
    system_data_flow_absent = page.get_by_text("System data flow", exact=True).count() == 0
    overflow = page.evaluate(OVERFLOW_JS)
    monitor_ready = (
        observed_asset_seen
        and latest_seen
        and trends_seen
        and bool(signal_values)
        and system_data_flow_absent
        and not overflow
    )
    page.screenshot(path=shot, full_page=True)
    browser.close()
print("BROWSER " + json.dumps({
    "observation_seconds": round(observation_seconds, 2),
    "seconds": round(seconds, 2),
    "attention": attention,
    "attention_seen": attention_seen,
    "observed_asset_seen": observed_asset_seen,
    "latest_observations_seen": latest_seen,
    "recent_trends_seen": trends_seen,
    "signal_value_count": len(signal_values),
    "signal_values": [" | ".join(item.split()) for item in signal_values[:8]],
    "system_data_flow_absent": system_data_flow_absent,
    "overflow_count": len(overflow),
    "overflow_examples": overflow[:6],
    "monitor_ready": monitor_ready,
}))
"""


_BROWSER_LIVE_SCRIPT = """
import json, sys, time
from playwright.sync_api import sync_playwright
url, expected_json, shot = sys.argv[1:4]
expected = json.loads(expected_json)
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1100})
    started = time.monotonic()
    page.goto(url)
    try:
        page.get_by_role("radio", name="Assets", exact=True).click(timeout=5000)
    except Exception:
        page.get_by_text("Assets", exact=True).first.click()
    try:
        page.get_by_role("radio", name="Signals", exact=True).click(timeout=5000)
    except Exception:
        page.get_by_text("Signals", exact=True).first.click()
    current_observation_seen = True
    try:
        page.get_by_text("Current observation", exact=True).first.wait_for(timeout=30000)
        page.locator(".phm-live-value").first.wait_for(timeout=30000)
    except Exception:
        current_observation_seen = False
    matched = None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        body = page.locator("body").inner_text()
        matched = next((item for item in expected if item in body), None)
        if matched is not None:
            break
        page.wait_for_timeout(200)
    seconds = time.monotonic() - started
    states = page.locator(".phm-live-state").all_inner_texts()
    values = page.locator(".phm-live-value").all_inner_texts()
    overflow = page.evaluate(OVERFLOW_JS)
    page.screenshot(path=shot, full_page=True)
    browser.close()
print("LIVE-BROWSER " + json.dumps({
    "seconds": round(seconds, 2),
    "expected": expected,
    "matched": matched,
    "current_observation_seen": current_observation_seen,
    "value_count": len(values),
    "states": [" | ".join(item.split()) for item in states],
    "values": [" | ".join(item.split()) for item in values],
    "overflow_count": len(overflow),
    "overflow_examples": overflow[:6],
}))
"""
_BROWSER_SCRIPT = f"OVERFLOW_JS = {_OVERFLOW_JS!r}\n" + _BROWSER_SCRIPT
_BROWSER_LIVE_SCRIPT = f"OVERFLOW_JS = {_OVERFLOW_JS!r}\n" + _BROWSER_LIVE_SCRIPT


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
        self.live: dict[str, dict[str, object]] = {}
        self.live_renders: dict[str, dict[str, object]] = {}
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
            expected = None
            if name in _UI_ATTENTION:
                titles = list(snapshot["attention"])  # type: ignore[call-overload]
                wanted = [t for t in _UI_ATTENTION[name] if t in titles]
                expected = (wanted or _UI_ATTENTION[name])[0]
            render = self.stack.browser_render(name, expected)
            self.renders[name] = render
            print(f"  {name}: browser {render.get('seconds')}s", flush=True)

    def _observe_live(
        self,
        name: str,
        channel_id: str,
        *,
        browser_expected: Sequence[str] = (),
    ) -> dict[str, object]:
        snapshot = self.stack.live_snapshot(channel_id)
        self.live[name] = snapshot
        if self.browser and browser_expected:
            render = self.stack.browser_live_render(name, browser_expected)
            self.live_renders[name] = render
            print(
                f"  live {name}: {snapshot['source_flow']}; browser {render.get('seconds')}s",
                flush=True,
            )
        else:
            print(f"  live {name}: {snapshot['source_flow']}", flush=True)
        return snapshot

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
        # Normal receiving: the screen an operator sees most of the time.
        self._observe_ui("normal")
        self._observe_live(
            "before_missing",
            AIHUB_BOILER_2297_OMITTED_CHANNEL,
            browser_expected=("Source flow · Receiving",),
        )
        self._observe_live("before_missing_peer", AIHUB_BOILER_2297_PEER_CHANNEL)

        # Missing phase: replay omits one current phase for three windows. The source
        # keeps receiving other channels; the selected channel must not fake continuity.
        fault = Fault("missing_phase", "missing_phase", _utc())
        s.stop(s.replay)
        s.start_replay("--omit-channel", AIHUB_BOILER_2297_OMITTED_CHANNEL)
        omitted_from = _utc()
        time.sleep(95)
        self._observe_ui("missing_phase")
        self._observe_live("during_missing", AIHUB_BOILER_2297_OMITTED_CHANNEL)
        self._observe_live("during_missing_peer", AIHUB_BOILER_2297_PEER_CHANNEL)
        self.omission = (omitted_from, _utc())
        s.stop(s.replay)
        s.start_replay()
        self._recover_data(fault)

        # Source stale: connected, values frozen.
        fault = Fault("ui_source_stale", "ui_source_stale", _utc())
        s.stop(s.replay)
        s.start_replay("--freeze-after-records", "3")
        time.sleep(50)
        self._observe_live(
            "paused",
            AIHUB_BOILER_2297_PEER_CHANNEL,
            browser_expected=("Source flow · No recent source data",),
        )
        self._observe_ui("source_stale")
        s.stop(s.replay)
        s.start_replay()
        self._recover_data(fault)

        # Source unreachable.
        fault = Fault("ui_source_unreachable", "ui_source_unreachable", _utc())
        s.stop(s.replay)
        time.sleep(15)
        self._observe_live(
            "reconnecting",
            AIHUB_BOILER_2297_PEER_CHANNEL,
            browser_expected=(
                "Source flow · Connecting",
                "Source flow · Reconnecting",
                "Source flow · Disconnected",
            ),
        )
        self._observe_ui("source_unreachable")
        s.start_replay()
        self._recover_data(fault)

        _deadline = time.monotonic() + self.recovery_timeout
        _recovered = self.stack.live_snapshot(AIHUB_BOILER_2297_OMITTED_CHANNEL)
        _missing_event = self.live["during_missing"].get("channel_event_at")
        while time.monotonic() < _deadline:
            _event = _recovered.get("channel_event_at")
            if _event is not None and _event != _missing_event:
                break
            time.sleep(1)
            _recovered = self.stack.live_snapshot(AIHUB_BOILER_2297_OMITTED_CHANNEL)
        self.live["recovered"] = _recovered
        if self.browser:
            self.live_renders["recovered"] = self.stack.browser_live_render(
                "recovered",
                ("Source flow · Receiving",),
            )

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
            "queue = defs['investigation_queue']\n"
            "latest = [g.latest for g in queue.groups() if g.capability_id == CAP\n"
            "          and g.review_state.value == 'not-requested']\n"
            "item = max(latest, key=lambda i: i.completed_at)\n"
            "result = next(r for r in defs['current_analysis_results']\n"
            "              if r.run.analysis_run_id == item.analysis_run_id)\n"
            "# The workspace-bound action the Investigations button calls.\n"
            "finding, _ = defs['operations_actions'].request_review(result)\n"
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
        SqlitePhaseUnbalanceRepository,
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
    observed = observed_events(root, AIHUB_BOILER_2297_SOURCE_ID)
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
    results = SqlitePhaseUnbalanceRepository(root / "phase-unbalance.sqlite").list_results()
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
            AIHUB_BOILER_2297_OMITTED_CHANNEL, omission_windows, skipped_in_omission
        ),
        "ui_states_distinct": check_ui_states(harness.ui),
        "live_replay_observation_journey": check_live_replay_sequence(harness.live),
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
        checks["live_browser_readable_within_5s"] = check_live_browser_journey(harness.live_renders)
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
        AIHUB_BOILER_2297_SOURCE_ID,
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
    # Only an unfiltered N>=3 run with the browser check qualifies as the full reliability gate.
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
        print("note: partial scenarios, repeat < 3 or no --browser; this is a diagnostic run")
    raise SystemExit(0 if verdict["passed"] else 1)


if __name__ == "__main__":
    main()
