"""Synchronous caller-owned polling runtime for registered operational sources."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from math import isfinite
from numbers import Real

from industrial_phm.application.source_cycle import (
    SourceRuntimeCycleResult,
    SourceRuntimeCycleState,
    run_registered_file_source_cycle,
    run_registered_opcua_source_cycle,
)
from industrial_phm.application.source_lifecycle import SourceLifecycleRepository
from industrial_phm.application.source_registration import (
    FileSourceConfig,
    OpcUaSourceConfig,
    SourceRepository,
)
from industrial_phm.application.source_runtime import SourceRuntimeRepository


@dataclass(frozen=True, slots=True)
class SourcePollingPolicy:
    """Explicit polling cadence for one synchronous caller-owned runtime."""

    interval_seconds: float
    max_cycles: int | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.interval_seconds, bool)
            or not isinstance(self.interval_seconds, Real)
            or not isfinite(self.interval_seconds)
            or self.interval_seconds <= 0
        ):
            raise ValueError("interval_seconds must be a positive finite number")
        if self.max_cycles is not None and (
            isinstance(self.max_cycles, bool)
            or not isinstance(self.max_cycles, int)
            or self.max_cycles <= 0
        ):
            raise ValueError("max_cycles must be a positive integer when provided")


def poll_registered_source(
    source_repository: SourceRepository,
    lifecycle_repository: SourceLifecycleRepository,
    runtime_repository: SourceRuntimeRepository,
    source_id: str,
    policy: SourcePollingPolicy,
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Iterator[SourceRuntimeCycleResult]:
    """Poll one registered FILE or OPC UA source with type-specific one-shot cycles.

    The loop is synchronous and caller-owned. OPC UA uses one fresh asyncio.run per
    bounded connect/read/disconnect iteration; no event loop, connection, or subscription
    is kept alive between cycles. Polling stops immediately when a cycle is skipped or
    failed. Platform failures are not retried because retry/backoff policy is not
    implemented yet.
    """
    source = source_repository.get(source_id)
    cycle_fn: Callable[[], SourceRuntimeCycleResult]
    if isinstance(source.config, FileSourceConfig):

        def _file_cycle() -> SourceRuntimeCycleResult:
            return run_registered_file_source_cycle(
                source_repository,
                lifecycle_repository,
                runtime_repository,
                source_id,
            )

        cycle_fn = _file_cycle
    elif isinstance(source.config, OpcUaSourceConfig):

        def _opcua_cycle() -> SourceRuntimeCycleResult:
            return asyncio.run(
                run_registered_opcua_source_cycle(
                    source_repository,
                    lifecycle_repository,
                    runtime_repository,
                    source_id,
                )
            )

        cycle_fn = _opcua_cycle
    else:
        raise ValueError("unsupported registered source config")

    yield from _poll_cycles(cycle_fn, policy, sleep_fn=sleep_fn)


def _poll_cycles(
    cycle_fn: Callable[[], SourceRuntimeCycleResult],
    policy: SourcePollingPolicy,
    *,
    sleep_fn: Callable[[float], None],
) -> Iterator[SourceRuntimeCycleResult]:
    if not isinstance(policy, SourcePollingPolicy):
        raise ValueError("policy must be SourcePollingPolicy")
    if not callable(sleep_fn):
        raise ValueError("sleep_fn must be callable")

    cycle_count = 0
    while True:
        result = cycle_fn()
        yield result
        cycle_count += 1

        if result.state != SourceRuntimeCycleState.SUCCEEDED:
            return
        if policy.max_cycles is not None and cycle_count >= policy.max_cycles:
            return

        sleep_fn(float(policy.interval_seconds))
