from functools import cache

import pytest

pytest.importorskip("torch", reason="install the deep-learning extra")

from industrial_phm.adapters import (
    XJTU_SY_CHANNELS,
    get_xjtu_expected_acquisition_count,
)
from industrial_phm.experiments import (
    XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID,
    fit_xjtu_lstm_development_model,
    get_xjtu_reference_split,
    score_xjtu_lstm_development_validation,
)
from industrial_phm.features import (
    VIBRATION_STATISTICAL_FEATURE_SET_ID,
    VibrationFeatureVector,
    vibration_feature_names,
)

_FEATURE_NAMES = vibration_feature_names(XJTU_SY_CHANNELS)


@cache
def _vectors(partition: str) -> tuple[VibrationFeatureVector, ...]:
    fold = get_xjtu_reference_split().folds[0]
    vectors: list[VibrationFeatureVector] = []
    for asset_id in getattr(fold, partition):
        for acquisition_index in range(1, get_xjtu_expected_acquisition_count(asset_id) + 1):
            vectors.append(
                VibrationFeatureVector(
                    feature_set_id=VIBRATION_STATISTICAL_FEATURE_SET_ID,
                    asset_id=asset_id,
                    feature_names=_FEATURE_NAMES,
                    values=tuple(
                        float(acquisition_index + feature_index)
                        for feature_index in range(len(_FEATURE_NAMES))
                    ),
                    metadata={
                        "dataset_id": "xjtu-sy",
                        "acquisition_index": acquisition_index,
                    },
                )
            )
    return tuple(vectors)


def test_xjtu_lstm_execution_connects_fit_and_validation_scoring() -> None:
    train = _vectors("train")
    validation = _vectors("validation")

    fitted = fit_xjtu_lstm_development_model(train, validation)
    scores = score_xjtu_lstm_development_validation(fitted)

    assert fitted.config.experiment_id == XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID
    assert fitted.preprocessing_state.experiment_id == fitted.config.experiment_id
    assert fitted.preprocessing_state.observation_count == len(train)
    assert fitted.model.training.fit_window_count == fitted.sequence_inputs.reference.window_count
    assert scores.window_count == fitted.sequence_inputs.validation.window_count
    assert scores.feature_names == _FEATURE_NAMES
    assert scores.partition_ids == ("validation",) * scores.window_count
    assert len(scores.feature_residuals[0]) == len(_FEATURE_NAMES)
    assert scores.higher_is_more_anomalous is True
