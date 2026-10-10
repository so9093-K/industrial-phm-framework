"""First-run sample lifecycle owned by the Operations UI process."""

from __future__ import annotations

import atexit
import socket
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from industrial_phm.demo.process import (
    DemoChildProcess,
    launch_logged_process,
    stop_demo_child,
    wait_for_loopback_listener,
)
from industrial_phm.runtime.operations_config import load_operations_runtime_config
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

_CLI_BOOTSTRAP = "from industrial_phm.cli import main; raise SystemExit(main())"
_SAMPLE_STARTUP_TIMEOUT_SECONDS = 15.0
_SAMPLE_PROCESS: DemoChildProcess | None = None
_SAMPLE_LAUNCH: FirstRunSampleLaunch | None = None
_CLEANUP_REGISTERED = False


@dataclass(frozen=True, slots=True)
class FirstRunSampleLaunch:
    """One isolated synthetic demo launched from the first-run experience."""

    workspace: Path
    url: str
    opcua_port: int
    ui_port: int


ProcessLauncher = Callable[[tuple[str, ...], Path], DemoChildProcess]
ListenerWaiter = Callable[..., None]
PortResolver = Callable[[int, set[int]], int]


def launch_first_run_sample(
    workspace: OperationsWorkspace,
    *,
    process_launcher: ProcessLauncher = launch_logged_process,
    listener_waiter: ListenerWaiter = wait_for_loopback_listener,
    port_resolver: PortResolver | None = None,
) -> FirstRunSampleLaunch:
    """Launch the existing synthetic demo in a workspace isolated from real data."""

    global _CLEANUP_REGISTERED, _SAMPLE_LAUNCH, _SAMPLE_PROCESS

    if not isinstance(workspace, OperationsWorkspace):
        raise ValueError("workspace must be an OperationsWorkspace")
    if _SAMPLE_PROCESS is not None and _SAMPLE_PROCESS.poll() is None:
        if _SAMPLE_LAUNCH is None:
            raise RuntimeError("sample process is running without launch metadata")
        return _SAMPLE_LAUNCH

    _SAMPLE_PROCESS = None
    _SAMPLE_LAUNCH = None

    config = load_operations_runtime_config(workspace.config_path)
    resolve_port = _first_available_loopback_port if port_resolver is None else port_resolver
    ui_port = resolve_port(max(1024, config.ui.port + 1), {config.ui.port})
    opcua_port = resolve_port(4841, {config.ui.port, ui_port})
    sample_workspace = workspace.root.parent / f"demo-synthetic-{ui_port}-{opcua_port}"
    launch = FirstRunSampleLaunch(
        workspace=sample_workspace,
        url=f"http://127.0.0.1:{ui_port}",
        opcua_port=opcua_port,
        ui_port=ui_port,
    )
    argv = (
        sys.executable,
        "-c",
        _CLI_BOOTSTRAP,
        "demo",
        "synthetic",
        "--workspace",
        str(sample_workspace),
        "--opcua-port",
        str(opcua_port),
        "--ui-port",
        str(ui_port),
        "--startup-timeout-seconds",
        str(_SAMPLE_STARTUP_TIMEOUT_SECONDS),
    )
    process = process_launcher(argv, workspace.logs_path / "first-run-sample.log")
    try:
        listener_waiter(
            ui_port,
            process,
            timeout_seconds=_SAMPLE_STARTUP_TIMEOUT_SECONDS,
        )
    except BaseException:
        stop_demo_child(process)
        raise

    _SAMPLE_PROCESS = process
    _SAMPLE_LAUNCH = launch
    if not _CLEANUP_REGISTERED:
        atexit.register(stop_first_run_sample)
        _CLEANUP_REGISTERED = True
    return launch


def current_first_run_sample() -> FirstRunSampleLaunch | None:
    """Return only a live sample owned by this process, never a stale launch URL."""
    if _SAMPLE_PROCESS is None or _SAMPLE_LAUNCH is None:
        return None
    if _SAMPLE_PROCESS.poll() is not None:
        return None
    return _SAMPLE_LAUNCH


def stop_first_run_sample() -> None:
    """Stop the sample process owned by this Operations UI process."""

    global _SAMPLE_LAUNCH, _SAMPLE_PROCESS

    process = _SAMPLE_PROCESS
    _SAMPLE_PROCESS = None
    _SAMPLE_LAUNCH = None
    if process is not None:
        stop_demo_child(process)


def _first_available_loopback_port(start: int, excluded: set[int]) -> int:
    if isinstance(start, bool) or not isinstance(start, int) or not 1 <= start <= 65535:
        raise ValueError("start must be an integer between 1 and 65535")
    if any(
        isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535
        for port in excluded
    ):
        raise ValueError("excluded ports must be integers between 1 and 65535")

    for port in range(start, 65536):
        if port in excluded:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    raise RuntimeError(f"no loopback port is available at or above {start}")
