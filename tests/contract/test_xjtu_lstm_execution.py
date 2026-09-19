from functools import cache
from pathlib import Path

import pytest

pytest.importorskip("torch", reason="install the deep-learning extra")

from industrial_phm.adapters import (
    XJTU_SY_CHANNELS,
    get_xjtu_expected_acquisition_count,
)
from industrial_phm.experiments import (
    XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID,
    build_xjtu_lstm_development_result,
    evaluate_xjtu_lstm_development_scores,
    fit_xjtu_lstm_development_model,
    get_xjtu_reference_split,
    inspect_experiment_result,
    score_xjtu_lstm_development_validation,
    write_xjtu_lstm_development_result,
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


def test_xjtu_lstm_execution_connects_fit_scoring_result_and_inspection(
    tmp_path: Path,
) -> None:
    train = _vectors("train")
    validation = _vectors("validation")

    fitted = fit_xjtu_lstm_development_model(train, validation)
    scores = score_xjtu_lstm_development_validation(fitted)
    evaluation = evaluate_xjtu_lstm_development_scores(scores)
    fold = get_xjtu_reference_split().folds[0]
    profile_assets = tuple(dict.fromkeys((*fold.train, *fold.validation, *fold.test)))
    result = build_xjtu_lstm_development_result(
        fitted,
        scores,
        evaluation,
        code_revision="a" * 40,
        source_acquisition_count=sum(
            get_xjtu_expected_acquisition_count(asset_id) for asset_id in profile_assets
        ),
    )
    output = tmp_path / "xjtu-lstm-development.json"
    write_xjtu_lstm_development_result(result, output)
    inspection = inspect_experiment_result(output)

    assert fitted.config.experiment_id == XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID
    assert fitted.preprocessing_state.experiment_id == fitted.config.experiment_id
    assert fitted.preprocessing_state.observation_count == len(train)
    assert fitted.model.training.fit_window_count == fitted.sequence_inputs.reference.window_count
    assert scores.window_count == fitted.sequence_inputs.validation.window_count
    assert scores.feature_names == _FEATURE_NAMES
    assert scores.partition_ids == ("validation",) * scores.window_count
    assert len(scores.feature_residuals[0]) == len(_FEATURE_NAMES)
    assert scores.higher_is_more_anomalous is True
    assert result.scores == scores
    assert tuple(stage.name for stage in inspection.stages)[5:10] == (
        "Sequence Construction",
        "Population",
        "Model",
        "Scoring",
        "Evaluation",
    )
