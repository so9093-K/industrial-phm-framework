"""Real history to condition analysis, with source and temporal query boundaries."""

import json
from datetime import UTC, datetime
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
        # The target ran at a current level the reference never reached: it is counted apart
        # with that level, not scored against a pattern of another load.
        levels = report["operating_levels"]
        assert levels["stopped_below"] == 1.0 and len(levels["levels"]) == 2
        assert report["pattern"]["split"] == "operating-level"
        parts = {part["band"]: part for part in report["pattern"]["levels"]}
        assert parts[2]["reference_samples"] == 0 and parts[2]["target_samples"] == 60
        assert parts[2]["state"] == "insufficient-reference"
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


def test_monitor_says_when_a_file_was_measured_not_when_it_was_read(tmp_path: Path) -> None:
    """A CSV loaded today is a record of 2020; the list must not call today its measurement."""
    pytest.importorskip("duckdb")
    workspace = condition_workspace(tmp_path / "file-record")
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        connection.request(
            "GET", "/api/v1/monitor", headers={"Host": f"127.0.0.1:{server.server_port}"}
        )
        monitor = json.loads(connection.getresponse().read())
        connection.close()
        (asset,) = monitor["assets"]["items"]
        assert asset["asset_id"] == "condition-motor"
        # Stored observations run 2020-11-13 00:00 to 03:59 UTC.
        assert asset["last_observed_at"] == "2020-11-13T03:59:00Z"
        assert asset["last_data_at"] != asset["last_observed_at"]
        # A file has no receive cadence; its stored rows are the record itself.
        assert asset["data_flow_status"] == "stored-history"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


@pytest.mark.parametrize(
    "missing,end,available", [(range(0), "03", True), (range(120, 180), "02", False)]
)
def test_next_period_checks_its_own_measurements_not_only_the_last_record(
    tmp_path: Path, missing: range, end: str, available: bool
) -> None:
    from tests.support.web_next import start_web, stop_web

    pytest.importorskip("duckdb")
    workspace = condition_workspace(tmp_path / "next-period", missing=missing)
    server, thread = start_web(workspace.root, writer=False)
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        connection.request(
            "GET",
            f"/api/v1/condition?asset_id=condition-motor&period=1h&end_at=2020-11-13T{end}:00:00Z",
        )
        response = connection.getresponse()
        body = json.loads(response.read())
        assert response.status == 200 and body["state"] == "analyzed"
        assert body["next_period_available"] is available
        assert datetime.fromisoformat(body["last_observed_at"]).astimezone(UTC) == datetime(
            2020, 11, 13, 3, 59, tzinfo=UTC
        )
    finally:
        connection.close()
        stop_web(server, thread)
