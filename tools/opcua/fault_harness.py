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

REPO = Path(__file__).resolve().parents[2]
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
        or int(r.get("asset_fact_count", 0)) < 1
        or not r.get("system_state_clearly_scoped")
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
    omitted_raw = states["during_missing"].get("omitted_from")
    omitted_from = None if omitted_raw is None else datetime.fromisoformat(str(omitted_raw))
    during = event_at("during_missing")
    during_peer = event_at("during_missing_peer")
    recovered = event_at("recovered")
    reconnect_flow = str(states["reconnecting"].get("source_flow"))

    passed = (
        states["before_missing"].get("source_flow") == "Receiving"
        and before is not None
        and before_peer is not None
        and states["during_missing"].get("source_flow") == "Receiving"
        # No value for the omitted channel after the omission started (a value stored
        # between the "before" snapshot and the replay restart is legitimate), while
        # its peer keeps arriving.
        and during is not None
        and before is not None
        and omitted_from is not None
        and before <= during <= omitted_from
        and during_peer is not None
        and before_peer is not None
        and during_peer > max(before_peer, omitted_from)
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
            not renders[name].get("source_evidence_seen")
            or int(renders[name].get("evidence_row_count", 0)) < 1
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
        """Inspect the shared Operations monitor read model, independent of any UI."""
        from industrial_phm.runtime.operations_app_composition import load_operations_app_snapshot

        snapshot = load_operations_app_snapshot(environ=self.app_env())
        monitor = snapshot.monitor
        stages = {stage.kind.value: stage for stage in monitor.stages}
        return {
            "sources": stages["source"].status.value,
            "collect": stages["collection"].status.value,
            "collect_summary": stages["collection"].summary,
            "analyze": stages["analysis"].status.value,
            "attention": sorted({item.title for item in monitor.attention}),
        }

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

    # ----------------------------------------------------------- real browser

    def start_ui_server(self, port: int) -> None:
        """Run the actual packaged Web in read-only mode against the replay root."""
        log = (self.root / "harness-ui.log").open("ab")
        self.ui_server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "industrial_phm.runtime.operations_web_preview",
                str(self.root),
                "--port",
                str(port),
            ],
            cwd=REPO,
            env=self.app_env(),
            stdout=log,
            stderr=log,
        )
        self.ui_url = f"http://127.0.0.1:{port}/web/"
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if self.ui_server.poll() is not None:
                raise RuntimeError("Operations Web process exited before readiness")
            try:
                with urllib.request.urlopen(self.ui_url, timeout=1) as response:
                    if response.status == 200:
                        return
            except OSError:
                time.sleep(0.5)
        raise RuntimeError("Operations Web UI server did not start")

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
                    render.get("source_evidence_seen")
                    and int(render.get("evidence_row_count", 0)) >= 1
                    and render.get("matched")
                    and int(render.get("overflow_count", 0)) == 0
                    and float(render["seconds"]) <= 5.0
                )
                return render
        return {"within_5s": False, "error": output.stderr[-1500:]}


# Detect visible horizontal overflow outside scrollable containers.
_OVERFLOW_JS = """() => {
  const limit = window.innerWidth + 1;
  return [...document.querySelectorAll('main *')].filter((element) => {
    const rect = element.getBoundingClientRect();
    if (!rect.width || !rect.height || rect.right <= limit) return false;
    for (let parent = element.parentElement; parent; parent = parent.parentElement) {
      const style = getComputedStyle(parent).overflowX;
      if (style === 'auto' || style === 'scroll') return false;
    }
    return true;
  }).map((element) => element.tagName + ':' + element.id).slice(0, 10);
}"""

