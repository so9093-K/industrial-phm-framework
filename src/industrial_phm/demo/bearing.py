"""A self-contained bearing investigation using real project estimators on synthetic data.

Training uses a separate, stationary reference stream. The two displayed streams are never
used to fit preprocessing, models or thresholds. Scores and EDA are computed by the normal
package runner and read APIs; no analysis response is manufactured for the tour.
"""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from industrial_phm.application.acquisition_snapshot import (
    AcquisitionSnapshot,
    SqliteAcquisitionSnapshotRepository,
    file_sha256,
)
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.phm_runner import PackageCache, run_snapshot_bindings
from industrial_phm.contracts import CanonicalTimeSeries
from industrial_phm.experiments.config import (
    ExperimentConfig,
    FitPartition,
    ModelFamily,
    ReferenceStrategy,
    ScalingStrategy,
)
from industrial_phm.features import extract_vibration_features
from industrial_phm.models import fit_lstm_autoencoder
from industrial_phm.models.package import (
    AffinePreprocessing,
    EstimatorKind,
    ModelTask,
    PackageBuild,
    PackageInputSpec,
    PackageOutputSpec,
    ReviewIntervalRule,
    StepKind,
    load_model_package,
    write_model_package,
)
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_phm_models import create_phm_binding
from industrial_phm.sequences import (
    SequenceFeatureObservation,
    SequenceWindowSpec,
    construct_sequence_windows,
)

CHANNELS = ("Horizontal_vibration_signals", "Vertical_vibration_signals")
COUNT = 96
SPLIT = 48
SAMPLES = 512
RATE = 2048.0
FEATURE_SET = "vibration-statistical-v1"
FEATURES = tuple(
    f"feature.{channel}.{stat}"
    for channel in CHANNELS
    for stat in ("rms", "standard_deviation", "absolute_peak", "excess_kurtosis")
)
ASSET = "demo-bearing-change"
STABLE = "demo-bearing-stable"
SOURCE = "bearing-example-v1"
RECIPES = ("demo-bearing-iforest-v1", "demo-bearing-lstm-autoencoder-v1")


def waveform(ordinal: int, *, stream: int, changing: bool = False) -> CanonicalTimeSeries:
    """Declared g amplitudes and a one-minute acquisition interval; no real fault labels."""
    rng = np.random.default_rng(10_000 * stream + ordinal)
    t = np.arange(SAMPLES) / RATE
    drift = max(0, ordinal - SPLIT) / SPLIT if changing else 0.0
    columns = []
    for channel in range(2):
        amplitude = 0.22 + 0.012 * math.sin(ordinal / 5 + channel) + drift * (0.55 + channel * 0.2)
        values = amplitude * np.sin(2 * np.pi * 64 * t + channel * 0.4)
        values += 0.04 * np.sin(2 * np.pi * 192 * t + ordinal * 0.1)
        values += rng.normal(0, 0.025, SAMPLES)
        # The later records also contain a new frequency component and repeated impulses.
        values += drift * 0.18 * np.sin(2 * np.pi * 320 * t)
        values[::64] += drift * (0.4 + channel * 0.1)
        columns.append(values)
    return CanonicalTimeSeries(
        asset_id=f"synthetic-stream-{stream}",
        timestamps=None,
        channels=CHANNELS,
        values=np.column_stack(columns).tolist(),
        sampling_rate_hz=RATE,
        metadata={"synthetic": True, "amplitude_unit": "g"},
    )


def _feature_row(series: CanonicalTimeSeries) -> tuple[float, ...]:
    vector = extract_vibration_features(series)
    values = dict(zip(vector.feature_names, vector.values, strict=True))
    return tuple(values[name] for name in FEATURES)


