"""PHM binding CLI → runner cycle → Web read routes on one real workspace."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from typing import Any

import pytest

from industrial_phm.application.acquisition_snapshot import (
    AcquisitionSnapshot,
    SqliteAcquisitionSnapshotRepository,
    file_sha256,
)
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.phm_runner import PackageCache, run_snapshot_bindings
from industrial_phm.cli import main
from industrial_phm.features.vibration import vibration_feature_names
from industrial_phm.models.package import (
    AffinePreprocessing,
    EstimatorKind,
    ModelTask,
    PackageBuild,
    PackageInputSpec,
    PackageOutputSpec,
    ReviewIntervalRule,
    StepKind,
    write_model_package,
)
from industrial_phm.runtime.operations_web_actions import execute_web_source_action
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from industrial_phm.runtime.operations_web_setup import SourceControlConflict
from industrial_phm.runtime.operations_workspace import (
    OperationsWorkspace,
    initialize_operations_workspace,
)
from tests.support.phm import analyze, deliver, phm_workspace

T0 = datetime(2026, 10, 12, tzinfo=UTC)
CHANNELS = ("h", "v")


def _package(workspace: OperationsWorkspace) -> str:
    names = vibration_feature_names(CHANNELS)
    rms_index = names.index("feature.h.rms")
    coefficients = [0.0] * len(names)
    coefficients[rms_index] = 1.0
    manifest = write_model_package(
        workspace.models_path,
        PackageBuild(
            recipe_id="rms-score-v1",
            estimator_kind=EstimatorKind.LINEAR,
            input=PackageInputSpec(
                step_kind=StepKind.ACQUISITION_SNAPSHOT,
                channels=CHANNELS,
                feature_set_id="vibration-statistical-v1",
                feature_names=names,
                sampling_rate_hz=1000.0,
                samples_per_step=64,
            ),
            output=PackageOutputSpec(
                task=ModelTask.ANOMALY_SCORE,
                value_name="h_rms",
                threshold=2.0,
                threshold_rule="fixed-for-test",
                review_interval=ReviewIntervalRule(2, 1),
            ),
            preprocessing=AffinePreprocessing((0.0,) * len(names), (1.0,) * len(names)),
            estimator_state={"coefficients": coefficients, "intercept": 0.0},
            fit_rows=None,
            probe_rows=[[1.0] * len(names)],
            training_scope={"dataset_id": "synthetic"},
            validation={},
            applicability={},
            created_at=T0.isoformat(),
            code_revision="0" * 40,
        ),
    )
    return manifest.package_id


def _deliver(
    repo: SqliteAcquisitionSnapshotRepository, root: Path, ordinal: int, scale: float
) -> None:
    path = root / f"{ordinal}.csv"
    rows = [f"{scale * ((i % 4) - 1.5):.6f},{(i % 3) - 1.0 + 0.01 * i:.6f}" for i in range(64)]
    path.write_text("h,v\n" + "\n".join(rows) + "\n", encoding="utf-8")
    repo.record(
        AcquisitionSnapshot(
            source_id="bench",
            asset_id="bearing-a",
            ordinal=ordinal,
            file_path=path.resolve(),
            sha256=file_sha256(path),
            channels=CHANNELS,
            sampling_rate_hz=1000.0,
            sample_count=64,
            delivered_at=T0 + timedelta(minutes=ordinal),
            replay=True,
        )
    )


def test_bound_package_results_are_served_incrementally_without_paths(
    tmp_path: Path, capsys: Any
) -> None:
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    package_id = _package(workspace)
    assert (
        main(
            [
                "operations",
                "phm",
                "bind",
                str(workspace.root),
                "--package",
                package_id,
                "--source-id",
                "bench",
                "--asset-id",
                "bearing-a",
                "--binding-id",
                "b1",
            ]
        )
        == 0
    )
    assert "binding=b1" in capsys.readouterr().out
    assert (
        main(
            [
                "operations",
                "phm",
                "bind",
                str(workspace.root),
                "--package",
                "missing-000",
                "--source-id",
                "bench",
                "--asset-id",
                "bearing-a",
            ]
        )
        == 1
    )

    waveforms = tmp_path / "waveforms"
    waveforms.mkdir()
    repo = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    cache = PackageCache(workspace.models_path)
    for ordinal, scale in enumerate((0.5, 0.5, 3.0, 3.0), start=1):
        _deliver(repo, waveforms, ordinal, scale)
    run_snapshot_bindings(store, repo, cache, now=lambda: T0)

    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def get(path: str) -> tuple[int, dict[str, Any]]:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            connection.request("GET", path, headers={"Host": f"127.0.0.1:{server.server_port}"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    try:
        status, bindings = get("/api/v1/phm/bindings")
        assert status == 200
        (item,) = bindings["bindings"]
        assert item["health"] == "ok" and item["open_intervals"] == 1
        assert item["latest_analyzed"]["position"] == 4
        assert item["latest_delivered"]["position"] == 4 and item["latest_delivered"]["replay"]
        assert item["package"]["output"]["task"] == "anomaly-score"

        status, series = get("/api/v1/phm/series?binding_id=b1")
        assert status == 200
        assert [s["position"] for s in series["steps"]] == [1, 2, 3, 4]
        assert [s["output"]["exceeds_threshold"] for s in series["steps"]] == [
            False,
            False,
            True,
            True,
        ]
        assert series["steps"][0]["features"]["feature.h.rms"] > 0
        (interval,) = series["intervals"]
        assert (interval["start_position"], interval["end_position"], interval["open"]) == (
            3,
            4,
            True,
        )
        assert str(tmp_path) not in json.dumps(series)

        seq = series["change_seq"]
        _deliver(repo, waveforms, 5, 0.5)
        run_snapshot_bindings(store, repo, cache, now=lambda: T0)
        status, delta = get(f"/api/v1/phm/series?binding_id=b1&since={seq}")
        assert [s["position"] for s in delta["steps"]] == [5]
        assert delta["change_seq"] > seq

        status, preview = get("/api/v1/phm/snapshot?binding_id=b1&position=3&bins=8")
        assert status == 200 and preview["available"]
        assert [c["channel"] for c in preview["channels"]] == list(CHANNELS)
        assert len(preview["channels"][0]["envelope"]) == 8
        assert str(tmp_path) not in json.dumps(preview)

        assert get("/api/v1/phm/series?binding_id=nope")[0] == 404
        assert get("/api/v1/phm/series")[0] == 400
        assert get("/api/v1/phm/snapshot?binding_id=b1&position=0")[0] == 400
        assert get("/api/v1/phm/series?binding_id=b1&since=-1")[0] == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def test_registered_opcua_model_fit_is_separate_from_available_window_input(tmp_path: Path) -> None:
    from industrial_phm.application import JsonSourceRepository, OpcUaSourceConfig, RegisteredSource
    from industrial_phm.application.observation_window_sqlite import (
        SqliteObservationWindowRepository,
    )
    from industrial_phm.connectors import OpcUaNodeMapping
    from industrial_phm.runtime.operations_web_phm_models import project_phm_models
    from tests.support.electrical_phm import CHANNELS as ELECTRICAL_CHANNELS
    from tests.support.electrical_phm import electrical_window, electrical_workspace
    from tests.support.window_analysis import START

    workspace = electrical_workspace(tmp_path / "ws")
    sample = electrical_window("input-shape", START)
    meanings = {
        event.event.semantic_binding.channel_id: event.event.semantic_binding
        for event in sample.events
    }
    JsonSourceRepository(workspace.source_registry_path).register(
        RegisteredSource(
            source_id="site-opcua",
            name="전기 신호",
            registered_at=START,
            config=OpcUaSourceConfig(
                endpoint_url="opc.tcp://127.0.0.1:4840/",
                asset_id="motor-7",
                measurement_point_id="mcc-3",
                node_mappings=tuple(
                    OpcUaNodeMapping(channel, f"ns=2;s={channel}")
                    for channel in ELECTRICAL_CHANNELS
                ),
                semantic_bindings=tuple(meanings.values()),
            ),
        )
    )
    exists = workspace.window_state_path.exists()
    models = project_phm_models(workspace, "motor-7")
    assert models["streams"][0]["input_state"] == "waiting-input"
    assert models["packages"][0]["candidates"][0]["compatible"] is True
    assert workspace.window_state_path.exists() == exists  # a read never creates input evidence
    windows = SqliteObservationWindowRepository(workspace.window_state_path)
    windows.record_window(electrical_window("other-point", START, point="other"))
    assert project_phm_models(workspace, "motor-7")["streams"][0]["input_state"] == "waiting-input"
    windows.record_window(electrical_window("own-point", START))
    assert project_phm_models(workspace, "motor-7")["streams"][0]["input_state"] == "stored-input"
    assert (
        project_phm_models(workspace, "motor-7")["packages"][0]["candidates"][0]["compatible"]
        is True
    )


def test_web_lists_fitting_models_and_connects_one_to_the_asset(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    package_id = _package(workspace)
    waveforms = tmp_path / "waveforms"
    waveforms.mkdir()
    repo = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    for ordinal, scale in enumerate((0.5, 3.0, 3.0), start=1):
        _deliver(repo, waveforms, ordinal, scale)
    other = waveforms / "other.csv"
    other.write_text("x\n" + "0.0\n" * 64, encoding="utf-8")
    repo.record(
        AcquisitionSnapshot(
            source_id="bench",
            asset_id="pump-b",
            ordinal=1,
            file_path=other.resolve(),
            sha256=file_sha256(other),
            channels=("x",),
            sampling_rate_hz=1000.0,
            sample_count=64,
            delivered_at=T0,
            replay=False,
        )
    )

    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def get(path: str) -> tuple[int, dict[str, Any]]:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            connection.request("GET", path, headers={"Host": f"127.0.0.1:{server.server_port}"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    try:
        status, models = get("/api/v1/phm/models?asset_id=bearing-a")
        assert status == 200
        (package,) = models["packages"]
        assert package["package_id"] == package_id and package["task"] == "anomaly-score"
        (candidate,) = package["candidates"]
        assert candidate == {
            "source_id": "bench",
            "measurement_point_id": None,
            "compatible": True,
            "reason": None,
            "connected": False,
        }
        status, models = get("/api/v1/phm/models?asset_id=pump-b")
        assert models["packages"][0]["candidates"][0]["reason"] == "채널 구성이 다릅니다"
        assert get("/api/v1/phm/models")[0] == 400

        payload: dict[str, object] = {
            "package_id": package_id,
            "source_id": "bench",
            "asset_id": "bearing-a",
        }
        connected = execute_web_source_action(
            workspace.root, "/api/v1/phm/bindings/create", payload
        )
        assert connected["created"] is True and connected["task"] == "anomaly-score"
        again = execute_web_source_action(workspace.root, "/api/v1/phm/bindings/create", payload)
        assert again["binding_id"] == connected["binding_id"] and again["created"] is False
        with pytest.raises(SourceControlConflict):
            execute_web_source_action(
                workspace.root, "/api/v1/phm/bindings/create", {**payload, "asset_id": "pump-b"}
            )
        with pytest.raises(SourceControlConflict):
            execute_web_source_action(
                workspace.root,
                "/api/v1/phm/bindings/create",
                {**payload, "package_id": "missing-000"},
            )

        # Already stored inputs are analyzed once the runner sees the new binding.
        store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
        run_snapshot_bindings(store, repo, PackageCache(workspace.models_path), now=lambda: T0)
        status, series = get(f"/api/v1/phm/series?binding_id={connected['binding_id']}")
        assert [s["state"] for s in series["steps"]] == ["analyzed"] * 3
        status, models = get("/api/v1/phm/models?asset_id=bearing-a")
        assert models["packages"][0]["candidates"][0]["connected"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def test_range_route_reads_the_shape_between_two_stored_results(tmp_path: Path) -> None:
    workspace = phm_workspace(tmp_path / "ws")
    for ordinal, scale in enumerate((0.5, 0.5, 0.55, 0.5, 3.0, 3.1, 3.0, 3.2), start=1):
        deliver(workspace, tmp_path / "waves", ordinal, scale)
    analyze(workspace)
    server = create_operations_web_read_server(workspace.root)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def get(path: str) -> tuple[int, dict[str, Any]]:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
        try:
            connection.request("GET", path, headers={"Host": f"127.0.0.1:{server.server_port}"})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    try:
        status, span = get("/api/v1/phm/range?binding_id=anomaly-a&from=1&to=8")
        assert status == 200 and span["steps"] == 8
        assert span["primary"]["level_shift"]["at"] == 5
        assert "feature.Horizontal_vibration_signals.rms" in span["features"]
        assert get("/api/v1/phm/range?binding_id=anomaly-a&from=8&to=1")[0] == 400
        assert get("/api/v1/phm/range?binding_id=anomaly-a&from=1&to=99")[0] == 400
        assert get("/api/v1/phm/range?binding_id=nope&from=1&to=8")[0] == 404
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
