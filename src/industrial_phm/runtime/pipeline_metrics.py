"""Opt-in collector pipeline diagnostics (Phase 10 queue-pressure investigation).

Measures, per reporting interval, where an OPC UA DataChange spends time between
arrival in the client and durable acceptance, plus what can stall the event loop:

    arrival -> subscription queue -> dequeue -> spool accept -> telemetry record
    event-loop lag · history batch commit · window coordinator cycle

Nothing here changes acquisition behaviour; it is only enabled with an explicit
metrics path and writes one JSON line per interval.

Scope: a Phase 10 diagnostic, not production observability. One instance is shared
by the whole collection service, so with several sources the counts are totals, the
high-watermark is the largest of all queues and per-source latencies are mixed;
production metrics would need source_id / component / session-epoch dimensions.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections import defaultdict
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path


def _summary(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
    return {
        "n": len(ordered),
        "max_ms": round(ordered[-1] * 1000, 2),
        "p95_ms": round(p95 * 1000, 2),
    }


class PipelineMetrics:
    """Interval counters and latency samples; one instance per collector process."""

    def __init__(self) -> None:
        self._counts: defaultdict[str, int] = defaultdict(int)
        self._samples: defaultdict[str, list[float]] = defaultdict(list)
        self._queue_high_watermark = 0
        self._queue_depth = 0
        self._queue_maxsize: int | None = None

    def count(self, name: str, amount: int = 1) -> None:
        self._counts[name] += amount

    def observe(self, name: str, seconds: float) -> None:
        self._samples[name].append(seconds)

    def queue_depth(self, depth: int, maxsize: int | None = None) -> None:
        self._queue_depth = depth
        self._queue_high_watermark = max(self._queue_high_watermark, depth)
        if maxsize is not None:
            self._queue_maxsize = maxsize

    def take(self) -> dict[str, object]:
        """Return this interval's metrics and start a new interval."""
        report: dict[str, object] = {
            "at": datetime.now(UTC).isoformat(timespec="milliseconds"),
            # Several collector processes may append to one file across restarts.
            "pid": os.getpid(),
            "counts": dict(sorted(self._counts.items())),
            "queue": {
                "depth": self._queue_depth,
                "high_watermark": self._queue_high_watermark,
                "maxsize": self._queue_maxsize,
            },
            "latency": {name: _summary(values) for name, values in sorted(self._samples.items())},
        }
        self._counts.clear()
        self._samples.clear()
        self._queue_high_watermark = self._queue_depth
        return report


async def run_pipeline_metrics_reporter(
    metrics: PipelineMetrics,
    path: Path,
    *,
    stop_event: asyncio.Event,
    interval_seconds: float = 10.0,
    loop_probe_seconds: float = 0.1,
) -> None:
    """Probe event-loop lag continuously and append one JSON line per interval."""
    path.parent.mkdir(parents=True, exist_ok=True)
    next_report = time.monotonic() + interval_seconds
    while not stop_event.is_set():
        started = time.monotonic()
        with suppress(TimeoutError):
            await asyncio.wait_for(stop_event.wait(), timeout=loop_probe_seconds)
        # Time beyond the requested sleep is time the loop could not run anything.
        metrics.observe("event_loop_lag", max(0.0, time.monotonic() - started - loop_probe_seconds))
        if time.monotonic() >= next_report:
            line = json.dumps(metrics.take(), sort_keys=True)
            # Off the event loop: the diagnostic must not stall what it measures.
            write_started = time.monotonic()
            await asyncio.to_thread(_append_line, path, line)
            metrics.observe("metrics_write", time.monotonic() - write_started)
            next_report += interval_seconds
    # Final partial interval on a graceful stop (the service stops sources first), so
    # per-process totals are complete; a killed process has no final record.
    report = metrics.take()
    report["final"] = True
    await asyncio.to_thread(_append_line, path, json.dumps(report, sort_keys=True))


def _append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line + "\n")
