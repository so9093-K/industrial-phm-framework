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

## Real systemd lifecycle acceptance

On Linux GitHub Actions, the `systemd Operations service` CI job builds and
**installs** the Operations wheel in an isolated virtual environment, renders
the exact reference unit `deploy/systemd/industrial-phm-operations.service.example`
with the CI service user's account and temporary workspace, then installs
that temporary unit into `/run/systemd/system`. It explicitly requires a
running systemd service manager; it must **fail**, not silently skip, if the
runner cannot execute real `systemctl` operations.

The gate checks `systemd-analyze verify`, `ExecStartPre` and first start
of the opt-in `--ui web-controlled` supervisor; rejects cross-site/invalid
CSRF source registration while persisting a valid FILE source. It then checks
a manual systemd restart, persistence of the source registration, kills the
actual supervised Web UI child to force supervisor non-zero exit, and waits
for `Restart=on-failure` to create a **different** supervisor PID. The saved
source identity must still be readable after recovery. Finally a
`systemctl stop` must leave the service inactive for longer than the
unit's `RestartSec`, with no unexpected restart. The script always attempts
to stop the temporary unit and removes it from `/run`.

The CI gate tests a genuine systemd service on the GitHub Ubuntu runner.
It does **not** install a permanent production service, certify all Linux
distributions, prove host reboot persistence, or grant an authenticated
remote/multi-user UI. The reference unit still launches marimo by default;
the opt-in Web mode is added **only to the rendered test copy**, not to the
reference file or normal `make up` default.

## Filesystem and permissions

The reference deployment uses:

```text
/opt/industrial-phm/                 read-only application/venv
/var/lib/industrial-phm/plant-a/    writable Operations workspace
```

This is a deployment convention, not a new hard-coded application path. The workspace root remains an
explicit CLI argument and may be placed elsewhere when the same ownership/permission contract is met.

Do not make the workspace world-writable. Preflight reports that condition as a warning. Credentials and
OPC UA certificates are not part of the non-secret workspace and must be provisioned separately once a
connected source requires an OPC UA security profile and that profile is implemented.

## Isolated installed-wheel acceptance gate

The Package CI builds the wheel and installs `wheel[operations]` into a **fresh virtual
environment outside the repository checkout**, then runs
`tools/operations_wheel_smoke.py` with that environment's Python interpreter.
The smoke runner asserts that `industrial_phm` imports from the installed
environment and invokes the installed `industrial-phm` console script rather
than a development checkout. It verifies deployment preflight and two real
supervisor-managed `--ui web-controlled` starts, packaged Web HTML/JS/CSS,
session/Monitor/source inventory reads, clean shutdown and offline
backup into a **different** restored root. In the restored workspace it
checks a CSRF-rejected source mutation, an accepted FILE registration,
a duplicate-registration conflict, and the distinction between
registration and an actual data receipt.

The sample FILE is deliberately created **after** restore. A workspace
backup captures durable Operations-managed state; it does **not** claim
to capture user-managed external FILE input. This gate tests a local
Linux wheel installation only. It does not exercise systemd service
restarts, production equipment, a previous wheel version or rollback.
Those remain independent gates before the default Web UI can change.

## Previous known-good wheel rollback acceptance

The Package CI also verifies a **real Python installation rollback**, not just
workspace snapshot restoration. It builds a wheel from verified green main
commit `b3f9d1076fe3d286e304e30d9f503d4ebb6c718c` (green CI run
`37911770483`) in a detached temporary Git worktree and compares it to
the current wheel. The test installs each wheel sequentially in one isolated
venv and uses one durable, stopped-between-stages workspace:

1. Install the previous green wheel, start supervised `web-controlled`, persist
   FILE registration A, verify same-origin/CSRF and stop cleanly.
2. Force-reinstall the current candidate wheel, reopen the **same** workspace
   with a fresh loopback port, confirm A and persist registration B; stop.
3. Force-reinstall the previous wheel, reopen the same workspace, confirm
   A and B and persist registration C; stop.
4. At every stage compare the **actual installed module bytes** to the
   corresponding built wheel and assert source identity, inventory counts,
   no fabricated data receipt, and duplicate-registration rejection.

The package version is currently `0.0.1` for both builds, so checking
`--version` or allowing an installer to skip an equal-version install would
not prove rollback. The check explicitly forces package reinstalls and
verifies wheel module contents differ before starting.

This acceptance covers only the known-good commit above, the unchanged
workspace schema and local Linux source-control flows; it is **not** a
promise that arbitrary future versions can read newer workspace schemas.
New irreversible migrations must block rollback or provide a separately
proven restore path. It does not exercise systemd, remote service management,
or connected industrial hardware; those are independent P2 gates.

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
