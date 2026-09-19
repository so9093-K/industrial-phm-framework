from dataclasses import replace

import pytest

from industrial_phm.experiments import (
    MIMII_DEVELOPMENT_CONFIGURATION_ID,
    MIMII_DEVELOPMENT_FOLD_ID,
    MIMII_DEVELOPMENT_SECTIONS,
    MIMII_DEVELOPMENT_SPLIT_ID,
    MIMII_DUE_DATASET_ID,
    MIMII_MACHINE_TYPES,
    MimiiExperimentProtocolError,
    get_mimii_development_configuration,
    get_mimii_section_configuration,
    get_mimii_section_scope,
    iter_mimii_development_section_scopes,
)
from industrial_phm.experiments.config import (
    ModelFamily,
    ReferenceStrategy,
    ScalingStrategy,
)
from industrial_phm.features import audio_logmel_feature_names


def test_mimii_development_configuration_matches_preregistered_v1() -> None:
    config = get_mimii_development_configuration()

    assert config.experiment_id == MIMII_DEVELOPMENT_CONFIGURATION_ID
    assert config.dataset_id == MIMII_DUE_DATASET_ID
    assert config.split_id == MIMII_DEVELOPMENT_SPLIT_ID
    assert config.fold_id == MIMII_DEVELOPMENT_FOLD_ID
    assert tuple(config.selected_features) == audio_logmel_feature_names()
    assert config.reference_strategy is ReferenceStrategy.ALL_TRAIN_OBSERVATIONS
    assert config.sampling_policy_id == "clip-uniform-v1"
    assert config.scaling_strategy is ScalingStrategy.ROBUST
    assert config.model_family is ModelFamily.ISOLATION_FOREST
    assert config.random_seed == 42
    assert dict(config.model_parameters) == {
        "n_estimators": 256,
        "max_samples": "auto",
        "contamination": "auto",
        "max_features": 1.0,
        "bootstrap": False,
    }


def test_mimii_development_has_fifteen_deterministic_section_model_scopes() -> None:
    scopes = iter_mimii_development_section_scopes()

    assert len(scopes) == 15
    assert tuple(scope.machine_type for scope in scopes[::3]) == MIMII_MACHINE_TYPES
    assert tuple(scope.section for scope in scopes[:3]) == MIMII_DEVELOPMENT_SECTIONS
    assert len({scope.experiment_id for scope in scopes}) == 15

    for scope in scopes:
        config = get_mimii_section_configuration(scope.machine_type, scope.section)
        assert config.experiment_id == scope.experiment_id
        assert config.fold_id == "fold-1"
        assert get_mimii_section_scope(config) == scope


def test_mimii_section_scope_rejects_configuration_drift() -> None:
    config = get_mimii_section_configuration("fan", "00")

    with pytest.raises(MimiiExperimentProtocolError, match="configuration drift"):
        get_mimii_section_scope(replace(config, scaling_strategy=ScalingStrategy.IDENTITY))
