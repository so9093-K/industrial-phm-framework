"""Cross-action, cross-process supervised HTTP mutations preserve each durable event."""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from dataclasses import replace
from http.client import HTTPConnection
from pathlib import Path

import pytest

from industrial_phm.application import (
    JsonFindingReviewRepository,
    JsonOperationalFindingRepository,
    JsonSourceRepository,
    SqlitePhaseUnbalanceRepository,
)
from industrial_phm.runtime import (
    OperationsUiConfig,
    OperationsWorkspace,
    initialize_operations_workspace,
)
from industrial_phm.runtime.operations_config import write_operations_runtime_config
from tests.acceptance.test_operations_web_controlled_journey_browser import _port, _start, _stop
from tests.support.window_analysis import phase_unbalance_analysis


_CLIENT = """
import json
import sys
import time
from http.client import HTTPConnection
from pathlib import Path

port, token, identity, ready, release, route, body = sys.argv[1:]
Path(ready, identity).touch()
deadline = time.monotonic() + 30
while not Path(release).is_file():
    if time.monotonic() >= deadline:
        raise TimeoutError("HTTP release gate was never opened")
    time.sleep(0.01)
connection = HTTPConnection("127.0.0.1", int(port), timeout=20)
try:
    connection.request(
        "POST", route, body=body,
        headers={
            "Host": f"127.0.0.1:{port}",
            "Origin": f"http://127.0.0.1:{port}",
            "Sec-Fetch-Site": "same-origin",
            "X-CSRF-Token": token,
            "Content-Type": "application/json",
        },
    )
    response = connection.getresponse()
    print(json.dumps({"status": response.status, "body": json.loads(response.read())}))
finally:
    connection.close()
"""


