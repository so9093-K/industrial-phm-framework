"""Export the frozen train-only XJTU LSTM recipes as reusable numeric packages."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from industrial_phm.adapters import XJTU_SY_CHANNELS
from industrial_phm.experiments.xjtu_lstm import get_xjtu_lstm_development_configuration
from industrial_phm.experiments.xjtu_operational_package import (
    XJTU_OPERATING_CONDITIONS,
    XJTU_REVIEW_INTERVAL_RULE,
)
from industrial_phm.experiments.xjtu_rul import build_xjtu_recorded_end_rul_targets
from industrial_phm.experiments.xjtu_rul_lstm import fit_xjtu_rul_lstm_model
from industrial_phm.experiments.xjtu_sequence import _acquisition_index, prepare_xjtu_lstm_reference
from industrial_phm.features import VibrationFeatureVector
from industrial_phm.models import fit_lstm_autoencoder
from industrial_phm.models.package import (
    AffinePreprocessing,
    EstimatorKind,
    ModelPackageManifest,
    ModelTask,
    PackageBuild,
    PackageInputSpec,
    PackageOutputSpec,
    StepKind,
    load_model_package,
    write_model_package,
)
from industrial_phm.preprocessing import PreprocessingFitProvenance, fit_preprocessing_state


def build_xjtu_lstm_packages(
    train: Sequence[VibrationFeatureVector],
    models_root: Path,
    *,
    created_at: datetime,
    code_revision: str,
    evidence_root: Path,
) -> tuple[ModelPackageManifest, ModelPackageManifest]:
    """Train only on fold-1 train acquisitions and save weights without opaque objects."""
    config = get_xjtu_lstm_development_configuration()
    state = fit_preprocessing_state(
        config,
        PreprocessingFitProvenance(
            dataset_id=config.dataset_id,
            split_id=config.split_id,
            fold_id=config.fold_id,
            fit_partition=config.fit_partition,
            feature_set_id=config.feature_set_id,
        ),
        config.selected_features,
        (v.values for v in train),
    )
    reference = prepare_xjtu_lstm_reference(state, train)
    autoencoder = fit_lstm_autoencoder(config, reference)
    raw_by_id = {
        f"{v.asset_id}:acquisition-{_acquisition_index(v, vector_index=i)}": tuple(v.values)
        for i, v in enumerate(train)
    }
    reference_raw = [
        tuple(x for name in window.source_observation_ids for x in raw_by_id[name])
        for window in reference.windows
    ]
    auto_build = PackageBuild(
        recipe_id=config.experiment_id,
        estimator_kind=EstimatorKind.LSTM_AUTOENCODER,
        input=_input(config, autoencoder.spec.length),
        output=PackageOutputSpec(
            task=ModelTask.ANOMALY_SCORE,
            value_name="lstm-reconstruction-mse",
            threshold=0.0,
            threshold_rule="train-reference-score-quantile-0.995",
            review_interval=XJTU_REVIEW_INTERVAL_RULE,
            step_period_seconds=60,
            provides_feature_contributions=True,
        ),
        preprocessing=AffinePreprocessing(state.fitted_center, state.fitted_scale),
        estimator_state={
            "input_size": len(config.selected_features),
            "model_parameters": dict(config.model_parameters),
            "weights": autoencoder.export_weights(),
        },
        fit_rows=None,
        probe_rows=reference_raw[:16],
        training_scope=_scope(config, autoencoder.training),
        validation=_validation(
            evidence_root, "xjtu-sy-lstm-autoencoder-fold-1-development-v1.json"
        ),
        applicability={"operating_condition": list(XJTU_OPERATING_CONDITIONS)},
        created_at=created_at.isoformat(),
        code_revision=code_revision,
    )
    provisional = write_model_package(models_root / "provisional", auto_build)
    reference_scores = load_model_package(
        models_root / "provisional" / provisional.package_id
    ).evaluate(reference_raw)
    from dataclasses import replace

    auto_build = replace(
        auto_build,
        output=replace(auto_build.output, threshold=float(np.quantile(reference_scores, 0.995))),
    )
    anomaly = write_model_package(models_root, auto_build)

    fitted = fit_xjtu_rul_lstm_model(
        train, build_xjtu_recorded_end_rul_targets(train, partition="train")
    )
    rul_raw = [
        tuple(x for name in window.source_observation_ids for x in raw_by_id[name])
        for window in fitted.train_sequence.windows[:16]
    ]
    rul = write_model_package(
        models_root,
        PackageBuild(
            recipe_id=fitted.config.experiment_id,
            estimator_kind=EstimatorKind.LSTM_RUL,
            input=_input(fitted.config, fitted.model.spec.length),
            output=PackageOutputSpec(
                task=ModelTask.RUL_ESTIMATE,
                value_name="lstm-rul",
                unit="acquisition-interval",
                endpoint_semantics="last-recorded-acquisition",
                step_period_seconds=60,
            ),
            preprocessing=AffinePreprocessing(
                fitted.preprocessing_state.fitted_center, fitted.preprocessing_state.fitted_scale
            ),
            estimator_state={
                "input_size": len(fitted.config.selected_features),
                "model_parameters": dict(fitted.config.model_parameters),
                "weights": fitted.model.export_weights(),
            },
            fit_rows=None,
            probe_rows=rul_raw,
            training_scope=_scope(fitted.config, fitted.model.training),
            validation=_validation(evidence_root, "xjtu-sy-rul-lstm-fold-1-benchmark-v1.json"),
            applicability={
                "dataset_id": ["xjtu-sy"],
                "operating_condition": list(XJTU_OPERATING_CONDITIONS),
                # Remaining life is defined to the dataset's last recorded acquisition.
                "recorded_replay": ["true"],
            },
            created_at=created_at.isoformat(),
            code_revision=code_revision,
        ),
    )
    return anomaly, rul


def _input(config: Any, length: int) -> PackageInputSpec:
    return PackageInputSpec(
        step_kind=StepKind.ACQUISITION_SNAPSHOT,
        channels=XJTU_SY_CHANNELS,
        feature_set_id=config.feature_set_id,
        feature_names=config.selected_features,
        sampling_rate_hz=25600,
        samples_per_step=32768,
        sequence_length=length,
    )


def _scope(config: Any, training: Any) -> dict[str, Any]:
    from dataclasses import asdict

    return {
        "dataset_id": config.dataset_id,
        "fold_id": config.fold_id,
        "partition": "train",
        "reference_strategy": config.reference_strategy.value,
        "training": asdict(training),
        "weights": "numeric CPU float32 arrays; restored without retraining",
    }


def _validation(root: Path, name: str) -> dict[str, Any]:
    content = (root / name).read_bytes()
    document = json.loads(content)
    return {
        "evidence_class": "research-configuration-reference-not-package-performance-certification",
        "artifact": name,
        "artifact_sha256": hashlib.sha256(content).hexdigest(),
        "acceptance": "not-yet-evaluated",
        "metrics_origin": "recorded-research-model",
        "mean_asset_mean_absolute_error": document.get("evaluation", {})
        .get("point", {})
        .get("mean_asset_mean_absolute_error"),
        "performance_note": (
            "Reference research performance; this package is newly fitted, "
            "not independently performance validated."
        ),
    }
