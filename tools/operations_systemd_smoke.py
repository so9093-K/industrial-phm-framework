"""Accept the real reference systemd service with an installed wheel on Linux CI."""

from __future__ import annotations

import argparse
import grp
import json
import os
import pwd
import signal
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
from http.client import HTTPConnection
from pathlib import Path

from industrial_phm.runtime import OperationsUiConfig, OperationsWorkspace
from industrial_phm.runtime.operations_config import (
    load_operations_runtime_config,
    write_operations_runtime_config,
)


def _run(*argv: str, timeout: int = 60) -> str:
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    assert result.returncode == 0, (
        f"{argv!r} failed: {result.stdout[-1500:]} {result.stderr[-3000:]}"
    )
    return result.stdout.strip()


def _ctl(*args: str) -> str:
    return _run("sudo", "systemctl", *args, timeout=80)


def _show(unit: str, property_name: str) -> str:
    return _ctl("show", unit, f"--property={property_name}", "--value")


def _request(
    port: int, route: str, *, body: dict[str, object] | None = None, csrf: str = ""
) -> tuple[int, dict[str, object]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=8)
    payload = json.dumps(body).encode() if body is not None else None
    headers = {"Host": f"127.0.0.1:{port}"}
    if body is not None:
        headers.update(
            {
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{port}",
                "Sec-Fetch-Site": "same-origin",
                "X-CSRF-Token": csrf,
            }
        )
    try:
        conn.request("POST" if payload is not None else "GET", route, payload, headers)
        response = conn.getresponse()
        result = json.loads(response.read())
        assert isinstance(result, dict)
        return response.status, result
    finally:
        conn.close()


def _ready(unit: str, port: int, previous_pid: int = 0) -> tuple[int, str]:
    deadline = time.monotonic() + 55
    while time.monotonic() < deadline:
        pid = int(_show(unit, "MainPID"))
        if _show(unit, "ActiveState") == "active" and pid > 0 and pid != previous_pid:
            try:
                code, session = _request(port, "/api/v1/session")
                if code == 200 and session.get("write_scope") == "supervisor-owned-source-control":
                    token = session["csrf_token"]
                    assert isinstance(token, str)
                    return pid, token
            except (OSError, ValueError):
                pass
        time.sleep(0.25)
    raise AssertionError(f"systemd service did not become Web-ready: {unit}")


def _inventory(port: int) -> None:
    code, response = _request(port, "/api/v1/sources")
    assert code == 200
    inventory = response["sources"]
    assert isinstance(inventory, dict)
    assert inventory["total"] == 1
    records = inventory["items"]
    assert isinstance(records, list)
    assert [item["source_id"] for item in records] == ["systemd-file"]
    assert records[0]["receipt_confirmed"] is False


