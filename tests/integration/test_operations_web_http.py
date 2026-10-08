"""Local-only read API contract and browser-origin protections."""

import json
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


def _request(port: int, method: str, path: str, *, host: str | None = None,
             origin: str | None = None, site: str | None = None):
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Host": host if host is not None else f"127.0.0.1:{port}"}
    if origin is not None:
        headers["Origin"] = origin
    if site is not None:
        headers["Sec-Fetch-Site"] = site
    try:
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        body = response.read()
        return response.status, dict(response.getheaders()), json.loads(body)
    finally:
        connection.close()


def test_local_operations_web_read_http_is_bounded_and_origin_checked(
    tmp_path: Path,
) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    initialize_operations_workspace(workspace)
    server = create_operations_web_read_server(workspace.root, port=0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert server.server_address[0] == "127.0.0.1"
        port = server.server_port
        status, headers, payload = _request(port, "GET", "/api/v1/monitor")
        assert status == 200
        assert payload["schema_version"] == 1
        assert payload["assets"]["items"] == []
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert "Access-Control-Allow-Origin" not in headers

        assert _request(port, "GET", "/api/v1/monitor", host="rebind.example")[0] == 403
        assert _request(port, "GET", "/api/v1/monitor", origin="https://evil.example")[0] == 403
        assert _request(port, "GET", "/api/v1/monitor", site="cross-site")[0] == 403
        assert _request(port, "GET", "/api/v1/monitor?path=extra")[0] == 404
        assert _request(port, "POST", "/api/v1/monitor")[0] == 405
        assert _request(port, "OPTIONS", "/api/v1/monitor")[0] == 405
        assert _request(
            port,
            "GET",
            "/api/v1/monitor",
            origin=f"http://127.0.0.1:{port}",
            site="same-origin",
        )[0] == 200
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_web_read_server_rejects_unknown_workspace(tmp_path: Path) -> None:
    try:
        create_operations_web_read_server(tmp_path / "missing")
    except ValueError as error:
        assert "workspace_root" in str(error)
    else:
        raise AssertionError("server accepted unknown workspace")
