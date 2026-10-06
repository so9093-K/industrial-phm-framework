"""Operations must render once analysis results and review requests exist."""

import runpy
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application import (
    JsonOperationalFindingRepository,
    JsonSourceRepository,
    OpcUaSourceConfig,
    RegisteredSource,
    SqlitePhaseUnbalanceRepository,
    create_human_review_finding,
)
from industrial_phm.apps import operations_app_path
from industrial_phm.connectors import OpcUaNodeMapping
from industrial_phm.runtime import OperationsWorkspace
from tests.support.window_analysis import END, phase_unbalance_analysis

OPERATIONS_APP = operations_app_path()


def _analysis():
    return phase_unbalance_analysis()


def _distinct_analysis(template, index: int):
    run_id = f"bounded-run-{index:04d}"
    reference = replace(template.evidence.input_reference, window_id=f"bounded-window-{index:04d}")
    return replace(
        template,
        run=replace(
            template.run,
            analysis_run_id=run_id,
            completed_at=template.run.completed_at + timedelta(seconds=index),
        ),
        evidence=replace(
            template.evidence,
            evidence_id=f"bounded-evidence-{index:04d}",
            analysis_run_id=run_id,
            input_reference=reference,
        ),
    )


def test_operations_empty_workspace_starts_in_setup(tmp_path, monkeypatch):
    pytest.importorskip("marimo")
    workspace = OperationsWorkspace(tmp_path / "workspace")
    monkeypatch.setenv("INDUSTRIAL_PHM_OPERATIONS_WORKSPACE", str(workspace.root))

    app = runpy.run_path(str(OPERATIONS_APP))["app"]
    _, defs = app.run()

    assert defs["navigation_initial_page"] == "Setup"
    assert defs["navigation"].value == "Setup"


def test_operations_registered_source_starts_in_monitor(tmp_path, monkeypatch):
    pytest.importorskip("marimo")
    workspace = OperationsWorkspace(tmp_path / "workspace")
    JsonSourceRepository(workspace.source_registry_path).register(
        RegisteredSource(
            source_id="acceptance-opcua",
            name="Acceptance OPC UA source",
            config=OpcUaSourceConfig(
                endpoint_url="opc.tcp://127.0.0.1:4840",
                asset_id="acceptance-pump",
                measurement_point_id="drive-end",
                node_mappings=(
                    OpcUaNodeMapping(
                        channel_id="vibration_x",
                        node_id="ns=2;s=Machine/VibrationX",
                    ),
                ),
                timeout_seconds=2.0,
            ),
            registered_at=datetime(2026, 10, 4, 3, 0, tzinfo=UTC),
        )
    )
    monkeypatch.setenv("INDUSTRIAL_PHM_OPERATIONS_WORKSPACE", str(workspace.root))

    app = runpy.run_path(str(OPERATIONS_APP))["app"]
    _, defs = app.run()

    assert defs["navigation_initial_page"] == "Monitor"
    assert defs["navigation"].value == "Monitor"
    assert defs["signal_range_selector"].value == "Live"
    assert defs["get_asset_section"]() == "Overview"
    assert defs["get_investigation_review_filter"]() == "All"


def test_operations_renders_investigation_and_maintenance_queues(tmp_path, monkeypatch):
    pytest.importorskip("marimo")
    workspace = OperationsWorkspace(tmp_path / "workspace")
    analysis = _analysis()
    SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path).record(analysis)
    JsonOperationalFindingRepository(workspace.finding_state_path).record(
        create_human_review_finding(analysis)
    )
    monkeypatch.setenv("INDUSTRIAL_PHM_OPERATIONS_WORKSPACE", str(workspace.root))

    app = runpy.run_path(str(OPERATIONS_APP))["app"]
    _, defs = app.run()

    assert defs["investigation_selected_id"] is not None
    assert defs["maintenance_selected_id"] is not None
    assert defs["selected_attention"] is not None
    assert defs["selected_attention"].finding_id is not None
    assert defs["attention_route"].page == "Investigations"
    assert defs["attention_open_button"] is not None


