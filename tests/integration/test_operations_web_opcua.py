"""Real loopback OPC UA Web browse, mapping and one-shot receipt contracts."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.application import JsonSourceRepository, JsonSourceRuntimeRepository
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.opcua import local_opcua_server


@contextmanager
def _web(workspace: OperationsWorkspace, *, controlled: bool = False) -> Iterator[int]:
    from tests.support.web_next import InProcessSupervisor

    client = InProcessSupervisor(workspace.root) if controlled else None
    server = create_operations_web_read_server(workspace.root, command_client=client)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()


def _http(
    port: int,
    route: str,
    payload: dict[str, object] | None = None,
    *,
    csrf: str | None = None,
    origin: str | None = None,
    fetch_site: str | None = None,
) -> tuple[int, dict[str, object]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=20)
    headers = {"Host": f"127.0.0.1:{port}"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if origin is not None:
        headers["Origin"] = origin
    if fetch_site is not None:
        headers["Sec-Fetch-Site"] = fetch_site
    try:
        conn.request(
            "GET" if payload is None else "POST",
            route,
            body=None if payload is None else json.dumps(payload).encode(),
            headers=headers,
        )
        response = conn.getresponse()
        data = json.loads(response.read())
        assert isinstance(data, dict)
        return response.status, data
    finally:
        conn.close()


def _post(
    port: int, route: str, payload: dict[str, object], csrf: str
) -> tuple[int, dict[str, object]]:
    return _http(
        port,
        route,
        payload,
        csrf=csrf,
        origin=f"http://127.0.0.1:{port}",
        fetch_site="same-origin",
    )


def _registration(endpoint: str, node_id: str = "ns=2;i=1") -> dict[str, object]:
    return {
        "source_id": "web-opcua-1",
        "name": "Loopback OPC UA",
        "asset_id": "pump-01",
        "measurement_point_id": "",
        "endpoint_url": endpoint,
        "node_mappings": [{"channel_id": "vibration_x", "node_id": node_id}],
    }


def test_opcua_web_denies_remote_urls_and_requires_auth(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "opcua-security")
    initialize_operations_workspace(workspace)
    with _web(workspace) as port:
        _, session = _http(port, "/api/v1/session")
        token = session["csrf_token"]
        assert isinstance(token, str)
        endpoint = "opc.tcp://127.0.0.1:4840/"
        route = "/api/v1/sources/opcua"
        diagnostic = "/api/v1/sources/opcua/diagnose"
        mapping = _registration(endpoint)
        assert _http(port, route, mapping)[0] == 403
        for rejected in (
            "opc.tcp://example.com:4840/",
            "opc.tcp://127.0.0.2:4840/",
            "opc.tcp://admin:pw@127.0.0.1:4840/",
        ):
            assert _post(port, route, _registration(rejected), token)[0] == 400
        assert _post(port, route, {**mapping, "extra": 1}, token)[0] == 400
        assert (
            _post(
                port,
                "/api/v1/sources/opcua/browse",
                {"endpoint_url": "opc.tcp://example.com:4840/"},
                token,
            )[0]
            == 400
        )
        for bad_browse in (
            {"endpoint_url": endpoint, "start_node_id": ""},
            {"endpoint_url": endpoint, "start_node_id": "x" * 129},
            {"endpoint_url": endpoint, "start_node_id": 100},
            {"endpoint_url": endpoint, "start_node_id": "i=85", "unexpected": True},
        ):
            assert _post(port, "/api/v1/sources/opcua/browse", bad_browse, token)[0] == 400
        assert _post(port, diagnostic, {"source_id": "unknown"}, token)[0] == 404
        assert _post(port, route, mapping, token)[0] == 201
        assert _post(port, route, mapping, token)[0] == 409
        assert _post(port, diagnostic, {"source_id": "web-opcua-1"}, token)[0] == 409
        runtime = JsonSourceRuntimeRepository(workspace.source_runtime_path)
        assert runtime.get_latest_receipt("web-opcua-1") is None
        assert not workspace.history_catalog_path.exists()


def test_web_browse_and_diagnostic_persist_real_opcua_receipt(tmp_path: Path) -> None:
    pytest.importorskip("asyncua")
    workspace = OperationsWorkspace(tmp_path / "opcua-receipt")
    initialize_operations_workspace(workspace)
    with local_opcua_server() as (endpoint, node_id), _web(workspace) as port:
        _, session = _http(port, "/api/v1/session")
        token = session["csrf_token"]
        status, browse = _post(
            port, "/api/v1/sources/opcua/browse", {"endpoint_url": endpoint}, token
        )
        assert status == 200
        assert browse["meaning"] == "address-space-candidates-not-received-or-registered"
        assert any(v["node_id"] == node_id for v in browse["variables"])
        machine = next(obj for obj in browse["objects"] if obj["browse_name"] == "Machine")
        status, scoped = _post(
            port,
            "/api/v1/sources/opcua/browse",
            {"endpoint_url": endpoint, "start_node_id": machine["node_id"]},
            token,
        )
        assert status == 200
        assert scoped["start_node_id"] == machine["node_id"]
        assert any(v["node_id"] == node_id for v in scoped["variables"])
        assert scoped["visited_node_count"] < browse["visited_node_count"]
        assert not scoped["truncated"]
        assert not workspace.source_runtime_path.exists()

        registration = _registration(endpoint, node_id)
        assert _post(port, "/api/v1/sources/opcua", registration, token)[0] == 201
        registry = JsonSourceRepository(workspace.source_registry_path)
        assert registry.get("web-opcua-1").asset_id == "pump-01"
        status, sources = _http(port, "/api/v1/sources")
        assert status == 200
        assert sources["sources"]["items"][0]["receipt_confirmed"] is False
        assert (
            _post(
                port,
                "/api/v1/sources/lifecycle",
                {"source_id": "web-opcua-1", "target_state": "active"},
                token,
            )[0]
            == 200
        )
        status, diagnosed = _post(
            port, "/api/v1/sources/opcua/diagnose", {"source_id": "web-opcua-1"}, token
        )
        assert status == 200
        assert diagnosed["cycle_state"] == "succeeded"
        assert diagnosed["accepted_new_receipt"] is True
        assert diagnosed["accepted_received_at"] is not None
        assert diagnosed["meaning"] == "one-shot-opcua-read-not-continuous-collection-or-history"
        receipt = JsonSourceRuntimeRepository(workspace.source_runtime_path).get_latest_receipt(
            "web-opcua-1"
        )
        assert receipt is not None
        assert receipt.received_at <= datetime.now(UTC)
        status, sources = _http(port, "/api/v1/sources")
        assert status == 200
        row = sources["sources"]["items"][0]
        assert row["receipt_confirmed"] is True
        assert row["collection_desired_state"] is None
        assert row["collection_service_state"] is None
        assert row["collection_service_heartbeat_fresh"] is False
        assert row["opcua_session_last_state"] is None
        assert row["recent_connected_evidence"] is False
        assert row["last_live_received_at"] is None
        assert row["last_live_history_committed_at"] is None
        assert "opc.tcp://" not in str(sources)
        assert not workspace.history_catalog_path.exists()
