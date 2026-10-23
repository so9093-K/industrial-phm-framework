# Verification Policy — New Foundation

## Product Runtime independence

Product Runtime must install, start and operate using product dependencies only.
It must not require pytest, Vitest, Playwright, the verification CLI, a JUnit
report, a CI server, CI environment variables, or historical test success.
Source-build requirements and release approval are separate concerns: rebuilding
the packaged Svelte UI may need Node/npm, but running an installed wheel does not.

The verification implementation lives in tools/verification. It is not a product
package import or runtime requirement, and must not modify production workspaces.

## Ownership

- The suite registry (tools/verification/suites.json) owns suite identity,
  native runner, working directory, command argument array, timeout and
  non-secret environment overrides. Schema version is 1.
- The development-only CLI owns execution IDs, invoking the declared command,
  evidence directories and run-level status.
- pytest, Vitest and Playwright own test collection, assertions, native
  per-case verdicts and JUnit generation. The CLI never invents passed cases.
- GitHub Actions, GitLab CI or local shells are thin callers and publishers;
  they must not duplicate verdict policy.

Only two tokens are expanded in suite arguments: {python} for the invoking
interpreter and {junit} for the absolute run's JUnit XML output. Commands are
executed directly (not through a shell). No implicit package installation or
network download happens in the verification CLI.

## Commands

From the repository root after installing development dependencies:

    python tools/verification/verify.py list
    python tools/verification/verify.py run verification-smoke

The default output is artifacts/verification/<UTC-run-id>/, ignored by git.
It contains a run-manifest.json, runner.log and native junit.xml if present.
Use --output to choose a different results root.

## Status contract

| Status | Meaning |
| --- | --- |
| PASSED | Native nonempty result, one or more executed cases, no failures/errors, process exit 0 |
| TEST_FAILED | JUnit assertion failure |
| EXECUTION_ERROR | Missing runner, native error case, abnormal process exit |
| CONFIG_ERROR | Unknown or malformed suite configuration |
| INTERRUPTED | Operator interrupt or configured timeout |
| INCOMPLETE | Missing, empty, invalid or wholly skipped JUnit results |

Only PASSED yields exit 0; TEST_FAILED yields 1; CONFIG_ERROR yields 2;
all other non-passing states yield 3. Missing JUnit cannot count as success.
Run Manifest records suite, command, revision if available, UTC times,
exit status, native case counts and evidence file names.

Only run verification with trusted sources and environments. Native runner logs
can include input data and must be reviewed for secrets before publication.
Evidence retention is determined by the caller, not by Product Runtime.

## Foundation boundary

verification-smoke is an actual pytest suite for the CLI contract. The Vitest
and Playwright suite entries are explicitly marked planned, and cannot execute
as active suites until their development toolchain is installed and checked: Node development dependencies, reproducible package-lock updates,
browser runtime and product browser cases require a separate implementation
change. When not installed, those native runners must fail visibly. The
foundation does not certify PHM model performance or product acceptance.

Existing product test automation is not evaluated, migrated or declared valid
by this first foundation change; the new workflow runs only on verification-related PR changes or explicit
manual dispatch and has an independent runtime-dependency boundary check.

The contract rejects unknown placeholders, contradictory JUnit outcomes and
JUnit root test-count mismatches; the manifest retains the suite definition
SHA-256, Python version and execution platform.
