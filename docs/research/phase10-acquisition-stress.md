# Phase 10 acquisition queue-pressure, fault reproduction and fault gate (2026-10-01)

Local AI-Hub 239 replay (device 2297, 35 channels, 60x: one record per second) → instrumented collector
(`--pipeline-metrics`) → DuckLake. Faults were injected with SIGSTOP/SIGCONT and loss was audited against the
replay publish ledger (`tools/opcua/replay_audit.py`). macOS idle sleep was blocked with `caffeinate`.

## Normal load

| Phase of the recording | Arrivals | Queue high-watermark | Arrival→dequeue p95 / max | Spool accept max | Event-loop lag max |
| --- | --- | --- | --- | --- | --- |
| stopped plant (~10 ev/s) | 93–118 / 10 s | 13–14 | 28–62 / 74 ms | 3–17 ms | 7–84 ms (startup) |
| running plant (~30 ev/s) | 247–321 / 10 s | 30–33 (one record = one burst) | 66–88 / 94–122 ms | 4–25 ms | 8–16 ms |

History batch commit ≈ 170–250 ms and window cycle ≈ 90–280 ms run in threads. The telemetry write per
event runs on the event loop (p95 ≈ 2 ms, max ≈ 30 ms). No overflow occurred under normal load; the queue
(4096) has about 100x headroom over the normal per-publish burst.

## Fault results

| Experiment | Before (asyncua in-client reconnect, queue 128) | After (ADR-0010, queue 4096) |
| --- | --- | --- |
| source stall 30 s | burst 1,173 → 1,019 rejected, `notify_transport_lost` storm, client **permanently disconnected** while evidence said CONNECTED | session lost → worker restart with backoff; loss = stall + backoff (491 events), no wedge |
| source stall 30 s (in-client path, queue 4096) | — | burst 1,007, max depth 914, drained in 2.2 s (~460 ev/s), 0 rejected |
| source stall 180 s | session re-activated, data for old subscription **discarded indefinitely** | worker restarts until the source returns; recovered ~30 s after resume |
| collector stall 20 s (x3) | not run | **0 missing**, 0 duplicates (same session; server queued notifications) |
| collector stall 20 s, writer reading backlog | spool stats from two autocommit reads → invariant error **stopped the collection service** | single read transaction; regression test fails 4/5 on old code, passes 10/10 |

Across all experiments the audit found 0 duplicate keys, 0 value mismatches (exact, null included), 0 Good/Bad
quality mismatches and 0 unknown events, and no (channel, timestamp) key was published by two replay runs.

## Not claimed

- No loss during a source or connection outage: data during the outage and the restart backoff is lost.
- The 2026-09-30 overflow coincided with a MacBook clamshell sleep (pmset 19:58:09–20:00:30 KST); the
  reproduction above shows the same burst/overflow/wedge mechanism without sleep.

## Repeatable fault gate result (N = 3)

`uv run --no-sync python -m tools.opcua.fault_harness --root artifacts/harness-n3b --repeat 3 --browser`
on the branch that adds the harness: **`"gate": "full"`, verdict PASS, all 13 checks**. Six scenarios × 3
plus missing phase and four Operations states = 23 injected faults; 17 minutes of wall clock (a
consequence, not a criterion). An earlier run with looser oracles (11 checks, no browser) also passed; the
numbers below are from the stricter run.

| Check | Result |
| --- | --- |
| audit | 16,334 expected deliveries; duplicate 0, value mismatch 0 (null included), quality mismatch 0, unknown 0 |
| missing within loss boundary | 4,047 missing, **0 outside** an injected fault's boundary |
| already-dequeued loss | 7 gracefully stopped collectors: handed to worker = spool accepts (4,228); 4 SIGKILLed collectors judged by the audit boundary instead (process-memory crash boundary, ADR-0010) |
| windows | 32 finalized windows, none repeated or overlapping |
| analysis | 32 analyzed, 0 skipped, 1 policy, no duplicate, no window left behind |
| wedge | 23/23 faults recovered; data resumed 0–6 s after a stall/kill ended, ≤16 s after replay restarts |
| metrics | a record within 15 s before every fault and within 15 s after every recovery (98 records) |
| forced overflow | 76 rejected notifications per injection; explicit worker end and restart, no wedge |
| spool backlog | baseline → peak → after drain: 31 → 551 → 0, 12 → 233 → 10, 24 → 603 → 27 |
| missing phase | both windows inside the omission record `T상전류` missing; current unresolved, voltage resolved; Investigation note "Not evaluated: no complete R/S/T channel set…" and provenance `missing_channels = T상전류`; no skip |
| Operations states | source stale `delayed/running/No new data`; unreachable `error/error/Collection needs attention`; collector down `unavailable/error/heartbeat … old/Collection service is not running`; analysis stale `running/running/delayed/Analysis service is not updating` — all distinct |
| review workflow | after the last fault, the newest phase-unbalance result went from a not-requested Investigation group → review request → OPEN group and OPEN Maintenance item |
| browser (Chromium) | Monitor data flow and the state's attention item visible 1.65 s (source stale), 1.08 s (unreachable), 1.10 s (collector down), 1.09 s (analysis stale) after opening |

The first harness runs found a real loss before this result: the worker requested the next notification
before persisting the current one, so a notification dequeued during that wait was dropped when the worker
ended (`dequeued 10 / accepted 5` under forced overflow). The worker now persists before requesting the
next notification and persists an already-dequeued one at shutdown; the gate above verifies it.

## Bounded steady-state run (fault-free)

`--steady-minutes 90` on the same stack, sampled every 60 s. The first attempt stopped at minute 50 on a
harness bug (an SQLite `-shm` file vanished between listing and `stat`); the harness now tolerates that and
appends every sample to `<root>-steady-series.jsonl`. Its 50 samples:

| Item | First half | Second half | Reading |
| --- | --- | --- | --- |
| collector RSS slope | +92 MB/h (315 → 355 MB warm-up) | +15 MB/h | still rising after warm-up: **trend**, measure longer |
| runner RSS slope | +19 MB/h | +25 MB/h | rising throughout: **trend**, cause below |
| queue high watermark | ≤ 53 | ≤ 35 | stationary (queue 4096) |
| arrival → dequeue p95 (median) | 85 ms | 80 ms | stationary |
| spool backlog | ≤ 32 | 0 at the end | not accumulating |
| storage growth | 2.63 MB/min | 2.58 MB/min | linear, not accelerating |

A ratio of worst values hid both RSS trends, so the steady check now judges memory by the least-squares
slope of the second half (≤ 10 MB/h) and also tracks history commit and window cycle p95.

**Runner memory follows the analysis result store.** `JsonPhaseUnbalanceRepository` reads and rewrites the
whole `phase-unbalance.json` for every window (O(results) per window; 103 results = 1.6 MB after 50 min,
about 16 KB per result, about 46 MB/day at 30 s windows). On CPython 3.14.7, reading a non-ASCII text file
with `open(..., encoding="utf-8").read()` / `Path.read_text` leaves process memory proportional to the file
size (a 1.6 MB file: 3 MB per read until it levels off near 196 MB; 33 MB on 3.13.12; none with
`read_bytes().decode()`). The Python heap itself does not grow (tracemalloc: 22 KB), so this is allocator
retention, and the store's unbounded growth makes it a trend. The structural issue is the whole-file
rewrite, the same pattern already removed from finalized windows.

**Storage.** `windows.sqlite` grew to 88 MB and DuckLake to 5,026 data files (39 MB) in 50 minutes, about
106 small files per minute. Volume is linear, but file count and window payload retention belong to the
storage lifecycle work (#317).

