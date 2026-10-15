import sys
from pathlib import Path

import pytest

from industrial_phm.runtime import (
    OperationsAnalysisConfig,
    OperationsCollectionConfig,
    OperationsRuntimeConfig,
    OperationsUiConfig,
    OperationsWorkspace,
)
from industrial_phm.runtime.operations_runtime import (
    OPERATIONS_WORKSPACE_ENV,
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
        ui=OperationsUiConfig(port=3818),
    )

    plan = build_operations_runtime_plan(workspace, config)

    assert tuple(component.kind for component in plan.components) == (
        OperationsComponentKind.COLLECTION,
        OperationsComponentKind.ANALYSIS,
        OperationsComponentKind.UI,
    )
    collection, analysis, ui = plan.components
    assert collection.argv == (
        sys.executable,
        "-c",
        "from industrial_phm.cli import main; raise SystemExit(main())",
        "internal",
        "collection-service",
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
        "internal",
        "window-analysis",
        "--workspace",
        str(workspace.root),
        "--interval-seconds",
        "2.5",
        "--alignment",
        "strict",
    )
    assert ui.argv == (
        sys.executable,
        "-m",
        "industrial_phm.runtime.operations_web_preview",
        str(workspace.root),
        "--port",
        "3818",
        "--supervised-actions",
    )
    assert ui.env_overrides == ((OPERATIONS_WORKSPACE_ENV, str(workspace.root)),)
    assert ui.clear_env == ()
    assert collection.log_path == workspace.logs_path / "collection.log"
    assert analysis.log_path == workspace.logs_path / "analysis.log"
    assert ui.log_path == workspace.logs_path / "ui.log"
    assert plan.ui_url == "http://127.0.0.1:3818/web/"


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
        "--alignment",
        "bounded-previous",
        "--max-carry-age-seconds",
        "5.0",
        "--alignment-basis",
        "device update contract",
    )


def test_the_supervised_web_is_the_only_ui(tmp_path: Path) -> None:
    from industrial_phm.cli import build_parser

    workspace = str(tmp_path / "site")
    assert build_parser().parse_args(["operations", "start", workspace]).ui == "web-controlled"
    assert build_parser().parse_args(["operations", "up", workspace]).ui == "web-controlled"
    for command in ("start", "up"):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["operations", command, workspace, "--ui", "web-preview"])


def test_retired_marimo_operations_mode_is_rejected(tmp_path: Path) -> None:
    import pytest

    from industrial_phm.cli import build_parser

    for command in ("up", "start"):
        with pytest.raises(SystemExit) as error:
            build_parser().parse_args(
                ["operations", command, str(tmp_path / "site"), "--ui", "marimo"]
            )
        assert error.value.code == 2
