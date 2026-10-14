"""Local-only read API contract and browser-origin protections."""

import json
from datetime import UTC, datetime, timedelta
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.application import (
    FileSourceConfig,
    InMemorySourceRepository,
    RegisteredSource,
    backfill_registered_file_source,
)
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server


def _request(
    port: int,
    method: str,
    path: str,
    *,
    host: str | None = None,
    origin: str | None = None,
    site: str | None = None,
):
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


def test_synthetic_workspace_declares_purpose_and_denies_web_writes(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "demo")
    initialize_operations_workspace(workspace)
    workspace.web_context_path.parent.mkdir(exist_ok=True)
    workspace.web_context_path.write_text('{"schema_version":1,"kind":"synthetic-demo"}')
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _, _, session = _request(server.server_port, "GET", "/api/v1/session")
        assert session["workspace_kind"] == "synthetic-demo"
        assert session["write_scope"] == "read-only-synthetic-demo"
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            origin = f"http://127.0.0.1:{server.server_port}"
            connection.request(
                "POST",
                "/api/v1/sources/file",
                body="{}",
                headers={
                    "Origin": origin,
                    "Sec-Fetch-Site": "same-origin",
                    "Content-Type": "application/json",
                    "X-CSRF-Token": session["csrf_token"],
                },
            )
            response = connection.getresponse()
            assert response.status == 403
            assert json.loads(response.read())["error"]["code"] == "synthetic_demo_read_only"
        finally:
            connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


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
        runtime_status, runtime_headers, runtime = _request(port, "GET", "/api/v1/system/runtime")
        assert runtime_status == 200
        assert runtime["schema_version"] == 1
        assert runtime["ready"] is False
        assert runtime["supervisor"]["condition"] == "unavailable"
        assert [item["kind"] for item in runtime["components"]] == [
            "collection",
            "analysis",
            "ui",
        ]
        assert "log_path" not in str(runtime)
        assert "detail" not in str(runtime)
        assert runtime_headers["Cache-Control"] == "no-store"
        assert _request(port, "GET", "/api/v1/system/runtime", host="rebind.example")[0] == 403
        assert _request(port, "GET", "/api/v1/system/runtime", site="cross-site")[0] == 403
        assert _request(port, "POST", "/api/v1/system/runtime")[0] == 405
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert "Access-Control-Allow-Origin" not in headers

        assert _request(port, "GET", "/api/v1/monitor", host="rebind.example")[0] == 403
        assert _request(port, "GET", "/api/v1/monitor", origin="https://evil.example")[0] == 403
        assert _request(port, "GET", "/api/v1/monitor", site="cross-site")[0] == 403
        assert _request(port, "GET", "/api/v1/monitor?path=extra")[0] == 404
        assert _request(port, "POST", "/api/v1/monitor")[0] == 405
        assert _request(port, "OPTIONS", "/api/v1/monitor")[0] == 405
        assert (
            _request(
                port,
                "GET",
                "/api/v1/monitor",
                origin=f"http://127.0.0.1:{port}",
                site="same-origin",
            )[0]
            == 200
        )
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


