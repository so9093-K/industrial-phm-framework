# 0020. Use one composition root for the Operations app

Status: Accepted

## Context

ADR-0018 moved concrete read repositories out of the marimo Operations V2 app.
ADR-0019 did the same for write actions. That separation removed storage adapters
from the UI, but left three pieces of composition duplicated across the two runtime
modules and the app:

- workspace/legacy path resolution lived with the read snapshot even though actions
  consumed the same path set;
- source registry projection (sources, lifecycle, freshness) was rebuilt separately
  after reads and writes;
- bounded async connector execution existed in the action facade while Setup still
  owned another asyncio + ThreadPoolExecutor bridge for OPC UA browse.

The UI also re-exported every resolved persistence path even though no downstream
cell used those values. Advanced diagnostics already expose paths deliberately.

## Decision

- Shared local-runtime primitives live in
  `industrial_phm.runtime.operations_app_wiring`.
- `OperationsAppPaths` and workspace-first path resolution have one owner there.
- Source registry projection into source/lifecycle/freshness state has one helper
  used by both read composition and write actions.
- The bounded async-worker bridge has one implementation there and is used for
  OPC UA browse and diagnostic connector calls.
- `OperationsAppActions` owns bounded OPC UA browse in addition to existing
  diagnostic/write actions; the marimo app does not own event-loop/thread plumbing.
- `OperationsAppContext` is the UI composition root. It combines one
  `OperationsAppSnapshot` with `OperationsAppActions` bound to the exact same
  `OperationsAppPaths`.
- The UI consumes `load_operations_app_context()` rather than independently
  constructing snapshot and actions.
- Individual persistence paths are no longer exported as marimo cell variables.
  Advanced System diagnostics remain the explicit path-disclosure surface.
- Legacy explicit environment-path overrides remain compatibility inputs to the
  shared path resolver; the packaged product runtime still supplies one workspace root.

## Consequences

Read and write composition remain separate modules because their failure and mutation
semantics differ, but they no longer duplicate the local runtime wiring that binds
them to one workspace.

Storage topology and async connector mechanics are no longer part of the UI graph.
Tests can verify the entire composition root without running marimo, while marimo
integration tests continue to exercise the resulting context.

This does not change persistence formats, source lifecycle rules, analysis semantics,
runtime process topology, or operator workflows.
