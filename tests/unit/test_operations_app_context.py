from datetime import UTC, datetime
from pathlib import Path

import pytest

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_app_actions import OperationsAppActions
from industrial_phm.runtime.operations_app_context import (
    OperationsAppContext,
    load_operations_app_context,
)
from industrial_phm.runtime.operations_app_wiring import resolve_operations_app_paths


def test_app_context_binds_snapshot_and_actions_to_same_paths(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    initialize_operations_workspace(workspace)

    context = load_operations_app_context(
        environ={"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(workspace.root)},
        assessed_at=datetime(2026, 10, 3, 9, 0, tzinfo=UTC),
    )

    assert context.snapshot.paths.workspace == workspace
    assert context.actions.paths == context.snapshot.paths
    assert context.snapshot.assessed_at == datetime(2026, 10, 3, 9, 0, tzinfo=UTC)


def test_app_context_rejects_actions_from_different_path_set(tmp_path: Path) -> None:
    left = resolve_operations_app_paths(
        {"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(tmp_path / "left")}
    )
    right = resolve_operations_app_paths(
        {"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(tmp_path / "right")}
    )
    snapshot = load_operations_app_context(
        environ={"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(tmp_path / "left")},
        assessed_at=datetime(2026, 10, 3, 9, 0, tzinfo=UTC),
    ).snapshot

    with pytest.raises(ValueError, match="same Operations app paths"):
        OperationsAppContext(snapshot=snapshot, actions=OperationsAppActions(right))

    assert snapshot.paths == left
