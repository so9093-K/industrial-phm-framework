# Local Operations deployment

The supported deployment target is one local Operations workspace owned by one foreground supervisor.
A service manager owns restart and boot lifecycle; the application continues to own collection, analysis
and UI child coordination.

## Preflight

Run preflight **as the same OS account that will run the service** and use an absolute workspace path.

```bash
/opt/industrial-phm/.venv/bin/industrial-phm \
  validate deployment /var/lib/industrial-phm/plant-a
```

Preflight checks the versioned runtime config/plan, packaged Operations dependencies, current account
permissions, supervisor/history lock availability and the loopback UI port. `WARN` findings do not block
startup; any `FAIL` returns exit 1.

The workspace account needs read/write/search access to the workspace root, `data/` and `logs/`, and
read/write access to existing durable state files. Deployment does not require the application package or
Python environment itself to be writable.

## Foreground service contract

The service manager executes the same supported foreground command used interactively:

```bash
industrial-phm operations start /var/lib/industrial-phm/plant-a
```

A coordinated/manual stop exits successfully. An unexpected managed component exit or startup failure
returns non-zero, so an external manager can distinguish a clean stop from a runtime failure.

SIGINT and SIGTERM are both translated into the supervisor's coordinated stop path. The supervisor asks
UI, analysis and collection children to stop in reverse order and escalates only when a child does not
exit inside its bounded shutdown time.

## systemd reference

`deploy/systemd/industrial-phm-operations.service.example` is the reference system service. Copy it to
the host and replace the executable, user/group and absolute workspace path.

The unit uses:

- `ExecStartPre=... validate deployment ...` to fail before child processes start when deployment
  prerequisites are invalid.
- `Restart=on-failure`, so clean/manual stops do not create a restart loop while unexpected non-zero
  runtime exits can be restarted by the service manager.
- bounded `StartLimit*` and `RestartSec` values to avoid an unbounded tight failure loop.
- `KillMode=mixed`, so the initial stop signal goes to the supervisor rather than independently racing
  all managed children; a later forced kill still covers the service cgroup.
- `TimeoutStopSec=60s`, which is longer than the current application-level graceful/terminate escalation
  window for the three local child processes.
- `UMask=0077` for newly created service-owned state and `NoNewPrivileges=yes`.

systemd documents `Restart=on-failure` as the recommended restart mode for long-running services. Its
`KillMode=mixed` mode sends the initial termination signal to the main process and reserves the later
forced kill for the remaining service processes. These semantics match the Operations supervisor's
ownership boundary.

## Filesystem and permissions

The reference deployment uses:

```text
/opt/industrial-phm/                 read-only application/venv
/var/lib/industrial-phm/plant-a/    writable Operations workspace
```

This is a deployment convention, not a new hard-coded application path. The workspace root remains an
explicit CLI argument and may be placed elsewhere when the same ownership/permission contract is met.

Do not make the workspace world-writable. Preflight reports that condition as a warning. Credentials and
OPC UA certificates are not part of the non-secret workspace and must be provisioned separately once the
target-source OPC UA security profile is implemented.

## Restart, backup, and retention

The application does not implement an internal infinite restart loop for the full node. Component/session
recovery that is already part of collection remains internal; failure of the managed node is surfaced as
a non-zero supervisor exit and the external service manager owns node restart.

Backup remains an offline recovery operation. Stop the service, create a workspace backup, and restore
into a new root before starting it. See ADR-0015.

No automatic destructive retention policy is enabled. Retention duration/size limits remain blocked on
the representative archive evidence in #316/#317-B; deployment must not guess those values.

## Non-goals

The reference unit does not provide HA, distributed coordination, leader election, public UI exposure,
TLS/reverse-proxy authentication, or container orchestration. The current product boundary is one local
writer/supervisor per workspace.
