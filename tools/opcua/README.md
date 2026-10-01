# Local live measurement demo

This explicit development tool exposes synthetic numeric `active_power` and `voltage` channels.
It does not reproduce AI-Hub recordings, establish their units, or diagnose equipment. FILE and OPC UA
use the same explicitly assigned demo asset/channel IDs to exercise history continuity. Nothing is
started on package import. The server binds only to `127.0.0.1` and is unauthenticated for local testing.

## Prepare and run

```bash
uv sync --locked --extra history --extra opcua --group research
uv run --no-sync python -m tools.opcua.demo prepare
uv run --no-sync python -m tools.opcua.demo server
```

`prepare` requires an empty `artifacts/live-demo` directory, seeds 30 minutes of synthetic FILE history,
registers the live source as ACTIVE, and leaves collection STOPPED. Do not run prepare again to restart;
reuse the existing state. `--root` and `--endpoint` select a different isolated scenario.

In a second terminal, start the independent collector:

```bash
uv run --no-sync industrial-phm operations run-collection-service \
  --registry artifacts/live-demo/sources.json \
  --control-state artifacts/live-demo/control.sqlite \
  --spool-state artifacts/live-demo/spool.sqlite \
  --telemetry-state artifacts/live-demo/telemetry.sqlite \
  --window-state artifacts/live-demo/windows.sqlite \
  --ducklake-catalog artifacts/live-demo/catalog.sqlite \
  --ducklake-data artifacts/live-demo/data
```

In a third terminal, open Operations with the same state paths:

```bash
export INDUSTRIAL_PHM_OPERATIONS_SOURCE_REGISTRY=artifacts/live-demo/sources.json
export INDUSTRIAL_PHM_OPERATIONS_SOURCE_RUNTIME=artifacts/live-demo/source-runtime.json
export INDUSTRIAL_PHM_OPERATIONS_COLLECTION_CONTROL=artifacts/live-demo/control.sqlite
export INDUSTRIAL_PHM_OPERATIONS_ACQUISITION_SPOOL=artifacts/live-demo/spool.sqlite
export INDUSTRIAL_PHM_OPERATIONS_ACQUISITION_TELEMETRY=artifacts/live-demo/telemetry.sqlite
export INDUSTRIAL_PHM_OPERATIONS_WINDOW_STATE=artifacts/live-demo/windows.sqlite
export INDUSTRIAL_PHM_OPERATIONS_ANALYSIS_LEDGER=artifacts/live-demo/window-analysis-ledger.sqlite
export INDUSTRIAL_PHM_HISTORY_CATALOG=artifacts/live-demo/catalog.sqlite
export INDUSTRIAL_PHM_HISTORY_DATA=artifacts/live-demo/data
uv run --no-sync marimo run apps/operations_v2.py
```

1. Setup → Data Sources: select `demo-opcua`, then **Start collection**. This records the desired
   state; the separately running collector does the collection.
2. Monitor: the Data Flow row shows Sources/Collect/Store/Analyze separately. Use **Refresh** to
   re-read runtime state.
3. Assets: select `demo-power-01` and open **Signals** to query recent history and latest values.
4. Close the browser, reopen it, and verify that the collector continued writing.
5. Stop/restart the server and collector separately; refresh Monitor and Signals to check recovery.
6. Setup **Stop collection** stops source acquisition. The collector process can remain available.
   Stop the simulator and collector terminals with Ctrl-C when finished.

The catalog adapter coordinates cooperating local connections through `<catalog>.phm.lock` for the
whole connection/transaction lifetime. Contention waits up to 10 seconds, then fails explicitly.
Keep the lock file in place while any process is active. This is local filesystem coordination, not
distributed locking, high-throughput concurrent writers, or collector leader election. Run one collector
for a given control/spool configuration. Source disconnect telemetry and uncommitted spool backlog
must not be read as machine failure.

Live and FILE backfill history stays inlined in the SQLite catalog until flushed. After a long run,
move it to Parquet with the same catalog/data paths (it waits for the shared catalog lease):

```bash
uv run --no-sync industrial-phm operations flush-history \
  --ducklake-catalog artifacts/live-demo/catalog.sqlite \
  --ducklake-data artifacts/live-demo/data
```

## Three-phase live analysis profile

The `three-phase` profile registers `demo-3phase-opcua` for asset `demo-motor-01` with site-style
channel names (`Voltage_L1..3`, `Current_L1..3`) and explicit synthetic semantic bindings (phase
voltage/current, phase R/S/T, V/A). Analysis selects these channels by bound meaning, not by name.
Values are synthetic; they do not describe a physical motor.

```bash
uv run --no-sync python -m tools.opcua.demo --root artifacts/live-3phase --profile three-phase \
  --endpoint opc.tcp://127.0.0.1:4842/phm-demo/ prepare
uv run --no-sync python -m tools.opcua.demo --profile three-phase \
  --endpoint opc.tcp://127.0.0.1:4842/phm-demo/ server
```

Run the collector with the `artifacts/live-3phase` paths as above (optionally
`--window-duration-seconds 10 --allowed-lateness-seconds 2` for faster windows), start collection for
`demo-3phase-opcua`, and run the window analysis runner as its own process:

