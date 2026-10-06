# Local live measurement demo

정상 product demo는 repository root의 canonical front door를 사용합니다.

```bash
make demo
```

이 target은 packaged synthetic demo에 위임하며 전용 `artifacts/demo-synthetic` workspace에 synthetic 3상 OPC UA source를 등록하고
simulator + collection + analysis + Operations UI lifecycle을 한 foreground command로 실행합니다.
아래 `tools.opcua.demo` 절차는 개별 process/failure boundary를 직접 다루는 개발·진단용 경로입니다.

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
uv run --no-sync industrial-phm internal collection-service \
  --workspace artifacts/live-demo
```

In a third terminal, open Operations with the same state paths:

```bash
export INDUSTRIAL_PHM_OPERATIONS_WORKSPACE=artifacts/live-demo
uv run --no-sync marimo run src/industrial_phm/apps/operations.py
```

1. Setup → Data Sources: select `demo-opcua`, then **Start collection**. This records the desired
   state; the separately running collector does the collection.
2. Monitor: inspect the selected asset, source activity and stored event-time signals. Use
   **Refresh** to re-read runtime state; collection/storage/analysis diagnostics remain in System.
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
uv run --no-sync industrial-phm maintenance history flush \
  --ducklake-catalog artifacts/live-demo/catalog.sqlite \
  --ducklake-data artifacts/live-demo/data
```


Small-file compaction is a separate, explicit maintenance operation. It merges active Parquet files
without expiring snapshots or deleting physical files. Each table is compacted in a separate provider
call so the catalog lease is released between tables. `--max-compacted-files` is DuckLake's per-table
output-operation limit, not an input-file count bound; no automatic schedule or retention threshold is implied.

```bash
uv run --no-sync industrial-phm maintenance history compact \
  --ducklake-catalog artifacts/live-demo/catalog.sqlite \
  --ducklake-data artifacts/live-demo/data \
  --max-compacted-files 32 \
  --target-file-size-bytes 1048576 \
  --max-file-size-bytes 262144
```

`flush` means catalog-inline rows → Parquet. `compact` means active small Parquet → fewer active
Parquet files. Snapshot expiration, old-file cleanup, catalog VACUUM and CHECKPOINT are deliberately
outside this command and require a separate storage-lifecycle policy.

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
uv run --no-sync industrial-phm internal window-analysis \
  --workspace artifacts/live-3phase
```

Runner는 기본적으로 analysis result 옆
`artifacts/live-3phase/phase-unbalance-runtime.json`에 자신의 heartbeat, 최근 cycle,
최근 analysis/skip/failure와 누적 처리 수를 기록합니다. 경로를 분리하려면
`--runtime-status <path>`를 사용합니다. 이 telemetry는 Operations가 runner를 시작·중지하기 위한
control state가 아니라, 독립 process가 실제로 갱신되고 있는지 관측하기 위한 evidence입니다.

Operations Monitor로 이 상태까지 함께 보려면 동일한 source/acquisition 환경변수에 다음을 추가해
실행합니다.

```bash
export INDUSTRIAL_PHM_OPERATIONS_WORKSPACE=artifacts/live-3phase
uv run --no-sync marimo run src/industrial_phm/apps/operations.py
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
uv run --no-sync industrial-phm internal window-analysis ... \
  --alignment bounded-previous --max-carry-age-seconds 2 \
  --alignment-basis "simulator writes every phase each second"
