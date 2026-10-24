"""The default Web bundle is manifest-only; the canonical entry serves no unlisted assets."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPConnection
from importlib.resources import files
from pathlib import Path
from threading import Thread

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


def _get(port: int, path: str, **headers: str) -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=6)
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        return (
            response.status,
            {key.lower(): value for key, value in response.getheaders()},
            response.read(),
        )
    finally:
        connection.close()


def test_default_web_is_manifest_only_and_same_origin(tmp_path: Path) -> None:
    built = files("industrial_phm.apps").joinpath("web_next")
    manifest = json.loads(built.joinpath("asset-manifest.json").read_text())
    assert "index.html" in manifest
    assert any(name.startswith("assets/") and name.endswith(".js") for name in manifest)
    with _server(tmp_path / "preview") as port:
        for name in manifest:
            path = "/web/" + ("" if name == "index.html" else name)
            status, headers, body = _get(port, path)
            assert status == 200 and body == built.joinpath(*name.split("/")).read_bytes()
            assert headers["content-length"] == str(len(body))
            assert headers["cache-control"] == "no-store"
            assert headers["x-content-type-options"] == "nosniff"
            assert headers["x-frame-options"] == "DENY"
            assert "script-src 'self'" in headers["content-security-policy"]
            assert "connect-src 'self'" in headers["content-security-policy"]
            assert "frame-ancestors 'none'" in headers["content-security-policy"]
            assert "access-control-allow-origin" not in headers
        assert b"/web/assets/" in _get(port, "/web/?page=system")[2]
        status, headers, body = _get(port, "/web?page=system&monitor_asset=a%2Fb")
        assert status == 308 and not body
        assert headers["location"] == "/web/?page=system&monitor_asset=a%2Fb"
        assert headers["cache-control"] == "no-store"
        for path in [
            "/web/asset-manifest.json",
            "/web/../config.toml",
            "/web/index.html",
            "/web/assets/not-listed.js",
            "/web/assets/../asset-manifest.json",
            "/web/%2e%2e/config.toml",
            "/web/app.js",
            "/web/styles.css",
            "/web/example-motor.csv",
            "/web/research-results.json",
            "/web/" + next(name for name in manifest if name.endswith(".js")) + "?path=../../.env",
        ]:
            assert _get(port, path)[0] == 404, path
        for path in ("/web/", "/web", "/web/" + manifest[0]):
            assert _get(port, path, Host="evil.test")[0] == 403
            assert _get(port, path, Origin="https://evil.test")[0] == 403


def test_missing_default_bundle_fails_explicitly(tmp_path: Path, monkeypatch) -> None:
    from industrial_phm.runtime import operations_web_http

    monkeypatch.setattr(operations_web_http, "files", lambda _package: tmp_path / "missing")
    with _server(tmp_path / "unbuilt") as port:
        status, _, body = _get(port, "/web/")
        assert status == 503
        assert json.loads(body) == {"error": {"code": "web_assets_unavailable"}}


def test_default_entry_missing_from_manifest_is_unavailable(tmp_path: Path, monkeypatch) -> None:
    from industrial_phm.runtime import operations_web_http

    (tmp_path / "web_next").mkdir()
    (tmp_path / "web_next/asset-manifest.json").write_text("[]")
    monkeypatch.setattr(operations_web_http, "files", lambda _package: tmp_path)
    with _server(tmp_path / "missing-entry") as port:
        status, _, body = _get(port, "/web/")
        assert status == 503
        assert json.loads(body) == {"error": {"code": "web_assets_unavailable"}}
