"""Bounded log access for workspace-owned Operations components."""

from __future__ import annotations

from collections import deque

from industrial_phm.runtime.operations_runtime import (
    OperationsComponentKind,
    OperationsRuntimePlan,
)


def tail_operations_component_log(
    plan: OperationsRuntimePlan,
    kind: OperationsComponentKind,
    *,
    lines: int = 100,
) -> tuple[str, ...]:
    """Return a bounded tail without exposing workspace log paths to callers."""
    if not isinstance(plan, OperationsRuntimePlan):
        raise ValueError("plan must be OperationsRuntimePlan")
    if not isinstance(kind, OperationsComponentKind):
        raise ValueError("kind must be OperationsComponentKind")
    if isinstance(lines, bool) or not isinstance(lines, int) or not 1 <= lines <= 10_000:
        raise ValueError("lines must be an integer between 1 and 10000")

    launch = next((item for item in plan.components if item.kind == kind), None)
    if launch is None:
        raise LookupError(f"Operations component is not in runtime plan: {kind.value}")
    if not launch.log_path.is_file():
        raise FileNotFoundError(launch.log_path)

    tail: deque[str] = deque(maxlen=lines)
    with launch.log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            tail.append(line.rstrip("\n"))
    return tuple(tail)
