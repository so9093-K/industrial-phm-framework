"""Real history to condition analysis, with source and temporal query boundaries."""

import json
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

import pytest

from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.electrical_condition import condition_workspace


def test_condition_http_analyzes_values_and_rejects_cross_source_or_leaking_reference(
    tmp_path: Path,
) -> None:
    pytest.importorskip("duckdb")
    workspace = condition_workspace(tmp_path / "analysis")
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def request(path: str, *, host: str | None = None, method: str = "GET"):
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            connection.request(
                method, path, headers={"Host": host or f"127.0.0.1:{server.server_port}"}
            )
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    try:
        query = "/api/v1/condition?asset_id=condition-motor&period=1h"
        status, report = request(query)
        assert status == 200 and report["state"] == "analyzed"
        assert report["target"]["current_mean_a"] > report["reference"]["current_mean_a"] + 60
        assert report["source_id"] == "synthetic-electrical"
        assert report["point_id"] == "meter"
        assert report["pattern"]["reference_samples"] == 60
        assert report["pattern"]["above_reference_count"] > 0
        assert str(workspace.root) not in str(report)
        assert request(query, host="evil.example")[0] == 403
        assert request(query, method="POST")[0] == 405
        assert request(query + "&source_id=other&point_id=meter")[0] == 400
        assert request(query + "&period=24h")[0] == 400
        assert request(query + "&end_at=2020-11-13T04:00:00")[0] == 400
        assert (
            request(
                query + "&reference_start=2020-11-13T03:00:00Z&reference_end=2020-11-13T04:00:00Z"
            )[0]
            == 400
        )
        assert request(query + "&source_path=../../.env")[0] == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        assert not thread.is_alive()