```bash
uv run --no-sync industrial-phm operations run-window-analysis \
  --window-state artifacts/live-3phase/windows.sqlite \
  --analysis-state artifacts/live-3phase/phase-unbalance.json \
  --ledger-state artifacts/live-3phase/window-analysis-ledger.sqlite
```

Runner는 기본적으로 analysis result 옆
`artifacts/live-3phase/phase-unbalance-runtime.json`에 자신의 heartbeat, 최근 cycle,
최근 analysis/skip/failure와 누적 처리 수를 기록합니다. 경로를 분리하려면
`--runtime-status <path>`를 사용합니다. 이 telemetry는 Operations가 runner를 시작·중지하기 위한
control state가 아니라, 독립 process가 실제로 갱신되고 있는지 관측하기 위한 evidence입니다.

Operations V2 Monitor로 이 상태까지 함께 보려면 동일한 source/acquisition 환경변수에 다음을 추가해
실행합니다.

```bash
export INDUSTRIAL_PHM_OPERATIONS_PHASE_UNBALANCE_STATE=artifacts/live-3phase/phase-unbalance.json
export INDUSTRIAL_PHM_OPERATIONS_WINDOW_STATE=artifacts/live-3phase/windows.sqlite
export INDUSTRIAL_PHM_OPERATIONS_ANALYSIS_LEDGER=artifacts/live-3phase/window-analysis-ledger.sqlite
uv run --no-sync marimo run apps/operations_v2.py
```

The collection service reads newly durable history through a bounded ingestion cursor and stores
finalized windows plus restart checkpoint state in the SQLite WAL window store. It does not rebuild
the source's full history on every coordinator cycle.

Each pending finalized window is analyzed from its accepted events (ADR-0008). The runner consumes
only windows after its capability/algorithm/policy cursor. The same
window/capability/algorithm/policy result is persisted once across runner restarts. Windows without all
three phases bound are recorded as skipped with a reason in the SQLite analysis ledger.

Operations must use the **same analysis result repository** as the runner (above). Results the runner
writes later appear after **Refresh**; no restart is needed. The result file is shared evidence storage; this does not make the Operations browser process own the
analysis runner lifecycle.

Alignment is strict by default (all phases at one source timestamp). OPC UA DataChange reports only
changed values, so a stable phase may be missing at most timestamps. When the device's update period
justifies it, the runner can carry a phase's latest earlier value within a stated age (ADR-0009):

```bash
uv run --no-sync industrial-phm operations run-window-analysis ... \
  --alignment bounded-previous --max-carry-age-seconds 2 \
  --alignment-basis "simulator writes every phase each second"
```

The carry age is a measurement-validity fact, not a transport timeout; the evidence records the policy,
its basis and the carried value count and ages.

## AI-Hub 239 recorded power replay

`tools/opcua/aihub_replay.py` publishes one explicit AI-Hub 239 selection as a local OPC UA server so
the whole Operations flow runs on recorded plant values instead of synthetic ones. It stands in for a
site server during local validation; it is not a production connector.

- Values are published unchanged, one write per recorded timestamp for every channel. A timestamp
  that recorded two different values for one channel publishes that value with Bad status.
- Time is rebased onto the replay clock (`--speed` recorded seconds per replay second, default 60), because
  a live collector judges lateness and freshness against wall time. `replay-log.jsonl` records each
  cycle's rule back to recorded source time; `replay.json` records the archive digest, member, binding,
  selected range and channels.
- OPC UA DataChange reports changed values only, as on site, so unchanged recorded values raise no
  notification and a phase can be absent at many timestamps.
- Measurement meaning is bound only for channels the AI-Hub 239 semantics-v2 dictionary resolves
  (phase voltages/currents, their means, line voltage mean, frequency); power, power factor, energy,
  harmonics and temperature stay unresolved.

The selection below (device 2297, 2020-11-14 06:00-12:30 local) contains a stopped period, a start at
08:11, a 3.7-hour run and a stop at 11:51. The raw archive is local only (see `tools/aihub/README.md`).

```bash
uv sync --locked --extra history --extra opcua --extra aihub --group research
uv run --no-sync python -m tools.opcua.aihub_replay prepare --root artifacts/phase10 \
  --endpoint opc.tcp://127.0.0.1:4850/aihub-replay/ \
  --archive data/raw/aihub/239/archives/training/raw/5.보일러.zip \
  --member "5.보일러/SourceData_211.json" \
  --binding tools/opcua/presets/aihub-boiler-2297-replay.json \
  --start 2020-11-14T06:00:00 --end 2020-11-14T12:30:00
uv run --no-sync python -m tools.opcua.aihub_replay server --root artifacts/phase10 --speed 60 --loop
```

Run the collector with the `artifacts/phase10` paths as in the synthetic demo, using
`--window-duration-seconds 30 --allowed-lateness-seconds 2` (30 recorded minutes per window at 60x),
and the analysis runner with a carry policy whose basis is the replay's publishing contract:

