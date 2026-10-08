"""FILE Web registration security and receipt semantics against real workspace files."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.application import (
    JsonSourceRepository,
    SourceReceiptEvidence,
)
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_app_composition import load_operations_app_snapshot
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from industrial_phm.runtime.operations_web_setup import project_web_source_setup


def _request(
    port: int,
    method: str,
    route: str,
    *,
    body: bytes | None = None,
    origin: str | None = None,
    csrf: str | None = None,
    content_type: str = "application/json",
    fetch_site: str | None = None,
) -> tuple[int, dict[str, object]]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Host": f"127.0.0.1:{port}"}
    if origin is not None:
        headers["Origin"] = origin
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if fetch_site is not None:
        headers["Sec-Fetch-Site"] = fetch_site
    if body is not None:
        headers["Content-Type"] = content_type
    try:
        connection.request(method, route, body=body, headers=headers)
        response = connection.getresponse()
        result = json.loads(response.read())
        assert isinstance(result, dict)
        return response.status, result
    finally:
        connection.close()


def _payload(path: str = "inputs/phases.csv") -> dict[str, object]:
    return {
        "source_id": "registered-file-01",
        "name": "Three phase file",
        "asset_id": "pump-01",
        "file_path": path,
        "channel_columns": ["phase-R", "phase-S", "phase-T"],
        "measurement_point_id": "panel",
        "timestamp_column": "timestamp",
    }


def test_workspace_file_registration_protected_and_not_mistaken_for_receipt(
    tmp_path: Path,
) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant")
    initialize_operations_workspace(workspace)
    folder = workspace.root / "inputs"
    folder.mkdir()
    (folder / "phases.csv").write_text(
        "timestamp,phase-R,phase-S,phase-T\n"
        "2026-10-08T12:00:00+00:00,220.5,219.0,221.0\n"
        "2026-10-08T12:00:01+00:00,220.6,219.1,221.1\n",
        encoding="utf-8",
    )
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_port
        origin = f"http://127.0.0.1:{port}"
        status, session = _request(port, "GET", "/api/v1/session")
        assert status == HTTPStatus.OK
        csrf = session["csrf_token"]
        assert isinstance(csrf, str) and len(csrf) > 32
        source_body = json.dumps(_payload()).encode("utf-8")
        route = "/api/v1/sources/file"

        def post(
            *,
            data: bytes = source_body,
            from_origin: str | None = origin,
            site: str | None = "same-origin",
            token: str | None = csrf,
        ) -> tuple[int, dict[str, object]]:
            return _request(
                port,
                "POST",
                route,
                body=data,
                origin=from_origin,
                fetch_site=site,
                csrf=token,
            )

        assert post(from_origin=None, site=None, token=None)[0] == 403
        assert post(token=None)[0] == 403
        assert post(from_origin="https://evil.example")[0] == 403
        assert post(site="cross-site")[0] == 403
        assert post(token="fake")[0] == 403
        assert post(data=b"x" * 5000)[0] == 400
        for path in ("../outside.csv", "/tmp/outside.csv", "inputs/../../outside.csv"):
            assert post(data=json.dumps(_payload(path)).encode("utf-8"))[0] == 400
        outside = tmp_path / "outside.csv"
        outside.write_text("timestamp,phase-R\\n", encoding="utf-8")
        (folder / "linked.csv").symlink_to(outside)
        assert post(data=json.dumps(_payload("inputs/linked.csv")).encode("utf-8"))[0] == 400

        status, created = post()
        assert status == HTTPStatus.CREATED
        assert created["registration_state"] == "registered"
        assert created["receipt_confirmed"] is False
        assert "phases.csv" not in str(created)
        stored = JsonSourceRepository(workspace.source_registry_path).get("registered-file-01")
        assert stored.asset_id == "pump-01"
        assert post()[0] == HTTPStatus.CONFLICT
        status, sources = _request(port, "GET", "/api/v1/sources")
        assert status == 200
        assert sources["sources"]["total"] == 1
        assert sources["sources"]["items"][0]["receipt_confirmed"] is False
        assert sources["sources"]["items"][0]["last_accepted_received_at"] is None
        assert "phases.csv" not in str(sources)
        file_collection = json.dumps(
            {"source_id": "registered-file-01", "target_state": "running"}
        ).encode()
        assert (
            _request(
                port,
                "POST",
                "/api/v1/sources/collection",
                body=file_collection,
                origin=origin,
                fetch_site="same-origin",
                csrf=csrf,
            )[0]
            == HTTPStatus.CONFLICT
        )
        assert _request(port, "POST", "/api/v1/monitor", body=source_body)[0] == 405
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_source_setup_projects_real_receipt_separately(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant")
    initialize_operations_workspace(workspace)
    snapshot = load_operations_app_snapshot(
        environ={"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(workspace.root)}
    )
    assert project_web_source_setup(snapshot)["sources"]["total"] == 0
    receipt = SourceReceiptEvidence(
        source_id="unregistered-test",
        received_at=datetime(2026, 10, 8, 11, 30, tzinfo=UTC),
        observed_at=datetime(2026, 10, 8, 11, 28, tzinfo=UTC),
    )
    # An orphan receipt cannot be counted as a configured data source.
    orphan = project_web_source_setup(replace(snapshot, receipts=(receipt,)))
    assert orphan["sources"]["total"] == 0


@pytest.mark.parametrize(
    "filename",
    ["../escape.csv", "absolute.csv"],
)
def test_file_registration_does_not_register_missing_paths(tmp_path: Path, filename: str) -> None:
    from industrial_phm.runtime.operations_web_setup import register_workspace_csv_source

    workspace = OperationsWorkspace(tmp_path / "plant")
    initialize_operations_workspace(workspace)
    with pytest.raises((OSError, ValueError)):
        register_workspace_csv_source(workspace.root.resolve(), _payload(filename))
    assert JsonSourceRepository(workspace.source_registry_path).list_sources() == ()


def test_web_source_controls_durable_request_not_receipt(tmp_path: Path) -> None:
    from industrial_phm.application import (
        CollectionDesiredState,
        JsonSourceRepository,
        OpcUaSourceConfig,
        RegisteredSource,
    )
    from industrial_phm.connectors import OpcUaNodeMapping
    from industrial_phm.runtime.collection_control import SqliteCollectionControlRepository

    workspace = OperationsWorkspace(tmp_path / "controls")
    initialize_operations_workspace(workspace)
    JsonSourceRepository(workspace.source_registry_path).register(
        RegisteredSource(
            source_id="opcua-1",
            name="OPC UA source",
            config=OpcUaSourceConfig(
                endpoint_url="opc.tcp://127.0.0.1:4840",
                asset_id="motor-01",
                node_mappings=(OpcUaNodeMapping(channel_id="v-r", node_id="ns=2;s=V_R"),),
            ),
            registered_at=datetime(2026, 10, 8, 11, 0, tzinfo=UTC),
        )
    )
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_port
        origin = f"http://127.0.0.1:{port}"
        _, session = _request(port, "GET", "/api/v1/session")
        csrf = session["csrf_token"]

        def action(
            route: str,
            target: str,
            *,
            token: str | None = csrf,
            source_id: str = "opcua-1",
            from_origin: str = origin,
        ) -> tuple[int, dict[str, object]]:
            return _request(
                port,
                "POST",
                "/api/v1/sources/" + route,
                body=json.dumps({"source_id": source_id, "target_state": target}).encode(),
                origin=from_origin,
                fetch_site="same-origin",
                csrf=token,
            )

        assert action("collection", "running")[0] == 409
        assert action("lifecycle", "active", source_id="unknown")[0] == 404
        assert action("collection", "running", source_id="unknown")[0] == 404
        assert action("lifecycle", "active", from_origin="https://evil.example")[0] == 403
        assert action("lifecycle", "active", token=None)[0] == 403
        assert action("lifecycle", "active")[0] == 200
        assert action("lifecycle", "active")[0] == 409
        assert action("collection", "running")[0] == 200
        assert action("collection", "running")[1]["meaning"] == (
            "desired-state-only-not-running-or-received"
        )
        assert (
            SqliteCollectionControlRepository(workspace.collection_control_path)
            .get("opcua-1")
            .desired_state
            == CollectionDesiredState.RUNNING
        )
        _, sources = _request(port, "GET", "/api/v1/sources")
        row = sources["sources"]["items"][0]
        assert row["lifecycle_state"] == "active"
        assert row["collection_desired_state"] == "running"
        assert row["collection_request_generation"] == 1
        assert row["receipt_confirmed"] is False
        assert row["last_accepted_received_at"] is None
        assert "opc.tcp" not in str(sources)
        assert action("lifecycle", "paused")[0] == 200
        assert action("collection", "stopped")[0] == 200
        assert action("collection", "running")[0] == 409
        assert action("collection", "bogus")[0] == 400
        assert action("lifecycle", "bogus")[0] == 400
        assert action("collection", "running", token="bogus")[0] == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_web_file_receipt_requires_active_and_persists_only_acceptance(tmp_path: Path) -> None:
    from industrial_phm.application import JsonSourceRuntimeRepository

    workspace = OperationsWorkspace(tmp_path / "file-receipt")
    initialize_operations_workspace(workspace)
    folder = workspace.root / "inputs"
    folder.mkdir()
    file_path = folder / "phase.csv"
    file_path.write_text(
        "timestamp,phase-R,phase-S,phase-T\n"
        "2026-10-08T12:00:00+00:00,220.5,219.0,221.0\n"
        "2026-10-08T12:00:01+00:00,220.6,219.1,221.1\n",
        encoding="utf-8",
    )
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_port
        origin = f"http://127.0.0.1:{port}"
        _, session = _request(port, "GET", "/api/v1/session")
        csrf = session["csrf_token"]

        def command(route: str, payload: dict[str, object], *, token: str | None = csrf):
            return _request(
                port,
                "POST",
                "/api/v1/sources/" + route,
                body=json.dumps(payload).encode(),
                origin=origin,
                fetch_site="same-origin",
                csrf=token,
            )

        assert command("file", _payload("inputs/phase.csv"))[0] == 201
        receive = {"source_id": "registered-file-01"}
        assert command("file/receive", receive)[0] == 409
        assert command("file/receive", receive, token=None)[0] == 403
        assert command("file/receive", {"source_id": "unknown"})[0] == 404
        assert command("file/receive", {"source_id": "registered-file-01", "extra": "x"})[0] == 400
        assert (
            command("lifecycle", {"source_id": "registered-file-01", "target_state": "active"})[0]
            == 200
        )

        status, accepted = command("file/receive", receive)
        assert status == 200
        assert accepted["cycle_state"] == "succeeded"
        assert accepted["accepted_new_receipt"] is True
        assert accepted["meaning"] == "file-receipt-only-not-history-backfill"
        assert accepted["accepted_received_at"] is not None
        stored = JsonSourceRuntimeRepository(workspace.source_runtime_path).get_latest_receipt(
            "registered-file-01"
        )
        assert stored is not None
        assert accepted["accepted_received_at"] == stored.received_at.isoformat().replace(
            "+00:00", "Z"
        )
        status, sources = _request(port, "GET", "/api/v1/sources")
        assert status == 200
        assert sources["sources"]["items"][0]["receipt_confirmed"] is True
        assert "phase.csv" not in str(sources)
        # Receipt acceptance does not initialize historical DuckLake storage.
        assert not workspace.history_catalog_path.exists()
        assert (
            command("lifecycle", {"source_id": "registered-file-01", "target_state": "paused"})[0]
            == 200
        )
        assert command("file/receive", receive)[0] == 409
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_web_file_receipt_rejects_swapped_outside_symlink(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "swapped")
    initialize_operations_workspace(workspace)
    folder = workspace.root / "inputs"
    folder.mkdir()
    file_path = folder / "phase.csv"
    file_path.write_text(
        "timestamp,phase-R,phase-S,phase-T\n2026-10-08T12:00:00+00:00,220,219,221\n",
        encoding="utf-8",
    )
    from industrial_phm.runtime.operations_web_setup import (
        SourceControlConflict,
        change_web_source_control,
        receive_workspace_file_source,
        register_workspace_csv_source,
    )

    register_workspace_csv_source(workspace.root.resolve(), _payload("inputs/phase.csv"))
    change_web_source_control(
        workspace.root.resolve(),
        "lifecycle",
        {"source_id": "registered-file-01", "target_state": "active"},
    )
    outside = tmp_path / "outside.csv"
    outside.write_text("timestamp,phase-R\n", encoding="utf-8")
    file_path.unlink()
    file_path.symlink_to(outside)

    with pytest.raises(SourceControlConflict):
        receive_workspace_file_source(workspace.root.resolve(), {"source_id": "registered-file-01"})
    assert not workspace.source_runtime_path.exists()
