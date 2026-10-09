"""Check actual installed-wheel rollback against one durable Operations workspace.

Executed with the isolated venv interpreter once per stage after reinstalling
a *specific built wheel*. Both wheels currently report 0.0.1, so a version
string alone must never be treated as evidence that rollback took place.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import replace
from http.client import HTTPConnection
from pathlib import Path
from zipfile import ZipFile

import industrial_phm
from industrial_phm.runtime import OperationsUiConfig, OperationsWorkspace
from industrial_phm.runtime.operations_config import (
    load_operations_runtime_config,
    write_operations_runtime_config,
)

_PROBE_MEMBER = "industrial_phm/runtime/operations_deployment.py"
_STAGE_SOURCES = {
    "previous": (),
    "upgraded": ("wheel-previous",),
    "rolled-back": ("wheel-previous", "wheel-upgraded"),
}


def _installed_wheel_identity(wheel: Path) -> str:
    """Compare wheel bytes with the actual installed module, not dist version."""
    with ZipFile(wheel) as archive:
        expected = archive.read(_PROBE_MEMBER)
    installed_root = Path(industrial_phm.__file__).resolve().parent
    installed_module = (installed_root / "runtime" / "operations_deployment.py").read_bytes()
    assert installed_module == expected, "wheel bytes do not match installed package"
    assert installed_root.is_relative_to(Path(sys.prefix).resolve()), installed_root
    checkout = os.getenv("GITHUB_WORKSPACE")
    if checkout:
        assert not installed_root.is_relative_to(Path(checkout).resolve())
    return hashlib.sha256(installed_module).hexdigest()


def _cli(binary: Path, cwd: Path, *args: str) -> None:
    process = subprocess.run(
        [str(binary), *args], cwd=cwd, capture_output=True, text=True, timeout=40
    )
    assert process.returncode == 0, (
        f"installed CLI {args!r} failed: {process.stdout[-1500:]} {process.stderr[-1500:]}"
    )


def _port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
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
    body = None
    headers = {"Host": f"127.0.0.1:{port}"}
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
    code, data = _http(port, route, payload=payload, csrf=csrf)
    result = json.loads(data)
    assert isinstance(result, dict), route
    return code, result


def _source(source_id: str) -> dict[str, object]:
    return {
        "source_id": source_id,
        "name": "Rollback file " + source_id,
        "asset_id": "pump-rollback",
        "file_path": f"inputs/{source_id}.csv",
        "channel_columns": ["phase-R", "phase-S", "phase-T"],
        "measurement_point_id": "panel",
        "timestamp_column": "timestamp",
    }


def _inventory(port: int, expected: tuple[str, ...]) -> None:
    status, listing = _json(port, "/api/v1/sources")
    assert status == 200, listing
    inventory = listing["sources"]
    assert isinstance(inventory, dict)
    records = inventory["items"]
    assert isinstance(records, list)
    assert inventory["total"] == len(expected)
    assert sorted(item["source_id"] for item in records) == sorted(expected)
    assert all(item["receipt_confirmed"] is False for item in records)


def _supervised_stage(binary: Path, root: Path, cwd: Path, phase: str, port: int) -> None:
    log_path = cwd / f"supervisor-{phase}.log"
    with log_path.open("wb") as output:
        child = subprocess.Popen(
            [str(binary), "operations", "start", str(root), "--ui", "web-controlled"],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
        )
    try:
        session = None
        deadline = time.monotonic() + 55
        while time.monotonic() < deadline:
            assert child.poll() is None, log_path.read_text(errors="replace")[-3500:]
            try:
                status, session_result = _json(port, "/api/v1/session")
                if status == 200:
                    session = session_result
                    break
            except OSError, ValueError:
                pass
            time.sleep(0.2)
        assert session is not None, log_path.read_text(errors="replace")[-3500:]
        assert session["write_scope"] == "supervisor-owned-source-control"
        csrf = session["csrf_token"]
        assert isinstance(csrf, str) and len(csrf) >= 32

        assert _http(port, "/web/")[0] == 200
        assert _http(port, "/web/app.js")[0] == 200
        assert _json(port, "/api/v1/monitor")[0] == 200
        expected = _STAGE_SOURCES[phase]
        _inventory(port, expected)

        source_id = "wheel-" + phase
        inputs = root / "inputs"
        inputs.mkdir(exist_ok=True)
        (inputs / f"{source_id}.csv").write_text(
            "timestamp,phase-R,phase-S,phase-T\n"
            "2026-10-08T12:00:00+00:00,220.5,219.0,221.0\n"
            "2026-10-08T12:00:01+00:00,220.6,219.1,221.1\n",
            encoding="utf-8",
        )
        body = _source(source_id)
        assert _json(port, "/api/v1/sources/file", payload=body, csrf="invalid")[0] == 403
        code, registered = _json(port, "/api/v1/sources/file", payload=body, csrf=csrf)
        assert code == 201 and registered["registration_state"] == "registered"
        assert registered["receipt_confirmed"] is False
        assert _json(port, "/api/v1/sources/file", payload=body, csrf=csrf)[0] == 409
        _inventory(port, (*expected, source_id))
        _cli(binary, cwd, "operations", "stop", str(root))
        assert child.wait(timeout=25) == 0, log_path.read_text(errors="replace")[-3500:]
    finally:
        if child.poll() is None:
            subprocess.run(
                [str(binary), "operations", "stop", str(root)],
                cwd=cwd,
                check=False,
                capture_output=True,
                timeout=15,
            )
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=tuple(_STAGE_SOURCES), required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()

    if sys.platform != "linux" or not hasattr(socket, "SO_PEERCRED"):
        raise RuntimeError("previous-wheel rollback acceptance requires Linux SO_PEERCRED")
    binary = Path(sys.executable).with_name("industrial-phm")
    assert binary.is_file(), binary
    fingerprint = _installed_wheel_identity(args.wheel)
    workspace = OperationsWorkspace(args.workspace.resolve())
    cwd = workspace.root.parent
    if args.stage == "previous":
        _cli(binary, cwd, "operations", "init", str(workspace.root))
    else:
        assert workspace.config_path.is_file(), "existing workspace lost across install"

    # Each stage uses a new port so TCP TIME_WAIT from the old wheel cannot
    # masquerade as a state compatibility or reinstall failure.
    port = _port()
    config = load_operations_runtime_config(workspace.config_path)
    write_operations_runtime_config(
        workspace.config_path, replace(config, ui=OperationsUiConfig(port=port))
    )
    _cli(binary, cwd, "doctor")
    _cli(binary, cwd, "validate", "deployment", str(workspace.root))
    _supervised_stage(binary, workspace.root, cwd, args.stage, port)
    print(
        f"wheel-rollback-stage={args.stage} installed_sha256={fingerprint} "
        f"source_count={len(_STAGE_SOURCES[args.stage]) + 1}",
        flush=True,
    )


if __name__ == "__main__":
    main()
