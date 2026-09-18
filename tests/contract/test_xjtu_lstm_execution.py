from collections.abc import Iterable, Sequence
from functools import cache
from inspect import signature

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
from industrial_phm.experiments import xjtu_lstm as module
from industrial_phm.experiments.config import ExperimentConfig
from industrial_phm.features import (
    VIBRATION_STATISTICAL_FEATURE_SET_ID,
    VibrationFeatureVector,
    vibration_feature_names,
)
from industrial_phm.preprocessing import (
    PreprocessingFitProvenance,
    PreprocessingState,
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


def test_canonical_xjtu_lstm_execution_fits_state_from_the_supplied_complete_train(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    train = _vectors("train")
    validation = _vectors("validation")
    original_fit = module.fit_preprocessing_state
    observed_rows: list[tuple[tuple[float, ...], ...]] = []

    def recording_fit(
        config: ExperimentConfig,
        provenance: PreprocessingFitProvenance,
        feature_names: Sequence[str],
        rows: Iterable[Sequence[float]],
    ) -> PreprocessingState:
        materialized = tuple(tuple(row) for row in rows)
        observed_rows.append(materialized)
        return original_fit(config, provenance, feature_names, materialized)

    monkeypatch.setattr(module, "fit_preprocessing_state", recording_fit)
    fitted = fit_xjtu_lstm_development_model(train, validation)
    scores = score_xjtu_lstm_development_validation(fitted)

    assert tuple(signature(fit_xjtu_lstm_development_model).parameters) == (
        "train_vectors",
        "validation_vectors",
    )
    assert observed_rows == [tuple(vector.values for vector in train)]
    assert fitted.config.experiment_id == XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID
    assert fitted.preprocessing_state.experiment_id == fitted.config.experiment_id
    assert fitted.preprocessing_state.observation_count == len(train) == 3_246
    assert fitted.sequence_inputs.reference.source_observation_count == 1_084
    assert fitted.sequence_inputs.reference.window_count == 1_021
    assert fitted.model.training.fit_window_count == 1_021
    assert fitted.model.training.parameter_count == 15_376
    assert fitted.model.training.epochs == 50
    assert len(fitted.model.training.epoch_losses) == 50
    assert scores.window_count == 2_797
    assert scores.partition_ids == ("validation",) * 2_797
    assert scores.aligned_source_observation_ids[0] == "Bearing1_2:acquisition-8"
    assert scores.aligned_source_observation_ids[-1] == "Bearing3_2:acquisition-2496"
    assert scores.aligned_source_positions[0] == 8
    assert scores.aligned_source_positions[-1] == 2_496
    assert len(scores.feature_residuals[0]) == 16
    assert scores.scores[0] == pytest.approx(sum(scores.feature_residuals[0]) / 16)
    assert all(score >= 0.0 for score in scores.scores)
    assert scores.higher_is_more_anomalous is True
