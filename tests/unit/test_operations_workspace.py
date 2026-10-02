from pathlib import Path

from industrial_phm.runtime.operations_workspace import OperationsWorkspace


def test_operations_workspace_owns_current_flat_live_layout(tmp_path: Path) -> None:
    root = tmp_path / "plant-a"
    workspace = OperationsWorkspace(root)

    assert workspace.config_path == root / "config.toml"
    assert workspace.source_registry_path == root / "sources.json"
    assert workspace.source_runtime_path == root / "source-runtime.json"
    assert workspace.collection_control_path == root / "control.sqlite"
    assert workspace.acquisition_spool_path == root / "spool.sqlite"
    assert workspace.acquisition_telemetry_path == root / "telemetry.sqlite"
    assert workspace.window_state_path == root / "windows.sqlite"
    assert workspace.analysis_ledger_path == root / "window-analysis-ledger.sqlite"
    assert workspace.field_analysis_path == root / "field-analysis.json"
    assert workspace.phase_unbalance_state_path == root / "phase-unbalance.sqlite"
    assert workspace.analysis_runtime_path == root / "phase-unbalance-runtime.json"
    assert workspace.finding_state_path == root / "findings.json"
    assert workspace.maintenance_review_state_path == root / "finding-review.json"
    assert workspace.history_catalog_path == root / "catalog.sqlite"
    assert workspace.history_data_path == root / "data"
    assert workspace.logs_path == root / "logs"


def test_operations_workspace_state_files_are_distinct_and_under_root(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "site")

    state_files = workspace.runtime_state_files

    assert len(state_files) == len(set(state_files))
    assert all(path.parent == workspace.root for path in state_files)
    assert workspace.managed_directories == (
        workspace.root,
        workspace.history_data_path,
        workspace.logs_path,
    )


def test_operations_workspace_path_projection_has_no_filesystem_side_effect(tmp_path: Path) -> None:
    root = tmp_path / "not-created"

    workspace = OperationsWorkspace(root)

    assert workspace.history_catalog_path == root / "catalog.sqlite"
    assert not root.exists()
