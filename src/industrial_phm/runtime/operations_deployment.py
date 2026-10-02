"""Deployment preflight for a long-running local Operations node."""

from __future__ import annotations

import importlib
import os
import socket
import stat
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from industrial_phm.apps import operations_app_path
from industrial_phm.runtime.operations_config import load_operations_runtime_config
from industrial_phm.runtime.operations_runtime import (
    OPERATIONS_UI_HOST,
    build_operations_runtime_plan,
)
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

try:
    import fcntl
except ImportError:  # pragma: no cover - reference deployment is POSIX
    fcntl = None  # type: ignore[assignment]

_OPERATIONS_RUNTIME_MODULES = ("asyncua", "duckdb", "filelock", "marimo")


class OperationsDeploymentCheckState(StrEnum):
    """One preflight finding without inventing runtime health."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True, slots=True)
class OperationsDeploymentCheck:
    """One factual deployment precondition result."""

    name: str
    state: OperationsDeploymentCheckState
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("name must not be empty")
        if not isinstance(self.state, OperationsDeploymentCheckState):
            raise ValueError("state must be OperationsDeploymentCheckState")
        if not isinstance(self.detail, str) or not self.detail.strip():
            raise ValueError("detail must not be empty")


@dataclass(frozen=True, slots=True)
class OperationsDeploymentPreflight:
    """Deployment suitability snapshot evaluated as the current service user."""

    workspace: OperationsWorkspace
    checks: tuple[OperationsDeploymentCheck, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.workspace, OperationsWorkspace):
            raise ValueError("workspace must be OperationsWorkspace")
        names = tuple(item.name for item in self.checks)
        if len(names) != len(set(names)):
            raise ValueError("deployment checks must have unique names")

    @property
    def ready(self) -> bool:
        return all(item.state != OperationsDeploymentCheckState.FAIL for item in self.checks)


def inspect_operations_deployment(
    workspace: OperationsWorkspace,
) -> OperationsDeploymentPreflight:
    """Validate the current process environment before service-manager startup."""
    if not isinstance(workspace, OperationsWorkspace):
        raise ValueError("workspace must be OperationsWorkspace")

    checks: list[OperationsDeploymentCheck] = []
    checks.append(_platform_check())
    checks.extend(_workspace_checks(workspace))

    config = None
    try:
        config = load_operations_runtime_config(workspace.config_path)
        build_operations_runtime_plan(workspace, config)
    except (OSError, RuntimeError, ValueError) as error:
        checks.append(
            OperationsDeploymentCheck(
                "config",
                OperationsDeploymentCheckState.FAIL,
                f"workspace runtime config/plan is invalid: {error}",
            )
        )
    else:
        checks.append(
            OperationsDeploymentCheck(
                "config",
                OperationsDeploymentCheckState.PASS,
                f"runtime config is valid: schema={config.schema}",
            )
        )

    checks.extend(_dependency_checks())
    checks.append(_supervisor_lock_check(workspace))
    checks.append(_history_lock_check(workspace))

    if config is not None:
        checks.append(_ui_port_check(config.ui.port))

    app_path = operations_app_path()
    checks.append(
        OperationsDeploymentCheck(
            "operations-app",
            (
                OperationsDeploymentCheckState.PASS
                if app_path.is_file() and os.access(app_path, os.R_OK)
                else OperationsDeploymentCheckState.FAIL
            ),
            (
                f"packaged Operations app is readable: {app_path}"
                if app_path.is_file() and os.access(app_path, os.R_OK)
                else f"packaged Operations app is unavailable or unreadable: {app_path}"
            ),
        )
    )
    return OperationsDeploymentPreflight(workspace, tuple(checks))


def _platform_check() -> OperationsDeploymentCheck:
    supported = os.name == "posix" and fcntl is not None
    return OperationsDeploymentCheck(
        "platform",
        (
            OperationsDeploymentCheckState.PASS
            if supported
            else OperationsDeploymentCheckState.FAIL
        ),
        (
            "POSIX advisory-lock runtime is available"
            if supported
            else "reference deployment requires POSIX advisory file locking"
        ),
    )


def _workspace_checks(workspace: OperationsWorkspace) -> list[OperationsDeploymentCheck]:
    root = workspace.root
    checks: list[OperationsDeploymentCheck] = []

    checks.append(
        OperationsDeploymentCheck(
            "workspace-path",
            (
                OperationsDeploymentCheckState.PASS
                if root.is_absolute()
                else OperationsDeploymentCheckState.FAIL
            ),
            (
                f"workspace path is absolute: {root}"
                if root.is_absolute()
                else f"deployment workspace must use an absolute path: {root}"
            ),
        )
    )
    if not root.is_dir():
        checks.append(
            OperationsDeploymentCheck(
                "workspace-access",
                OperationsDeploymentCheckState.FAIL,
                f"workspace root does not exist or is not a directory: {root}",
            )
        )
        return checks

    root_access = os.R_OK | os.W_OK | os.X_OK
    checks.append(
        OperationsDeploymentCheck(
            "workspace-access",
            (
                OperationsDeploymentCheckState.PASS
                if os.access(root, root_access)
                else OperationsDeploymentCheckState.FAIL
            ),
            (
                f"workspace is readable/writable/searchable by uid={_effective_uid()}: {root}"
                if os.access(root, root_access)
                else (
                    "workspace lacks read/write/search permission for "
                    f"uid={_effective_uid()}: {root}"
                )
            ),
        )
    )
    checks.append(_ownership_check(root, "workspace-owner"))

    if not workspace.config_path.is_file() or not os.access(workspace.config_path, os.R_OK):
        checks.append(
            OperationsDeploymentCheck(
                "config-access",
                OperationsDeploymentCheckState.FAIL,
                f"workspace config is unavailable or unreadable: {workspace.config_path}",
            )
        )
    else:
        checks.append(
            OperationsDeploymentCheck(
                "config-access",
                OperationsDeploymentCheckState.PASS,
                f"workspace config is readable: {workspace.config_path}",
            )
        )

    for name, path in (
        ("history-data-access", workspace.history_data_path),
        ("logs-access", workspace.logs_path),
    ):
        usable = path.is_dir() and os.access(path, os.R_OK | os.W_OK | os.X_OK)
        checks.append(
            OperationsDeploymentCheck(
                name,
                (
                    OperationsDeploymentCheckState.PASS
                    if usable
                    else OperationsDeploymentCheckState.FAIL
                ),
                (
                    f"directory is readable/writable/searchable: {path}"
                    if usable
                    else (
                        "directory is unavailable or not writable by "
                        f"uid={_effective_uid()}: {path}"
                    )
                ),
            )
        )
        if path.exists():
            checks.append(_ownership_check(path, f"{name}-owner"))

    bad_state_files = tuple(
        path
        for path in workspace.runtime_state_files
        if path.exists() and (not path.is_file() or not os.access(path, os.R_OK | os.W_OK))
    )
    checks.append(
        OperationsDeploymentCheck(
            "state-access",
            (
                OperationsDeploymentCheckState.PASS
                if not bad_state_files
                else OperationsDeploymentCheckState.FAIL
            ),
            (
                "existing workspace state files are readable/writable"
                if not bad_state_files
                else "workspace state files are not readable/writable: "
                + ", ".join(str(path) for path in bad_state_files)
            ),
        )
    )
    return checks


def _effective_uid() -> int:
    getter = getattr(os, "geteuid", None)
    return -1 if getter is None else int(getter())


def _ownership_check(path: Path, name: str) -> OperationsDeploymentCheck:
    info = path.stat()
    world_writable = bool(info.st_mode & stat.S_IWOTH)
    same_owner = info.st_uid == _effective_uid()
    if world_writable:
        return OperationsDeploymentCheck(
            name,
            OperationsDeploymentCheckState.WARN,
            (
                f"path is world-writable: uid={info.st_uid} "
                f"mode={stat.filemode(info.st_mode)} path={path}"
            ),
        )
    if not same_owner:
        return OperationsDeploymentCheck(
            name,
            OperationsDeploymentCheckState.WARN,
            (
                f"path owner differs from current service uid={_effective_uid()}: "
                f"owner_uid={info.st_uid} mode={stat.filemode(info.st_mode)} path={path}"
            ),
        )
    return OperationsDeploymentCheck(
        name,
        OperationsDeploymentCheckState.PASS,
        f"path owner matches current uid={_effective_uid()}: {path}",
    )


def _dependency_checks() -> list[OperationsDeploymentCheck]:
    checks: list[OperationsDeploymentCheck] = []
    for module_name in _OPERATIONS_RUNTIME_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as error:
            checks.append(
                OperationsDeploymentCheck(
                    f"dependency-{module_name}",
                    OperationsDeploymentCheckState.FAIL,
                    f"cannot import {module_name}: {type(error).__name__}: {error}",
                )
            )
        else:
            checks.append(
                OperationsDeploymentCheck(
                    f"dependency-{module_name}",
                    OperationsDeploymentCheckState.PASS,
                    f"runtime dependency imports successfully: {module_name}",
                )
            )
    return checks


def _supervisor_lock_check(workspace: OperationsWorkspace) -> OperationsDeploymentCheck:
    if fcntl is None or os.name != "posix":
        return OperationsDeploymentCheck(
            "supervisor-lock",
            OperationsDeploymentCheckState.FAIL,
            "cannot validate supervisor ownership without POSIX advisory locking",
        )
    lock_path = workspace.supervisor_lock_path
    if not lock_path.exists():
        return OperationsDeploymentCheck(
            "supervisor-lock",
            OperationsDeploymentCheckState.PASS,
            "no existing supervisor lock file",
        )
    try:
        with lock_path.open("a+") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return OperationsDeploymentCheck(
                    "supervisor-lock",
                    OperationsDeploymentCheckState.FAIL,
                    f"workspace supervisor is already running or lock is owned: {lock_path}",
                )
            finally:
                with suppress(OSError):
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError as error:
        return OperationsDeploymentCheck(
            "supervisor-lock",
            OperationsDeploymentCheckState.FAIL,
            f"cannot inspect supervisor lock: {error}",
        )
    return OperationsDeploymentCheck(
        "supervisor-lock",
        OperationsDeploymentCheckState.PASS,
        "supervisor lock is available for service startup",
    )


def _history_lock_check(workspace: OperationsWorkspace) -> OperationsDeploymentCheck:
    if not workspace.history_catalog_path.exists():
        return OperationsDeploymentCheck(
            "history-lock",
            OperationsDeploymentCheckState.PASS,
            "history catalog does not exist yet; no history lock is required",
        )
    try:
        filelock = importlib.import_module("filelock")
        lock = filelock.FileLock(str(workspace.history_catalog_path) + ".phm.lock")
        lock.acquire(timeout=0)
    except Exception as error:
        return OperationsDeploymentCheck(
            "history-lock",
            OperationsDeploymentCheckState.FAIL,
            f"history catalog lock is unavailable: {type(error).__name__}: {error}",
        )
    else:
        lock.release()
        return OperationsDeploymentCheck(
            "history-lock",
            OperationsDeploymentCheckState.PASS,
            "history catalog lock is available for service startup",
        )


def _ui_port_check(port: int) -> OperationsDeploymentCheck:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind((OPERATIONS_UI_HOST, port))
    except OSError as error:
        return OperationsDeploymentCheck(
            "ui-port",
            OperationsDeploymentCheckState.FAIL,
            f"cannot bind local Operations UI at {OPERATIONS_UI_HOST}:{port}: {error}",
        )
    return OperationsDeploymentCheck(
        "ui-port",
        OperationsDeploymentCheckState.PASS,
        f"local Operations UI port is available: {OPERATIONS_UI_HOST}:{port}",
    )