def _models(workspace: OperationsWorkspace) -> tuple[str, ...]:
    existing = {}
    for path in workspace.models_path.glob("*/package.json"):
        package = load_model_package(path.parent)
        existing[package.manifest.recipe_id] = package.manifest.package_id
    if all(recipe in existing for recipe in RECIPES):
        return tuple(existing[recipe] for recipe in RECIPES)

    raw = tuple(_feature_row(waveform(i, stream=1)) for i in range(1, 129))
    array = np.asarray(raw)
    center = np.median(array, axis=0)
    scale = np.maximum(np.quantile(array, 0.75, axis=0) - np.quantile(array, 0.25, axis=0), 1e-5)
    preprocessing = AffinePreprocessing(center.tolist(), scale.tolist())
    transformed = preprocessing.transform(raw)
    parameters: dict[str, str | int | float | bool] = {
        "sequence_length": 8,
        "hidden_size": 8,
        "layer_count": 1,
        "dropout": 0.0,
        "loss": "mean-squared-error",
        "optimizer": "adam",
        "learning_rate": 0.003,
        "adam_beta1": 0.9,
        "adam_beta2": 0.999,
        "adam_epsilon": 1e-8,
        "weight_decay": 0.0,
        "gradient_clip_norm": 1.0,
        "batch_size": 32,
        "epochs": 30,
        "shuffle": True,
        "checkpoint": "final-epoch",
        "numeric_precision": "float32",
        "device": "cpu",
        "deterministic_algorithms": True,
    }
    config = ExperimentConfig(
        experiment_id=RECIPES[1],
        dataset_id=SOURCE,
        split_id="independent-streams-v1",
        fold_id="demo",
        fit_partition=FitPartition.TRAIN,
        feature_set_id=FEATURE_SET,
        selected_features=FEATURES,
        reference_strategy=ReferenceStrategy.ALL_TRAIN_OBSERVATIONS,
        sampling_policy_id="reference-window-uniform-v1",
        scaling_strategy=ScalingStrategy.ROBUST,
        model_family=ModelFamily.LSTM_AUTOENCODER,
        model_parameters=parameters,
        random_seed=42,
    )
    construction = construct_sequence_windows(
        (
            SequenceFeatureObservation("reference", "reference", "train", f"reference-{i}", i, row)
            for i, row in enumerate(transformed)
        ),
        feature_set_id=FEATURE_SET,
        feature_names=FEATURES,
        spec=SequenceWindowSpec(8, 1),
    )
    fitted = fit_lstm_autoencoder(config, construction)
    builds = []
    for index, recipe in enumerate(RECIPES):
        sequence_length = 1 if index == 0 else 8
        probes = (
            raw
            if index == 0
            else tuple(
                tuple(value for row in raw[i : i + 8] for value in row) for i in range(len(raw) - 7)
            )
        )
        state: dict[str, Any] = (
            {
                "n_estimators": 64,
                "max_samples": 128,
                "contamination": "auto",
                "max_features": 1.0,
                "bootstrap": False,
                "random_seed": 42,
            }
            if index == 0
            else {
                "input_size": len(FEATURES),
                "model_parameters": parameters,
                "weights": fitted.export_weights(),
            }
        )
        build = PackageBuild(
            recipe_id=recipe,
            estimator_kind=EstimatorKind.ISOLATION_FOREST_REFIT
            if index == 0
            else EstimatorKind.LSTM_AUTOENCODER,
            input=PackageInputSpec(
                StepKind.ACQUISITION_SNAPSHOT,
                CHANNELS,
                FEATURE_SET,
                FEATURES,
                RATE,
                SAMPLES,
                sequence_length,
            ),
            output=PackageOutputSpec(
                task=ModelTask.ANOMALY_SCORE,
                value_name="anomaly-score",
                threshold=0,
                threshold_rule="synthetic-train-reference-quantile-0.995",
                review_interval=ReviewIntervalRule(2, 1),
                step_period_seconds=60,
                provides_feature_contributions=index == 1,
            ),
            preprocessing=preprocessing,
            estimator_state=state,
            fit_rows=transformed if index == 0 else None,
            probe_rows=probes[:8],
            training_scope={
                "dataset_id": SOURCE,
                "partition": "train",
                "asset_ids": ["reference"],
                "synthetic": True,
                "reference_sha256": hashlib.sha256(array.tobytes()).hexdigest(),
            },
            validation={"evidence_class": "synthetic-product-example-not-field-validation"},
            applicability={"operating_condition": ["synthetic-bearing-example"]},
            created_at=datetime.now(UTC).isoformat(),
            code_revision=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        )
        with tempfile.TemporaryDirectory(prefix=".calibration-", dir=workspace.root) as temporary:
            provisional = write_model_package(Path(temporary), build)
            scores = load_model_package(Path(temporary) / provisional.package_id).evaluate(probes)
        builds.append(
            replace(
                build, output=replace(build.output, threshold=float(np.quantile(scores, 0.995)))
            )
        )
    return tuple(
        existing.get(build.recipe_id)
        or write_model_package(workspace.models_path, build).package_id
        for build in builds
    )


