"""Deterministic launch plan for local Operations service processes."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from industrial_phm.apps import operations_app_path
from industrial_phm.runtime.operations_config import OperationsRuntimeConfig
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

_CLI_BOOTSTRAP = "from industrial_phm.cli import main; raise SystemExit(main())"
OPERATIONS_UI_HOST = "127.0.0.1"
OPERATIONS_WORKSPACE_ENV = "INDUSTRIAL_PHM_OPERATIONS_WORKSPACE"


class OperationsComponentKind(StrEnum):
    """Independent local processes managed by the Operations runtime."""

    COLLECTION = "collection"
    ANALYSIS = "analysis"
    UI = "ui"


@dataclass(frozen=True, slots=True)
class OperationsComponentLaunch:
    """One child-process command, environment projection and log destination."""

    kind: OperationsComponentKind
    argv: tuple[str, ...]
    log_path: Path
    env_overrides: tuple[tuple[str, str], ...] = ()
    clear_env: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, OperationsComponentKind):
            raise ValueError("kind must be OperationsComponentKind")
        if not self.argv or any(not isinstance(item, str) or not item for item in self.argv):
            raise ValueError("argv must contain non-empty strings")
        if not isinstance(self.log_path, Path):
            raise ValueError("log_path must be Path")
        override_keys = []
        for key, value in self.env_overrides:
            if not isinstance(key, str) or not key or not isinstance(value, str):
                raise ValueError(
                    "env_overrides must contain non-empty string keys and string values"
                )
            override_keys.append(key)
        if len(override_keys) != len(set(override_keys)):
            raise ValueError("env_overrides must not contain duplicate keys")
        if any(not isinstance(key, str) or not key for key in self.clear_env):
            raise ValueError("clear_env must contain non-empty strings")
        if len(self.clear_env) != len(set(self.clear_env)):
            raise ValueError("clear_env must not contain duplicate keys")


@dataclass(frozen=True, slots=True)
class OperationsRuntimePlan:
    """Workspace/config-resolved process topology without process side effects."""

    workspace: OperationsWorkspace
    config: OperationsRuntimeConfig
    components: tuple[OperationsComponentLaunch, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.workspace, OperationsWorkspace):
            raise ValueError("workspace must be OperationsWorkspace")
        if not isinstance(self.config, OperationsRuntimeConfig):
            raise ValueError("config must be OperationsRuntimeConfig")
        kinds = tuple(component.kind for component in self.components)
        if kinds != tuple(OperationsComponentKind):
            raise ValueError(
                "components must contain collection, analysis and ui in canonical order"
            )

    @property
    def ui_url(self) -> str:
        return f"http://{OPERATIONS_UI_HOST}:{self.config.ui.port}"


def build_operations_runtime_plan(
    workspace: OperationsWorkspace,
    config: OperationsRuntimeConfig,
) -> OperationsRuntimePlan:
    """Build the local process set from one authoritative workspace config."""
    collection = config.collection
    analysis = config.analysis

    collection_argv = (
        sys.executable,
        "-c",
        _CLI_BOOTSTRAP,
        "internal",
        "collection-service",
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
        "internal",
        "window-analysis",
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

    ui_argv = (
        sys.executable,
        "-m",
        "marimo",
        "run",
        str(operations_app_path()),
        "--headless",
        "--no-token",
        "--host",
        OPERATIONS_UI_HOST,
        "--port",
        str(config.ui.port),
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
            OperationsComponentLaunch(
                OperationsComponentKind.UI,
                ui_argv,
                workspace.logs_path / "ui.log",
                env_overrides=((OPERATIONS_WORKSPACE_ENV, str(workspace.root)),),
            ),
        ),
    )
