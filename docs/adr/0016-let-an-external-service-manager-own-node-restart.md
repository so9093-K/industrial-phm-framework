# 0016. Let an external service manager own local-node restart

Status: Accepted

## Context

ADR-0013 made the Operations supervisor the owner of the local collection, analysis and UI child-process
set, but intentionally left node-level restart/deployment policy outside the application. The product now
has a clean workspace lifecycle, readiness/status, bounded logs and an offline recovery contract, so a
long-running host deployment needs an explicit owner for boot, restart and service-account permissions.

Adding an application-level infinite restart loop would duplicate service-manager responsibilities and
make a persistent configuration/permission failure indistinguishable from a transient runtime failure.
A service manager also stops processes with SIGTERM by default, while the early local supervisor path was
only guaranteed to coordinate shutdown through the interactive SIGINT/KeyboardInterrupt path.

## Decision

- `industrial-phm operations start <workspace>` remains a foreground process. It does not daemonize,
  fork, or implement an unbounded node-level restart loop.
- The supervisor translates both SIGINT and SIGTERM into the same coordinated child shutdown path.
- A clean/manual coordinated stop exits successfully. Unexpected child/process startup failure remains a
  non-zero supervisor outcome.
- Long-running deployment restart is owned by an external service manager.
- The reference Linux service manager is systemd. The repository provides a reference unit, not an
  installer that mutates `/etc/systemd`.
- The reference unit uses `Restart=on-failure` with bounded restart/start-limit delay. Clean stops do not
  form a restart loop.
- The reference unit uses `KillMode=mixed`: the initial termination signal reaches the main supervisor
  first, allowing it to stop children in its defined reverse-order lifecycle; a later forced kill still
  covers the remaining service cgroup.
- `operations preflight <absolute-workspace>` is the service-manager `ExecStartPre` contract. It is run
  as the same OS account as the service and validates runtime config/plan, required Operations
  dependencies, workspace permissions, supervisor/history lock availability, packaged UI availability
  and the loopback UI port.
- Preflight `FAIL` blocks service startup. `WARN` records a deployment concern such as unexpected
  ownership/world-writable state without changing application evidence.
- The reference filesystem convention is a read-only application installation under `/opt` and a
  writable service workspace under `/var/lib`, but the application does not hard-code either path.
- The workspace remains the only durable application state root. Service-manager PID/cgroup state is not
  copied into the workspace recovery format.
- HA, leader election and distributed coordination remain non-goals for this local reference deployment.

## Consequences

The same foreground command is usable interactively and under systemd. Restart policy is visible in host
configuration instead of hidden inside the application, while the supervisor remains the sole owner of
child ordering and graceful shutdown.

Deployment failures can be checked under the real service account before process startup. A passing
preflight is not a runtime-health verdict and does not replace `operations status`.

Container/Compose/Kubernetes deployment can be added later as an adapter to this foreground/preflight
contract rather than defining another process topology.

## References

- systemd NEWS: `Restart=on-failure` or `Restart=on-abnormal` is recommended for long-running services:
  https://cgit.freedesktop.org/systemd/systemd/tree/NEWS
- systemd `KillMode=mixed`: initial termination targets the main daemon and later SIGKILL covers the
  remaining service processes:
  https://www.freedesktop.org/software/systemd/man/latest/systemd.kill.html
- Filesystem Hierarchy Standard: persistent variable application state belongs under the `/var`
  hierarchy:
  https://specifications.freedesktop.org/fhs/latest-single/
