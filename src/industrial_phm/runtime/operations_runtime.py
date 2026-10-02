"""Deterministic launch plan for local Operations service processes."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from industrial_phm.runtime.operations_config import OperationsRuntimeConfig
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

_CLI_BOOTSTRAP = "from industrial_phm.cli import main; raise SystemExit(main())"


class OperationsComponentKind(StrEnum):
    """Independent local processes currently managed by the service runtime."""

    COLLECTION = "collection"
    ANALYSIS = "analysis"


@dataclass(frozen=True, slots=True)
class OperationsComponentLaunch:
    """One child-process command and its workspace-owned log destination."""

    kind: OperationsComponentKind
    argv: tuple[str, ...]
    log_path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.kind, OperationsComponentKind):
            raise ValueError("kind must be OperationsComponentKind")
        if not self.argv or any(not isinstance(item, str) or not item for item in self.argv):
            raise ValueError("argv must contain non-empty strings")
        if not isinstance(self.log_path, Path):
            raise ValueError("log_path must be Path")


@dataclass(frozen=True, slots=True)
class OperationsRuntimePlan:
    """Workspace/config-resolved service topology without process side effects."""

    workspace: OperationsWorkspace
    config: OperationsRuntimeConfig
    components: tuple[OperationsComponentLaunch, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.workspace, OperationsWorkspace):
            raise ValueError("workspace must be OperationsWorkspace")
        if not isinstance(self.config, OperationsRuntimeConfig):
            raise ValueError("config must be OperationsRuntimeConfig")
        kinds = tuple(component.kind for component in self.components)
        if kinds != (
            OperationsComponentKind.COLLECTION,
            OperationsComponentKind.ANALYSIS,
        ):
            raise ValueError("components must contain collection then analysis exactly once")


def build_operations_runtime_plan(
    workspace: OperationsWorkspace,
    config: OperationsRuntimeConfig,
) -> OperationsRuntimePlan:
    """Build the current local service plan from one authoritative workspace config."""
    collection = config.collection
    analysis = config.analysis

    collection_argv = (
        sys.executable,
        "-c",
        _CLI_BOOTSTRAP,
        "operations",
        "run-collection-service",
        "--workspace",
        str(workspace.root),
        "--reconcile-interval-seconds",
        str(collection.reconcile_interval_seconds),
        "--window-duration-seconds",
        str(collection.window_duration_seconds),
        "--allowed-lateness-seconds",
        str(collection.allowed_lateness_seconds),
    )

    analysis_args = [
        sys.executable,
        "-c",
        _CLI_BOOTSTRAP,
        "operations",
        "run-window-analysis",
        "--workspace",
        str(workspace.root),
        "--interval-seconds",
        str(analysis.poll_interval_seconds),
        "--alignment",
        analysis.alignment,
    ]
    if analysis.alignment == "bounded-previous":
        if analysis.max_carry_age_seconds is None or analysis.alignment_basis is None:
            raise ValueError("bounded-previous config is missing carry age or basis")
        analysis_args.extend(
            (
                "--max-carry-age-seconds",
                str(analysis.max_carry_age_seconds),
                "--alignment-basis",
                analysis.alignment_basis,
            )
        )

    return OperationsRuntimePlan(
        workspace=workspace,
        config=config,
        components=(
            OperationsComponentLaunch(
                OperationsComponentKind.COLLECTION,
                collection_argv,
                workspace.logs_path / "collection.log",
            ),
            OperationsComponentLaunch(
                OperationsComponentKind.ANALYSIS,
                tuple(analysis_args),
                workspace.logs_path / "analysis.log",
            ),
        ),
    )
