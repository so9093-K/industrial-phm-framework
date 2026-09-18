from dataclasses import fields
from itertools import product

from industrial_phm.adapters import XJTU_SY_CHANNELS
from industrial_phm.experiments import (
    ExperimentConfig,
    FitPartition,
    ModelFamily,
    ReferenceStrategy,
    ScalingStrategy,
    get_xjtu_isolation_forest_candidates,
)
from industrial_phm.features import vibration_feature_names


def test_experiment_config_schema_remains_dataset_neutral() -> None:
    assert {field.name for field in fields(ExperimentConfig)} == {
        "experiment_id",
        "dataset_id",
        "split_id",
        "fold_id",
        "fit_partition",
        "feature_set_id",
        "selected_features",
        "reference_strategy",
        "sampling_policy_id",
        "scaling_strategy",
        "model_family",
        "model_parameters",
        "random_seed",
    }


def test_packaged_xjtu_candidates_cover_the_full_factorial_matrix() -> None:
    candidates = get_xjtu_isolation_forest_candidates()
    all_features = vibration_feature_names(XJTU_SY_CHANNELS)
    without_standard_deviation = tuple(
        name for name in all_features if not name.endswith(".standard_deviation")
    )
    expected_dimensions = set(
        product(
            ("acquisition-uniform-v1", "bearing-balanced-resample-v1"),
            (all_features, without_standard_deviation),
            (ScalingStrategy.IDENTITY, ScalingStrategy.ROBUST),
        )
    )

    assert len(candidates) == 8
    assert {
        (candidate.sampling_policy_id, candidate.selected_features, candidate.scaling_strategy)
        for candidate in candidates
    } == expected_dimensions

    for candidate in candidates:
        assert candidate.dataset_id == "xjtu-sy"
        assert candidate.split_id == "xjtu-sy-condition-stratified-5fold-v1"
        assert candidate.fold_id == "fold-1"
        assert candidate.fit_partition is FitPartition.TRAIN
        assert candidate.feature_set_id == "vibration-statistical-v1"
        assert candidate.reference_strategy is ReferenceStrategy.ALL_TRAIN_OBSERVATIONS
        assert candidate.model_family is ModelFamily.ISOLATION_FOREST
        assert dict(candidate.model_parameters) == {
            "n_estimators": 256,
            "max_samples": "auto",
            "contamination": "auto",
            "max_features": 1.0,
            "bootstrap": False,
        }
        assert candidate.random_seed == 42