def test_supervisor_serializes_concurrent_file_review_and_replay_across_restart(
    tmp_path: Path,
) -> None:
    """Independent HTTP clients may not lose notes or multiply evidence-linked findings."""
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux peer credentials required")
    pytest.importorskip("duckdb")
    pytest.importorskip("filelock")

    workspace = OperationsWorkspace(tmp_path / "mixed-commands")
    initialized = initialize_operations_workspace(workspace)
    port = _port()
    write_operations_runtime_config(
        workspace.config_path, replace(initialized.config, ui=OperationsUiConfig(port=port))
    )
    analysis = phase_unbalance_analysis()
    SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path).record(analysis)
    inputs = workspace.root / "inputs"
    inputs.mkdir()
    (inputs / "phase.csv").write_text(
        "timestamp,phase-R,phase-S,phase-T\n"
        "2026-10-01T00:00:00+00:00,220.5,219.0,221.0\n",
        encoding="utf-8",
    )

    def request(
        method: str,
        route: str,
        *,
        body: dict[str, object] | None = None,
        token: str = "",
    ) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", port, timeout=15)
        headers = {"Host": f"127.0.0.1:{port}"}
        payload = None
        if body is not None:
            payload = json.dumps(body)
            headers.update(
                {
                    "Origin": f"http://127.0.0.1:{port}",
                    "Sec-Fetch-Site": "same-origin",
                    "Content-Type": "application/json",
                    "X-CSRF-Token": token,
                }
            )
        try:
            connection.request(method, route, body=payload, headers=headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    review_request = {
        "analysis_run_id": analysis.run.analysis_run_id,
        "evidence_id": analysis.evidence.evidence_id,
    }
    sources = [
        {
            "source_id": f"mixed-file-{index}",
            "name": f"FILE {index}",
            "asset_id": analysis.run.asset_id,
            "measurement_point_id": "panel",
            "file_path": "inputs/phase.csv",
            "channel_columns": ["phase-R", "phase-S", "phase-T"],
            "timestamp_column": "timestamp",
        }
        for index in range(3)
    ]
    notes = [f"Concurrent operator note {index}" for index in range(4)]
    log = tmp_path / "supervisor.log"
    clients: list[subprocess.Popen[bytes]] = []
    proc = _start(workspace.root, port, log)
    try:
        status, session = request("GET", "/api/v1/session")
        assert status == 200
        assert session["write_scope"] == "supervisor-owned-source-control"
        token = session["csrf_token"]
        assert isinstance(token, str)
        status, created = request(
            "POST", "/api/v1/reviews/request", body=review_request, token=token
        )
        assert status == 201
        finding_id = created["finding_id"]
        assert isinstance(finding_id, str)
        assert created["evidence_ids"] == [analysis.evidence.evidence_id]

        # Every subprocess starts from its own PID and is released together.
        # Only the bound Web child may forward these commands to the broker.
        tasks: list[tuple[str, dict[str, object], int]] = [
            ("/api/v1/sources/file", source, 201) for source in sources
        ]
        tasks.extend(("/api/v1/reviews/request", review_request, 201) for _ in range(3))
        tasks.extend(
            (
                "/api/v1/reviews/action",
                {"finding_id": finding_id, "action": "note", "note": note},
                200,
            )
            for note in notes
        )
        ready = tmp_path / "ready"
        ready.mkdir()
        release = tmp_path / "release"
        for index, (route, payload, _) in enumerate(tasks):
            clients.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        _CLIENT,
                        str(port),
                        token,
                        str(index),
                        str(ready),
                        str(release),
                        route,
                        json.dumps(payload),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            )
        deadline = time.monotonic() + 30
        while len(list(ready.iterdir())) != len(tasks):
            if any(client.poll() is not None for client in clients):
                pytest.fail("a subprocess exited before the cross-action release gate")
            if time.monotonic() >= deadline:
                pytest.fail("cross-action clients never reached the release gate")
            time.sleep(0.02)
        release.touch()
        for client, (route, _payload, expected) in zip(clients, tasks, strict=True):
            stdout, stderr = client.communicate(timeout=35)
            assert client.returncode == 0, stderr.decode(errors="replace")
            response = json.loads(stdout)
            assert response["status"] == expected, (route, response)
            if route == "/api/v1/sources/file":
                assert response["body"]["receipt_confirmed"] is False
            else:
                assert response["body"]["finding_id"] == finding_id
                assert response["body"]["status"] == "open"

        assert sorted(
            source.source_id
            for source in JsonSourceRepository(workspace.source_registry_path).list_sources()
        ) == [source["source_id"] for source in sources]
        findings = JsonOperationalFindingRepository(workspace.finding_state_path).list_findings()
        assert len(findings) == 1 and findings[0].finding_id == finding_id
        events = JsonFindingReviewRepository(workspace.maintenance_review_state_path).list_events()
        assert sorted(event.note for event in events) == sorted(notes)
        assert len({event.event_id for event in events}) == len(notes)
        assert all(event.action.value == "note" for event in events)
        assert not workspace.history_catalog_path.exists()
        status, listing = request("GET", "/api/v1/sources")
        assert status == 200 and listing["sources"]["total"] == len(sources)
        assert all(item["receipt_confirmed"] is False for item in listing["sources"]["items"])
    finally:
        for client in clients:
            if client.poll() is None:
                client.kill()
                client.communicate(timeout=10)
        _stop(proc, workspace.root)
    assert proc.returncode == 0, log.read_text(errors="replace")[-4000:]

    # A fresh supervisor generation keeps committed evidence and events, but
    # cannot replay the old CSRF capability or guarantee transport exactly-once.
    proc = _start(workspace.root, port, log)
    try:
        status, new_session = request("GET", "/api/v1/session")
        assert status == 200
        new_token = new_session["csrf_token"]
        assert isinstance(new_token, str) and new_token != token
        status, denied = request(
            "POST",
            "/api/v1/reviews/action",
            body={"finding_id": finding_id, "action": "note", "note": "stale"},
            token=token,
        )
        assert status == 403 and denied == {"error": {"code": "write_not_authorized"}}
        status, finding = request(
            "POST", "/api/v1/reviews/request", body=review_request, token=new_token
        )
        assert status == 201
        assert finding["finding_id"] == finding_id and finding["status"] == "open"
        status, duplicate = request(
            "POST", "/api/v1/sources/file", body=sources[0], token=new_token
        )
        assert status == 409 and duplicate == {"error": {"code": "source_id_exists"}}
        assert len(JsonOperationalFindingRepository(workspace.finding_state_path).list_findings()) == 1
        assert len(JsonSourceRepository(workspace.source_registry_path).list_sources()) == 3
        events = JsonFindingReviewRepository(workspace.maintenance_review_state_path).list_events()
        assert sorted(event.note for event in events) == sorted(notes)
        assert not workspace.history_catalog_path.exists()
    finally:
        _stop(proc, workspace.root)
    assert proc.returncode == 0, log.read_text(errors="replace")[-4000:]
