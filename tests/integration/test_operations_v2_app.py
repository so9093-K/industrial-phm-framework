"""Operations V2 must render once analysis results and review requests exist."""

import ast
import runpy
import sys
from pathlib import Path

import pytest

from industrial_phm.application import (
    JsonOperationalFindingRepository,
    JsonPhaseUnbalanceRepository,
    ObservationWindowBuffer,
    create_human_review_finding,
)
from industrial_phm.application.phase_unbalance import run_phase_unbalance_on_window

REPO = Path(__file__).resolve().parents[2]
APPS = sorted((REPO / "apps").glob("*.py"))


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


def test_operations_v2_renders_investigation_and_maintenance_queues(tmp_path, monkeypatch):
    pytest.importorskip("marimo")
    analysis = _analysis()
    JsonPhaseUnbalanceRepository(tmp_path / "phase-unbalance.json").record(analysis)
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
        ("PHASE_UNBALANCE_STATE", "phase-unbalance.json"),
        ("FINDING_STATE", "findings.json"),
        ("MAINTENANCE_REVIEW_STATE", "finding-review.json"),
    ):
        monkeypatch.setenv(f"INDUSTRIAL_PHM_OPERATIONS_{name}", str(tmp_path / file))
    monkeypatch.setenv("INDUSTRIAL_PHM_HISTORY_CATALOG", str(tmp_path / "catalog.sqlite"))
    monkeypatch.setenv("INDUSTRIAL_PHM_HISTORY_DATA", str(tmp_path / "data"))

    app = runpy.run_path(str(REPO / "apps" / "operations_v2.py"))["app"]
    _, defs = app.run()

    assert defs["investigation_selected_id"] is not None
    assert defs["maintenance_selected_id"] is not None


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
