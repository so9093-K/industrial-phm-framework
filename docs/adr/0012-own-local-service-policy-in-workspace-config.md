# 0012. Own local service policy in the workspace config

Status: Accepted

## Context

ADR-0011 made one `OperationsWorkspace(root)` the authoritative owner of local non-secret paths.
The collector and live-analysis runner still expose their own CLI tuning flags, however, and a future
supervisor must not copy those defaults into another launch path. If the same window/alignment policy is
owned independently by CLI defaults, demo scripts and a supervisor, one local Operations instance can
silently run different policies depending on how it was started.

The first v1 workspace config added by #349 was deliberately only a versioned marker because no product
runtime owned these policies yet. The next runtime layer needs one stable, inspectable configuration
before it starts child processes.

## Decision

- `config.toml` owns the user-facing collection/window and live-analysis policies used by the local
  product runtime.
- The v1 config has optional `[collection]` and `[analysis]` tables. A v1 file containing only the
  original `schema` marker remains valid and receives the same code defaults, so workspaces initialized
  by #349 do not require a migration.
- The initial collection policy is limited to values already exposed by the supported local stack:
  reconcile interval, finalized-window duration and allowed lateness.
- The initial analysis policy owns runner poll interval and temporal alignment. `bounded-previous`
  requires both a positive carry age and a non-empty basis, preserving ADR-0009 rather than turning
  transport timing into an implicit measurement-validity assumption.
- A pure `OperationsRuntimePlan` resolves workspace + config into deterministic collection and analysis
  child-process commands and workspace-owned log destinations. Building the plan has no process or
  filesystem side effect.
- Existing `run-collection-service` and `run-window-analysis` commands keep their explicit flags as
  compatibility/internal surfaces. They are not a second product configuration owner.
- Process supervision, readiness, restart and UI launching are separate runtime responsibilities layered
  on top of this plan.

## Consequences

A future supervisor can start the same local service topology without re-declaring collection/window/
analysis defaults. Demo presets can create or override one workspace config before launch rather than
constructing several unrelated command lines.

Adding a new user-facing runtime policy now requires deciding whether it belongs in the versioned
workspace config. Component-internal diagnostics and fault-injection flags do not automatically become
product configuration.

This ADR does not make collector and analysis one process, does not define HA/distributed coordination,
and does not make the current repository-local marimo app an installable Operations application.
