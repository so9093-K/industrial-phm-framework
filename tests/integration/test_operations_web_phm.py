"""PHM binding CLI → runner cycle → Web read routes on one real workspace."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from typing import Any

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
from industrial_phm.runtime.operations_web_http import create_operations_web_read_server
from industrial_phm.runtime.operations_workspace import (
    OperationsWorkspace,
    initialize_operations_workspace,
)

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
