"""Shared helpers for PHM product acceptance runs through the real supervised Operations node."""

from __future__ import annotations

import json
import re
import socket
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CLI = [str(Path(sys.executable).with_name("industrial-phm"))]


def cli(*args: str, check: bool = True, timeout: float = 1800) -> str:
    completed = subprocess.run(
        [*CLI, *args], capture_output=True, text=True, timeout=timeout, check=False
    )
    if check and completed.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed: {completed.stdout}\n{completed.stderr}")
    return completed.stdout + completed.stderr


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def set_config(workspace: Path, section: str, key: str, value: str) -> None:
    path = workspace / "config.toml"
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"(\[{section}\][^\[]*?^{key} = )[^\n]*", re.S | re.M)
    if not pattern.search(text):
        raise RuntimeError(f"{section}.{key} not found in {path}")
    path.write_text(pattern.sub(rf"\g<1>{value}", text, count=1), encoding="utf-8")


@dataclass
class Supervisor:
    """Foreground `operations start` run as a child, with explicit stop/restart."""

    workspace: Path
    log: Path
    process: subprocess.Popen[bytes] | None = None
    starts: list[dict[str, float]] = field(default_factory=list)

    def start(self, timeout: float = 120) -> float:
        began = time.monotonic()
        handle = self.log.open("ab")
        self.process = subprocess.Popen(
            [*CLI, "operations", "start", str(self.workspace)],
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        while time.monotonic() - began < timeout:
            if self.process.poll() is not None:
                raise RuntimeError(f"supervisor exited early; see {self.log}")
            if "ready=yes" in cli("operations", "status", str(self.workspace), check=False):
                elapsed = time.monotonic() - began
                self.starts.append({"ready_seconds": elapsed})
                return elapsed
            time.sleep(0.5)
        raise RuntimeError("supervisor did not become ready")

    def stop(self, timeout: float = 90) -> float:
        began = time.monotonic()
        cli("operations", "stop", str(self.workspace), check=False)
        if self.process is not None:
            self.process.wait(timeout=timeout)
        return time.monotonic() - began


def percentiles(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "p50": None, "p95": None, "max": None}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]
    return {
        "count": len(ordered),
        "p50": round(statistics.median(ordered), 3),
        "p95": round(p95, 3),
        "max": round(ordered[-1], 3),
    }


def wait_until(predicate: Callable[[], bool], timeout: float, interval: float = 0.5) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def utc(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n")


@dataclass
class Checks:
    items: list[dict[str, Any]] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: Any = None) -> bool:
        self.items.append({"name": name, "pass": bool(passed), "detail": detail})
        print(
            f"{'PASS' if passed else 'FAIL'} {name} {'' if detail is None else detail}", flush=True
        )
        return bool(passed)

    @property
    def passed(self) -> bool:
        return all(item["pass"] for item in self.items)