def test_operations_uses_single_workspace_environment(tmp_path, monkeypatch):
    pytest.importorskip("marimo")
    workspace = OperationsWorkspace(tmp_path / "workspace")
    analysis = _analysis()
    SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path).record(analysis)
    JsonOperationalFindingRepository(workspace.finding_state_path).record(
        create_human_review_finding(analysis)
    )
    monkeypatch.setenv("INDUSTRIAL_PHM_OPERATIONS_WORKSPACE", str(workspace.root))

    app = runpy.run_path(str(OPERATIONS_APP))["app"]
    _, defs = app.run()

    paths = defs["operations_context"].snapshot.paths
    assert paths.phase_analysis == workspace.phase_unbalance_state_path
    assert paths.history_catalog == workspace.history_catalog_path
    assert defs["investigation_selected_id"] is not None
    assert defs["maintenance_selected_id"] is not None


def test_operations_keeps_reviewed_result_outside_recent_limit(tmp_path, monkeypatch):
    pytest.importorskip("marimo")
    workspace = OperationsWorkspace(tmp_path / "workspace")
    template = _analysis()
    result_store = SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path)
    oldest = None
    for index in range(502):
        result = _distinct_analysis(template, index)
        result_store.record(result)
        if index == 0:
            oldest = result
    assert oldest is not None
    JsonOperationalFindingRepository(workspace.finding_state_path).record(
        create_human_review_finding(oldest)
    )
    monkeypatch.setenv("INDUSTRIAL_PHM_OPERATIONS_WORKSPACE", str(workspace.root))

    app = runpy.run_path(str(OPERATIONS_APP))["app"]
    _, defs = app.run()

    loaded_ids = {item.run.analysis_run_id for item in defs["analysis_results"]}
    assert "bounded-run-0000" in loaded_ids
    assert "bounded-run-0001" not in loaded_ids
    assert "bounded-run-0501" in loaded_ids
    queue_run_ids = {item.analysis_run_id for item in defs["investigation_queue"].items}
    assert "bounded-run-0000" in queue_run_ids


def test_review_request_updates_review_projections_without_reloading_state(tmp_path):
    import shutil

    from industrial_phm.runtime.operations_app_composition import (
        load_operations_app_snapshot,
        project_review_workflow,
    )

    workspace = OperationsWorkspace(tmp_path / "workspace")
    analysis = _analysis()
    SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path).record(analysis)
    snapshot = load_operations_app_snapshot(
        environ={"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(workspace.root)},
        assessed_at=END + timedelta(minutes=1),
    )
    (asset,) = (item for item in snapshot.monitor.assets if item.asset_id == "motor-7")
    assert asset.pending_review_count == 0
    assert not any(item.finding_id for item in snapshot.monitor.attention)

    # The projection reads nothing from disk: removing the workspace must not matter.
    shutil.rmtree(workspace.root)
    finding = create_human_review_finding(analysis)
    projection = project_review_workflow(snapshot, findings=(finding,), review_events=())

    (asset,) = (item for item in projection.monitor.assets if item.asset_id == "motor-7")
    assert asset.pending_review_count == 1
    assert [item.finding_id for item in projection.monitor.attention] == [finding.finding_id]
    assert projection.monitor.assessed_at == snapshot.assessed_at


def test_maintenance_review_reads_its_evidence_by_reference(tmp_path, monkeypatch):
    pytest.importorskip("marimo")
    workspace = OperationsWorkspace(tmp_path / "workspace")
    analysis = _analysis()
    SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path).record(analysis)
    JsonOperationalFindingRepository(workspace.finding_state_path).record(
        create_human_review_finding(analysis)
    )
    monkeypatch.setenv("INDUSTRIAL_PHM_OPERATIONS_WORKSPACE", str(workspace.root))

    app = runpy.run_path(str(OPERATIONS_APP))["app"]
    _, defs = app.run()

    evidence = defs["maintenance_evidence"]
    assert evidence is not None
    assert evidence.analysis_run_id == analysis.run.analysis_run_id
    assert evidence.observed_start_at == analysis.run.observed_start_at
    assert [row["quantity"] for row in defs["maintenance_evidence_metrics"]]
    assert defs["maintenance_open_investigation_button"] is not None
    # The persisted review keeps references only.
    stored = workspace.finding_state_path.read_text(encoding="utf-8")
    assert "median_percent" not in stored
