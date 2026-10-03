# 0017. Separate the operational CLI by user responsibility

Status: Accepted

## Context

The local-node product runtime was built incrementally. Early operational commands all lived under
`industrial-phm operations`, including normal node lifecycle, offline backup/restore, DuckLake
maintenance, deployment validation and the collector/analysis service entrypoints used by the supervisor.

That shape preserved implementation progress but exposed the internal process/storage topology in the same
namespace used by normal operators. It also made help output imply that commands such as
`run-collection-service` and explicit DuckLake compaction were normal ways to operate the product.

The research/data/experiment CLI has a separate purpose and does not need to be reorganized to solve this
local-runtime responsibility problem.

## Decision

The operational CLI is grouped by responsibility:

- `operations` owns the normal local-node lifecycle only:
  `init`, `start`, `status`, `logs`, `stop`.
- `maintenance` owns explicit recovery/migration/history work:
  `backup`, `restore`, `migrate-phase-unbalance-results`, and
  `history backfill|flush|compact`.
- `validate` owns explicit operational/deployment gates. The first canonical gate is
  `validate deployment`.
- `internal` owns service/source plumbing that the product runtime or diagnostics may invoke directly:
  `collection-service`, `window-analysis`, `poll-source`, and `request-collection`.

The Operations supervisor itself uses the canonical `internal` service commands. systemd and current
documentation use `validate deployment`; backup/restore documentation uses `maintenance`.

Legacy `operations` spellings for commands moved by this ADR remain accepted at the executable
entrypoint through deterministic argv rewriting. They are not registered in the canonical parser and
therefore do not appear in `operations --help`. Compatibility routing changes spelling only and passes
all remaining arguments to the same handler.

The compatibility routes are:

- `operations backup|restore` → `maintenance backup|restore`
- `operations preflight` → `validate deployment`
- `operations backfill-source` → `maintenance history backfill`
- `operations flush-history` → `maintenance history flush`
- `operations compact-history` → `maintenance history compact`
- `operations migrate-phase-unbalance-results` →
  `maintenance migrate-phase-unbalance-results`
- `operations poll-source|request-collection` → matching `internal` commands
- `operations run-collection-service` → `internal collection-service`
- `operations run-window-analysis` → `internal window-analysis`

No deprecation-removal date is implied while the package remains pre-release. Removing compatibility
routes requires a separate versioning/deprecation decision.

## Consequences

A normal operator can discover the supported node lifecycle without seeing individual SQLite/DuckLake
paths or child-process entrypoints. Maintenance and deployment procedures have stable, explicit homes,
while internal process separation remains available to the supervisor and fault/development tooling.

The `internal` namespace is packaged because the supervisor launches those entrypoints in independent
processes. Its presence does not make those commands the recommended user workflow.

Existing shell scripts using the old `operations` spelling continue to execute, but new docs, CI,
runtime launch plans and service-manager examples use only the canonical taxonomy.

This ADR does not reorganize `data`, `feature`, `experiment`, or `analysis`; those are research and
evidence workflows rather than the local Operations lifecycle.
