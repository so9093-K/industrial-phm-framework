"""Shared local child-process primitives for packaged demos."""

from __future__ import annotations

import signal
import socket
import subprocess
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Protocol


class DemoChildProcess(Protocol):
    pid: int

    def poll(self) -> int | None: ...

    def send_signal(self, sig: int) -> None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


def launch_logged_process(argv: tuple[str, ...], log_path: Path) -> DemoChildProcess:
    """Start one demo child with bounded ownership of its log destination."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab", buffering=0) as log:
        return subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
        )


def wait_for_loopback_listener(
    port: int,
    process: DemoChildProcess,
    *,
    timeout_seconds: float,
    listener_probe: Callable[[str, int], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Wait for one loopback child listener without treating PID existence as readiness."""
    probe = loopback_listener_ready if listener_probe is None else listener_probe
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        return_code = process.poll()
        if return_code is not None:
            raise RuntimeError(f"demo child exited before readiness: code={return_code}")
        if probe("127.0.0.1", port):
            return
        sleep(0.05)
    raise RuntimeError(
        f"demo child did not listen on 127.0.0.1:{port} within {timeout_seconds:g}s"
    )


def loopback_listener_ready(host: str, port: int) -> bool:
    if host != "127.0.0.1":
        raise ValueError("demo listener probe is loopback-only")
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False


def stop_demo_child(process: DemoChildProcess) -> None:
    """Gracefully stop one demo-owned child with bounded terminate/kill fallbacks."""
    if process.poll() is not None:
        return
    try:
        process.send_signal(signal.SIGINT)
        process.wait(timeout=5.0)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        process.terminate()
        process.wait(timeout=2.0)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    with suppress(OSError):
        process.kill()
    with suppress(OSError, subprocess.TimeoutExpired):
        process.wait(timeout=2.0)
