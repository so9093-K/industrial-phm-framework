"""Operations V2 must render once analysis results and review requests exist."""

import ast
import runpy
import sys
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from industrial_phm.application import (
    JsonOperationalFindingRepository,
    JsonPhaseUnbalanceRepository,
    ObservationWindowBuffer,
    SqlitePhaseUnbalanceRepository,
    create_human_review_finding,
)
from industrial_phm.application.phase_unbalance import run_phase_unbalance_on_window
from industrial_phm.apps import operations_app_path
from industrial_phm.runtime import OperationsWorkspace

REPO = Path(__file__).resolve().parents[2]
OPERATIONS_APP = operations_app_path()
APPS = [*sorted((REPO / "apps").glob("*.py")), OPERATIONS_APP]


def _analysis():
    sys.path.insert(0, str(REPO / "tests" / "unit"))
    from test_window_analysis_input import END, START, _event

    buffer = ObservationWindowBuffer(
        window_id="ops-v2-render",
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


def test_operations_v2_renders_investigation_and_maintenance_queues(tmp_path, monkeypatch):
    pytest.importorskip("marimo")
    analysis = _analysis()
    SqlitePhaseUnbalanceRepository(tmp_path / "phase-unbalance.sqlite").record(analysis)
    JsonOperationalFindingRepository(tmp_path / "findings.json").record(
        create_human_review_finding(analysis)
    )
    for name, file in (
        ("SOURCE_REGISTRY", "sources.json"),
        ("SOURCE_RUNTIME", "source-runtime.json"),
        ("ACQUISITION_TELEMETRY", "telemetry.sqlite"),
        ("ACQUISITION_SPOOL", "spool.sqlite"),
        ("COLLECTION_CONTROL", "control.sqlite"),
        ("ANALYSIS_STATE", "field-analysis.json"),
        ("PHASE_UNBALANCE_STATE", "phase-unbalance.sqlite"),
        ("FINDING_STATE", "findings.json"),
        ("MAINTENANCE_REVIEW_STATE", "finding-review.json"),
    ):
        monkeypatch.setenv(f"INDUSTRIAL_PHM_OPERATIONS_{name}", str(tmp_path / file))
    monkeypatch.setenv("INDUSTRIAL_PHM_HISTORY_CATALOG", str(tmp_path / "catalog.sqlite"))
    monkeypatch.setenv("INDUSTRIAL_PHM_HISTORY_DATA", str(tmp_path / "data"))

    app = runpy.run_path(str(OPERATIONS_APP))["app"]
    _, defs = app.run()

    assert defs["investigation_selected_id"] is not None
    assert defs["maintenance_selected_id"] is not None


def test_operations_v2_uses_single_workspace_environment(tmp_path, monkeypatch):
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


def test_operations_v2_keeps_reviewed_result_outside_recent_limit(tmp_path, monkeypatch):
    pytest.importorskip("marimo")
    template = _analysis()
    result_store = SqlitePhaseUnbalanceRepository(tmp_path / "phase-unbalance.sqlite")
    oldest = None
    for index in range(502):
        result = _distinct_analysis(template, index)
        result_store.record(result)
        if index == 0:
            oldest = result
    assert oldest is not None
    JsonOperationalFindingRepository(tmp_path / "findings.json").record(
        create_human_review_finding(oldest)
    )

    for name, file in (
        ("SOURCE_REGISTRY", "sources.json"),
        ("SOURCE_RUNTIME", "source-runtime.json"),
        ("ACQUISITION_TELEMETRY", "telemetry.sqlite"),
        ("ACQUISITION_SPOOL", "spool.sqlite"),
        ("COLLECTION_CONTROL", "control.sqlite"),
        ("ANALYSIS_STATE", "field-analysis.json"),
        ("PHASE_UNBALANCE_STATE", "phase-unbalance.sqlite"),
        ("FINDING_STATE", "findings.json"),
        ("MAINTENANCE_REVIEW_STATE", "finding-review.json"),
    ):
        monkeypatch.setenv(f"INDUSTRIAL_PHM_OPERATIONS_{name}", str(tmp_path / file))
    monkeypatch.setenv("INDUSTRIAL_PHM_HISTORY_CATALOG", str(tmp_path / "catalog.sqlite"))
    monkeypatch.setenv("INDUSTRIAL_PHM_HISTORY_DATA", str(tmp_path / "data"))

    app = runpy.run_path(str(OPERATIONS_APP))["app"]
    _, defs = app.run()

    loaded_ids = {item.run.analysis_run_id for item in defs["analysis_results"]}
    assert "bounded-run-0000" in loaded_ids
    assert "bounded-run-0001" not in loaded_ids
    assert "bounded-run-0501" in loaded_ids
    queue_run_ids = {item.analysis_run_id for item in defs["investigation_queue"].items}
    assert "bounded-run-0000" in queue_run_ids


def test_operations_v2_surfaces_legacy_phase_result_migration(tmp_path, monkeypatch):
    pytest.importorskip("marimo")
    monkeypatch.chdir(tmp_path)
    state_dir = tmp_path / "artifacts" / "operations"
    state_dir.mkdir(parents=True)
    JsonPhaseUnbalanceRepository(state_dir / "phase-unbalance.json").record(_analysis())

    app = runpy.run_path(str(OPERATIONS_APP))["app"]
    _, defs = app.run()

    migration_errors = [
        error for error in defs["system_errors"] if error.scope == "phase-analysis-migration"
    ]
    assert len(migration_errors) == 1
    assert "migrate-phase-unbalance-results" in migration_errors[0].detail


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
