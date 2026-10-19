"""Two anomaly models scoring one recorded XJTU-SY bearing they were not trained on.

``industrial-phm demo xjtu`` prepares a dedicated workspace: it fits the fold-1 Isolation Forest
and LSTM autoencoder on the train bearings (or reuses the packages already there), connects both
to the replay stream and delivers the chosen held-out bearing's acquisitions. Operations then
scores them, and the anomaly screen opens with both models, the raw waveforms, AI questions and
review on recorded data.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.demo.xjtu_snapshot_replay import XjtuReplayProgress, replay_xjtu_bearing
from industrial_phm.runtime import (
    OperationsRuntimeConfig,
    OperationsUiConfig,
    OperationsWorkspace,
    initialize_operations_workspace,
)
from industrial_phm.runtime.operations_config import write_operations_runtime_config

XJTU_DEMO_SOURCE_ID = "xjtu-sy-replay"
XJTU_DEMO_DEFAULT_SOURCE = Path("data/interim/xjtu-sy/XJTU-SY_Bearing_Datasets")
IFOREST_RECIPE = "xjtu-sy-iforest-fold-1-finalized-v1"
LSTM_RECIPE = "xjtu-lstm-autoencoder-fold-1-development-v1"


@dataclass(frozen=True, slots=True)
class XjtuModelDemoConfig:
    source: Path = XJTU_DEMO_DEFAULT_SOURCE
    workspace: Path = Path("artifacts/demo-xjtu")
    bearing: str = "Bearing1_1"
    ui_port: int = 2718
    evidence_root: Path = Path("docs/research/results")
    code_revision: str | None = None


@dataclass(frozen=True, slots=True)
class XjtuModelDemoPreparation:
    workspace: OperationsWorkspace
    config: OperationsRuntimeConfig
    packages: tuple[str, ...]
    replay: XjtuReplayProgress


def held_out_bearings() -> tuple[str, ...]:
    """Fold-1 bearings that no packaged model was fitted on."""
    from industrial_phm.experiments.xjtu import get_xjtu_reference_split

    fold = next(f for f in get_xjtu_reference_split().folds if f.fold_id == "fold-1")
    return fold.validation + fold.test


def existing_packages(models_root: Path) -> dict[str, str]:
    """Newest package ID per recipe already in the workspace (descriptive manifest fields only)."""
    found: dict[str, tuple[str, str]] = {}
    manifests = sorted(models_root.glob("*/package.json")) if models_root.is_dir() else []
    for manifest in manifests:
        try:
            body = json.loads(manifest.read_text(encoding="utf-8"))
        except OSError, ValueError:
            continue
        recipe, created = body.get("recipe_id"), str(body.get("created_at", ""))
        if isinstance(recipe, str) and (recipe not in found or created > found[recipe][1]):
            found[recipe] = (manifest.parent.name, created)
    return {recipe: package for recipe, (package, _created) in found.items()}


def prepare_xjtu_model_demo(
    preset: XjtuModelDemoConfig,
    *,
    code_revision: Callable[[], str | None] = lambda: None,
    report: Callable[[str], None] = print,
) -> XjtuModelDemoPreparation:
    """Create or reopen the demo workspace with both models connected and the bearing delivered."""
    from industrial_phm.runtime.operations_web_phm_models import create_phm_binding

    held_out = held_out_bearings()
    if preset.bearing not in held_out:
        raise ValueError(
            f"{preset.bearing} is not a bearing the models were not trained on; "
            f"choose one of {', '.join(held_out)}"
        )
    if not preset.source.is_dir():
        raise OSError(
            f"prepared XJTU-SY source is unavailable: {preset.source}. "
            "Follow data/README.md#xjtu-sy or pass --source."
        )
    workspace = OperationsWorkspace(preset.workspace.resolve())
    initialization = initialize_operations_workspace(workspace)
    config = replace(initialization.config, ui=OperationsUiConfig(port=preset.ui_port))
    write_operations_runtime_config(workspace.config_path, config)

    packages = existing_packages(workspace.models_path)
    missing = [recipe for recipe in (IFOREST_RECIPE, LSTM_RECIPE) if recipe not in packages]
    if missing:
        packages.update(_fit_packages(preset, workspace, missing, code_revision(), report))
    for recipe in (IFOREST_RECIPE, LSTM_RECIPE):
        create_phm_binding(
            workspace,
            package_id=packages[recipe],
            source_id=XJTU_DEMO_SOURCE_ID,
            asset_id=preset.bearing,
            recorded_replay=True,
        )
    replay = replay_xjtu_bearing(
        SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
        preset.source,
        asset_id=preset.bearing,
        source_id=XJTU_DEMO_SOURCE_ID,
        interval_seconds=0.0,
    )
    return XjtuModelDemoPreparation(
        workspace, config, (packages[IFOREST_RECIPE], packages[LSTM_RECIPE]), replay
    )


def _fit_packages(
    preset: XjtuModelDemoConfig,
    workspace: OperationsWorkspace,
    recipes: list[str],
    checkout_revision: str | None,
    report: Callable[[str], None],
) -> dict[str, str]:
    from industrial_phm.adapters import XjtuSyAdapter, validate_xjtu_source
    from industrial_phm.experiments.xjtu import get_xjtu_reference_split
    from industrial_phm.experiments.xjtu_lstm_operational_package import build_xjtu_lstm_packages
    from industrial_phm.experiments.xjtu_operational_package import build_xjtu_fold_1_packages
    from industrial_phm.features import iter_vibration_features

    revision = preset.code_revision or checkout_revision
    if revision is None:
        raise ValueError("pass --code-revision outside a clean Git checkout")
    if not validate_xjtu_source(preset.source).profile_matches:
        raise ValueError("XJTU-SY source does not match the complete profile")
    fold = next(f for f in get_xjtu_reference_split().folds if f.fold_id == "fold-1")
    report(f"fitting {', '.join(recipes)} on {len(fold.train)} train bearing runs (a few minutes)")
    train = tuple(
        iter_vibration_features(XjtuSyAdapter().iter_asset_series(preset.source, fold.train))
    )
    builders = {IFOREST_RECIPE: build_xjtu_fold_1_packages, LSTM_RECIPE: build_xjtu_lstm_packages}
    fitted: dict[str, str] = {}
    for recipe in recipes:
        manifest = builders[recipe](
            train,
            workspace.models_path,
            created_at=datetime.now(UTC),
            code_revision=revision,
            evidence_root=preset.evidence_root,
        )
        report(f"package={manifest.package_id}")
        fitted[recipe] = manifest.package_id
    return fitted
