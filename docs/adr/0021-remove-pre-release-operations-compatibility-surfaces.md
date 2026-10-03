# 0021. Remove pre-release Operations compatibility surfaces

Status: Accepted

## Context

ADR-0011 established one local Operations workspace as the owner of runtime paths. ADR-0017 later
separated the operational CLI by responsibility but kept the earlier `operations ...` spellings as
executable argv rewrites. ADR-0020 established one Operations app composition root while retaining
individual persistence-path environment variables as compatibility inputs.

Those compatibility surfaces were useful while the local-node product runtime was assembled. The
canonical runtime is now workspace-first end to end: `operations start` launches collection, analysis
and the packaged UI from one workspace, current documentation uses the responsibility-based CLI, and
the package is still `0.0.1` / Pre-Alpha without a declared public compatibility baseline.

Keeping both paths now has a cost:

- stale scripts can continue to use moved CLI spellings without noticing the current taxonomy;
- the packaged UI can be composed from paths that do not belong to one workspace;
- tests and CI must preserve two ways to address the same local state;
- path-level overrides weaken the workspace invariant used by backup/restore, deployment and runtime
  composition.

Internal service commands still need explicit path flags for bounded diagnostics and isolated contract
tests. That is an internal execution boundary, not a second packaged-app composition model.

## Decision

- The executable no longer rewrites moved `operations ...` spellings. Callers must use the canonical
  responsibility namespaces:
  - normal node lifecycle: `operations`
  - recovery/history maintenance: `maintenance`
  - deployment validation: `validate`
  - service/source plumbing: `internal`
- The packaged Operations app requires `INDUSTRIAL_PHM_OPERATIONS_WORKSPACE`.
- Individual Operations/history persistence-path environment variables are not app composition inputs.
  The app resolves source/runtime/control/spool/telemetry/window/analysis/finding/review/history paths
  from that one workspace.
- Internal service/diagnostic commands may retain explicit path flags where their contract requires
  isolated process or storage testing. They are not the normal product lifecycle.
- Persisted schemas, capability IDs, evidence identity and the explicit phase-result migration command
  are unchanged by this decision.
- ADR-0017 remains authoritative for the responsibility-based CLI taxonomy, but its compatibility
  routing decision is superseded by this ADR.
- ADR-0020 remains authoritative for the single app composition root, but its legacy explicit-path
  environment compatibility input is superseded by this ADR.

## Consequences

There is one discoverable user-facing CLI taxonomy and one packaged Operations persistence composition
model. Backup/restore, deployment, supervisor launch and the UI now share the same workspace boundary.

Scripts that still use moved `operations backup/preflight/run-*` spellings fail at argument parsing and
must be updated to the canonical namespace. Direct packaged-UI development must provide one workspace
root rather than individual state paths.

Historical CHANGELOG/ADR text and persisted version identifiers remain unchanged because they describe
past behavior or durable evidence, not current compatibility promises.