```

The carry age is a measurement-validity fact, not a transport timeout; the evidence records the policy,
its basis and the carried value count and ages.

## AI-Hub 239 recorded power replay

정상 product demo는 아래 packaged preset을 우선 사용합니다.

```bash
uv sync --locked --extra operations --extra aihub
uv run --no-sync industrial-phm demo aihub-boiler
```

기본 archive 위치가 다르면 `--archive /path/to/5.보일러.zip`만 지정합니다. preset은 아래 explicit
development runbook과 같은 device/member/time range, 60× replay, 30 recorded-minute window,
5 recorded-minute bounded carry semantics를 소유합니다.

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
- Measurement meaning is bound only for channels the AI-Hub 239 semantics-v3 dictionary resolves
  (phase voltages/currents, their means, line voltage mean, frequency); power, power factor, energy,
  harmonics and temperature stay unresolved. An archive outside the semantics-v3 profiled scope is
  replayed with no bound meaning at all.

The selection below (device 2297, 2020-11-14 06:00-12:30 local) contains a stopped period, a start at
08:11, a 3.7-hour run and a stop at 11:51. The raw archive is local only (see `tools/aihub/README.md`).

```bash
uv sync --locked --extra history --extra opcua --extra aihub --group research
uv run --no-sync python -m tools.opcua.aihub_replay prepare --root artifacts/aihub-replay \
  --endpoint opc.tcp://127.0.0.1:4850/aihub-replay/ \
  --archive data/raw/aihub/239/archives/training/raw/5.보일러.zip \
  --member "5.보일러/SourceData_211.json" \
  --binding tools/opcua/presets/aihub-boiler-2297-replay.json \
  --start 2020-11-14T06:00:00 --end 2020-11-14T12:30:00
uv run --no-sync python -m tools.opcua.aihub_replay server --root artifacts/aihub-replay --speed 60 --loop
```

The air-compressor reference asset (#403) uses the same commands with its own selection; see the
[reference profile](../../docs/research/aihub-239-air-compressor-reference-profile.md) for why this
device and range were chosen:

```bash
uv run --no-sync python -m tools.opcua.aihub_replay prepare --root artifacts/aihub-replay-air-compressor \
  --endpoint opc.tcp://127.0.0.1:4850/aihub-replay/ \
  --archive data/raw/aihub/239/archives/training/raw/3.공기압축기.zip \
  --member "3.공기압축기/SourceData_16.json" \
  --binding tools/opcua/presets/aihub-air-compressor-1338-replay.json \
  --start 2020-11-16T04:00:00 --end 2020-11-16T10:00:00 \
  --asset-display-name "공기압축기 · reference asset"
```

`--asset-display-name` is an optional presentation label stored on the registered source. Operations
shows it instead of the asset ID and keeps `aihub-air-compressor-1338` underneath and in provenance.

Use the same workspace root for prepare, replay server, collector, analysis runner and Operations.
For the air-compressor example above:

```bash
export WORKSPACE=artifacts/aihub-replay-air-compressor

uv run --no-sync industrial-phm internal collection-service \
  --workspace "$WORKSPACE" \
  --window-duration-seconds 30 --allowed-lateness-seconds 2

uv run --no-sync industrial-phm internal window-analysis \
  --workspace "$WORKSPACE" \
  --alignment bounded-previous --max-carry-age-seconds 5 \
  --alignment-basis "AI-Hub 239 replay: every channel is written once per recorded minute (1 s at 60x); unchanged values raise no DataChange; carry bounded to 5 recorded minutes"

