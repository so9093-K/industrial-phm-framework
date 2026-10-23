# 0032. Separate Product Runtime from the verification control plane

Status: Proposed (2026-10-23)

## Context

Product startup and PHM operation must not depend on test infrastructure.
At the same time, external verification needs reproducible suite selection,
native runner results and comparable execution evidence across environments.

## Decision

1. Product Runtime depends only on actual product dependencies, product assets,
   operational configuration and service readiness. Test runners, verification
   CLI, JUnit files, CI credentials or past pipeline success cannot be startup
   prerequisites.
2. Building the source distribution may require Node/npm to compile packaged
   Svelte assets; running a built wheel does not. Release approval policies
   are distinct from service startup and health checks.
3. External development-only verification selects declarative suites, executes
   native runners, collects execution evidence and produces a final status.
   pytest, Vitest and Playwright retain test discovery, assertions and
   per-test reporting. Do not create a replacement test runner.
4. CLI/CI must fail closed on missing or incomplete native evidence.
   CI providers are thin invocation/publication adapters, not test engines.
5. Keep one suite registry and introduce abstractions only when a real,
   validated integration requires them. Unprovisioned runners are explicitly
   planned rather than silently selectable as active suites. New developer
   dependencies remain outside production distribution.
6. Targeted verification PR checks may run in addition to standard Source CI.
   They do not add a default product-wide browser or container gate. The
   detailed control-plane execution policy is owned by
   [Verification Policy](../verification-policy.md); per-product test policy
   remains separately owned by docs/testing-policy.md.

## Consequences

The dependency arrow is verification -> Product Runtime, never the reverse.
Product wheel imports, service startup, workspace ownership and operational
readiness remain independent of test and CI code. The initial contract and
smoke cases do not claim product or field PHM acceptance.
