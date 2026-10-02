# 0013. Supervise local service processes without owning component health

Status: Accepted

## Context

ADR-0011 and ADR-0012 define one local Operations workspace and its service launch policy. The supported
live stack still requires collection and analysis to run as independent processes because they have
different failure/recovery boundaries and telemetry.

A local product runtime now needs to own those process lifecycles without turning process ownership
into a second health model. Collection already records process heartbeat and source/session/data-flow
evidence in acquisition telemetry. The analysis runner separately records its heartbeat, last work,
skip and failure evidence. Replacing those facts with "PIDs exist" would regress the Phase 10
observability contract.

There is also already a component-local restart boundary: the collection service restarts failed OPC UA
workers and window coordinators according to ADR-0010. Adding another automatic process-restart loop at
the supervisor layer without a deployment policy would create overlapping retry semantics.

## Decision

- The local Operations runtime has one foreground supervisor for the collection service and analysis
  runner.
- The supervisor owns only process identity and lifecycle:
  - deterministic start order,
  - child PIDs and log destinations,
  - coordinated graceful shutdown,
  - unexpected child exit,
  - its own latest lifecycle state.
- Collection and analysis telemetry remain authoritative for component readiness/health. Supervisor
  state must not translate a live PID into a healthy component verdict.
- A child process that exits unexpectedly fails the current local service set. The supervisor records
  the exit and gracefully stops remaining children instead of independently restarting the failed
  process.
- Process-level restart/supervision policy above this foreground set belongs to the deployment boundary
  (#318). It may later be provided by a service manager or another explicitly designed mode.
- POSIX advisory locking prevents two cooperating foreground supervisors from owning the same workspace.
  Until equivalent cross-platform ownership is validated, the local reference supervisor fails closed
  when POSIX file locking is unavailable.
- Graceful local shutdown sends SIGINT on POSIX so the existing collection and analysis commands can
  persist their normal stop evidence. Forced terminate/kill is only a bounded fallback when a child does
  not exit.
- Supervisor state is atomic local evidence under the workspace runtime path and stores process identity,
  return codes and failure detail, but not command lines or credentials.
- The supervisor runtime API is introduced before a user-facing `operations start` command. The product
  start surface is not considered complete until the Operations UI is an installable/runtime-owned
  component rather than a repository-local marimo command.

## Consequences

The user-facing product can later collapse multiple service terminals into one lifecycle without merging
collector and analysis into one Python process. Existing fault/recovery and telemetry contracts stay
unchanged.

A supervisor PID or RUNNING state is insufficient to claim the collection or analysis service is ready.
Status projection must combine supervisor process identity with the existing component telemetry instead.

If the supervisor itself crashes, child-process ownership and restart behavior are a deployment recovery
problem rather than an implicit in-process retry contract. Backup, service-manager integration and full
deployment recovery remain in #318.
