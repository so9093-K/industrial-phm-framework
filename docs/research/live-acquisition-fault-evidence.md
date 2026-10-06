# Live acquisition queue-pressure and fault/recovery evidence

Measured: 2026-10-01

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
- One observed overflow coincided with host sleep; the controlled reproduction above demonstrates the
  same burst/overflow/wedge mechanism independently of host sleep.

## Repeatable fault gate result (N = 3)

`uv run --no-sync python -m tools.opcua.fault_harness --root artifacts/harness-n3b --repeat 3 --browser`
produced **`"gate": "full"`, verdict PASS, all 13 checks**. Six scenarios × 3 plus missing phase and four
Operations states = 23 injected faults; 17 minutes of wall clock (a consequence, not a criterion).

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

The gate protects a previously observed loss mode: requesting the next notification before persisting the
current one allowed an already-dequeued notification to be dropped when the worker ended (`dequeued 10 /
accepted 5` under forced overflow). The current worker persists before requesting the next notification and
persists an already-dequeued one at shutdown.

## Observation-first Monitor browser gate after the redesign (#424, 2026-10-06)

The N = 3 result above checked the pre-redesign Monitor (System data flow). After #417–#423 the gate checks
the observation-first Monitor and also captures **normal receiving** and **missing phase**, which have no
expected attention. A render fails if any notebook-output element extends past the 1440 px viewport.

`uv run --no-sync python -m tools.opcua.fault_harness --root artifacts/harness-424c --repeat 3 --browser`
(boiler device 2297 reference archive, Chromium 1440×1100) produced **`"gate": "full"`, verdict PASS, all
15 checks**: 23 injected faults, all recovered; audit duplicate 0, value/quality mismatch 0, 0 missing
outside a fault boundary; 32 windows, 32 analyzed, 0 skipped; review request reached an OPEN Maintenance item.