```bash
uv run --no-sync industrial-phm operations run-window-analysis \
  --window-state artifacts/phase10/windows.sqlite \
  --analysis-state artifacts/phase10/phase-unbalance.json \
  --ledger-state artifacts/phase10/window-analysis-ledger.sqlite \
  --alignment bounded-previous --max-carry-age-seconds 5 \
  --alignment-basis "AI-Hub 239 replay: every channel is written once per recorded minute (1 s at 60x); unchanged values raise no DataChange; carry bounded to 5 recorded minutes"
```

Point every `INDUSTRIAL_PHM_OPERATIONS_*` state path and `INDUSTRIAL_PHM_HISTORY_CATALOG/DATA` at
`artifacts/phase10`. In particular, set
`INDUSTRIAL_PHM_OPERATIONS_WINDOW_STATE=artifacts/phase10/windows.sqlite` and
`INDUSTRIAL_PHM_OPERATIONS_ANALYSIS_LEDGER=artifacts/phase10/window-analysis-ledger.sqlite`
so Assets can resolve skipped analysis attempts back to exact finalized-window evidence. Then start
Operations and use Setup → **Start collection**.

Fault scenarios for Operations validation:

- `--omit-channel T상전류` (repeatable) never publishes a channel: a missing phase.
- `--freeze-after-records N` keeps the server connected but stops updating after N records: stale data.
- Stopping the replay server, the collector or the analysis runner separately exercises source,
  collection and analysis outages.

## Repeatable fault gate (Phase 10)

`tools/opcua/fault_harness.py` runs the replay, the collection service and the analysis runner as
separate processes, injects every scenario `--repeat` times and judges the run by machine. Exit code 0
only when every check passes; the verdict is written to `<root>/harness-verdict.json`.

```bash
uv run --no-sync python -m tools.opcua.fault_harness --root artifacts/harness-n3 --repeat 3
```

Scenarios: collector stall (SIGSTOP), source stall, collector kill/restart (SIGKILL), analysis runner
kill/restart, forced queue overflow (queue 16 < one subscription's 35 initial values), spool backlog
(holding the DuckLake catalog lease), then missing phase and the four Operations states (source stale,
source unreachable, collector down, analysis stale).

| Check | Pass condition |
| --- | --- |
| `audit_exact` | duplicate, value (null included), quality and unknown events = 0 |
| `missing_within_loss_boundary` | every missing delivery is inside an injected fault's documented boundary (ADR-0010) |
| `already_dequeued_loss_zero` | per gracefully stopped collector: notifications handed to the worker = spool accepts |
| `windows_no_rollback` | finalized windows neither repeat nor overlap |
| `analysis_once_and_complete` | one outcome per window/capability/algorithm/policy, none left behind |
| `no_permanent_wedge` | every fault recovered within `--recovery-timeout` |
| `metrics_present_around_faults` | pipeline metrics records exist around every fault |
| `forced_overflow_happened`, `spool_backlog_drained`, `missing_phase_explained` | the fault really happened and was handled |
| `ui_states_distinct` | the Operations Monitor read model shows the four states as expected and distinct |

Run time follows from the scenarios and `--repeat`; it is not a pass criterion.

## Queue-pressure and fault reproduction

Short, repeatable experiments replace waiting for failures in a long soak:

- Start the replay with `--publish-ledger <root>/publish-ledger.jsonl`. Each line records a server run, the
  replay time and the channel values actually written; it is the ground truth for loss audits.
- Start the collector with `--pipeline-metrics <root>/pipeline-metrics.jsonl` (opt-in). Every 10 s it writes
  arrivals, dequeues, rejected notifications, queue depth/high-watermark, arrival→dequeue lag, spool accept,
  event-loop-blocking telemetry writes, event-loop lag, history commit and window cycle latencies.
- Inject a fault by pausing the real python process (not the `uv run` wrapper) with `kill -STOP` /
  `kill -CONT`: the replay process for a source stall, the collector process for a client stall.
- Audit stored history against the ledger:

```bash
uv run --no-sync python -m tools.opcua.replay_audit --root artifacts/phase10b \
  --ledger artifacts/phase10b/publish-ledger.jsonl --source-id aihub239-replay-boiler-2297
```

The audit expects one delivery per changed write within a server run and reports missing gaps,
duplicate keys, exact value mismatches (null included), Good/Bad quality mismatches, unknown events and
re-delivered current values (subscription start). A recorded null is published as a Null variant with Bad
status. One audit accepts one publish per (channel, timestamp); a key written by two server runs fails fast.
Measured results are recorded in `docs/research/phase10-acquisition-stress.md`.

## Regression validation

```bash
uv run --locked --extra history --extra opcua pytest tests/contract/test_live_measurement_stack.py
```

This uses a real loopback asyncua server and separate collector process with synthetic inputs. It
checks concurrent history reads, source restart/reconnect, collector restart with durable epochs,
Stop Collection, FILE/live separation, latest-point budgets and unique delivery identities. It needs
no external server, credentials or AI-Hub payload. On failure, pytest's temporary stack `process.log`
contains the subprocess output.
