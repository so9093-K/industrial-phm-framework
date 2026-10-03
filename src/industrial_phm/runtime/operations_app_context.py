"""Single composition root consumed by the packaged Operations UI."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from industrial_phm.runtime.operations_app_actions import OperationsAppActions
from industrial_phm.runtime.operations_app_composition import (
    OperationsAppSnapshot,
    load_operations_app_snapshot,
)


@dataclass(frozen=True, slots=True)
class OperationsAppContext:
    """One coherent read/write runtime composition for a UI render."""

    snapshot: OperationsAppSnapshot
    actions: OperationsAppActions

    def __post_init__(self) -> None:
        if self.actions.paths != self.snapshot.paths:
            raise ValueError("snapshot and actions must use the same Operations app paths")


def load_operations_app_context(
    *,
    environ: Mapping[str, str] | None = None,
    assessed_at: datetime | None = None,
) -> OperationsAppContext:
    """Resolve paths once through the snapshot and bind write actions to the same root."""
    snapshot = load_operations_app_snapshot(environ=environ, assessed_at=assessed_at)
    return OperationsAppContext(
        snapshot=snapshot,
        actions=OperationsAppActions(snapshot.paths),
    )