export INDUSTRIAL_PHM_OPERATIONS_WORKSPACE="$WORKSPACE"
uv run --no-sync marimo run src/industrial_phm/apps/operations.py
```

Then use Setup → **Start collection**. The workspace root projects the source/runtime/control/spool,
window/ledger, analysis and DuckLake paths consistently. The packaged Operations app resolves these
paths from that one workspace; isolated internal service commands may still take explicit path flags.

Fault scenarios for Operations validation:

- `--omit-channel T상전류` (repeatable) never publishes a channel: a missing phase.
- `--freeze-after-records N` keeps the server connected but stops updating after N records: stale data.
- Stopping the replay server, the collector or the analysis runner separately exercises source,
  collection and analysis outages.

## Repeatable live fault/recovery gate

`tools/opcua/fault_harness.py` is intentionally scoped to the bundled AI-Hub 239 boiler device 2297
replay profile and its explicit R/T phase-current identities. It is not a generic live-source fault
harness; a different source profile needs its own preset/CLI contract before reusing this gate.

`tools/opcua/fault_harness.py` runs the replay, the collection service and the analysis runner as
separate processes, injects every scenario `--repeat` times and judges the run by machine. Exit code 0
only when every check passes; the verdict is written to `<root>/harness-verdict.json`.

```bash
uv run --no-sync python -m tools.opcua.fault_harness --root artifacts/harness-n3 --repeat 3 --browser
```

Only a run with every scenario, `--repeat` of at least 3 and `--browser` is recorded as `"gate": "full"`.
A run with `--scenarios`, a smaller N or no browser check is `"gate": "diagnostic"` and does not stand in for
the full reliability gate. `--browser` starts `marimo run src/industrial_phm/apps/operations.py` against the harness root and opens
Monitor in Chromium through `uv run --no-sync --with playwright` (screenshots: `<root>/ui-*.png`).

Scenarios: collector stall (SIGSTOP), source stall, collector kill/restart (SIGKILL), analysis runner
kill/restart, forced queue overflow (queue 16 < one subscription's 35 initial values), spool backlog
(holding the DuckLake catalog lease), then missing phase, the four Operations states (source stale,
source unreachable, collector down, analysis stale) and a review request on the newest result.

| Check | Pass condition |
| --- | --- |
| `audit_exact` | duplicate, value (null included), quality and unknown events = 0 |
| `missing_within_loss_boundary` | every missing delivery is inside an injected fault's documented boundary (ADR-0010) |
| `already_dequeued_loss_zero` | per gracefully stopped collector: notifications handed to the worker = spool accepts; SIGKILLed collectors are a process-memory crash boundary and are judged by the audit boundary instead (ADR-0010) |
| `windows_no_rollback` | finalized windows neither repeat nor overlap |
| `analysis_once_and_complete` | one outcome per window/capability/algorithm/policy, none left behind |
| `no_permanent_wedge` | every fault recovered within `--recovery-timeout` |
| `metrics_present_around_faults` | a pipeline metrics record just before each fault and another just after its recovery |
| `forced_overflow_happened` | every forced overflow made asyncua reject notifications |
| `spool_backlog_drained_to_baseline` | the held lease raised the backlog above the pre-fault baseline by more than 100 and it drained back to baseline + 50 |
| `missing_phase_explained` | every window inside the omission records T상전류 missing, the result leaves only current unresolved, and the Investigation summary note and provenance `missing_channels` show that reason; no skips there |
| `ui_states_distinct` | the Operations Monitor read model shows the four states as expected and distinct |
| `review_workflow_continues` | after the faults the newest phase-unbalance result moves from a not-requested Investigation group, through a review request, to an OPEN Maintenance item |
| `browser_readable_within_5s` (`--browser`) | in Chromium each of the four states shows the data flow and its attention item within 5 s of opening |

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
uv run --no-sync python -m tools.opcua.replay_audit --root artifacts/aihub-replayb \
  --ledger artifacts/aihub-replayb/publish-ledger.jsonl --source-id aihub239-replay-boiler-2297
```

The audit expects one delivery per changed write within a server run and reports missing gaps,
duplicate keys, exact value mismatches (null included), Good/Bad quality mismatches, unknown events and
re-delivered current values (subscription start). A recorded null is published as a Null variant with Bad
status. One audit accepts one publish per (channel, timestamp); a key written by two server runs fails fast.
Measured results are recorded in `docs/research/live-acquisition-fault-evidence.md`.

## Regression validation

```bash
uv run --locked --extra history --extra opcua pytest tests/contract/test_live_measurement_stack.py
```

This uses a real loopback asyncua server and separate collector process with synthetic inputs. It
checks concurrent history reads, source restart/reconnect, collector restart with durable epochs,
Stop Collection, FILE/live separation, latest-point budgets and unique delivery identities. It needs
no external server, credentials or AI-Hub payload. On failure, pytest's temporary stack `process.log`
contains the subprocess output.


## Monitor interaction browser gate

For a running Operations UI backed by a populated workspace, test actual Monitor controls:

```bash
uv run --no-sync --with playwright python -m tools.opcua.monitor_browser \
  --url http://127.0.0.1:27192 \
  --output artifacts/monitor-browser \
  --focus R상전압 \
  --compare T상전류
```

The channel arguments must exist in that workspace. Chromium must already be installed
(`uv run --no-sync --with playwright playwright install chromium` if needed).
The caller owns the UI server lifecycle. The gate checks 1440px and 1024px viewports, the initial
chart position, actual chart changes for all four ranges, focus/comparison selection, return from
Assets signal detail with selection preserved, browser errors, and viewport overflow. It writes
JSON and screenshots; screenshots still require visual review. This is a stored-data interaction
gate, not the live fault/reconnect protocol owned by `fault_harness.py`.
