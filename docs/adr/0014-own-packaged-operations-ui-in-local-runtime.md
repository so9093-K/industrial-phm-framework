# 0014. Own the packaged Operations UI in the local runtime

Status: Accepted

## Context

ADR-0013 deliberately introduced the local foreground supervisor before the canonical Operations UI was
an installable runtime-owned component. #353 moved the marimo application into the wheel and published an
`operations` extra, while #355 completed the workspace-owned collection/analysis start/stop lifecycle.

Leaving the UI outside that lifecycle would still require a second terminal and manual workspace
environment wiring. Treating the UI as healthy merely because its child PID exists would also violate
ADR-0013's rule that process identity is not component readiness.

The existing Operations app already resolves all operational state from
`INDUSTRIAL_PHM_OPERATIONS_WORKSPACE`. Legacy granular path environment variables remain supported for
diagnostics and compatibility, but they must not override the workspace when the product runtime launches
the app.

## Decision

- The local Operations runtime owns three child processes in deterministic order:
  collection → analysis → packaged Operations UI.
- The UI is launched from the installed `industrial_phm.apps.operations_v2` package surface with
  `marimo run --headless --no-token`.
- The reference local runtime binds the UI to `127.0.0.1` and deliberately disables marimo token auth.
  This is a local single-user reference boundary: headless default token auth would require an out-of-band
  token handoff while the product CLI prints a directly usable local URL. Any non-loopback or shared-host
  exposure must introduce an explicit authentication/TLS boundary under #318 instead of reusing this mode.
- The workspace config advances to schema v2 and adds a bounded `[ui] port` setting. Existing v1
  workspaces remain readable and `operations init` upgrades them atomically without rewriting
  repository evidence.
- The supervised UI child receives one authoritative workspace environment variable. Legacy granular
  Operations/history path overrides are removed from that child's inherited environment so a shell
  setting cannot silently split one node across different repositories.
- UI readiness is not inferred from its PID. Status requires both the supervisor-owned UI process identity
  and a successful connection to the configured loopback listener.
- Collection and analysis continue to use their own runtime heartbeat evidence; the UI listener probe does
  not replace those contracts.
- `operations logs` reads only workspace-owned component logs and exposes bounded tails rather than
  requiring users to know internal file paths.
- An unexpected UI exit fails the same foreground service set and triggers coordinated shutdown, matching
  the existing collection/analysis supervisor failure policy.

## Consequences

`operations start <workspace>` becomes the single local entry point for the collection, analysis and
Operations web application process set. A normal user no longer has to launch marimo separately or export
individual state paths.

A live UI PID can still be reported as not ready while its listener is unavailable. This is intentional:
process existence and usable application transport are distinct facts.

This decision does not define public-network exposure, TLS, reverse-proxy authentication, daemonization or
automatic restart. The `--no-token` reference mode must not be promoted to those deployments; those remain
deployment responsibilities under #318.
