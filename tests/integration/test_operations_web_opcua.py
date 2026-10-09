"""Real loopback OPC UA Web browse, mapping and one-shot receipt contracts."""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from http.client import HTTPConnection
from pathlib import Path
from threading import Event, Thread

import pytest

from industrial_phm.application import JsonSourceRepository, JsonSourceRuntimeRepository
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


@contextmanager
def _web(workspace: OperationsWorkspace) -> Iterator[int]:
    server = create_operations_web_read_server(workspace.root)
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


@contextmanager
def _opc_server() -> Iterator[tuple[str, str]]:
    asyncua = pytest.importorskip("asyncua")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = int(sock.getsockname()[1])
    endpoint = f"opc.tcp://127.0.0.1:{port}/industrial-phm/"
    ready, stopped = Event(), Event()
    captured: dict[str, object] = {}

    async def serve() -> None:
        server = asyncua.Server()
        await server.init()
        server.set_endpoint(endpoint)
        namespace = await server.register_namespace("urn:industrial-phm:web-opcua")
        machine = await server.nodes.objects.add_object(namespace, "Machine")
        vibration = await machine.add_variable(namespace, "VibrationX", 12.5)
        captured["node_id"] = vibration.nodeid.to_string()
        async with server:
            ready.set()
            while not stopped.is_set():
                await asyncio.sleep(0.05)

    def runner() -> None:
        try:
            asyncio.run(serve())
        except Exception as error:
            captured["error"] = error
            ready.set()

    thread = Thread(target=runner, daemon=True)
    thread.start()
    try:
        assert ready.wait(30), "local OPC UA fixture did not start"
        assert "error" not in captured, str(captured.get("error"))
        yield endpoint, str(captured["node_id"])
    finally:
        stopped.set()
        thread.join(timeout=30)
        assert not thread.is_alive()


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
        assert _post(
            port, "/api/v1/sources/opcua/browse",
            {"endpoint_url": "opc.tcp://example.com:4840/"}, token
        )[0] == 400
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
    with _opc_server() as (endpoint, node_id), _web(workspace) as port:
        _, session = _http(port, "/api/v1/session")
        token = session["csrf_token"]
        status, browse = _post(
            port, "/api/v1/sources/opcua/browse", {"endpoint_url": endpoint}, token
        )
        assert status == 200
        assert browse["meaning"] == "address-space-candidates-not-received-or-registered"
        assert any(v["node_id"] == node_id for v in browse["variables"])
        assert not workspace.source_runtime_path.exists()

        registration = _registration(endpoint, node_id)
        assert _post(port, "/api/v1/sources/opcua", registration, token)[0] == 201
        registry = JsonSourceRepository(workspace.source_registry_path)
        assert registry.get("web-opcua-1").asset_id == "pump-01"
        status, sources = _http(port, "/api/v1/sources")
        assert status == 200
        assert sources["sources"]["items"][0]["receipt_confirmed"] is False
        assert _post(
            port,
            "/api/v1/sources/lifecycle",
            {"source_id": "web-opcua-1", "target_state": "active"},
            token,
        )[0] == 200
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
        assert "opc.tcp://" not in str(sources)
        assert not workspace.history_catalog_path.exists()


def test_web_opcua_full_browser_flow(tmp_path: Path) -> None:
    sync_api = pytest.importorskip("playwright.sync_api")
    pytest.importorskip("asyncua")
    workspace = OperationsWorkspace(tmp_path / "opcua-browser")
    initialize_operations_workspace(workspace)
    with (
        _opc_server() as (endpoint, node_id),
        _web(workspace) as port,
        sync_api.sync_playwright() as playwright,
    ):
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1024, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"http://127.0.0.1:{port}/web/", wait_until="networkidle")
        page.locator("#opcua-endpoint").fill(endpoint)
        page.get_by_role("button", name="로컬 변수 탐색").click()
        sync_api.expect(page.locator("#opcua-browse-result")).to_contain_text(node_id)
        sync_api.expect(page.locator("#source-list")).to_contain_text("등록 소스가 없습니다")
        page.locator('#opcua-form input[name="source_id"]').fill("web-opcua-1")
        page.locator('#opcua-form input[name="name"]').fill("OPC UA browser")
        page.locator('#opcua-form input[name="asset_id"]').fill("pump-01")
        page.locator('#opcua-form textarea[name="node_mappings"]').fill(
            "vibration_x=" + node_id
        )
        page.get_by_role("button", name="OPC UA 매핑 등록").click()
        listing = page.locator("#source-list")
        sync_api.expect(listing).to_contain_text("web-opcua-1")
        sync_api.expect(listing).to_contain_text("수신 근거 미확인")
        page.on("dialog", lambda dialog: dialog.accept())
        listing.get_by_role("button", name="소스 활성화").click()
        sync_api.expect(listing).to_contain_text("관리 상태: active")
        listing.get_by_role("button", name="OPC UA 1회 수신 진단").click()
        sync_api.expect(page.locator("#source-control-result")).to_contain_text(
            "수신 근거 기록 완료"
        )
        sync_api.expect(listing).to_contain_text("실제 수신 근거 있음")
        assert not page.locator("#last-values .latest-item").count()
        assert not workspace.history_catalog_path.exists()
        assert not errors, errors
        browser.close()
