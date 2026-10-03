# 0018. Keep the Operations UI out of read-repository composition

Status: Accepted

## Context

The packaged Operations V2 marimo app accumulated two distinct responsibilities in one large reactive cell:

1. resolve workspace and legacy environment paths for every operational repository;
2. construct JSON/SQLite/DuckLake adapters, read bounded evidence, isolate repository failures, and build
   the monitor/overview read models.

That wiring is not presentation logic. Keeping it in the app made the UI aware of every storage adapter,
duplicated the workspace contract already owned by the runtime layer, and made repository changes require
editing a large reactive cell.

The app still legitimately owns interaction state and user-triggered setup/review actions. Moving all
write-side commands in one change would mix a structural refactor with action semantics and make review
harder.

## Decision

- Concrete **read-side** composition for Operations V2 lives in
  `industrial_phm.runtime.operations_app_composition`.
- `OperationsAppPaths` resolves one workspace root first and retains legacy explicit-path environment
  overrides only for compatibility.
- `OperationsAppSnapshot` loads a bounded, immutable snapshot of registered sources, runtime evidence,
  analysis results, findings/reviews, acquisition state, history discovery and collection intent.
- Repository-specific read failures remain isolated as `SystemStateErrorEvidence`; one corrupt store must
  not blank unrelated Operations evidence.
- The snapshot loader owns concrete JSON/SQLite/DuckLake adapter construction and the monitor/overview
  projection that depends on those reads.
- The marimo app invokes one snapshot loader and exports the same downstream variable names used by its
  existing UI cells.
- Review-referenced phase-unbalance runs outside the recent-result bound remain loaded exactly as before.
- The current legacy path compatibility remains available for repository-local diagnostics/tests, while
  the product runtime continues to launch the UI with one workspace root.
- Write-side Setup/Investigation/Maintenance action composition remains in the app for this tranche and
  must be extracted separately rather than hidden inside the read snapshot.

## Consequences

The Operations UI no longer constructs DuckLake, acquisition telemetry/spool, observation-window,
phase-result, analysis-runtime or analysis-ledger read adapters directly. Storage evolution can be tested
against a normal Python composition service without running marimo.

The app source becomes materially smaller while preserving existing presentation and action semantics.
This change does not merge repositories, change persistence formats, or introduce a new source of truth.

The new composition module is still concrete local-runtime wiring. It is not a domain/application service
and should not be imported by PHM analysis code.

A later consolidation can move write-side action repository construction behind explicit application
commands and then reassess whether the remaining marimo module should be split further.
