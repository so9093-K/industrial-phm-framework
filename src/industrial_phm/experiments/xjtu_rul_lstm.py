"""Frozen XJTU temporal LSTM RUL model for prognostics protocol v1."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from industrial_phm.adapters import (
    XJTU_SY_CHANNELS,
    get_xjtu_expected_acquisition_count,
)
from industrial_phm.experiments.config import (
    ExperimentConfig,
    FitPartition,
    ModelFamily,
    ReferenceStrategy,
    ScalingStrategy,
)
from industrial_phm.experiments.xjtu import (
    get_xjtu_reference_split,
    load_packaged_xjtu_experiment_configs,
)
from industrial_phm.experiments.xjtu_rul import (
    XJTU_RUL_TARGET_DEFINITION_ID,
    XJTU_RUL_TARGET_UNIT,
    XjtuRulTargetError,
    get_xjtu_rul_partition_assets,
    validate_xjtu_recorded_end_rul_targets,
)
from industrial_phm.features import VibrationFeatureVector, vibration_feature_names
from industrial_phm.models import (
    FittedLstmRulRegressor,
    LstmRulRegressionError,
    fit_lstm_rul_regression,
)
from industrial_phm.preprocessing import (
    PreprocessingError,
    PreprocessingFitProvenance,
    PreprocessingState,
    fit_preprocessing_state,
)
from industrial_phm.prognostics import (
    RulPredictionObservation,
    RulPredictionSeries,
    RulTargetSeries,
)
from industrial_phm.sequences import (
    SequenceConstruction,
    SequenceFeatureObservation,
    SequenceWindowError,
    SequenceWindowSpec,
    construct_sequence_windows,
)

XJTU_RUL_LSTM_METHOD_ID = "xjtu-sy-rul-lstm-fold-1-v1"
XJTU_RUL_LSTM_SEQUENCE_SPEC = SequenceWindowSpec(length=8, stride=1)

_MANIFEST = "xjtu-sy-rul-lstm-fold-1-v1.toml"
_DATASET_ID = "xjtu-sy"
_FOLD_ID = "fold-1"
_EXPECTED_TRAIN_ACQUISITION_COUNT = 3_246
_EXPECTED_TRAIN_WINDOW_COUNT = 3_183
_EXPECTED_VALIDATION_ACQUISITION_COUNT = 2_818
_EXPECTED_VALIDATION_WINDOW_COUNT = 2_797
_EXPECTED_PARAMETERS: dict[str, str | int | float | bool] = {
    "sequence_length": 8,
    "hidden_size": 32,
    "layer_count": 1,
    "dropout": 0.0,
    "loss": "mean-squared-error",
    "optimizer": "adam",
    "learning_rate": 0.001,
    "adam_beta1": 0.9,
    "adam_beta2": 0.999,
    "adam_epsilon": 1e-8,
    "weight_decay": 0.0,
    "gradient_clip_norm": 1.0,
    "batch_size": 64,
    "epochs": 50,
    "shuffle": True,
    "checkpoint": "final-epoch",
    "numeric_precision": "float32",
    "device": "cpu",
    "deterministic_algorithms": True,
}
_Partition = Literal["train", "validation", "test"]


class XjtuRulLstmError(ValueError):
    """Raised when the frozen XJTU temporal RUL contract is violated."""


@dataclass(frozen=True, slots=True)
class XjtuRulLstmFit:
    """Train-fitted preprocessing, sequence construction, and LSTM RUL model."""

    config: ExperimentConfig
    preprocessing_state: PreprocessingState
    train_sequence: SequenceConstruction
    model: FittedLstmRulRegressor

    def __post_init__(self) -> None:
        if not isinstance(self.config, ExperimentConfig):
            raise XjtuRulLstmError("config must be an ExperimentConfig")
        if not isinstance(self.preprocessing_state, PreprocessingState):
            raise XjtuRulLstmError("preprocessing_state must be a PreprocessingState")
        if not isinstance(self.train_sequence, SequenceConstruction):
            raise XjtuRulLstmError("train_sequence must be a SequenceConstruction")
        if not isinstance(self.model, FittedLstmRulRegressor):
            raise XjtuRulLstmError("model must be a FittedLstmRulRegressor")

        identities = {
            self.config.experiment_id,
            self.preprocessing_state.experiment_id,
            self.model.experiment_id,
        }
        if identities != {XJTU_RUL_LSTM_METHOD_ID}:
            raise XjtuRulLstmError(
                "configuration, preprocessing state, and model must share method identity"
            )
        if self.preprocessing_state.observation_count != _EXPECTED_TRAIN_ACQUISITION_COUNT:
            raise XjtuRulLstmError(
                "preprocessing state must use the complete fold-1 train population"
            )
        if self.train_sequence.window_count != _EXPECTED_TRAIN_WINDOW_COUNT:
            raise XjtuRulLstmError(
                "train sequence population must match the frozen temporal RUL protocol"
            )
        if self.model.training.fit_window_count != self.train_sequence.window_count:
            raise XjtuRulLstmError("model fit population must match the train sequence population")


@lru_cache(maxsize=1)
def get_xjtu_rul_lstm_configuration() -> ExperimentConfig:
    """Return the single frozen XJTU temporal LSTM RUL configuration."""
    configs = load_packaged_xjtu_experiment_configs(_MANIFEST)
    if len(configs) != 1:
        raise XjtuRulLstmError("XJTU temporal RUL manifest must contain exactly one experiment")
    config = configs[0]
    expected = (
        ("experiment_id", config.experiment_id, XJTU_RUL_LSTM_METHOD_ID),
        ("dataset_id", config.dataset_id, _DATASET_ID),
        ("split_id", config.split_id, get_xjtu_reference_split().split_id),
        ("fold_id", config.fold_id, _FOLD_ID),
        ("fit_partition", config.fit_partition, FitPartition.TRAIN),
        (
            "reference_strategy",
            config.reference_strategy,
            ReferenceStrategy.ALL_TRAIN_OBSERVATIONS,
        ),
        (
            "sampling_policy_id",
            config.sampling_policy_id,
            "sequence-window-uniform-v1",
        ),
        ("scaling_strategy", config.scaling_strategy, ScalingStrategy.ROBUST),
        ("model_family", config.model_family, ModelFamily.LSTM_REGRESSION),
        ("random_seed", config.random_seed, 42),
    )
    for field_name, value, configured in expected:
        if value != configured:
            raise XjtuRulLstmError(
                f"XJTU temporal RUL {field_name} must match protocol v1; "
                f"expected {configured!r}, got {value!r}"
            )

    expected_features = vibration_feature_names(XJTU_SY_CHANNELS)
    if tuple(config.selected_features) != expected_features:
        raise XjtuRulLstmError("XJTU temporal RUL model requires the full 16-feature schema")
    if dict(config.model_parameters) != _EXPECTED_PARAMETERS:
        raise XjtuRulLstmError("XJTU temporal RUL model parameters must match the frozen protocol")
    return config


def fit_xjtu_rul_lstm_model(
    train_vectors: Sequence[VibrationFeatureVector],
    train_targets: Sequence[RulTargetSeries],
) -> XjtuRulLstmFit:
    """Fit train-only preprocessing and a supervised right-edge LSTM RUL model."""
    config = get_xjtu_rul_lstm_configuration()
    ordered_train = _ordered_complete_vectors(train_vectors, partition="train")
    try:
        validated_targets = validate_xjtu_recorded_end_rul_targets(
            train_targets,
            partition="train",
        )
    except XjtuRulTargetError as error:
        raise XjtuRulLstmError(
            f"invalid XJTU train RUL targets for temporal model: {error}"
        ) from error

    provenance = PreprocessingFitProvenance(
        dataset_id=config.dataset_id,
        split_id=config.split_id,
        fold_id=config.fold_id,
        fit_partition=config.fit_partition,
        feature_set_id=config.feature_set_id,
    )
    try:
        state = fit_preprocessing_state(
            config,
            provenance,
            config.selected_features,
            (vector.values for vector in ordered_train),
        )
        train_sequence = prepare_xjtu_rul_sequence_construction(
            state,
            ordered_train,
            partition="train",
        )
    except (PreprocessingError, SequenceWindowError) as error:
        raise XjtuRulLstmError(
            f"invalid XJTU temporal RUL sequence preparation: {error}"
        ) from error

    target_by_id = {
        observation.source_observation_id: observation.remaining_useful_life
        for series in validated_targets
        for observation in series.observations
    }
    try:
        target_values = tuple(
            target_by_id[window.aligned_source_observation_id] for window in train_sequence.windows
        )
    except KeyError as error:
        raise XjtuRulLstmError(
            "train sequence alignment is absent from complete train RUL targets"
        ) from error

    try:
        model = fit_lstm_rul_regression(config, train_sequence, target_values)
    except LstmRulRegressionError as error:
        raise XjtuRulLstmError(f"failed to fit XJTU temporal LSTM RUL model: {error}") from error

    return XjtuRulLstmFit(
        config=config,
        preprocessing_state=state,
        train_sequence=train_sequence,
        model=model,
    )


def predict_xjtu_rul_lstm(
    fitted: XjtuRulLstmFit,
    vectors: Sequence[VibrationFeatureVector],
    *,
    partition: _Partition,
) -> tuple[RulPredictionSeries, ...]:
    """Predict RUL from current and preceding acquisitions in each right-edge window."""
    if not isinstance(fitted, XjtuRulLstmFit):
        raise XjtuRulLstmError("fitted must be an XjtuRulLstmFit")

    construction = prepare_xjtu_rul_sequence_construction(
        fitted.preprocessing_state,
        vectors,
        partition=partition,
    )
    try:
        predicted_values = fitted.model.predict(construction)
    except LstmRulRegressionError as error:
        raise XjtuRulLstmError(f"invalid XJTU temporal RUL scoring input: {error}") from error

    grouped: dict[str, list[RulPredictionObservation]] = defaultdict(list)
    for window, predicted in zip(
        construction.windows,
        predicted_values,
        strict=True,
    ):
        grouped[window.asset_id].append(
            RulPredictionObservation(
                asset_id=window.asset_id,
                partition_id=partition,
                source_observation_id=window.aligned_source_observation_id,
                predicted_remaining_useful_life=predicted,
            )
        )

    return tuple(
        RulPredictionSeries(
            prediction_method_id=XJTU_RUL_LSTM_METHOD_ID,
            target_definition_id=XJTU_RUL_TARGET_DEFINITION_ID,
            unit=XJTU_RUL_TARGET_UNIT,
            asset_id=asset_id,
            partition_id=partition,
            observations=tuple(grouped[asset_id]),
        )
        for asset_id in get_xjtu_rul_partition_assets(partition)
    )


def prepare_xjtu_rul_sequence_construction(
    preprocessing_state: PreprocessingState,
    vectors: Sequence[VibrationFeatureVector],
    *,
    partition: _Partition,
) -> SequenceConstruction:
    """Transform a complete partition and construct frozen right-edge RUL windows."""
    _validate_preprocessing_state(preprocessing_state)
    ordered = _ordered_complete_vectors(vectors, partition=partition)
    try:
        transformed = preprocessing_state.transform(
            preprocessing_state.feature_names,
            (vector.values for vector in ordered),
        )
    except PreprocessingError as error:
        raise XjtuRulLstmError(f"invalid XJTU temporal RUL preprocessing input: {error}") from error

    observations = tuple(
        SequenceFeatureObservation(
            sequence_id=vector.asset_id,
            asset_id=vector.asset_id,
            partition_id=partition,
            source_observation_id=(f"{vector.asset_id}:acquisition-{_acquisition_index(vector)}"),
            sequence_position=_acquisition_index(vector),
            feature_values=row,
        )
        for vector, row in zip(ordered, transformed, strict=True)
    )
    try:
        construction = construct_sequence_windows(
            observations,
            feature_set_id=preprocessing_state.feature_set_id,
            feature_names=preprocessing_state.feature_names,
            spec=XJTU_RUL_LSTM_SEQUENCE_SPEC,
        )
    except SequenceWindowError as error:
        raise XjtuRulLstmError(f"invalid XJTU temporal RUL sequence input: {error}") from error

    _validate_partition_construction(construction, partition=partition)
    return construction


def _validate_preprocessing_state(state: PreprocessingState) -> None:
    config = get_xjtu_rul_lstm_configuration()
    expected = (
        ("experiment_id", state.experiment_id, config.experiment_id),
        ("dataset_id", state.dataset_id, config.dataset_id),
        ("split_id", state.split_id, config.split_id),
        ("fold_id", state.fold_id, config.fold_id),
        ("fit_partition", state.fit_partition, FitPartition.TRAIN),
        ("feature_set_id", state.feature_set_id, config.feature_set_id),
        (
            "feature_names",
            tuple(state.feature_names),
            tuple(config.selected_features),
        ),
        (
            "reference_strategy",
            state.reference_strategy,
            ReferenceStrategy.ALL_TRAIN_OBSERVATIONS,
        ),
        ("scaling_strategy", state.scaling_strategy, ScalingStrategy.ROBUST),
        (
            "observation_count",
            state.observation_count,
            _EXPECTED_TRAIN_ACQUISITION_COUNT,
        ),
    )
    for field_name, value, configured in expected:
        if value != configured:
            raise XjtuRulLstmError(
                f"preprocessing state {field_name} must match the frozen temporal "
                f"RUL protocol; expected {configured!r}, got {value!r}"
            )


def _ordered_complete_vectors(
    vectors: Sequence[VibrationFeatureVector],
    *,
    partition: _Partition,
) -> tuple[VibrationFeatureVector, ...]:
    if not vectors:
        raise XjtuRulLstmError(f"XJTU temporal RUL {partition} input requires feature vectors")

    expected_assets = get_xjtu_rul_partition_assets(partition)
    by_asset: dict[str, dict[int, VibrationFeatureVector]] = defaultdict(dict)
    for vector_index, vector in enumerate(vectors):
        if not isinstance(vector, VibrationFeatureVector):
            raise XjtuRulLstmError(
                f"XJTU temporal RUL vector {vector_index} must be a VibrationFeatureVector"
            )
        if vector.feature_set_id != "vibration-statistical-v1":
            raise XjtuRulLstmError(
                f"XJTU temporal RUL vector {vector_index} has unexpected feature_set_id"
            )
        if tuple(vector.feature_names) != vibration_feature_names(XJTU_SY_CHANNELS):
            raise XjtuRulLstmError(
                f"XJTU temporal RUL vector {vector_index} has unexpected feature schema"
            )
        if vector.metadata.get("dataset_id") != _DATASET_ID:
            raise XjtuRulLstmError(
                f"XJTU temporal RUL vector {vector_index} must preserve dataset_id {_DATASET_ID!r}"
            )
        if vector.asset_id not in expected_assets:
            raise XjtuRulLstmError(
                f"XJTU temporal RUL input received asset outside {partition}: {vector.asset_id!r}"
            )
        acquisition_index = _acquisition_index(vector)
        if acquisition_index in by_asset[vector.asset_id]:
            raise XjtuRulLstmError(
                f"XJTU temporal RUL {partition} contains duplicate acquisition "
                f"{acquisition_index} for {vector.asset_id}"
            )
        by_asset[vector.asset_id][acquisition_index] = vector

    observed_assets = set(by_asset)
    expected_asset_set = set(expected_assets)
    if observed_assets != expected_asset_set:
        raise XjtuRulLstmError(
            f"XJTU temporal RUL input must cover configured {partition} bearings; "
            f"missing={sorted(expected_asset_set - observed_assets)}, "
            f"unexpected={sorted(observed_assets - expected_asset_set)}"
        )

    ordered: list[VibrationFeatureVector] = []
    for asset_id in expected_assets:
        expected_count = get_xjtu_expected_acquisition_count(asset_id)
        expected_indices = set(range(1, expected_count + 1))
        observed_indices = set(by_asset[asset_id])
        if observed_indices != expected_indices:
            raise XjtuRulLstmError(
                f"XJTU temporal RUL {partition} input must cover {asset_id} "
                f"acquisitions 1..{expected_count}; "
                f"missing={sorted(expected_indices - observed_indices)[:10]}, "
                f"unexpected={sorted(observed_indices - expected_indices)[:10]}"
            )
        ordered.extend(by_asset[asset_id][index] for index in range(1, expected_count + 1))
    return tuple(ordered)


def _validate_partition_construction(
    construction: SequenceConstruction,
    *,
    partition: _Partition,
) -> None:
    expected_assets = get_xjtu_rul_partition_assets(partition)
    expected_source_count = sum(
        get_xjtu_expected_acquisition_count(asset_id) for asset_id in expected_assets
    )
    expected_window_count = expected_source_count - len(expected_assets) * (
        XJTU_RUL_LSTM_SEQUENCE_SPEC.length - 1
    )
    if partition == "train":
        expected_source_count = _EXPECTED_TRAIN_ACQUISITION_COUNT
        expected_window_count = _EXPECTED_TRAIN_WINDOW_COUNT
    elif partition == "validation":
        expected_source_count = _EXPECTED_VALIDATION_ACQUISITION_COUNT
        expected_window_count = _EXPECTED_VALIDATION_WINDOW_COUNT

    expected = (
        ("spec", construction.spec, XJTU_RUL_LSTM_SEQUENCE_SPEC),
        (
            "feature_set_id",
            construction.feature_set_id,
            "vibration-statistical-v1",
        ),
        (
            "feature_names",
            tuple(construction.feature_names),
            vibration_feature_names(XJTU_SY_CHANNELS),
        ),
        ("sequence_count", construction.sequence_count, len(expected_assets)),
        (
            "source_observation_count",
            construction.source_observation_count,
            expected_source_count,
        ),
        ("window_count", construction.window_count, expected_window_count),
        (
            "dropped_prefix_observation_count",
            construction.dropped_prefix_observation_count,
            len(expected_assets) * (XJTU_RUL_LSTM_SEQUENCE_SPEC.length - 1),
        ),
    )
    for field_name, value, configured in expected:
        if value != configured:
            raise XjtuRulLstmError(
                f"{partition} sequence {field_name} must match the frozen temporal "
                f"RUL protocol; expected {configured!r}, got {value!r}"
            )
    if any(window.partition_id != partition for window in construction.windows):
        raise XjtuRulLstmError(f"{partition} RUL sequence windows must preserve partition identity")


def _acquisition_index(vector: VibrationFeatureVector) -> int:
    value = vector.metadata.get("acquisition_index")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise XjtuRulLstmError(
            "XJTU temporal RUL vectors require a positive integer acquisition_index"
        )
    return value
