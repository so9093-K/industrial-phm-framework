# 0031. Separate default source CI from targeted product acceptance

Status: Accepted (2026-10-19; review through PR #655).

Supersedes **only the default automated verification scope** of
[ADR-0030 §6](0030-svelte-typescript-operations-web.md). It does not supersede
ADR-0030's Svelte choice, mandatory frontend compilation in standard sdist/wheel
builds, safety of served assets, runtime permissions, or product acceptance criteria.
The execution rules are owned by [Testing Policy](../testing-policy.md), not by
copies of command lists in this ADR.

## Context

After the Svelte cutover the repository again ran five independent workflows for
many small changes. The Web and Forecast workflows repeated six browser test files
as well as dependency and browser setup; standalone container and showcase
acceptance were also triggered for broad source/frontend changes.
At 2026-10-19 main `0934229`, the workflows consumed about 24 minutes summed
elapsed time per push and had a roughly 10-minute longest individual run.
The source unit/contract suite alone already contains over one thousand checks.

Running tests on fewer paths while leaving duplicate verification scripts,
meta-tests and build-only containers in the repository does not solve the
maintenance problem. A passed source check cannot establish real operator
usability, production distribution behavior or in-field PHM performance.

## Decision

1. Keep one always-on GitHub Actions Source CI job for dependency lock, Ruff,
   mypy and unit/contract tests. The exact workflow is
   `.github/workflows/ci.yml`; no separate path classifier or result aggregator.
2. Remove duplicate Web, Forecast, packaged-container and Product showcase
   *automatic workflows* and their exclusive orchestration/test-gate machinery.
   Do not re-home the same gate into Makefile, shell tools or another CI job.
3. Preserve meaningful product regressions. Place subprocess/full-system scenarios
   in the integration or acceptance layer, not in a basic contract suite merely
   to force them to run on every change. Profiling tools remain opt-in research
   utilities rather than default functional contracts.
4. For changes to frontend behavior, packaging, HTTP security, supervisor,
   storage recovery, forecasting or showcase distribution, the PR must execute
   the relevant existing checks and record exact results and any unexecuted
   boundaries. The product requirements of ADR-0030 still apply at these
   change boundaries; an unrelated PR does not rebuild and browser-test the
   entire application.
5. A green Source CI is evidence only for the checks it actually runs. Never
   claim wheel distribution, browser acceptance, container restarts, model
   validity, or field safety from that result.

## Consequences and alternatives

This lowers redundant CI execution and removes stale code ownership, but accepts
the risk that an untested cross-language regression could escape a change whose
author does not run the relevant acceptance. The PR review must treat missing
acceptance evidence as missing evidence, not as success.

Keeping all workflows with path filters was rejected: repeated environment
preparation, overlapping browser suites and test gate maintenance would remain.
Deleting all storage, security or browser test code was also rejected because
it would remove evidence for real product failures rather than redundant CI cost.
