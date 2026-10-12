"""Promote frozen XJTU-SY fold-1 research configurations to operational model packages.

The packages are fitted with exactly the research code paths (same manifests, preprocessing,
sampling and seeds). They add only what operation needs and the research never defined: an
anomaly threshold taken from the train-reference score distribution, and the review-interval
rule fixed by the operational inference acceptance protocol v1.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from industrial_phm.adapters import XJTU_SY_CHANNELS
from industrial_phm.experiments.xjtu import get_xjtu_reference_split
from industrial_phm.experiments.xjtu_finalized import get_xjtu_finalized_configuration
from industrial_phm.experiments.xjtu_model_input import (
    fit_xjtu_preprocessing_and_prepare_model_input,
)
from industrial_phm.experiments.xjtu_rul import build_xjtu_recorded_end_rul_targets
from industrial_phm.experiments.xjtu_rul_feature_baseline import fit_xjtu_feature_rul_baseline
from industrial_phm.features import VibrationFeatureVector
from industrial_phm.models import ModelScoringInput, fit_isolation_forest
from industrial_phm.models.isolation_forest import isolation_forest_parameters
from industrial_phm.models.package import (
    AffinePreprocessing,
    EstimatorKind,
    ModelPackageManifest,
    ModelTask,
    PackageBuild,
    PackageInputSpec,
    PackageOutputSpec,
    ReviewIntervalRule,
    StepKind,
    write_model_package,
)
from industrial_phm.models.rul_ridge_regression import ridge_linear_state

XJTU_ANOMALY_THRESHOLD_QUANTILE = 0.995
XJTU_REVIEW_INTERVAL_RULE = ReviewIntervalRule(min_consecutive_steps=2, max_gap_steps=1)
XJTU_OPERATING_CONDITIONS = ("35Hz12kN", "37.5Hz11kN", "40Hz10kN")
_SAMPLING_RATE_HZ = 25_600.0
_SAMPLES_PER_ACQUISITION = 32_768
_ACQUISITION_PERIOD_SECONDS = 60.0
_PROBE_ROWS = 16
_RESULTS_DIR = Path("docs/research/results")


def build_xjtu_fold_1_packages(
    train_vectors: Sequence[VibrationFeatureVector],
    models_root: Path,
    *,
    created_at: datetime,
    code_revision: str,
    evidence_root: Path,
) -> tuple[ModelPackageManifest, ModelPackageManifest]:
    """Fit and write the fold-1 Isolation Forest anomaly and Ridge RUL packages."""
    fold = next(f for f in get_xjtu_reference_split().folds if f.fold_id == "fold-1")
    input_spec = _input_spec()
    anomaly = _anomaly_build(
        train_vectors, input_spec, fold.train, created_at, code_revision, evidence_root
    )
    rul = _rul_build(
        train_vectors, input_spec, fold.train, created_at, code_revision, evidence_root
    )
    return write_model_package(models_root, anomaly), write_model_package(models_root, rul)


def _input_spec() -> PackageInputSpec:
    config = get_xjtu_finalized_configuration()
    return PackageInputSpec(
        step_kind=StepKind.ACQUISITION_SNAPSHOT,
        channels=XJTU_SY_CHANNELS,
        feature_set_id=config.feature_set_id,
        feature_names=tuple(config.selected_features),
        sampling_rate_hz=_SAMPLING_RATE_HZ,
        samples_per_step=_SAMPLES_PER_ACQUISITION,
    )


def _anomaly_build(
    train_vectors: Sequence[VibrationFeatureVector],
    input_spec: PackageInputSpec,
    train_assets: Sequence[str],
    created_at: datetime,
    code_revision: str,
    evidence_root: Path,
) -> PackageBuild:
    config = get_xjtu_finalized_configuration()
    state, fit_input = fit_xjtu_preprocessing_and_prepare_model_input(config, train_vectors)
    model = fit_isolation_forest(config, fit_input)
    reference_scores = model.score(
        ModelScoringInput(
            experiment_id=fit_input.experiment_id,
            feature_set_id=fit_input.feature_set_id,
            feature_names=fit_input.feature_names,
            source_observation_ids=fit_input.source_observation_ids,
            feature_rows=fit_input.feature_rows,
        )
    ).scores
    threshold = float(np.quantile(np.asarray(reference_scores), XJTU_ANOMALY_THRESHOLD_QUANTILE))
    holdout = _evidence(evidence_root, "xjtu-sy-iforest-fold-1-holdout-v1.json")
    return PackageBuild(
        recipe_id=config.experiment_id,
        estimator_kind=EstimatorKind.ISOLATION_FOREST_REFIT,
        input=input_spec,
        output=PackageOutputSpec(
            task=ModelTask.ANOMALY_SCORE,
            value_name="isolation_forest_anomaly_score",
            threshold=threshold,
            threshold_rule=f"train-reference-score-quantile-{XJTU_ANOMALY_THRESHOLD_QUANTILE}",
            review_interval=XJTU_REVIEW_INTERVAL_RULE,
            step_period_seconds=_ACQUISITION_PERIOD_SECONDS,
        ),
        preprocessing=AffinePreprocessing(state.fitted_center, state.fitted_scale),
        estimator_state=isolation_forest_parameters(config),
        fit_rows=[list(row) for row in fit_input.feature_rows],
        probe_rows=[list(row) for row in fit_input.feature_rows[:_PROBE_ROWS]],
        training_scope={
            "dataset_id": config.dataset_id,
            "split_id": config.split_id,
            "fold_id": config.fold_id,
            "partition": "train",
            "asset_ids": list(train_assets),
            "reference_strategy": config.reference_strategy.value,
            "sampling_policy_id": config.sampling_policy_id,
            "complete_train_observation_count": state.observation_count,
            "fit_observation_count": fit_input.fit_observation_count,
        },
        validation={
            "evidence_class": "one-shot-holdout-ranking-evidence",
            "artifact": holdout["artifact"],
            "artifact_sha256": holdout["sha256"],
            "per_asset": [
                {
                    "asset_id": item["asset_id"],
                    "acquisition_order_spearman_rho": item["acquisition_order_spearman_rho"],
                    "late_vs_middle_rank_probability": item["late_vs_middle_rank_probability"],
                }
                for item in holdout["document"]["holdout_bearings"]
            ],
            "score_semantics": "higher is more anomalous; not a failure probability",
        },
        applicability={"operating_condition": list(XJTU_OPERATING_CONDITIONS)},
        created_at=created_at.isoformat(),
        code_revision=code_revision,
    )


def _rul_build(
    train_vectors: Sequence[VibrationFeatureVector],
    input_spec: PackageInputSpec,
    train_assets: Sequence[str],
    created_at: datetime,
    code_revision: str,
    evidence_root: Path,
) -> PackageBuild:
    targets = build_xjtu_recorded_end_rul_targets(train_vectors, partition="train")
    fitted = fit_xjtu_feature_rul_baseline(train_vectors, targets)
    coefficients, intercept = ridge_linear_state(fitted.model)
    validation = _evidence(evidence_root, "xjtu-sy-rul-three-model-fold-1-validation-v1.json")
    method = next(
        m
        for m in validation["document"]["methods"]
        if m["method_id"] == fitted.config.experiment_id
    )
    names = tuple(fitted.config.selected_features)
    probe = [
        [dict(zip(v.feature_names, v.values, strict=True))[name] for name in names]
        for v in train_vectors[:_PROBE_ROWS]
    ]
    return PackageBuild(
        recipe_id=fitted.config.experiment_id,
        estimator_kind=EstimatorKind.LINEAR,
        input=input_spec,
        output=PackageOutputSpec(
            task=ModelTask.RUL_ESTIMATE,
            value_name="remaining_acquisition_intervals",
            unit="acquisition-interval",
            endpoint_semantics="last-recorded-acquisition",
            step_period_seconds=_ACQUISITION_PERIOD_SECONDS,
        ),
        preprocessing=AffinePreprocessing(
            fitted.preprocessing_state.fitted_center, fitted.preprocessing_state.fitted_scale
        ),
        estimator_state={"coefficients": list(coefficients), "intercept": intercept},
        fit_rows=None,
        probe_rows=probe,
        training_scope={
            "dataset_id": fitted.config.dataset_id,
            "split_id": fitted.config.split_id,
            "fold_id": fitted.config.fold_id,
            "partition": "train",
            "asset_ids": list(train_assets),
            "sampling_policy_id": fitted.config.sampling_policy_id,
            "complete_train_observation_count": fitted.preprocessing_state.observation_count,
            "target_definition": "N-k acquisition intervals to the last recorded acquisition",
        },
        validation={
            "evidence_class": validation["document"]["provenance"]["evidence_class"],
            "artifact": validation["artifact"],
            "artifact_sha256": validation["sha256"],
            "mean_asset_mean_absolute_error": method["evaluation"][
                "mean_asset_mean_absolute_error"
            ],
            "per_asset": [
                {
                    "asset_id": item["asset_id"],
                    "mean_absolute_error": item["mean_absolute_error"],
                    "mean_signed_error": item["mean_signed_error"],
                }
                for item in method["evaluation"]["bearings"]
            ],
            "uncertainty": "not validated in RUL v1; no interval is reported",
        },
        applicability={
            "dataset_id": ["xjtu-sy"],
            "operating_condition": list(XJTU_OPERATING_CONDITIONS),
            # Remaining life is defined to the dataset's last recorded acquisition.
            "recorded_replay": ["true"],
        },
        created_at=created_at.isoformat(),
        code_revision=code_revision,
    )


def _evidence(root: Path, name: str) -> dict[str, Any]:
    path = root / name
    data = path.read_bytes()
    return {
        "artifact": (_RESULTS_DIR / name).as_posix(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "document": json.loads(data),
    }