| Surface | State | Readable after opening | Overflow |
| --- | --- | --- | --- |
| Monitor | normal / missing phase | 2.65 s / 2.16 s | 0 |
| Monitor | source stale / unreachable / collector down / analysis stale | 2.18 / 2.18 / 2.15 / 2.18 s (with the state's attention) | 0 |
| Assets → Signals | receiving / paused / disconnected / recovered | 3.17 / 3.18 / 3.21 / ~3.2 s | 0 |

The first reference run of the updated gate did not finish. Reviewing its screenshots found defects that the
presence-only gate had passed:

- the Monitor was wider than the viewport at every state: observation values, header facts and the
  attention rail were cut off (marimo stacks keep `min-width: auto`);
- the observation board sorted raw names, so unresolved channels filled the first view and the omitted
  `T상전류` sat in the collapsed list;
- Korean channel names in charts rendered as empty boxes (matplotlib's default font has no Hangul);
- an OPC UA worker that ended on an error showed "Stopped", which reads as an operator stop;
- the harness itself: the review step used an environment variable removed in #371, attention was
  matched on a hidden `<option>`, and the missing-phase check required the omitted channel's last value to
  equal the pre-omission snapshot, which fails when a value lands between the snapshot and the restart.

Remaining after the fixes, recorded rather than claimed solved:

- **Missing phase is not a Monitor attention, by design.** The first view shows R/S/T current, but the omitted
  phase keeps its pre-omission value (e.g. `627 A`, 1.6 min old) next to R/S at `0 A` (1.5 min old). OPC UA
  DataChange sends no event for unchanged values, so stored history cannot tell "unchanged" from "not
  arriving". Window evidence does not settle it either: in the same run, 10 of 32 finalized windows had no
  event for **all three** phase currents during normal stopped periods (0 A held), and only the injected
  omission window lacked T alone. Raising "missing phase" from window absence would alarm during normal
  stops or infer from a coincidence, so the Monitor shows value and last-change age only. Distinguishing
  the two would need source-side evidence, such as a subscription that notifies on source-timestamp change.
- Trend charts are a white panel inside the dark surface. Values remain readable.

## Dedicated Monitor full reference gate (2026-10-06)

The dedicated JS/CSS Monitor and view-action corrections were exercised with the same boiler 2297
archive/profile using the full fault protocol, not a duration-based stability run:

```bash
uv run --locked --extra operations --extra aihub python -m tools.opcua.fault_harness \
  --root artifacts/monitor-p0/full-gate --repeat 3 --browser \
  --port 4860 --ui-port 27202
```

`harness-verdict.json` reports `gate=full`, PASS, all 15 checks. The six recurring fault types
were injected three times each; including UI-specific faults, 23 injections recovered without a
permanent wedge. Exact audit found no duplicate keys, unknown events or value/quality mismatches.
Missing deliveries were contained within the declared loss boundaries; this is not a zero-loss claim.
There were 32 finalized windows and 32 analyses, with no duplicate or uncovered window. The review
request reached OPEN Maintenance after the last fault.

| Surface | State | Readable after opening | Overflow |
| --- | --- | ---: | ---: |
| Monitor | normal | 2.15 s | 0 |
| Monitor | missing phase | 1.62 s | 0 |
| Monitor | source stale / unreachable | 1.67 / 1.61 s | 0 |
| Monitor | collector down / analysis stale | 1.61 / 1.65 s | 0 |
| Assets → Signals | receiving / paused | 2.65 / 2.70 s | 0 |
| Assets → Signals | disconnected / recovered | 2.65 / 2.66 s | 0 |

Chromium used a 1440×1100 viewport. The saved `ui-*.png` artifacts show the actual dedicated Monitor,
with source receipt and its assessment time separated from per-channel recorded event timestamps.
In the omission state, R/S held 0 A while T retained 631.25 A at an earlier timestamp; there was no
invented missing-phase attention or equipment diagnosis. The DataChange ambiguity described above
still applies. This recorded replay is not field-endpoint or equipment-diagnosis validation.

Separate 1440px/1024px synthetic fixture checks covered unobserved registered selection/comparison,
two origins sharing a channel name, date-bearing 24h/7d axes, bucket/observed intervals and min/max,
and keyboard focus return. Frontend error/rejection injection verified pending release and Refresh
retry. These checks do not replace visual review, which still identified readability work; unrelated
pages and narrower/mobile layouts are not certified by this reference.

## Growth with accumulated state

A fault-free run of the same stack (50 minutes, sampled every 60 s) showed queue high watermark (≤ 53 of
4096), arrival → dequeue p95 (about 80 ms), spool backlog (not accumulating) and storage rate (about
2.6 MB/min, linear) stable, but process memory still rising: runner about +25 MB/h, collector about
+15 MB/h after warm-up. Elapsed time is not what drives this; accumulated state is. Growth is therefore
judged by scale tests that preload state of a known size N and measure the cost and memory of one more
operation, not by running longer.

**Runner: the analysis result store.** `JsonPhaseUnbalanceRepository` reads and rewrites the whole
`phase-unbalance.json` for every window: O(results) per window, about 16 KB per result (103 results =
1.6 MB after 50 minutes; about 46 MB/day at 30 s windows). On CPython 3.14.7, reading a non-ASCII text
file with `open(..., encoding="utf-8").read()` / `Path.read_text` also leaves process memory proportional
to the file size (a 1.6 MB file: 3 MB per read, levelling off near 196 MB; 33 MB on 3.13.12; none with
`read_bytes().decode()`; the Python heap itself does not grow). The structural issue is the whole-file
rewrite, the same pattern already removed from finalized windows. `SqlitePhaseUnbalanceRepository` avoids the whole-file rewrite (one row per run): with a fixed N of stored results, one more record costs 3 / 24 / 96 ms and 0.47 / 2.15 /
7.70 MB peak at N = 10 / 100 / 400 in the JSON store, and 0.8 ms and 0.012 MB at N = 10 / 2,000 / 10,000 in
the SQLite store (`test_recording_one_window_result_does_not_scale_with_stored_results`).

**Collector.** The cause of the remaining growth is not yet identified; the candidates are per-commit
costs that grow with DuckLake data files (about 106 small files per minute) and window payloads.

**Storage.** `windows.sqlite` reached 88 MB and DuckLake 5,026 data files (39 MB) in 50 minutes. Volume is
linear, but file count and window payload retention require a separate storage lifecycle policy.
