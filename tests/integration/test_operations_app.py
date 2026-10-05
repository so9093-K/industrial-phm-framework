"""Operations must render once analysis results and review requests exist."""

import ast
import runpy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from industrial_phm.application import (
    JsonOperationalFindingRepository,
    JsonSourceRepository,
    ObservationWindowBuffer,
    OpcUaSourceConfig,
    RegisteredSource,
    SqlitePhaseUnbalanceRepository,
    create_human_review_finding,
)
from industrial_phm.application.phase_unbalance import run_phase_unbalance_on_window
from industrial_phm.apps import operations_app_path
from industrial_phm.connectors import OpcUaNodeMapping
from industrial_phm.runtime import OperationsWorkspace

from tests.support.window_analysis import END, START
from tests.support.window_analysis import window_event as _event

REPO = Path(__file__).resolve().parents[2]
OPERATIONS_APP = operations_app_path()
APPS = [*sorted((REPO / "apps").glob("*.py")), OPERATIONS_APP]


def _analysis():
    buffer = ObservationWindowBuffer(
        window_id="ops-render",
        source_id="site-opcua",
        asset_id="motor-7",
        measurement_point_id="mcc-3",
        expected_channel_ids=("va", "vb", "vc"),
        window_start=START,
        window_end=END,
        max_buffered_events=32,
        max_future_skew_seconds=5.0,
    )
    for second in range(10, 14):
        for offset, channel in enumerate(("va", "vb", "vc")):
            buffer.ingest(_event(channel, second, 220.0 + offset + second, 3 * second + offset))
    buffer.advance_watermark(END)
    return run_phase_unbalance_on_window(buffer.finalize(finalized_at=END))


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


def _ui_values_read_in_creating_cell(path: Path) -> list[str]:
    """``x = mo.ui.*(...)`` followed by ``x.value`` in the same cell (not a callback)."""
    tree = ast.parse(path.read_text())
    problems = []
    for cell in tree.body:
        if not isinstance(cell, ast.FunctionDef):
            continue
        created = {
            target.id
            for node in ast.walk(cell)
            if isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Call)
            and ast.unparse(node.value.func).startswith("mo.ui.")
            for target in node.targets
            if isinstance(target, ast.Name)
        }
        callbacks = {
            id(inner)
            for node in ast.walk(cell)
            if isinstance(node, ast.Lambda)
            for inner in ast.walk(node)
        }
        problems += [
            f"{path.name}:{node.lineno} {node.value.id}.value"
            for node in ast.walk(cell)
            if isinstance(node, ast.Attribute)
            and node.attr == "value"
            and isinstance(node.value, ast.Name)
            and node.value.id in created
            and id(node) not in callbacks
        ]
    return problems


@pytest.mark.parametrize("path", APPS, ids=lambda path: path.name)
def test_no_cell_reads_the_value_of_a_ui_element_it_creates(path):
    # marimo raises at runtime and every dependent cell (the whole page) fails.
    assert _ui_values_read_in_creating_cell(path) == []
