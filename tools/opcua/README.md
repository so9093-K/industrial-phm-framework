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
  --window-state artifacts/live-demo/windows.json \
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
export INDUSTRIAL_PHM_HISTORY_CATALOG=artifacts/live-demo/catalog.sqlite
export INDUSTRIAL_PHM_HISTORY_DATA=artifacts/live-demo/data
uv run --no-sync marimo run apps/operations.py
```

1. Sources: select `demo-opcua`, then **Start Collection** and **Refresh Live Monitor**.
2. Assets: select `demo-power-01`, use **설비 이력 목록 새로고침** if ingestion began after page load.
3. Select a channel and **최근 15분**, then **이력 조회 / 새로고침**. Relative ranges move on every query.
4. Inspect source-specific latest values and history age. Historical FILE rows have no expected-live
   freshness assessment; live rows refer to Sources policy/receipt assessment. Future times are flagged.
   Choose 24 hours or 7 days for UI-only full-range min/max/mean buckets, not source averages.
5. Close the browser, reopen it, and verify that the collector continued writing.
6. Stop/restart the server and collector separately; refresh the monitor and history to check recovery.
7. Sources **Stop Collection** stops source acquisition. The collector process can remain available.
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
  --window-state artifacts/live-3phase/windows.json \
  --analysis-state artifacts/live-3phase/phase-unbalance.json \
  --ledger-state artifacts/live-3phase/window-analysis-ledger.json
```

Each finalized window is analyzed once from its accepted events (ADR-0008). Restarting the runner does
not record a window twice. Windows without all three phases bound are recorded as skipped with a reason.

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

## Regression validation

```bash
uv run --locked --extra history --extra opcua pytest tests/contract/test_live_measurement_stack.py
```

This uses a real loopback asyncua server and separate collector process with synthetic inputs. It
checks concurrent history reads, source restart/reconnect, collector restart with durable epochs,
Stop Collection, FILE/live separation, latest-point budgets and unique delivery identities. It needs
no external server, credentials or AI-Hub payload. On failure, pytest's temporary stack `process.log`
contains the subprocess output.
