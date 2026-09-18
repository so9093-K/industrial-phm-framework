from collections import Counter
from dataclasses import replace
from functools import cache

import pytest

from industrial_phm.adapters import (
    XJTU_SY_CHANNELS,
    get_xjtu_expected_acquisition_count,
)
from industrial_phm.experiments import (
    XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID,
    XJTU_LSTM_SEQUENCE_SPEC,
    FitPartition,
    ReferenceStrategy,
    ScalingStrategy,
    XjtuSequenceConstructionError,
    get_xjtu_reference_split,
    prepare_xjtu_lstm_sequence_inputs,
)
from industrial_phm.features import (
    VIBRATION_STATISTICAL_FEATURE_SET_ID,
    VibrationFeatureVector,
    vibration_feature_names,
)
from industrial_phm.preprocessing import PreprocessingState

_FEATURE_NAMES = vibration_feature_names(XJTU_SY_CHANNELS)


def _state() -> PreprocessingState:
    return PreprocessingState(
        experiment_id=XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID,
        dataset_id="xjtu-sy",
        split_id="xjtu-sy-condition-stratified-5fold-v1",
        fold_id="fold-1",
        fit_partition=FitPartition.TRAIN,
        reference_strategy=ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD,
        feature_set_id=VIBRATION_STATISTICAL_FEATURE_SET_ID,
        feature_names=_FEATURE_NAMES,
        scaling_strategy=ScalingStrategy.ROBUST,
        observation_count=3_246,
        fitted_center=tuple(float(index) for index in range(len(_FEATURE_NAMES))),
        fitted_scale=(2.0,) * len(_FEATURE_NAMES),
        zero_iqr_features=(),
    )


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


def test_xjtu_sequence_edge_freezes_reference_and_validation_populations() -> None:
    prepared = prepare_xjtu_lstm_sequence_inputs(
        _state(),
        _vectors("train"),
        _vectors("validation"),
    )

    assert prepared.protocol_id == XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID
    assert prepared.complete_train_acquisition_count == 3_246
    assert prepared.reference.spec == prepared.validation.spec == XJTU_LSTM_SEQUENCE_SPEC
    assert prepared.reference.source_observation_count == 1_084
    assert prepared.reference.sequence_count == 9
    assert prepared.reference.window_count == 1_021
    assert prepared.reference.dropped_prefix_observation_count == 63
    assert prepared.reference.unaligned_source_observation_count == 63
    assert prepared.validation.source_observation_count == 2_818
    assert prepared.validation.sequence_count == 3
    assert prepared.validation.window_count == 2_797
    assert prepared.validation.dropped_prefix_observation_count == 21
    assert prepared.validation.unaligned_source_observation_count == 21

    assert Counter(window.asset_id for window in prepared.reference.windows) == {
        "Bearing1_3": 46,
        "Bearing1_4": 34,
        "Bearing1_5": 11,
        "Bearing2_3": 171,
        "Bearing2_4": 7,
        "Bearing2_5": 106,
        "Bearing3_3": 117,
        "Bearing3_4": 498,
        "Bearing3_5": 31,
    }
    assert Counter(window.asset_id for window in prepared.validation.windows) == {
        "Bearing1_2": 154,
        "Bearing2_2": 154,
        "Bearing3_2": 2_489,
    }


def test_xjtu_sequence_edge_preserves_scaled_rows_and_right_edge_lineage() -> None:
    prepared = prepare_xjtu_lstm_sequence_inputs(
        _state(),
        _vectors("train"),
        _vectors("validation"),
    )

    first = prepared.reference.windows[0]
    assert first.sequence_id == first.asset_id == "Bearing1_3"
    assert first.partition_id == "train"
    assert first.source_positions == tuple(range(1, 9))
    assert first.source_observation_ids == tuple(
        f"Bearing1_3:acquisition-{index}" for index in range(1, 9)
    )
    assert first.aligned_source_observation_id == "Bearing1_3:acquisition-8"
    assert first.values[0] == (0.5,) * len(_FEATURE_NAMES)
    assert first.values[-1] == (4.0,) * len(_FEATURE_NAMES)

    final_by_asset = {
        window.asset_id: window
        for window in (*prepared.reference.windows, *prepared.validation.windows)
    }
    assert final_by_asset["Bearing3_5"].end_source_observation_id == ("Bearing3_5:acquisition-38")
    assert final_by_asset["Bearing3_2"].end_source_observation_id == ("Bearing3_2:acquisition-2496")


def test_xjtu_sequence_edge_canonicalizes_input_order_from_acquisition_metadata() -> None:
    expected = prepare_xjtu_lstm_sequence_inputs(
        _state(),
        _vectors("train"),
        _vectors("validation"),
    )
    reordered = prepare_xjtu_lstm_sequence_inputs(
        _state(),
        tuple(reversed(_vectors("train"))),
        tuple(reversed(_vectors("validation"))),
    )

    assert reordered == expected


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"experiment_id": "another-experiment"}, "experiment_id"),
        ({"dataset_id": "ims-bearings"}, "dataset_id"),
        ({"fold_id": "fold-2"}, "fold_id"),
        ({"reference_strategy": ReferenceStrategy.ALL_TRAIN_OBSERVATIONS}, "reference_strategy"),
        ({"scaling_strategy": ScalingStrategy.IDENTITY}, "scaling_strategy"),
        ({"observation_count": 3_245}, "observation_count"),
    ],
)
def test_xjtu_sequence_edge_rejects_preprocessing_protocol_drift(
    changes: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(XjtuSequenceConstructionError, match=message):
        prepare_xjtu_lstm_sequence_inputs(
            replace(_state(), **changes),
            _vectors("train"),
            _vectors("validation"),
        )


def test_xjtu_sequence_edge_rejects_incomplete_partition_coverage() -> None:
    with pytest.raises(XjtuSequenceConstructionError, match="complete validation acquisition"):
        prepare_xjtu_lstm_sequence_inputs(
            _state(),
            _vectors("train"),
            _vectors("validation")[:-1],
        )


def test_xjtu_sequence_edge_rejects_duplicate_acquisition_identity() -> None:
    train = _vectors("train")
    duplicate = replace(
        train[0],
        metadata={"dataset_id": "xjtu-sy", "acquisition_index": 2},
    )

    with pytest.raises(XjtuSequenceConstructionError, match="duplicate acquisition 2"):
        prepare_xjtu_lstm_sequence_inputs(
            _state(),
            (duplicate, *train[1:]),
            _vectors("validation"),
        )


def test_xjtu_sequence_edge_rejects_feature_schema_drift() -> None:
    validation = _vectors("validation")
    invalid = replace(
        validation[0],
        feature_names=tuple(reversed(validation[0].feature_names)),
        values=tuple(reversed(validation[0].values)),
    )

    with pytest.raises(XjtuSequenceConstructionError, match="schema"):
        prepare_xjtu_lstm_sequence_inputs(
            _state(),
            _vectors("train"),
            (invalid, *validation[1:]),
        )
