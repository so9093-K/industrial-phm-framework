"""Real loopback OPC UA → collector → finalized window → live analysis runner (ADR-0008)."""

import importlib.util
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytest.importorskip("asyncua")
pytest.importorskip("duckdb")
pytest.importorskip("filelock")

from industrial_phm.application import (
    CollectionDesiredState,
    JsonPhaseUnbalanceRepository,
    JsonSourceRepository,
    SqliteObservationWindowRepository,
    WindowInputReference,
    request_collection_state,
    window_input_reference,
)
from industrial_phm.runtime import SqliteCollectionControlRepository

REPO = Path(__file__).resolve().parents[2]
CLI = [sys.executable, "-c", "from industrial_phm.cli import main; raise SystemExit(main())"]


def _wait(predicate, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.25)
    raise AssertionError("live window analysis condition was not reached")


def _stop(process):
    if process.poll() is None:
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=12)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_finalized_live_windows_are_analyzed_once_from_their_accepted_events(tmp_path):
    spec = importlib.util.spec_from_file_location("power_demo", REPO / "tools/opcua/demo.py")
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    endpoint = f"opc.tcp://127.0.0.1:{port}/phm-demo/"
    root = tmp_path / "stack"
    demo.prepare(root, endpoint, profile="three-phase")
    sources = JsonSourceRepository(root / "sources.json")
    windows = SqliteObservationWindowRepository(root / "windows.sqlite")
    results = JsonPhaseUnbalanceRepository(root / "phase-unbalance.json")
    server_cmd = [
        sys.executable,
        "-m",
        "tools.opcua.demo",
        "server",
        "--endpoint",
        endpoint,
        "--profile",
        "three-phase",
    ]
    collector_cmd = [*CLI, "operations", "run-collection-service"]
    for flag, file in (
        ("registry", "sources.json"),
        ("control-state", "control.sqlite"),
        ("spool-state", "spool.sqlite"),
        ("telemetry-state", "telemetry.sqlite"),
        ("window-state", "windows.sqlite"),
        ("ducklake-catalog", "catalog.sqlite"),
        ("ducklake-data", "data"),
    ):
        collector_cmd += ["--" + flag, str(root / file)]
    collector_cmd += ["--window-duration-seconds", "4", "--allowed-lateness-seconds", "1"]
    analysis_cmd = [
        *CLI,
        "operations",
        "run-window-analysis",
        "--window-state",
        str(root / "windows.sqlite"),
        "--analysis-state",
        str(root / "phase-unbalance.json"),
        "--ledger-state",
        str(root / "window-analysis-ledger.sqlite"),
        "--once",
    ]
    env = os.environ.copy()
    env.pop("AIHUB_APIKEY", None)
    processes = []
    with (root / "process.log").open("w") as log:

        def launch(command):
            process = subprocess.Popen(command, cwd=REPO, env=env, stdout=log, stderr=log)
            processes.append(process)
            return process

        try:
            launch(server_cmd)
            collector = launch(collector_cmd)
            request_collection_state(
                sources,
                sources,
                SqliteCollectionControlRepository(root / "control.sqlite"),
                demo.THREE_PHASE_SOURCE,
                CollectionDesiredState.RUNNING,
                requested_at=datetime.now(UTC),
            )
            _wait(
                lambda: root.joinpath("windows.sqlite").exists()
                and len(windows.list_windows()) >= 2
            )
            assert collector.poll() is None

            # The analysis runner is its own process, as in operation.
            assert launch(analysis_cmd).wait(timeout=60) == 0
            analyzed = results.list_results()
            finalized = {w.window_id: w for w in windows.list_windows()}
            assert analyzed, root.joinpath("process.log").read_text()[-2000:]
            complete = 0
            for result in analyzed:
                reference = result.evidence.input_reference
                assert isinstance(reference, WindowInputReference)
                # Evidence names exactly the accepted events of its stored window.
                window = finalized[reference.window_id]
                assert reference == window_input_reference(window)
                assert result.evidence.semantic_versions == ("demo-three-phase-semantics-v1",)
                if window.missing_channel_ids:
                    continue
                complete += 1
                voltage, _current = result.evidence.results
                assert voltage.channels == ("Voltage_L1", "Voltage_L2", "Voltage_L3")
                assert voltage.channel_selection == "semantic-role"
                assert voltage.evaluated_samples > 0
            assert complete >= 1

            # A restarted runner analyzes nothing twice.
            assert launch(analysis_cmd).wait(timeout=60) == 0
            again = results.list_results()
            analyzed_ids = {r.evidence.input_reference.window_id for r in analyzed}
            assert {r.run.analysis_run_id for r in analyzed} <= {
                r.run.analysis_run_id for r in again
            }
            assert len({r.evidence.input_reference.window_id for r in again}) == len(again)
            assert analyzed_ids <= {r.evidence.input_reference.window_id for r in again}
        finally:
            for process in reversed(processes):
                _stop(process)