# The current Web shows bounded evidence, not a live measurement widget.
_BROWSER_SCRIPT = """
import json, sys, time
from playwright.sync_api import sync_playwright
url, attention, shot = sys.argv[1:4]
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1100})
    started = time.monotonic()
    page.goto(url, wait_until="domcontentloaded")
    try:
        page.wait_for_function(
            "() => document.getElementById('asset-count').textContent.trim() !== '—'",
            timeout=30000,
        )
    except Exception:
        pass
    seconds = time.monotonic() - started
    count = page.locator("#asset-count").inner_text().strip()
    facts = page.locator("#asset-facts .fact strong").all_inner_texts()
    statuses = page.locator("#monitor-attention strong").all_inner_texts()
    attention_seen = None if not attention else attention in statuses
    system_scoped = "설비 정상" in page.locator("#system-status").inner_text()
    overflow = page.evaluate(OVERFLOW_JS)
    monitor_ready = count not in ("—", "0") and bool(facts) and system_scoped and not overflow
    page.screenshot(path=shot, full_page=True)
    browser.close()
print("BROWSER " + json.dumps({
    "seconds": round(seconds, 2),
    "attention": attention,
    "attention_seen": attention_seen,
    "asset_count": count,
    "asset_fact_count": len(facts),
    "system_state_clearly_scoped": system_scoped,
    "overflow_count": len(overflow),
    "overflow_examples": overflow,
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
    page.goto(url, wait_until="domcontentloaded")
    card = page.locator('.source-record[data-source-id="aihub239-replay-boiler-2297"]')
    try:
        card.wait_for(state="visible", timeout=30000)
    except Exception:
        pass
    text = card.inner_text() if card.count() else ""
    # Web exposes accepted receipts, session and recent live evidence separately.
    source_evidence_seen = (
        "OPC UA 세션 마지막 기록:" in text and "live 이벤트 마지막 수신:" in text
    )
    conditions = {
        "Source flow · Receiving": "30초 이내 수신 근거 있음",
        "Source flow · No recent source data": "최근 수신 근거 미확인",
        "Source flow · Connecting": "connecting",
        "Source flow · Reconnecting": "reconnect",
        "Source flow · Disconnected": "disconnected",
    }
    matched = next(
        (item for item in expected if conditions.get(item, item) in text), None
    )
    evidence_rows = card.locator("span").count() if card.count() else 0
    seconds = time.monotonic() - started
    overflow = page.evaluate(OVERFLOW_JS)
    page.screenshot(path=shot, full_page=True)
    browser.close()
print("LIVE-BROWSER " + json.dumps({
    "seconds": round(seconds, 2),
    "expected": expected,
    "matched": matched,
    "source_evidence_seen": source_evidence_seen,
    "evidence_row_count": evidence_rows,
    "overflow_count": len(overflow),
    "overflow_examples": overflow,
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
        self.live["during_missing"]["omitted_from"] = omitted_from.isoformat()
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
        """Request and verify exact persisted evidence through the Web review facade."""
        from industrial_phm.application.phase_unbalance import PHASE_UNBALANCE_CAPABILITY_ID
        from industrial_phm.runtime.operations_app_composition import load_operations_app_snapshot
        from industrial_phm.runtime.operations_web_review import request_web_analysis_review

        snapshot = load_operations_app_snapshot(environ=self.stack.app_env())
        reviewed = {item.finding.analysis_run_id for item in snapshot.overview.review_summaries}
        candidates = [
            result
            for result in snapshot.analysis_results
            if result.run.capability_id == PHASE_UNBALANCE_CAPABILITY_ID
            and result.run.analysis_run_id not in reviewed
        ]
        if not candidates:
            raise RuntimeError("no unreviewed persisted phase analysis after injected faults")
        result = max(candidates, key=lambda item: item.run.completed_at)
        before = {
            "analysis_run_id": result.run.analysis_run_id,
            "observed_end_at": result.run.observed_end_at.isoformat(),
            "before_state": "not-requested",
        }
        response = request_web_analysis_review(
            self.stack.root,
            {
                "analysis_run_id": result.run.analysis_run_id,
                "evidence_id": result.evidence.evidence_id,
            },
        )
        after = load_operations_app_snapshot(environ=self.stack.app_env())
        matching = [
            item
            for item in after.overview.review_summaries
            if item.finding.finding_id == response["finding_id"]
            and item.finding.analysis_run_id == result.run.analysis_run_id
        ]
        if len(matching) != 1:
            raise RuntimeError("persisted review reference missing or ambiguous")
        status = matching[0].status.value
        last_fault = max(fault.started for fault in self.faults)
        self.workflow = {
            **before,
            "finding_id": response["finding_id"],
            "after_state": status,
            "maintenance_status": status,
            "result_after_last_fault": result.run.observed_end_at > last_fault,
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
