"""Authoritative local path layout for one Operations runtime instance."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from industrial_phm.runtime.operations_config import (
    OperationsRuntimeConfig,
    load_operations_runtime_config,
    write_operations_runtime_config,
)


@dataclass(frozen=True, slots=True)
class OperationsWorkspace:
    """Own deterministic non-secret paths below one local Operations root.

    The workspace defines locations only. Individual repositories remain authoritative
    for their contents, and service lifecycle is owned by a separate runtime layer.
    """

    root: Path

    @property
    def config_path(self) -> Path:
        """Return the user-facing runtime configuration path."""
        return self.root / "config.toml"

    @property
    def source_registry_path(self) -> Path:
        return self.root / "sources.json"

    @property
    def source_runtime_path(self) -> Path:
        return self.root / "source-runtime.json"

    @property
    def collection_control_path(self) -> Path:
        return self.root / "control.sqlite"

    @property
    def acquisition_spool_path(self) -> Path:
        return self.root / "spool.sqlite"

    @property
    def acquisition_telemetry_path(self) -> Path:
        return self.root / "telemetry.sqlite"

    @property
    def window_state_path(self) -> Path:
        return self.root / "windows.sqlite"

    @property
    def analysis_ledger_path(self) -> Path:
        return self.root / "window-analysis-ledger.sqlite"

    @property
    def file_feature_analysis_path(self) -> Path:
        """Return the canonical FILE feature-analysis result-store path."""
        return self.root / "field-analysis.json"

    @property
    def phase_unbalance_state_path(self) -> Path:
        return self.root / "phase-unbalance.sqlite"

    @property
    def analysis_runtime_path(self) -> Path:
        return self.root / "phase-unbalance-runtime.json"

    @property
    def finding_state_path(self) -> Path:
        return self.root / "findings.json"

    @property
    def maintenance_review_state_path(self) -> Path:
        return self.root / "finding-review.json"

    @property
    def history_catalog_path(self) -> Path:
        return self.root / "catalog.sqlite"

    @property
    def history_data_path(self) -> Path:
        return self.root / "data"

    @property
    def logs_path(self) -> Path:
        return self.root / "logs"

    @property
    def supervisor_state_path(self) -> Path:
        return self.root / "runtime" / "supervisor.json"

    @property
    def supervisor_lock_path(self) -> Path:
        return self.root / "runtime" / "supervisor.lock"

    @property
    def runtime_state_files(self) -> tuple[Path, ...]:
        """Return durable/local state files owned by this workspace layout."""
        return (
            self.source_registry_path,
            self.source_runtime_path,
            self.collection_control_path,
            self.acquisition_spool_path,
            self.acquisition_telemetry_path,
            self.window_state_path,
            self.analysis_ledger_path,
            self.file_feature_analysis_path,
            self.phase_unbalance_state_path,
            self.analysis_runtime_path,
            self.finding_state_path,
            self.maintenance_review_state_path,
            self.history_catalog_path,
        )

    @property
    def managed_directories(self) -> tuple[Path, ...]:
        """Return directories whose creation is owned by workspace initialization."""
        return (self.root, self.history_data_path, self.logs_path)


class OperationsWorkspaceState(StrEnum):
    """User-facing classification used before mutating one workspace root."""

    NEW = "new"
    EMPTY = "empty"
    INITIALIZED = "initialized"
    RECOGNIZED_LEGACY = "recognized-legacy"
    UNRECOGNIZED = "unrecognized"


@dataclass(frozen=True, slots=True)
class OperationsWorkspaceInspection:
    """Describe whether a root can be safely initialized, reopened, or adopted."""

    workspace: OperationsWorkspace
    state: OperationsWorkspaceState
    entries: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OperationsWorkspaceInitialization:
    """Result of creating, adopting, or reopening an initialized workspace."""

    workspace: OperationsWorkspace
    config: OperationsRuntimeConfig
    created: bool
    adopted: bool = False


def inspect_operations_workspace(workspace: OperationsWorkspace) -> OperationsWorkspaceInspection:
    """Classify a workspace root without creating, deleting, or rewriting anything."""
    if not isinstance(workspace, OperationsWorkspace):
        raise ValueError("workspace must be an OperationsWorkspace")

    root = workspace.root
    if not root.exists():
        return OperationsWorkspaceInspection(workspace, OperationsWorkspaceState.NEW)
    if not root.is_dir():
        raise OSError(f"Operations workspace root is not a directory: {root}")

    entries = tuple(sorted(path.name for path in root.iterdir()))
    if workspace.config_path.exists():
        return OperationsWorkspaceInspection(
            workspace,
            OperationsWorkspaceState.INITIALIZED,
            entries,
        )
    if not entries:
        return OperationsWorkspaceInspection(workspace, OperationsWorkspaceState.EMPTY)

    allowed_entries = {path.name for path in workspace.runtime_state_files}
    allowed_entries.update(
        {
            workspace.history_data_path.name,
            workspace.logs_path.name,
            workspace.supervisor_state_path.parent.name,
        }
    )
    if not set(entries) <= allowed_entries:
        return OperationsWorkspaceInspection(
            workspace,
            OperationsWorkspaceState.UNRECOGNIZED,
            entries,
        )

    runtime_dir = workspace.supervisor_state_path.parent
    if runtime_dir.is_dir():
        runtime_entries = {path.name for path in runtime_dir.iterdir()}
        allowed_runtime_entries = {
            workspace.supervisor_state_path.name,
            workspace.supervisor_lock_path.name,
        }
        if not runtime_entries <= allowed_runtime_entries:
            return OperationsWorkspaceInspection(
                workspace,
                OperationsWorkspaceState.UNRECOGNIZED,
                entries,
            )

    has_state_file = any(path.is_file() for path in workspace.runtime_state_files)
    has_runtime_state = runtime_dir.is_dir() and any(runtime_dir.iterdir())
    if has_state_file or has_runtime_state:
        return OperationsWorkspaceInspection(
            workspace,
            OperationsWorkspaceState.RECOGNIZED_LEGACY,
            entries,
        )

    return OperationsWorkspaceInspection(
        workspace,
        OperationsWorkspaceState.UNRECOGNIZED,
        entries,
    )


def initialize_operations_workspace(
    workspace: OperationsWorkspace,
    *,
    allow_recognized_legacy: bool = False,
) -> OperationsWorkspaceInitialization:
    """Initialize an empty workspace or explicitly adopt recognized pre-config state."""
    inspection = inspect_operations_workspace(workspace)
    root = workspace.root

    if inspection.state == OperationsWorkspaceState.INITIALIZED:
        config = load_operations_runtime_config(workspace.config_path)
        workspace.history_data_path.mkdir(parents=True, exist_ok=True)
        workspace.logs_path.mkdir(parents=True, exist_ok=True)
        return OperationsWorkspaceInitialization(workspace, config, created=False)

    if inspection.state == OperationsWorkspaceState.RECOGNIZED_LEGACY:
        if not allow_recognized_legacy:
            raise ValueError(
                f"refusing to initialize a non-empty Operations workspace without config.toml: {root}"
            )
        config = OperationsRuntimeConfig()
        write_operations_runtime_config(workspace.config_path, config)
        workspace.history_data_path.mkdir(parents=True, exist_ok=True)
        workspace.logs_path.mkdir(parents=True, exist_ok=True)
        return OperationsWorkspaceInitialization(
            workspace,
            config,
            created=False,
            adopted=True,
        )

    if inspection.state == OperationsWorkspaceState.UNRECOGNIZED:
        raise ValueError(
            f"refusing to initialize a non-empty Operations workspace without config.toml: {root}"
        )

    root.mkdir(parents=True, exist_ok=True)
    config = OperationsRuntimeConfig()
    write_operations_runtime_config(workspace.config_path, config)
    workspace.history_data_path.mkdir(parents=True, exist_ok=True)
    workspace.logs_path.mkdir(parents=True, exist_ok=True)
    return OperationsWorkspaceInitialization(workspace, config, created=True)
