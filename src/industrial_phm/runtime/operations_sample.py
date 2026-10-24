"""Isolated first-run data investigation lifecycle owned by the Operations supervisor."""

from __future__ import annotations

import atexit
import os
import socket
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from industrial_phm.demo.process import (
    DemoChildProcess,
    launch_logged_process,
    stop_demo_child,
    wait_for_loopback_listener,
)
from industrial_phm.runtime.operations_config import (
    load_operations_runtime_config,
    write_operations_runtime_config,
)
from industrial_phm.runtime.operations_demo_context import read_bearing_journey
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

_CLI_BOOTSTRAP = "from industrial_phm.cli import main; raise SystemExit(main())"
# The nested demo starts a simulator, supervisor, collector and Web Python workers.
# A packaged Docker cold start can legitimately exceed 15 seconds; still bound
# the single startup attempt and only return after the real Web listener answers.
_SAMPLE_STARTUP_TIMEOUT_SECONDS = 60.0
_SAMPLE_PROCESS: DemoChildProcess | None = None
_SAMPLE_LAUNCH: FirstRunSampleLaunch | None = None
_CLEANUP_REGISTERED = False


@dataclass(frozen=True, slots=True)
class FirstRunSampleLaunch:
    """One isolated data experience launched from the first-run experience."""

    workspace: Path
    url: str
    opcua_port: int
    ui_port: int
    scenario: str = "live"
    asset_id: str | None = None


ProcessLauncher = Callable[[tuple[str, ...], Path], DemoChildProcess]
ListenerWaiter = Callable[..., None]
PortResolver = Callable[[int, set[int]], int]


def prepared_xjtu_workspace(parent: OperationsWorkspace) -> OperationsWorkspace | None:
    """An administrator-selected, already prepared local replay; never a browser path."""
    configured = os.environ.get("INDUSTRIAL_PHM_XJTU_WORKSPACE")
    if not configured:
        return None
    candidate = OperationsWorkspace(Path(configured).resolve())
    if (
        candidate.root == parent.root
        or candidate.root in parent.root.parents
        or parent.root in candidate.root.parents
    ):
        return None
    journey = read_bearing_journey(candidate.root)
    if not journey or journey["dataset"] != "xjtu-sy":
        return None
    if not candidate.config_path.is_file() or not candidate.acquisition_snapshot_path.is_file():
        return None
    return candidate


def launch_first_run_sample(
    workspace: OperationsWorkspace,
    *,
    process_launcher: ProcessLauncher = launch_logged_process,
    listener_waiter: ListenerWaiter = wait_for_loopback_listener,
    port_resolver: PortResolver | None = None,
    scenario: str = "live",
) -> FirstRunSampleLaunch:
    """Launch a prepared real replay or generated example in its own workspace."""

    global _CLEANUP_REGISTERED, _SAMPLE_LAUNCH, _SAMPLE_PROCESS

    if not isinstance(workspace, OperationsWorkspace):
        raise ValueError("workspace must be an OperationsWorkspace")
    if scenario not in {"live", "bearing", "xjtu"}:
        raise ValueError("unknown example scenario")
    if _SAMPLE_PROCESS is not None and _SAMPLE_PROCESS.poll() is None:
        if _SAMPLE_LAUNCH is None:
            raise RuntimeError("sample process is running without launch metadata")
        if _SAMPLE_LAUNCH.scenario != scenario:
            raise ValueError("다른 예시가 실행 중입니다. 실행 중인 예시를 종료한 뒤 시작하세요.")
        return _SAMPLE_LAUNCH

    _SAMPLE_PROCESS = None
    _SAMPLE_LAUNCH = None

    config = load_operations_runtime_config(workspace.config_path)
    resolve_port = _first_available_loopback_port if port_resolver is None else port_resolver
    fixed_port = os.environ.get("INDUSTRIAL_PHM_SAMPLE_UI_PORT")
    start_port = int(fixed_port) if fixed_port is not None else max(1024, config.ui.port + 1)
    if not 1024 <= start_port <= 65535 or start_port == config.ui.port:
        raise ValueError("example UI port must be distinct and between 1024 and 65535")
    ui_port = resolve_port(start_port, {config.ui.port})
    if fixed_port is not None and ui_port != start_port:
        raise RuntimeError(
            f"예시 화면 포트 {start_port}가 사용 중입니다. 기존 예시를 종료한 뒤 다시 시작하세요."
        )
    opcua_port = resolve_port(4841, {config.ui.port, ui_port})
    sample_workspace = workspace.root.parent / (
        f"demo-synthetic-{ui_port}-{opcua_port}"
        if scenario == "live"
        else f"demo-bearing-v1-{ui_port}"
    )
    asset_id = None
    if scenario == "xjtu":
        prepared = prepared_xjtu_workspace(workspace)
        if prepared is None:
            raise ValueError("준비된 XJTU-SY 작업공간이 없습니다. 로컬 데이터로 먼저 준비하세요.")
        from industrial_phm.runtime import supervisor_is_live

        if supervisor_is_live(prepared):
            raise ValueError(
                "XJTU-SY 작업공간이 별도로 실행 중입니다. 해당 실행을 종료한 뒤 여세요."
            )
        sample_workspace = prepared.root
        journey = read_bearing_journey(prepared.root)
        assert journey is not None
        asset_id = journey["asset_id"]
        prepared_config = load_operations_runtime_config(prepared.config_path)
        write_operations_runtime_config(
            prepared.config_path,
            replace(prepared_config, ui=replace(prepared_config.ui, port=ui_port)),
        )
    launch = FirstRunSampleLaunch(
        workspace=sample_workspace,
        url=f"http://127.0.0.1:{ui_port}/web/",
        opcua_port=opcua_port,
        ui_port=ui_port,
        scenario=scenario,
        asset_id=asset_id,
    )
    argv = (
        sys.executable,
        "-c",
        _CLI_BOOTSTRAP,
        "demo",
        "synthetic" if scenario == "live" else "bearing",
        "--workspace",
        str(sample_workspace),
        "--ui-port",
        str(ui_port),
        *(
            (
                "--opcua-port",
                str(opcua_port),
                "--startup-timeout-seconds",
                str(_SAMPLE_STARTUP_TIMEOUT_SECONDS),
            )
            if scenario == "live"
            else ()
        ),
    )
    if scenario == "xjtu":
        argv = (sys.executable, "-c", _CLI_BOOTSTRAP, "operations", "up", str(sample_workspace))
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
    """Stop the sample process owned by this supervisor process."""

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
            # Match the HTTP server's allow_reuse_address. A stopped listener's TCP
            # TIME_WAIT connections must not move the sample outside the published port.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    raise RuntimeError(f"no loopback port is available at or above {start}")
