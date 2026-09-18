from dataclasses import replace

import pytest

from industrial_phm.experiments import (
    ImsModelInputError,
    ReferenceStrategy,
    fit_ims_preprocessing_and_prepare_model_input,
    get_ims_cross_test_configuration,
)
from industrial_phm.features import VibrationFeatureVector, vibration_feature_names

_FEATURE_NAMES = vibration_feature_names(("vibration",))


def _vectors(
    test_id: str,
    acquisition_count: int,
    *,
    archive_scope: str = "readme-documented",
) -> tuple[VibrationFeatureVector, ...]:
    result: list[VibrationFeatureVector] = []
    for acquisition_index in range(1, acquisition_count + 1):
        for bearing_number in range(1, 5):
            result.append(
                VibrationFeatureVector(
                    feature_set_id="vibration-statistical-v1",
                    asset_id=f"{test_id}-bearing-{bearing_number}",
                    feature_names=_FEATURE_NAMES,
                    values=tuple(
                        float(acquisition_index + bearing_number + offset)
                        for offset in range(len(_FEATURE_NAMES))
                    ),
                    metadata={
                        "dataset_id": "ims-bearings",
                        "test_id": test_id,
                        "bearing_number": bearing_number,
                        "acquisition_index": acquisition_index,
                        "archive_scope": archive_scope,
                        "rotational_speed_rpm": 2_000.0,
                        "radial_load_lb": 6_000.0,
                    },
                )
            )
    return tuple(result)


@pytest.fixture(scope="module")
def train_vectors() -> tuple[VibrationFeatureVector, ...]:
    return _vectors("set-2", 984)


def test_ims_model_fit_preserves_complete_reference_and_fit_populations(
    train_vectors: tuple[VibrationFeatureVector, ...],
) -> None:
    config = get_ims_cross_test_configuration()

    state, model_input = fit_ims_preprocessing_and_prepare_model_input(config, train_vectors)

    assert state.observation_count == 3_936
    assert tuple(state.feature_names) == _FEATURE_NAMES
    assert state.scaling_strategy.value == "identity"
    assert model_input.source_observation_count == 3_936
    assert model_input.reference_observation_count == 3_936
    assert model_input.fit_observation_count == 3_936
    assert len(set(model_input.source_observation_ids)) == 3_936


def test_ims_model_input_rejects_incomplete_train_scope(
    train_vectors: tuple[VibrationFeatureVector, ...],
) -> None:
    config = get_ims_cross_test_configuration()

    with pytest.raises(ImsModelInputError, match="must contain 3936"):
        fit_ims_preprocessing_and_prepare_model_input(config, train_vectors[:-1])


def test_ims_model_input_rejects_reference_strategy_drift() -> None:
    config = replace(
        get_ims_cross_test_configuration(),
        reference_strategy=ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD,
    )

    with pytest.raises(ImsModelInputError, match="reference_strategy drift"):
        fit_ims_preprocessing_and_prepare_model_input(config, ())
