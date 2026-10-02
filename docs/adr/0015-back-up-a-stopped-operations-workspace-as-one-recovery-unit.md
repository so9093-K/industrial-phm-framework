# 0015. Back up a stopped Operations workspace as one recovery unit

Status: Accepted

## Context

The local Operations node deliberately keeps source registration, control, spool, telemetry, finalized
windows, analysis state and DuckLake history in separate repositories. That separation preserves each
component's durability and failure boundary, but disaster recovery must not require an operator to know
which individual SQLite/JSON/Parquet files need to be copied.

Copying a live workspace directory is unsafe. SQLite repositories may have WAL state, DuckLake coordinates
its catalog/data files under a local catalog lock, and the supervisor can change multiple repositories
while a filesystem copy is in progress. Restoring a saved supervisor PID/lock would also manufacture
stale process identity.

## Decision

- One local Operations workspace is the recovery unit.
- The supported v1 backup is **offline**: the product supervisor must be stopped before backup.
- Backup acquires the workspace supervisor lock for the entire capture so a supported
  `operations start` cannot race with the snapshot.
- If a DuckLake catalog exists, backup also acquires the same catalog file lock used by the history
  adapter before copying catalog/history state.
- Workspace-owned SQLite repositories are captured with SQLite's backup API rather than byte-copying
  their database files. This folds committed WAL content into a consistent destination database.
- The backup payload contains the versioned workspace config, durable source/control/spool/telemetry/
  window/analysis/finding/review state, the DuckLake catalog and managed history data files.
- The payload deliberately excludes component logs, supervisor PID/state/lock files, history lock files
  and the rebuildable DuckLake batch-provenance accelerator.
- Each payload file is listed in a versioned manifest with relative path, byte size and SHA-256 digest.
  Restore verifies the complete file set and every digest before writing a workspace.
- SHA-256 here is corruption/tamper detection for the backup artifact, not authentication, encryption or
  secret management.
- Restore never overwrites an existing workspace. It materializes the verified payload in a temporary
  sibling directory, validates the restored config and then atomically renames it into a new root.
- Runtime process identity and logs start fresh after restore; durable operational/evidence state remains.
- Credentials and certificates remain outside the non-secret workspace contract and therefore are not
  added to this backup format.

## Consequences

Operators can back up and restore a local node without knowing individual repository filenames, while the
existing repository and process boundaries remain intact. A restored node can be started with the normal
`operations start <workspace>` lifecycle.

The first supported contract requires a stopped node. Hot backup, remote object storage, encryption,
automatic backup scheduling and retention periods are separate deployment policies and are not implied by
this ADR.

Manual/internal writers that bypass the supported workspace supervisor are outside this consistency
contract. Deployment tooling must stop or otherwise coordinate them before backup.

A recovery drill must exercise backup → restore into a new root → normal runtime start before #318 can be
considered complete.
