"""Shared safety guard for product-demo workspaces."""

from __future__ import annotations

from industrial_phm.runtime import OperationsWorkspace


def require_unclaimed_demo_workspace(workspace: OperationsWorkspace) -> None:
    """Refuse to adopt runtime/history state that has no matching demo registration."""
    if not isinstance(workspace, OperationsWorkspace):
        raise ValueError("workspace must be OperationsWorkspace")
    unexpected_files = tuple(path for path in workspace.runtime_state_files if path.exists())
    history_entries = (
        tuple(workspace.history_data_path.iterdir()) if workspace.history_data_path.is_dir() else ()
    )
    runtime_entries = (
        tuple(workspace.supervisor_state_path.parent.iterdir())
        if workspace.supervisor_state_path.parent.is_dir()
        else ()
    )
    if unexpected_files or history_entries or runtime_entries:
        raise ValueError(
            "existing Operations workspace contains runtime/history state but no matching demo source; "
            "choose another --workspace"
        )
