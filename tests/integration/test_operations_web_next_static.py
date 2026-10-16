"""Compiled Svelte pilot assets must stay scoped to a packaged, safe, read-only route."""

from __future__ import annotations

import json
from contextlib import contextmanager
from http.client import HTTPConnection
from importlib.resources import files
from pathlib import Path
from threading import Thread
from typing import Iterator

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


@contextmanager
def _server(root: Path) -> Iterator[int]:
    workspace = OperationsWorkspace(root)
    initialize_operations_workspace(workspace)
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


def _get(port: int, path: str, *, host: str | None = None) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=6)
    try:
        connection.request(
            "GET", path, headers={"Host": host or f"127.0.0.1:{port}"}
        )
        response = connection.getresponse()
        headers = {key.lower(): value for key, value in response.getheaders()}
        return response.status, headers, response.read()
    finally:
        connection.close()


def test_packaged_web_next_is_manifest_only_and_same_origin(tmp_path: Path) -> None:
    built = files("industrial_phm.apps").joinpath("web_next")
    manifest = json.loads(built.joinpath("asset-manifest.json").read_text())
    assert "index.html" in manifest
    assert any(name.startswith("assets/") and name.endswith(".js") for name in manifest)
    assert all(built.joinpath(*name.split("/")).is_file() for name in manifest)

    with _server(tmp_path / "preview") as port:
        status, headers, html = _get(port, "/web-next/")
        assert status == 200
        assert headers["content-type"] == "text/html; charset=utf-8"
        assert headers["cache-control"] == "no-store"
        assert "script-src 'self'" in headers["content-security-policy"]
        assert b"/web-next/assets/" in html
        for name in manifest:
            if name == "index.html":
                continue
            code, asset_headers, body = _get(port, "/web-next/" + name)
            assert code == 200
            assert body
            assert asset_headers["x-content-type-options"] == "nosniff"
        for path in [
            "/web-next/asset-manifest.json",
            "/web-next/../web/styles.css",
            "/web-next/assets/not-listed.js",
            "/web-next/assets/../asset-manifest.json",
            "/web-next/%2e%2e/web/app.js",
        ]:
            code, _, _ = _get(port, path)
            assert code == 404
        code, _, _ = _get(port, "/web-next/", host="evil.test")
        assert code == 403
        code, _, original = _get(port, "/web/")
        assert code == 200
        assert b"/web/app.js" in original
