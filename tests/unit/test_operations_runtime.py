import sys
from pathlib import Path

from industrial_phm.apps import operations_app_path
from industrial_phm.runtime import (
    OperationsAnalysisConfig,
    OperationsCollectionConfig,
    OperationsRuntimeConfig,
    OperationsUiConfig,
    OperationsWorkspace,
)
from industrial_phm.runtime.operations_runtime import (
    OPERATIONS_UI_HOST,
    OPERATIONS_WORKSPACE_ENV,
    OperationsComponentKind,
    OperationsUiMode,
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
        "marimo",
        "run",
        str(operations_app_path()),
        "--headless",
        "--no-token",
        "--host",
        OPERATIONS_UI_HOST,
        "--port",
        "3818",
    )
    assert ui.env_overrides == ((OPERATIONS_WORKSPACE_ENV, str(workspace.root)),)
    assert ui.clear_env == ()
    assert collection.log_path == workspace.logs_path / "collection.log"
    assert analysis.log_path == workspace.logs_path / "analysis.log"
    assert ui.log_path == workspace.logs_path / "ui.log"
    assert plan.ui_url == "http://127.0.0.1:3818"


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


def test_web_preview_plan_is_opt_in_and_keeps_supervisor_topology(tmp_path: Path) -> None:
    workspace = OperationsWorkspace(tmp_path / "readonly-pilot")
    config = OperationsRuntimeConfig(ui=OperationsUiConfig(port=4876))

    plan = build_operations_runtime_plan(
        workspace, config, ui_mode=OperationsUiMode.WEB_PREVIEW
    )
    collection, analysis, ui = plan.components
    assert collection.kind == OperationsComponentKind.COLLECTION
    assert analysis.kind == OperationsComponentKind.ANALYSIS
    assert ui.kind == OperationsComponentKind.UI
    assert ui.argv == (
        sys.executable,
        "-m",
        "industrial_phm.runtime.operations_web_preview",
        str(workspace.root),
        "--port",
        "4876",
    )
    assert ui.env_overrides == ((OPERATIONS_WORKSPACE_ENV, str(workspace.root)),)
    assert plan.ui_url == "http://127.0.0.1:4876/web/"
    assert ui.log_path == workspace.logs_path / "ui.log"
    assert build_operations_runtime_plan(workspace, config).ui_mode == OperationsUiMode.MARIMO


def test_web_preview_cli_argument_is_explicit_opt_in(tmp_path: Path) -> None:
    from industrial_phm.cli import build_parser

    workspace = str(tmp_path / "site")
    default = build_parser().parse_args(["operations", "start", workspace])
    opt_in = build_parser().parse_args(
        ["operations", "start", workspace, "--ui", "web-preview"]
    )
    assert default.ui == "marimo"
    assert opt_in.ui == "web-preview"
