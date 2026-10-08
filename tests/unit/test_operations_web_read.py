"""Read transport contract tests: real workspace projection and capability evidence."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from industrial_phm.application.asset_history import HistoricalInputReference
from industrial_phm.application.operational import AnalysisRun
from industrial_phm.application.phase_unbalance import (
    PhaseUnbalanceAnalysis,
    PhaseUnbalanceConfig,
    PhaseUnbalanceEvidence,
    UnbalanceQuantity,
    UnbalanceSeriesResult,
)
from industrial_phm.contracts import DataQualityAssessment
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_app_composition import load_operations_app_snapshot
from industrial_phm.runtime.operations_web_read import project_operations_monitor


def _snapshot(tmp_path: Path):
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    initialize_operations_workspace(workspace)
    snapshot = load_operations_app_snapshot(
        environ={"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(workspace.root)},
        assessed_at=datetime(2026, 10, 8, 9, 30, tzinfo=UTC),
    )
    return workspace, snapshot


def test_web_read_empty_workspace_never_invents_observations_or_health(tmp_path: Path) -> None:
    workspace, snapshot = _snapshot(tmp_path)
    result = project_operations_monitor(snapshot)

    assert result["schema_version"] == 1
    assert result["assessed_at"] == "2026-10-08T09:30:00Z"
    assert result["assets"] == {"items": [], "total": 0, "truncated": False}
    assert result["phase_unbalance_analyses"] == {
        "items": [],
        "total": 0,
        "truncated": False,
    }
    assert result["meaning"] == "observations-and-review-evidence-not-asset-health"
    assert "paths" not in result
    assert str(workspace.root) not in str(result)


def test_web_read_preserves_exact_phase_analysis_and_exclusions(tmp_path: Path) -> None:
    _, snapshot = _snapshot(tmp_path)
    at = snapshot.assessed_at
    start = at - timedelta(minutes=15)
    run = AnalysisRun(
        analysis_run_id="run-1",
        asset_id="compressor-01",
        source_id="opcua-01",
        measurement_point_id="motor",
        observed_start_at=start,
        observed_end_at=at,
        started_at=start,
        completed_at=at,
        data_quality=DataQualityAssessment(),
        capability_ids=("three-phase-unbalance-v1",),
    )
    evidence = PhaseUnbalanceEvidence(
        evidence_id="evidence-1",
        analysis_run_id=run.analysis_run_id,
        input_reference=HistoricalInputReference(
            snapshot_id=11,
            asset_id=run.asset_id,
            start_at=start,
            end_at=at,
            channel_ids=("R", "S", "T"),
        ),
        source_id=run.source_id,
        config=PhaseUnbalanceConfig(),
        semantic_versions=("voltage-v3",),
        results=(
            UnbalanceSeriesResult(
                quantity=UnbalanceQuantity.VOLTAGE,
                evaluated_samples=56,
                excluded_samples={"null-value": 3, "incomplete-phases": 1},
                median_percent=2.1,
                p95_percent=3.2,
                max_percent=4.1,
                max_at=at,
                channels=("R", "S", "T"),
            ),
        ),
    )
    projected = project_operations_monitor(
        replace(snapshot, analysis_results=(PhaseUnbalanceAnalysis(run, evidence),))
    )
    rows = projected["phase_unbalance_analyses"]["items"]
    assert len(rows) == 1
    row = rows[0]
    assert row["analysis_run_id"] == "run-1"
    assert row["observed_start_at"] == "2026-10-08T09:15:00Z"
    assert row["input"] == {"kind": "history-snapshot", "snapshot_id": 11}
    assert row["quantities"][0]["excluded_samples"] == {
        "incomplete-phases": 1,
        "null-value": 3,
    }
    assert row["quantities"][0]["median_percent"] == 2.1
    assert row["quantities"][0]["unit"] == "%"
    assert "alarm" in row["interpretation"]


def test_web_read_repository_error_reports_scope_without_path_or_message(
    tmp_path: Path,
) -> None:
    workspace, _ = _snapshot(tmp_path)
    workspace.source_registry_path.write_text("{invalid-json", encoding="utf-8")
    snapshot = load_operations_app_snapshot(
        environ={"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(workspace.root)},
        assessed_at=datetime(2026, 10, 8, 9, 30, tzinfo=UTC),
    )
    payload = project_operations_monitor(snapshot)

    assert "source-settings" in payload["system_error_scopes"]
    assert "invalid-json" not in str(payload)
    assert str(workspace.root) not in str(payload)
