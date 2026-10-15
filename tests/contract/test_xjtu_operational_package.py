"""The operational XJTU anomaly package reproduces the frozen research code path exactly."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import cache
from pathlib import Path

import numpy as np

from industrial_phm.adapters import XJTU_SY_CHANNELS, get_xjtu_expected_acquisition_count
from industrial_phm.experiments import get_xjtu_reference_split
from industrial_phm.experiments.xjtu_finalized import get_xjtu_finalized_configuration
from industrial_phm.experiments.xjtu_model_input import (
    fit_xjtu_preprocessing_and_prepare_model_input,
    prepare_xjtu_model_scoring_input,
)
from industrial_phm.experiments.xjtu_operational_package import (
    XJTU_ANOMALY_THRESHOLD_QUANTILE,
    build_xjtu_fold_1_packages,
)
from industrial_phm.features import (
    VIBRATION_STATISTICAL_FEATURE_SET_ID,
    VibrationFeatureVector,
    vibration_feature_names,
)
from industrial_phm.models import ModelScoringInput, fit_isolation_forest
from industrial_phm.models.package import ModelTask, load_model_package

_NAMES = vibration_feature_names(XJTU_SY_CHANNELS)
_EVIDENCE = Path(__file__).resolve().parents[2] / "docs" / "research" / "results"


@cache
def _vectors(partition: str) -> tuple[VibrationFeatureVector, ...]:
    fold = get_xjtu_reference_split().folds[0]
    rng = np.random.default_rng(len(partition))
    vectors = []
    for asset_id in getattr(fold, partition):
        run_length = get_xjtu_expected_acquisition_count(asset_id)
        for index in range(1, run_length + 1):
            wear = index / run_length
            vectors.append(
                VibrationFeatureVector(
                    feature_set_id=VIBRATION_STATISTICAL_FEATURE_SET_ID,
                    asset_id=asset_id,
                    feature_names=_NAMES,
                    values=tuple(
                        float(wear * (1 + k) + rng.normal(scale=0.05)) for k in range(len(_NAMES))
                    ),
                    metadata={
                        "dataset_id": "xjtu-sy",
                        "acquisition_index": index,
                        "operating_condition": "35Hz12kN",
                    },
                )
            )
    return tuple(vectors)


def _build(tmp_path: Path):  # type: ignore[no-untyped-def]
    anomaly = build_xjtu_fold_1_packages(
        _vectors("train"),
        tmp_path / "models",
        created_at=datetime(2026, 10, 12, tzinfo=UTC),
        code_revision="0" * 40,
        evidence_root=_EVIDENCE,
    )
    return load_model_package(tmp_path / "models" / anomaly.package_id)


def test_anomaly_package_scores_like_the_research_isolation_forest(tmp_path: Path) -> None:
    anomaly = _build(tmp_path)
    config = get_xjtu_finalized_configuration()
    state, fit_input = fit_xjtu_preprocessing_and_prepare_model_input(config, _vectors("train"))
    model = fit_isolation_forest(config, fit_input)
    validation = _vectors("validation")
    research = model.score(
        prepare_xjtu_model_scoring_input(config, state, validation, partition="validation")
    )
    rows = [list(v.values) for v in validation]
    assert anomaly.evaluate(rows) == research.scores

    reference = model.score(
        ModelScoringInput(
            experiment_id=fit_input.experiment_id,
            feature_set_id=fit_input.feature_set_id,
            feature_names=fit_input.feature_names,
            feature_rows=fit_input.feature_rows,
            source_observation_ids=fit_input.source_observation_ids,
        )
    ).scores
    output = anomaly.manifest.output
    assert output.task is ModelTask.ANOMALY_SCORE
    assert output.threshold == float(np.quantile(reference, XJTU_ANOMALY_THRESHOLD_QUANTILE))
    assert output.review_interval is not None and output.review_interval.min_consecutive_steps == 2
    assert anomaly.manifest.training_scope["asset_ids"] == list(
        get_xjtu_reference_split().folds[0].train
    )


def test_rebuilding_from_identical_inputs_yields_identical_package_ids(tmp_path: Path) -> None:
    first = _build(tmp_path / "a")
    again = _build(tmp_path / "b")
    assert first.package_id != ""
    # created_at and code revision are part of the manifest, so identical inputs give identical IDs.
    assert first.package_id == again.package_id
