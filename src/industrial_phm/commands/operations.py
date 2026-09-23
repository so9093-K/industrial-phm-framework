"""Operational source-runtime command handlers."""

from __future__ import annotations

import argparse
import sys

from industrial_phm.application import (
    JsonSourceRepository,
    JsonSourceRuntimeRepository,
    SourcePollingPolicy,
    SourceRuntimeCycleFailureScope,
    SourceRuntimeCycleState,
    poll_registered_file_source,
    validate_distinct_source_state_paths,
)


def _run_operations_poll_source(args: argparse.Namespace) -> int:
    registry_path = args.registry
    runtime_path = args.runtime_state

    try:
        validate_distinct_source_state_paths(registry_path, runtime_path)
        source_repository = JsonSourceRepository(registry_path)
        runtime_repository = JsonSourceRuntimeRepository(runtime_path)
        policy = SourcePollingPolicy(
            interval_seconds=args.interval_seconds,
            max_cycles=args.max_cycles,
        )
        results = poll_registered_file_source(
            source_repository,
            source_repository,
            runtime_repository,
            args.source_id,
            policy,
        )

        last_state: SourceRuntimeCycleState | None = None
        for cycle_number, result in enumerate(results, start=1):
            last_state = result.state
            if result.state == SourceRuntimeCycleState.SUCCEEDED:
                received = result.received
                if received is None:
                    print(
                        "runtime polling invariant violation: succeeded cycle has no receipt",
                        file=sys.stderr,
                    )
                    return 1
                print(
                    f"cycle {cycle_number}: succeeded "
                    f"received_at={received.receipt.received_at.isoformat()}"
                )
            elif result.state == SourceRuntimeCycleState.SKIPPED:
                print(
                    f"cycle {cycle_number}: skipped "
                    f"reason={result.message or 'source is not active'}",
                    file=sys.stderr,
                )
            else:
                scope = (
                    "unknown"
                    if result.failure_scope is None
                    else result.failure_scope.value
                )
                print(
                    f"cycle {cycle_number}: failed scope={scope} "
                    f"reason={result.message or 'runtime cycle failed'}",
                    file=sys.stderr,
                )
    except KeyboardInterrupt:
        print("source polling interrupted by user", file=sys.stderr)
        return 130
    except (LookupError, OSError, ValueError) as error:
        print(f"source polling failed: {error}", file=sys.stderr)
        return 1

    if last_state is None:
        print("source polling produced no runtime cycle", file=sys.stderr)
        return 1
    if last_state == SourceRuntimeCycleState.SUCCEEDED:
        return 0
    if last_state == SourceRuntimeCycleState.SKIPPED:
        return 2
    if last_state == SourceRuntimeCycleState.FAILED:
        return (
            1
            if result.failure_scope
            in {
                SourceRuntimeCycleFailureScope.SOURCE,
                SourceRuntimeCycleFailureScope.PLATFORM,
            }
            else 1
        )
    return 1
