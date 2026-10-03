from datetime import UTC, datetime
from pathlib import Path

from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_app_composition import load_operations_app_snapshot
from industrial_phm.runtime.operations_app_wiring import resolve_operations_app_paths


def test_operations_app_paths_use_single_workspace_root(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")

    paths = resolve_operations_app_paths(
        {"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(workspace.root)}
    )

    assert paths.workspace == workspace
    assert paths.registry == workspace.source_registry_path
    assert paths.source_runtime == workspace.source_runtime_path
    assert paths.acquisition_telemetry == workspace.acquisition_telemetry_path
    assert paths.acquisition_spool == workspace.acquisition_spool_path
    assert paths.collection_control == workspace.collection_control_path
    assert paths.file_feature_analysis == workspace.file_feature_analysis_path
    assert paths.phase_analysis == workspace.phase_unbalance_state_path
    assert paths.analysis_runtime == workspace.analysis_runtime_path
    assert paths.window_state == workspace.window_state_path
    assert paths.analysis_ledger == workspace.analysis_ledger_path
    assert paths.findings == workspace.finding_state_path
    assert paths.review == workspace.maintenance_review_state_path
    assert paths.history_catalog == workspace.history_catalog_path
    assert paths.history_data == workspace.history_data_path


def test_operations_app_paths_require_workspace_root() -> None:
    try:
        resolve_operations_app_paths({})
    except ValueError as error:
        assert "INDUSTRIAL_PHM_OPERATIONS_WORKSPACE is required" in str(error)
    else:
        raise AssertionError("packaged Operations app accepted missing workspace root")


def test_operations_app_paths_ignore_granular_path_environment(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    explicit_registry = tmp_path / "other-sources.json"
    explicit_phase = tmp_path / "other-phase.sqlite"

    paths = resolve_operations_app_paths(
        {
            "INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(workspace.root),
            "INDUSTRIAL_PHM_OPERATIONS_SOURCE_REGISTRY": str(explicit_registry),
            "INDUSTRIAL_PHM_OPERATIONS_PHASE_UNBALANCE_STATE": str(explicit_phase),
        }
    )

    assert paths.registry == workspace.source_registry_path
    assert paths.phase_analysis == workspace.phase_unbalance_state_path
    assert paths.analysis_runtime == workspace.analysis_runtime_path


def test_operations_app_snapshot_is_error_tolerant_for_one_bad_repository(
    tmp_path: Path,
) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    initialize_operations_workspace(workspace)
    workspace.source_registry_path.write_text("{not-json", encoding="utf-8")
    assessed_at = datetime(2026, 10, 3, 8, 0, tzinfo=UTC)

    snapshot = load_operations_app_snapshot(
        environ={"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(workspace.root)},
        assessed_at=assessed_at,
    )

    assert snapshot.assessed_at == assessed_at
    assert snapshot.registered_sources == ()
    assert snapshot.lifecycle_records == ()
    assert snapshot.freshness_policies == ()
    assert any(error.scope == "source-settings" for error in snapshot.system_errors)
    assert snapshot.monitor is not None
    assert snapshot.overview is not None