def _reference(template: Path, binary: Path, workspace: Path) -> str:
    text = template.read_text(encoding="utf-8")
    changes = {
        "User=industrial-phm": f"User={pwd.getpwuid(os.getuid()).pw_name}",
        "Group=industrial-phm": f"Group={grp.getgrgid(os.getgid()).gr_name}",
        (
            "ExecStartPre=/opt/industrial-phm/.venv/bin/industrial-phm "
            "validate deployment /var/lib/industrial-phm/plant-a"
        ): f"ExecStartPre={binary} validate deployment {workspace}",
        (
            "ExecStart=/opt/industrial-phm/.venv/bin/industrial-phm "
            "operations start /var/lib/industrial-phm/plant-a"
        ): f"ExecStart={binary} operations start {workspace} --ui web-controlled",
    }
    for old, new in changes.items():
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    for policy in ("Restart=on-failure", "KillMode=mixed", "UMask=0077", "TimeoutStopSec=60s"):
        assert policy in text, policy
    return text


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, required=True)
    opts = parser.parse_args()
    if sys.platform != "linux" or not hasattr(socket, "SO_PEERCRED"):
        raise RuntimeError("real systemd gate requires Linux peer credentials")
    # Never silently downgrade this acceptance to a mocked service manager.
    _ctl("list-units", "--no-pager")
    binary = Path(sys.executable).with_name("industrial-phm").resolve()
    assert binary.is_file() and binary.is_relative_to(Path(sys.prefix).resolve())
    checkout = os.getenv("GITHUB_WORKSPACE")
    if checkout:
        assert not binary.is_relative_to(Path(checkout).resolve())

    with tempfile.TemporaryDirectory(
        prefix="phm-systemd-", dir=os.getenv("RUNNER_TEMP")
    ) as name:
        work = Path(name).resolve()
        workspace = OperationsWorkspace(work / "plant")
        _run(str(binary), "operations", "init", str(workspace.root))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = int(sock.getsockname()[1])
        config = load_operations_runtime_config(workspace.config_path)
        write_operations_runtime_config(
            workspace.config_path, replace(config, ui=OperationsUiConfig(port=port))
        )
        inputs = workspace.root / "inputs"
        inputs.mkdir()
        (inputs / "phases.csv").write_text(
            "timestamp,phase-R,phase-S,phase-T\n"
            "2026-10-08T12:00:00+00:00,220.5,219.0,221.0\n"
            "2026-10-08T12:00:01+00:00,220.6,219.1,221.1\n",
            encoding="utf-8",
        )
        source = {
            "source_id": "systemd-file",
            "name": "systemd retained CSV",
            "asset_id": "pump-01",
            "file_path": "inputs/phases.csv",
            "channel_columns": ["phase-R", "phase-S", "phase-T"],
            "measurement_point_id": "panel",
            "timestamp_column": "timestamp",
        }
        unit = f"phm-accept-{os.getpid()}.service"
        target = Path("/run/systemd/system") / unit
        rendered = work / unit
        rendered.write_text(_reference(opts.template, binary, workspace.root))
        installed = False
        try:
            _run("sudo", "install", "-m", "0644", str(rendered), str(target))
            installed = True
            _ctl("daemon-reload")
            _run("sudo", "systemd-analyze", "verify", str(target))
            _ctl("start", unit)
            initial, csrf = _ready(unit, port)
            assert int(_show(unit, "NRestarts")) == 0
            assert _request(port, "/api/v1/sources/file", body=source, csrf="wrong")[0] == 403
            assert _request(port, "/api/v1/sources/file", body=source, csrf=csrf)[0] == 201
            _inventory(port)

            _ctl("restart", unit)
            restarted, _ = _ready(unit, port, previous_pid=initial)
            _inventory(port)

            # Kill a *managed UI child*, not the service itself. The supervisor
            # must exit nonzero and systemd must restart it by Restart=on-failure.
            children = _run("ps", "--ppid", str(restarted), "-o", "pid=,args=").splitlines()
            ui = [int(x.split(None, 1)[0]) for x in children if "operations_web_preview" in x]
            assert len(ui) == 1, children
            old_restarts = int(_show(unit, "NRestarts"))
            os.kill(ui[0], signal.SIGKILL)
            deadline = time.monotonic() + 70
            auto = 0
            while time.monotonic() < deadline:
                if int(_show(unit, "NRestarts")) > old_restarts:
                    try:
                        auto, _ = _ready(unit, port, previous_pid=restarted)
                        break
                    except AssertionError:
                        pass
                time.sleep(0.3)
            assert auto > 0 and auto != restarted
            _inventory(port)

            _ctl("stop", unit)
            assert _show(unit, "ActiveState") == "inactive"
            stopped_restarts = int(_show(unit, "NRestarts"))
            time.sleep(7)  # More than RestartSec=5s: clean stop must not restart.
            assert _show(unit, "ActiveState") == "inactive"
            assert int(_show(unit, "NRestarts")) == stopped_restarts
            print("systemd-web=passed start=1 manual-restart=1 "
                  "child-failure-restart=1 clean-stop=1", flush=True)
        finally:
            if installed:
                for command in (
                    ("systemctl", "stop", unit),
                    ("systemctl", "reset-failed", unit),
                    ("rm", "-f", str(target)),
                    ("systemctl", "daemon-reload"),
                ):
                    subprocess.run(
                        ("sudo", *command), capture_output=True, check=False, timeout=75
                    )


if __name__ == "__main__":
    _main()