def write_journey(
    workspace: OperationsWorkspace,
    *,
    asset: str,
    bindings: tuple[str, ...],
    first: int,
    last: int,
    dataset: str,
) -> None:
    """Selection context only. All observations and scores still come from the real stores."""
    workspace.web_context_path.parent.mkdir(parents=True, exist_ok=True)
    workspace.web_context_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "bearing-demo",
                "dataset": dataset,
                "asset_id": asset,
                "bindings": list(bindings),
                "first": first,
                "last": last,
                "feature": f"feature.{CHANNELS[0]}.rms",
                "other_feature": f"feature.{CHANNELS[1]}.rms",
            }
        ),
        encoding="utf-8",
    )


def prepare_bearing_demo(root: Path, *, port: int = 2719) -> OperationsWorkspace:
    root = root.resolve()
    if root.exists() and not (root / "bearing-example-v1.json").is_file():
        raise ValueError("Bearing example requires a new or previously prepared example workspace")
    workspace = OperationsWorkspace(root)
    initialized = initialize_operations_workspace(workspace)
    (root / "bearing-example-v1.json").write_text('{"schema_version":1}', encoding="utf-8")
    from industrial_phm.runtime.operations_config import write_operations_runtime_config

    write_operations_runtime_config(
        workspace.config_path,
        replace(initialized.config, ui=replace(initialized.config.ui, port=port)),
    )
    packages = _models(workspace)
    snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
    bindings = []
    for asset, stream, changing in ((STABLE, 2, False), (ASSET, 3, True)):
        folder = root / "inputs" / asset
        folder.mkdir(parents=True, exist_ok=True)
        for ordinal in range(1, COUNT + 1):
            series = waveform(ordinal, stream=stream, changing=changing)
            path = folder / f"{ordinal}.csv"
            content = (
                ",".join(CHANNELS)
                + "\n"
                + "\n".join(",".join(f"{value:.9f}" for value in row) for row in series.values)
                + "\n"
            )
            if path.exists() and path.read_text(encoding="utf-8") != content:
                raise ValueError("Example waveform changed; use a new example workspace")
            path.write_text(content, encoding="utf-8")
            snapshots.record(
                AcquisitionSnapshot(
                    source_id=SOURCE,
                    asset_id=asset,
                    ordinal=ordinal,
                    file_path=path,
                    sha256=file_sha256(path),
                    channels=CHANNELS,
                    sampling_rate_hz=RATE,
                    sample_count=SAMPLES,
                    delivered_at=datetime.now(UTC),
                    replay=True,
                    acquisition_period_seconds=60,
                    metadata={
                        "dataset_id": SOURCE,
                        "synthetic": True,
                        "amplitude_unit": "g",
                        "operating_condition": "synthetic-bearing-example",
                    },
                )
            )
        for package in packages:
            binding, _, _ = create_phm_binding(
                workspace,
                package_id=package,
                source_id=SOURCE,
                asset_id=asset,
                recorded_replay=True,
            )
            if asset == ASSET:
                bindings.append(binding.binding_id)
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    run_snapshot_bindings(store, snapshots, PackageCache(workspace.models_path))
    write_journey(
        workspace, asset=ASSET, bindings=tuple(bindings), first=1, last=COUNT, dataset="synthetic"
    )
    return workspace
