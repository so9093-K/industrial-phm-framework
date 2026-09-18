"""XJTU-owned preparation of LSTM development sequence windows."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from industrial_phm.adapters import (
    XJTU_SY_CHANNELS,
    get_xjtu_expected_acquisition_count,
)
from industrial_phm.experiments.config import (
    FitPartition,
    ReferenceStrategy,
    ScalingStrategy,
)
from industrial_phm.experiments.xjtu import get_xjtu_reference_split
from industrial_phm.experiments.xjtu_lifecycle import early_third_length
from industrial_phm.features import (
    VIBRATION_STATISTICAL_FEATURE_SET_ID,
    VibrationFeatureVector,
    vibration_feature_names,
)
from industrial_phm.preprocessing import PreprocessingError, PreprocessingState
from industrial_phm.sequences import (
    SequenceConstruction,
    SequenceFeatureObservation,
    SequenceWindowError,
    SequenceWindowSpec,
    construct_sequence_windows,
)

XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID = "xjtu-lstm-autoencoder-fold-1-development-v1"
XJTU_LSTM_SEQUENCE_SPEC = SequenceWindowSpec(length=8, stride=1)

_DATASET_ID = "xjtu-sy"
_FOLD_ID = "fold-1"
_EXPECTED_COMPLETE_TRAIN_ACQUISITION_COUNT = 3_246
_EXPECTED_REFERENCE_ACQUISITION_COUNT = 1_084
_EXPECTED_REFERENCE_WINDOW_COUNT = 1_021
_EXPECTED_VALIDATION_ACQUISITION_COUNT = 2_818
_EXPECTED_VALIDATION_WINDOW_COUNT = 2_797
_Partition = Literal["train", "validation"]


class XjtuSequenceConstructionError(ValueError):
    """Raised when XJTU features cannot form the frozen development sequences."""


@dataclass(frozen=True, slots=True)
class XjtuSequenceInputs:
    """Reference and validation windows for the frozen XJTU LSTM protocol."""

    complete_train_acquisition_count: int
    reference: SequenceConstruction
    validation: SequenceConstruction
    protocol_id: str = field(default=XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID, init=False)

    def __post_init__(self) -> None:
        if self.complete_train_acquisition_count != _EXPECTED_COMPLETE_TRAIN_ACQUISITION_COUNT:
            raise XjtuSequenceConstructionError(
                "complete train population must match the frozen XJTU LSTM protocol"
            )
        _validate_construction(
            self.reference,
            partition="train",
            expected_sequence_count=9,
            expected_source_count=_EXPECTED_REFERENCE_ACQUISITION_COUNT,
            expected_window_count=_EXPECTED_REFERENCE_WINDOW_COUNT,
        )
        _validate_construction(
            self.validation,
            partition="validation",
            expected_sequence_count=3,
            expected_source_count=_EXPECTED_VALIDATION_ACQUISITION_COUNT,
            expected_window_count=_EXPECTED_VALIDATION_WINDOW_COUNT,
        )


def prepare_xjtu_lstm_sequence_inputs(
    preprocessing_state: PreprocessingState,
    train_vectors: Sequence[VibrationFeatureVector],
    validation_vectors: Sequence[VibrationFeatureVector],
) -> XjtuSequenceInputs:
    """Transform fold-1 features and construct the frozen reference/validation windows."""
    _validate_preprocessing_state(preprocessing_state)
    fold = next(
        fold
        for fold in get_xjtu_reference_split().folds
        if fold.fold_id == preprocessing_state.fold_id
    )
    ordered_train = _ordered_partition_vectors(
        preprocessing_state,
        train_vectors,
        partition="train",
        expected_assets=fold.train,
    )
    ordered_validation = _ordered_partition_vectors(
        preprocessing_state,
        validation_vectors,
        partition="validation",
        expected_assets=fold.validation,
    )

    transformed_train = _transform_complete_partition(preprocessing_state, ordered_train)
    transformed_validation = _transform_complete_partition(
        preprocessing_state,
        ordered_validation,
    )
    reference_observations = tuple(
        _sequence_observation(vector, row, partition="train", vector_index=index)
        for index, (vector, row) in enumerate(zip(ordered_train, transformed_train, strict=True))
        if _acquisition_index(vector, vector_index=index)
        <= early_third_length(get_xjtu_expected_acquisition_count(vector.asset_id))
    )
    validation_observations = tuple(
        _sequence_observation(vector, row, partition="validation", vector_index=index)
        for index, (vector, row) in enumerate(
            zip(ordered_validation, transformed_validation, strict=True)
        )
    )

    try:
        reference = construct_sequence_windows(
            reference_observations,
            feature_set_id=preprocessing_state.feature_set_id,
            feature_names=preprocessing_state.feature_names,
            spec=XJTU_LSTM_SEQUENCE_SPEC,
        )
        validation = construct_sequence_windows(
            validation_observations,
            feature_set_id=preprocessing_state.feature_set_id,
            feature_names=preprocessing_state.feature_names,
            spec=XJTU_LSTM_SEQUENCE_SPEC,
        )
    except SequenceWindowError as error:
        raise XjtuSequenceConstructionError(
            f"invalid XJTU sequence construction input: {error}"
        ) from error

    return XjtuSequenceInputs(
        complete_train_acquisition_count=len(ordered_train),
        reference=reference,
        validation=validation,
    )


def _validate_preprocessing_state(state: PreprocessingState) -> None:
    expected_feature_names = vibration_feature_names(XJTU_SY_CHANNELS)
    expected = (
        ("experiment_id", state.experiment_id, XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID),
        ("dataset_id", state.dataset_id, _DATASET_ID),
        ("split_id", state.split_id, get_xjtu_reference_split().split_id),
        ("fold_id", state.fold_id, _FOLD_ID),
        ("fit_partition", state.fit_partition, FitPartition.TRAIN),
        ("feature_set_id", state.feature_set_id, VIBRATION_STATISTICAL_FEATURE_SET_ID),
        ("feature_names", tuple(state.feature_names), expected_feature_names),
        (
            "reference_strategy",
            state.reference_strategy,
            ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD,
        ),
        ("scaling_strategy", state.scaling_strategy, ScalingStrategy.ROBUST),
        (
            "observation_count",
            state.observation_count,
            _EXPECTED_COMPLETE_TRAIN_ACQUISITION_COUNT,
        ),
    )
    for field_name, value, configured in expected:
        if value != configured:
            raise XjtuSequenceConstructionError(
                f"preprocessing state {field_name} must match the frozen XJTU LSTM protocol; "
                f"expected {configured!r}, got {value!r}"
            )


def _ordered_partition_vectors(
    state: PreprocessingState,
    vectors: Sequence[VibrationFeatureVector],
    *,
    partition: _Partition,
    expected_assets: Sequence[str],
) -> tuple[VibrationFeatureVector, ...]:
    if not vectors:
        raise XjtuSequenceConstructionError(
            f"XJTU {partition} sequence construction requires feature vectors"
        )

    by_asset: dict[str, dict[int, VibrationFeatureVector]] = defaultdict(dict)
    for vector_index, vector in enumerate(vectors):
        _validate_vector(state, vector, vector_index=vector_index)
        acquisition_index = _acquisition_index(vector, vector_index=vector_index)
        if acquisition_index in by_asset[vector.asset_id]:
            raise XjtuSequenceConstructionError(
                f"XJTU {partition} contains duplicate acquisition {acquisition_index} "
                f"for {vector.asset_id}"
            )
        by_asset[vector.asset_id][acquisition_index] = vector

    expected_asset_set = set(expected_assets)
    observed_asset_set = set(by_asset)
    if observed_asset_set != expected_asset_set:
        raise XjtuSequenceConstructionError(
            f"XJTU sequence input must cover the configured {partition} bearing runs; "
            f"missing={sorted(expected_asset_set - observed_asset_set)}, "
            f"unexpected={sorted(observed_asset_set - expected_asset_set)}"
        )

    ordered: list[VibrationFeatureVector] = []
    for asset_id in expected_assets:
        expected_count = get_xjtu_expected_acquisition_count(asset_id)
        expected_indices = set(range(1, expected_count + 1))
        observed_indices = set(by_asset[asset_id])
        if observed_indices != expected_indices:
            raise XjtuSequenceConstructionError(
                f"XJTU sequence input must cover the complete {partition} acquisition "
                f"sequence for {asset_id}; expected=1..{expected_count}, "
                f"missing={sorted(expected_indices - observed_indices)[:10]}, "
                f"unexpected={sorted(observed_indices - expected_indices)[:10]}"
            )
        ordered.extend(by_asset[asset_id][index] for index in range(1, expected_count + 1))
    return tuple(ordered)


def _validate_vector(
    state: PreprocessingState,
    vector: VibrationFeatureVector,
    *,
    vector_index: int,
) -> None:
    if vector.feature_set_id != state.feature_set_id:
        raise XjtuSequenceConstructionError(
            f"XJTU feature vector {vector_index} feature_set_id does not match preprocessing state"
        )
    if tuple(vector.feature_names) != tuple(state.feature_names):
        raise XjtuSequenceConstructionError(
            f"XJTU feature vector {vector_index} schema does not match preprocessing state"
        )
    if vector.metadata.get("dataset_id") != _DATASET_ID:
        raise XjtuSequenceConstructionError(
            f"XJTU feature vector {vector_index} must preserve dataset_id {_DATASET_ID!r}"
        )


def _transform_complete_partition(
    state: PreprocessingState,
    vectors: Sequence[VibrationFeatureVector],
) -> tuple[tuple[float, ...], ...]:
    try:
        return state.transform(
            state.feature_names,
            (vector.values for vector in vectors),
        )
    except PreprocessingError as error:
        raise XjtuSequenceConstructionError(f"invalid XJTU preprocessing input: {error}") from error


def _sequence_observation(
    vector: VibrationFeatureVector,
    feature_values: Sequence[float],
    *,
    partition: _Partition,
    vector_index: int,
) -> SequenceFeatureObservation:
    acquisition_index = _acquisition_index(vector, vector_index=vector_index)
    return SequenceFeatureObservation(
        sequence_id=vector.asset_id,
        asset_id=vector.asset_id,
        partition_id=partition,
        source_observation_id=f"{vector.asset_id}:acquisition-{acquisition_index}",
        sequence_position=acquisition_index,
        feature_values=feature_values,
    )


def _acquisition_index(vector: VibrationFeatureVector, *, vector_index: int) -> int:
    value = vector.metadata.get("acquisition_index")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise XjtuSequenceConstructionError(
            f"XJTU feature vector {vector_index} requires a positive integer acquisition_index"
        )
    return value


def _validate_construction(
    construction: SequenceConstruction,
    *,
    partition: _Partition,
    expected_sequence_count: int,
    expected_source_count: int,
    expected_window_count: int,
) -> None:
    if not isinstance(construction, SequenceConstruction):
        raise XjtuSequenceConstructionError(f"{partition} must be a SequenceConstruction")
    expected_prefix_count = expected_sequence_count * (XJTU_LSTM_SEQUENCE_SPEC.length - 1)
    expected = (
        ("spec", construction.spec, XJTU_LSTM_SEQUENCE_SPEC),
        ("feature_set_id", construction.feature_set_id, VIBRATION_STATISTICAL_FEATURE_SET_ID),
        (
            "feature_names",
            tuple(construction.feature_names),
            vibration_feature_names(XJTU_SY_CHANNELS),
        ),
        ("sequence_count", construction.sequence_count, expected_sequence_count),
        ("source_observation_count", construction.source_observation_count, expected_source_count),
        ("window_count", construction.window_count, expected_window_count),
        (
            "dropped_prefix_observation_count",
            construction.dropped_prefix_observation_count,
            expected_prefix_count,
        ),
        (
            "unaligned_source_observation_count",
            construction.unaligned_source_observation_count,
            expected_prefix_count,
        ),
    )
    for field_name, value, configured in expected:
        if value != configured:
            raise XjtuSequenceConstructionError(
                f"{partition} {field_name} must match the frozen XJTU LSTM protocol; "
                f"expected {configured!r}, got {value!r}"
            )
    if any(window.partition_id != partition for window in construction.windows):
        raise XjtuSequenceConstructionError(
            f"{partition} windows must preserve their partition identity"
        )
