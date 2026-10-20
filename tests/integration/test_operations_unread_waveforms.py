"""Delivered waveforms that no model reads yet still list their asset and lead to a model."""

from __future__ import annotations

import json
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.phm_read import project_phm_monitor
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from tests.support.phm import analyze, deliver, phm_workspace


def test_the_monitor_read_names_streams_no_model_reads(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    for ordinal in range(1, 4):
        deliver(workspace, tmp_path / "waves", ordinal, 0.5)
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    (stream,) = project_phm_monitor(store, workspace.models_path, snapshots)["unbound_streams"]
    assert (stream["asset_id"], stream["source_id"], stream["last_ordinal"]) == (
        "bearing-a",
        "bench",
        3,
    )
    assert stream["recorded_replay"] is True

    bound = phm_workspace(tmp_path / "bound")
    deliver(bound, tmp_path / "waves-b", 1, 0.5)
    analyze(bound)
    read = project_phm_monitor(
        SqlitePhmAnalysisStore(bound.phm_analysis_path),
        bound.models_path,
        SqliteAcquisitionSnapshotRepository(bound.acquisition_snapshot_path),
    )
    assert read["unbound_streams"] == []


def test_the_asset_list_names_the_newest_waveform_by_its_order(tmp_path: Path) -> None:
    """A replayed waveform has no measurement clock; the list says which one is newest."""
    workspace = phm_workspace(tmp_path / "ws", bind=False)
    for ordinal in range(1, 4):
        deliver(workspace, tmp_path / "waves", ordinal, 0.5)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        connection.request(
            "GET", "/api/v1/monitor", headers={"Host": f"127.0.0.1:{server.server_port}"}
        )
        (asset,) = json.loads(connection.getresponse().read())["assets"]["items"]
        connection.close()
        assert (asset["asset_id"], asset["last_observed_at"], asset["last_position"]) == (
            "bearing-a",
            None,
            3,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
