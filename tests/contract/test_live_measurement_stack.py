"""Opt-in real loopback server + collector process + concurrent history reader."""

import importlib.util
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

pytest.importorskip("asyncua")
pytest.importorskip("duckdb")
pytest.importorskip("filelock")

from industrial_phm.application import (
    CollectionDesiredState,
    JsonSourceRepository,
    OpcUaPersistentSessionState,
    request_collection_state,
)
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime import (
    SqliteAcquisitionTelemetryRepository,
    SqliteCollectionControlRepository,
)

REPO = Path(__file__).resolve().parents[2]


def _wait(predicate, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.15)
    raise AssertionError("local live-stack condition was not reached")


def _stop(process):
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=12)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_file_and_independent_live_collector_share_history_across_restart(tmp_path):
    spec = importlib.util.spec_from_file_location("power_demo", REPO / "tools/opcua/demo.py")
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    endpoint = f"opc.tcp://127.0.0.1:{port}/phm-demo/"
    root = tmp_path / "stack"
    demo.prepare(root, endpoint)
    sources = JsonSourceRepository(root / "sources.json")
    control = SqliteCollectionControlRepository(root / "control.sqlite")
    telemetry = SqliteAcquisitionTelemetryRepository(root / "telemetry.sqlite")
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(root / "catalog.sqlite", root / "data")
    )
    server_cmd = [sys.executable, "-m", "tools.opcua.demo", "server", "--endpoint", endpoint]
    collector_cmd = [
        sys.executable,
        "-c",
        "from industrial_phm.cli import main; raise SystemExit(main())",
        "operations",
        "run-collection-service",
    ]
    for flag, file in (
        ("registry", "sources.json"),
        ("control-state", "control.sqlite"),
        ("spool-state", "spool.sqlite"),
        ("telemetry-state", "telemetry.sqlite"),
        ("window-state", "windows.json"),
        ("ducklake-catalog", "catalog.sqlite"),
        ("ducklake-data", "data"),
    ):
        collector_cmd += ["--" + flag, str(root / file)]
    env = os.environ.copy()
    env.pop("AIHUB_APIKEY", None)
    processes = []
    with (root / "process.log").open("w") as log:

        def launch(command):
            process = subprocess.Popen(command, cwd=REPO, env=env, stdout=log, stderr=log)
            processes.append(process)
            return process

        try:
            server = launch(server_cmd)
            collector = launch(collector_cmd)
            request_collection_state(
                sources,
                sources,
                control,
                demo.SOURCE,
                CollectionDesiredState.RUNNING,
                requested_at=datetime.now(UTC),
            )
            _wait(lambda: telemetry.get(demo.SOURCE).history)
            initial = telemetry.get(demo.SOURCE).session.connection_epoch
            for _ in range(8):
                latest = history.query_latest_measurements(demo.ASSET, channel_id="active_power")
                assert {p.measurement.source_id for p in latest} == {"demo-file", demo.SOURCE}
                assert not any(p.conflicting_duplicate for p in latest)
                assert collector.poll() is None
            before = history.list_history_assets()[0].measurement_count
            _wait(lambda: history.list_history_assets()[0].measurement_count > before)
            # Source outage must be observed by the collector, not by a browser process.
            _stop(server)
            _wait(
                lambda: (
                    telemetry.get(demo.SOURCE).session.state
                    != OpcUaPersistentSessionState.CONNECTED
                )
            )
            server = launch(server_cmd)
            _wait(
                lambda: (
                    telemetry.get(demo.SOURCE).session.state
                    == OpcUaPersistentSessionState.CONNECTED
                )
            )
            # Durable epoch reservation survives a collector process restart.
            before_restart = telemetry.get(demo.SOURCE).session.connection_epoch
            assert before_restart > initial
            _stop(collector)
            collector = launch(collector_cmd)
            _wait(lambda: telemetry.get(demo.SOURCE).session.connection_epoch > before_restart)
            count = history.list_history_assets()[0].measurement_count
            _wait(lambda: history.list_history_assets()[0].measurement_count > count)
            request_collection_state(
                sources,
                sources,
                control,
                demo.SOURCE,
                CollectionDesiredState.STOPPED,
                requested_at=datetime.now(UTC),
            )
            _wait(
                lambda: (
                    telemetry.get(demo.SOURCE).session.state == OpcUaPersistentSessionState.STOPPED
                )
            )
            now = datetime.now(UTC)
            page = history.query_measurement_page(
                demo.ASSET,
                channel_id="active_power",
                start_at=now - timedelta(hours=1),
                end_at=now,
                point_budget=2,
                latest=True,
            )
            assert page.truncated
            assert len(page.points) == 2
            assert all(p.measurement.source_id == demo.SOURCE for p in page.points)
            raw = history.query_opcua_events(demo.SOURCE)
            assert len(raw) == len({e.local_delivery_identity for e in raw})
        finally:
            for process in reversed(processes):
                _stop(process)
    assert "database is locked" not in (root / "process.log").read_text()
