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

`uv run --no-sync python -m tools.opcua.fault_harness --root artifacts/harness-n3 --repeat 3` on the
branch that adds the harness: **verdict PASS, all 11 checks**. Six scenarios × 3 plus missing phase and
four Operations states = 23 injected faults; 14 minutes of wall clock (a consequence, not a criterion).

| Check | Result |
| --- | --- |
| audit | 12,358 expected deliveries; duplicate 0, value mismatch 0 (null included), quality mismatch 0, unknown 0 |
| missing within loss boundary | 3,606 missing, **0 outside** an injected fault's boundary |
| already-dequeued loss | 7 gracefully stopped collectors: handed to worker = spool accepts (8,931); 4 SIGKILLed excluded (crash boundary) |
| windows | 26 finalized windows, none repeated or overlapping |
| analysis | 26 analyzed, 0 skipped, 1 policy, no duplicate, no window left behind |
| wedge | 23/23 faults recovered; data resumed 0–6 s after a stall/kill ended, ≤16 s after replay restarts |
| forced overflow | 76 rejected notifications per injection; explicit worker end and restart, no wedge |
| spool backlog | peak 245–617 pending while the catalog lease was held, drained each time |
| missing phase | current series reported unresolved for the omitted-phase windows |
| Operations states | source stale `delayed/running/No new data`; unreachable `error/error/Collection needs attention`; collector down `unavailable/error/heartbeat 25s old/Collection service is not running`; analysis stale `running/running/delayed/Analysis service is not updating` — all distinct |

The first harness runs found a real loss before this result: the worker requested the next notification
before persisting the current one, so a notification dequeued during that wait was dropped when the worker
ended (`dequeued 10 / accepted 5` under forced overflow). The worker now persists before requesting the
next notification and persists an already-dequeued one at shutdown; the gate above verifies it.
