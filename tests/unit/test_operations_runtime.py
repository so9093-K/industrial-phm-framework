import sys
from pathlib import Path

from industrial_phm.runtime import (
    OperationsAnalysisConfig,
    OperationsCollectionConfig,
    OperationsRuntimeConfig,
    OperationsWorkspace,
)
from industrial_phm.runtime.operations_runtime import (
    OperationsComponentKind,
    build_operations_runtime_plan,
)


def test_operations_runtime_plan_uses_one_workspace_root_and_config(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    config = OperationsRuntimeConfig(
        collection=OperationsCollectionConfig(
            reconcile_interval_seconds=1.0,
            window_duration_seconds=30.0,
            allowed_lateness_seconds=2.0,
        ),
        analysis=OperationsAnalysisConfig(poll_interval_seconds=2.5),
    )

    plan = build_operations_runtime_plan(workspace, config)

    assert tuple(component.kind for component in plan.components) == (
        OperationsComponentKind.COLLECTION,
        OperationsComponentKind.ANALYSIS,
    )
    collection, analysis = plan.components
    assert collection.argv == (
        sys.executable,
        "-c",
        "from industrial_phm.cli import main; raise SystemExit(main())",
        "operations",
        "run-collection-service",
        "--workspace",
        str(workspace.root),
        "--reconcile-interval-seconds",
        "1.0",
        "--window-duration-seconds",
        "30.0",
        "--allowed-lateness-seconds",
        "2.0",
    )
    assert analysis.argv == (
        sys.executable,
        "-c",
        "from industrial_phm.cli import main; raise SystemExit(main())",
        "operations",
        "run-window-analysis",
        "--workspace",
        str(workspace.root),
        "--interval-seconds",
        "2.5",
        "--alignment",
        "strict",
    )
    assert collection.log_path == workspace.logs_path / "collection.log"
    assert analysis.log_path == workspace.logs_path / "analysis.log"


def test_operations_runtime_plan_preserves_bounded_previous_provenance(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "plant-a")
    config = OperationsRuntimeConfig(
        analysis=OperationsAnalysisConfig(
            alignment="bounded-previous",
            max_carry_age_seconds=5.0,
            alignment_basis="device update contract",
        )
    )

    plan = build_operations_runtime_plan(workspace, config)

    analysis = plan.components[1]
    assert analysis.argv[-6:] == (
        "bounded-previous",
        "--max-carry-age-seconds",
        "5.0",
        "--alignment-basis",
        "device update contract",
    )[-6:]
