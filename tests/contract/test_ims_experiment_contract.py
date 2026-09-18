from dataclasses import replace

import pytest

from industrial_phm.experiments import (
    IMS_CROSS_TEST_CONFIGURATION_ID,
    IMS_CROSS_TEST_SPLIT_ID,
    ImsExperimentProtocolError,
    ReferenceStrategy,
    ScalingStrategy,
    get_ims_cross_test_configuration,
    get_ims_cross_test_split,
)
from industrial_phm.features import vibration_feature_names


def test_ims_cross_test_split_is_one_fixed_test_level_assignment() -> None:
    split = get_ims_cross_test_split()

    assert split.split_id == IMS_CROSS_TEST_SPLIT_ID
    assert split.split_unit == "test"
    assert split.strategy == "fixed-cross-test"
    assert split.fold_id == "fold-1"
    assert split.train_test_id == "set-2"
    assert split.evaluation_test_id == "set-3"
    assert split.evaluation_archive_scope == "readme-documented"
    assert split.train_acquisition_count == 984
    assert split.evaluation_acquisition_count == 4_448


def test_ims_cross_test_configuration_is_exactly_the_preregistered_v1() -> None:
    config = get_ims_cross_test_configuration()

    assert config.experiment_id == IMS_CROSS_TEST_CONFIGURATION_ID
    assert config.dataset_id == "ims-bearings"
    assert config.split_id == IMS_CROSS_TEST_SPLIT_ID
    assert config.fold_id == "fold-1"
    assert tuple(config.selected_features) == vibration_feature_names(("vibration",))
    assert config.reference_strategy is ReferenceStrategy.ALL_TRAIN_OBSERVATIONS
    assert config.sampling_policy_id == "acquisition-uniform-v1"
    assert config.scaling_strategy is ScalingStrategy.IDENTITY
    assert config.model_family.value == "isolation-forest"
    assert config.random_seed == 42
    assert dict(config.model_parameters) == {
        "n_estimators": 256,
        "max_samples": "auto",
        "contamination": "auto",
        "max_features": 1.0,
        "bootstrap": False,
    }


def test_ims_split_validation_rejects_scope_drift() -> None:
    split = get_ims_cross_test_split()

    with pytest.raises(ImsExperimentProtocolError, match="evaluation_archive_scope"):
        replace(split, evaluation_archive_scope="readme-documented+archive-extension").validate()