def test_history_http_query_validation_and_uninitialized_storage(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-b")
    initialize_operations_workspace(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_port
        valid = "/api/v1/history/channels?asset_id=pump-01"
        assert _request(port, "GET", valid)[0] == 503
        assert _request(port, "GET", valid, host="rebind.example")[0] == 403
        assert _request(port, "GET", valid, site="cross-site")[0] == 403
        assert _request(port, "GET", valid + "&unexpected=x")[0] == 400
        assert _request(port, "GET", valid + "&asset_id=pump-02")[0] == 400
        assert _request(port, "GET", "/api/v1/history/trend?asset_id=pump-01")[0] == 400
        assert (
            _request(
                port, "GET", "/api/v1/history/trend?asset_id=pump-01&channel_id=R&buckets=9999"
            )[0]
            == 400
        )
        assert (
            _request(
                port, "GET", "/api/v1/history/trend?asset_id=pump-01&channel_id=R&channel_id=R"
            )[0]
            == 400
        )
        assert _request(port, "POST", valid)[0] == 405
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_history_http_exposes_actual_bounded_file_observations(tmp_path: Path) -> None:
    pytest.importorskip("duckdb")
    workspace = OperationsWorkspace(tmp_path / "plant-c")
    initialize_operations_workspace(workspace)
    source_path = tmp_path / "phase-voltage.csv"
    event_at = datetime.now(UTC) - timedelta(minutes=2)
    source_path.write_text(
        "timestamp,voltage-R,voltage-S\n"
        f"{event_at.isoformat()},220.5,219.2\n"
        f"{(event_at + timedelta(seconds=1)).isoformat()},221.0,219.7\n",
        encoding="utf-8",
    )
    sources = InMemorySourceRepository()
    sources.register(
        RegisteredSource(
            source_id="file-01",
            name="Phase voltage import",
            config=FileSourceConfig(
                source_path=str(source_path),
                asset_id="pump-01",
                measurement_point_id="panel-main",
                channel_columns=("voltage-R", "voltage-S"),
                timestamp_column="timestamp",
            ),
            registered_at=event_at - timedelta(minutes=1),
        )
    )
    repository = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(
            catalog_path=workspace.history_catalog_path,
            data_path=workspace.history_data_path,
        )
    )
    result = backfill_registered_file_source(sources, repository, "file-01")
    assert result.event_count == 4
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_port
        status, _, channels = _request(port, "GET", "/api/v1/history/channels?asset_id=pump-01")
        assert status == 200
        assert channels["channels"]["items"] == ["voltage-R", "voltage-S"]
        status, _, trend = _request(
            port,
            "GET",
            "/api/v1/history/trend?asset_id=pump-01&channel_id=voltage-R"
            "&channel_id=voltage-S&range=15m&buckets=15",
        )
        assert status == 200
        assert trend["snapshot_id"] >= 1
        assert trend["asset_id"] == "pump-01"
        assert trend["channel_ids"] == ["voltage-R", "voltage-S"]
        assert {p["channel_id"] for p in trend["latest_stored"]} == {"voltage-R", "voltage-S"}
        assert {row["source_type"] for row in trend["latest_stored"]} == {"file"}
        assert all(row["source_quality"] == "unknown" for row in trend["latest_stored"])
        assert all(row["usable_for_display"] for row in trend["latest_stored"])
        assert all(row["event_at"].endswith("Z") for row in trend["latest_stored"])
        assert trend["buckets"]
        assert sum(bucket["usable_count"] for bucket in trend["buckets"]) == 4
        assert all(bucket["conflict_count"] == 0 for bucket in trend["buckets"])
        assert str(source_path) not in str(trend)
        assert "phase-voltage.csv" not in str(trend)
        assert "opc.tcp" not in str(trend)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_packaged_web_static_assets_are_exactly_allowlisted_and_same_origin(
    tmp_path: Path,
) -> None:
    workspace = OperationsWorkspace(tmp_path / "web-surface")
    initialize_operations_workspace(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(path: str, *, host: str | None = None, origin: str | None = None):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        headers = {"Host": host or f"127.0.0.1:{server.server_port}"}
        if origin is not None:
            headers["Origin"] = origin
        try:
            connection.request("GET", path, headers=headers)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    try:
        for path, mime, marker in (
            ("/web/", "text/html", b"Industrial PHM"),
            ("/web/app.js", "text/javascript", b"/api/v1/monitor"),
            ("/web/styles.css", "text/css", b"focus-visible"),
            ("/web/navigation.js", "text/javascript", b"renderView"),
            ("/web/asset-context.js", "text/javascript", b"monitor_asset"),
            ("/web/phm.js", "text/javascript", b"/api/v1/phm/series"),
            ("/web/source-management.js", "text/javascript", b"/api/v1/sources"),
            ("/web/source-card.js", "text/javascript", b"renderSourceCard"),
            ("/web/file-registration.js", "text/javascript", b"csvRequest"),
            ("/web/opcua-registration.js", "text/javascript", b"opcuaPost"),
            ("/web/analysis-records.js", "text/javascript", b"createAnalysisRecords"),
            ("/web/system-status.js", "text/javascript", b"/api/v1/system/runtime"),
            ("/web/synthetic-demo.js", "text/javascript", b"/api/v1/demo/synthetic/"),
            ("/web/web-utils.js", "text/javascript", b"getJSON"),
            ("/web/phm-explanation.js", "text/javascript", b"/api/v1/phm/explanations"),
        ):
            status, headers, data = request(path)
            assert status == 200
            assert headers["Content-Type"].startswith(mime)
            assert headers["Content-Length"] == str(len(data))
            assert headers["Cache-Control"] == "no-store"
            assert headers["X-Content-Type-Options"] == "nosniff"
            assert "Access-Control-Allow-Origin" not in headers
            assert marker in data

        _, headers, html = request("/web/")
        assert "script-src 'self'" in headers["Content-Security-Policy"]
        assert "connect-src 'self'" in headers["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]
        assert b'src="/web/app.js"' in html
        assert request("/web/../config.toml")[0] == 404
        assert request("/web/index.html")[0] == 404
        assert request("/web/app.js?debug=1")[0] == 404
        assert request("/web/", host="remote.example")[0] == 403
        assert request("/web/", origin="https://remote.example")[0] == 403
        assert request("/web/styles.css", host="remote.example")[0] == 403
        assert request("/web/styles.css?path=../../.env")[0] == 404
        # The research catalog is no longer part of the operations product.
        assert request("/web/research-results.json")[0] == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_standalone_web_never_controls_synthetic_processes(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "read-preview")
    initialize_operations_workspace(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_port
        for route in (
            "/api/v1/demo/synthetic/start",
            "/api/v1/demo/synthetic/stop",
            "/api/v1/demo/synthetic/status",
        ):
            status, _, payload = _request(
                port,
                "POST",
                route,
                origin=f"http://127.0.0.1:{port}",
                site="same-origin",
            )
            assert status == 403
            assert payload == {"error": {"code": "supervisor_required"}}
        assert not list(tmp_path.glob("demo-synthetic-*"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def test_recorded_history_anchor_preserves_old_event_time_without_source_registration(
    tmp_path: Path,
) -> None:
    pytest.importorskip("duckdb")
    workspace = OperationsWorkspace(tmp_path / "recorded-only")
    initialize_operations_workspace(workspace)
    source_path = tmp_path / "recorded.csv"
    source_path.write_text(
        "timestamp,voltage-R\n2020-11-12T15:00:04+00:00,220.5\n2020-11-12T15:59:04+00:00,221.5\n",
        encoding="utf-8",
    )
    sources = InMemorySourceRepository()
    sources.register(
        RegisteredSource(
            source_id="recorded",
            name="Historical recording",
            config=FileSourceConfig(
                source_path=str(source_path),
                asset_id="old-asset",
                channel_columns=("voltage-R",),
                timestamp_column="timestamp",
            ),
            registered_at=datetime(2026, 10, 12, tzinfo=UTC),
        )
    )
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    backfill_registered_file_source(sources, history, "recorded")
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        query = "/api/v1/history/trend?asset_id=old-asset&channel_id=voltage-R&range=1h"
        status, _, now = _request(server.server_port, "GET", query)
        assert status == 200
        assert now["time_anchor"] == "now"
        assert sum(bucket["usable_count"] for bucket in now["buckets"]) == 0
        status, _, recorded = _request(server.server_port, "GET", query + "&anchor=latest")
        assert status == 200
        assert recorded["time_anchor"] == "latest"
        assert recorded["end_at"] == "2020-11-12T15:59:05Z"
        assert sum(bucket["usable_count"] for bucket in recorded["buckets"]) == 2
        assert recorded["latest_stored"][0]["event_at"] == "2020-11-12T15:59:04Z"
        assert not workspace.source_registry_path.exists()
        _, _, monitor = _request(server.server_port, "GET", "/api/v1/monitor")
        assert monitor["assets"]["total"] == 1
        assert _request(server.server_port, "GET", query + "&anchor=guess")[0] == 400
        assert _request(server.server_port, "GET", query + "&anchor=now&anchor=latest")[0] == 400
        newer = tmp_path / "newer.csv"
        newer.write_text(
            "timestamp,voltage-R\n2026-10-12T00:00:00Z,999\n2026-10-12T00:01:00Z,998\n",
            encoding="utf-8",
        )
        sources.register(
            RegisteredSource(
                source_id="newer",
                name="Newer file for the same asset",
                config=FileSourceConfig(
                    str(newer),
                    "old-asset",
                    channel_columns=("voltage-R",),
                    timestamp_column="timestamp",
                ),
                registered_at=datetime(2026, 10, 12, tzinfo=UTC),
            )
        )
        backfill_registered_file_source(sources, history, "newer")
        _, _, selected = _request(
            server.server_port, "GET", query + "&anchor=latest&source_id=recorded"
        )
        assert selected["end_at"] == "2020-11-12T15:59:05Z"
        assert {p["source_id"] for p in selected["latest_stored"]} == {"recorded"}
        assert sum(b["usable_count"] for b in selected["buckets"]) == 2
        assert {b["source_id"] for b in selected["buckets"]} == {"recorded"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()
