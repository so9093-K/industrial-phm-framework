"""Exercise the installed Operations wheel outside the source checkout (Linux only)."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
from http.client import HTTPConnection
from pathlib import Path

import industrial_phm
from industrial_phm.runtime import OperationsUiConfig, OperationsWorkspace
from industrial_phm.runtime.operations_config import (
    load_operations_runtime_config,
    write_operations_runtime_config,
)


def _run(binary: Path, *args: str, cwd: Path) -> None:
    result = subprocess.run(
        [str(binary), *args], cwd=cwd, capture_output=True, text=True, timeout=40
    )
    assert result.returncode == 0, (
        f"installed CLI {args!r} failed:\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}"
    )


def _free_port() -> int:
    with socket.socket() as connection:
        connection.bind(("127.0.0.1", 0))
        return int(connection.getsockname()[1])


def _http(
    port: int,
    route: str,
    *,
    payload: dict[str, object] | None = None,
    csrf: str = "",
) -> tuple[int, bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=12)
    headers = {"Host": f"127.0.0.1:{port}"}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers.update(
            {
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{port}",
                "Sec-Fetch-Site": "same-origin",
                "X-CSRF-Token": csrf,
            }
        )
    try:
        connection.request("POST" if body is not None else "GET", route, body, headers)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def _json(
    port: int,
    route: str,
    *,
    payload: dict[str, object] | None = None,
    csrf: str = "",
) -> tuple[int, dict[str, object]]:
    status, data = _http(port, route, payload=payload, csrf=csrf)
    parsed = json.loads(data)
    assert isinstance(parsed, dict), route
    return status, parsed


def _web(binary: Path, workspace: Path, *, port: int, cwd: Path, mutate: bool) -> None:
    log_path = cwd / ("restored.log" if mutate else "original.log")
    with log_path.open("wb") as log:
        supervisor = subprocess.Popen(
            [str(binary), "operations", "start", str(workspace)],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
    try:
        deadline = time.monotonic() + 55
        session: dict[str, object] | None = None
        while time.monotonic() < deadline:
            if supervisor.poll() is not None:
                raise AssertionError(f"wheel supervisor exited:\n{log_path.read_text()[-5000:]}")
            try:
                status, result = _json(port, "/api/v1/session")
                if status == 200:
                    session = result
                    break
            except OSError, ValueError:
                pass
            time.sleep(0.2)
        assert session is not None, f"wheel Web not ready:\n{log_path.read_text()[-5000:]}"
        assert session["write_scope"] == "supervisor-owned-source-control"
        csrf = session["csrf_token"]
        assert isinstance(csrf, str) and len(csrf) >= 32
        for route in ("/web/", "/web/app.js", "/web/styles.css"):
            status, content = _http(port, route)
            assert status == 200 and len(content) > 100, (route, status)
        status, monitor = _json(port, "/api/v1/monitor")
        assert status == 200 and monitor["schema_version"] == 1

        if mutate:
            inputs = workspace / "inputs"
            inputs.mkdir()
            (inputs / "phases.csv").write_text(
                "timestamp,phase-R,phase-S,phase-T\n"
                "2026-10-08T12:00:00+00:00,220.5,219.0,221.0\n"
                "2026-10-08T12:00:01+00:00,220.6,219.1,221.1\n",
                encoding="utf-8",
            )
            source = {
                "source_id": "wheel-file",
                "name": "Wheel-only CSV",
                "asset_id": "pump-01",
                "file_path": "inputs/phases.csv",
                "channel_columns": ["phase-R", "phase-S", "phase-T"],
                "measurement_point_id": "panel",
                "timestamp_column": "timestamp",
            }
            assert _json(port, "/api/v1/sources/file", payload=source, csrf="wrong")[0] == 403
            status, result = _json(port, "/api/v1/sources/file", payload=source, csrf=csrf)
            assert status == 201 and result["registration_state"] == "registered"
            assert result["receipt_confirmed"] is False
            assert _json(port, "/api/v1/sources/file", payload=source, csrf=csrf)[0] == 409

        status, inventory = _json(port, "/api/v1/sources")
        assert status == 200
        sources = inventory["sources"]
        assert isinstance(sources, dict) and sources["total"] == (1 if mutate else 0)
        if mutate:
            item = sources["items"][0]
            assert item["source_id"] == "wheel-file" and not item["receipt_confirmed"]
        _run(binary, "operations", "stop", str(workspace), cwd=cwd)
        assert supervisor.wait(timeout=25) == 0, log_path.read_text()[-5000:]
        print(f"installed-web={workspace.name} controlled_mutation={mutate}", flush=True)
    finally:
        if supervisor.poll() is None:
            subprocess.run(
                [str(binary), "operations", "stop", str(workspace)],
                cwd=cwd,
                capture_output=True,
                timeout=15,
                check=False,
            )
            try:
                supervisor.wait(timeout=15)
            except subprocess.TimeoutExpired:
                supervisor.kill()
                supervisor.wait(timeout=10)


def main() -> None:
    if sys.platform != "linux" or not hasattr(socket, "SO_PEERCRED"):
        raise RuntimeError("supervisor Web wheel test requires Linux SO_PEERCRED")
    binary = Path(sys.executable).with_name("industrial-phm")
    installed = Path(industrial_phm.__file__).resolve()
    assert binary.is_file() and installed.is_relative_to(Path(sys.prefix).resolve())
    checkout = os.environ.get("GITHUB_WORKSPACE")
    if checkout:
        assert not installed.is_relative_to(Path(checkout).resolve()), installed

    with tempfile.TemporaryDirectory(
        dir=os.getenv("RUNNER_TEMP"), prefix="phm-standalone-wheel-"
    ) as temp_dir:
        cwd = Path(temp_dir)
        original = cwd / "original"
        restored = cwd / "restored"
        port = _free_port()
        _run(binary, "doctor", cwd=cwd)
        _run(binary, "operations", "init", str(original), cwd=cwd)
        config_path = OperationsWorkspace(original).config_path
        config = load_operations_runtime_config(config_path)
        write_operations_runtime_config(
            config_path, replace(config, ui=OperationsUiConfig(port=port))
        )
        _run(binary, "validate", "deployment", str(original), cwd=cwd)
        _web(binary, original, port=port, cwd=cwd, mutate=False)

        archive = cwd / "backup"
        _run(binary, "maintenance", "backup", str(original), str(archive), cwd=cwd)
        _run(binary, "maintenance", "restore", str(archive), str(restored), cwd=cwd)
        _run(binary, "validate", "deployment", str(restored), cwd=cwd)
        _web(binary, restored, port=port, cwd=cwd, mutate=True)
        assert not (original / "inputs").exists()
    print(f"standalone-wheel=passed installed_package={installed}", flush=True)


if __name__ == "__main__":
    main()
