"""Frozen XJTU LSTM configuration and protocol-defined model-fitting execution path."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache

from industrial_phm.adapters import XJTU_SY_CHANNELS
from industrial_phm.experiments.config import (
    ExperimentConfig,
    FitPartition,
    ModelFamily,
    ReferenceStrategy,
    ScalingStrategy,
)
from industrial_phm.experiments.xjtu import load_packaged_xjtu_experiment_configs
from industrial_phm.experiments.xjtu_sequence import (
    XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID,
    XJTU_LSTM_SEQUENCE_SPEC,
    XjtuSequenceInputs,
    prepare_xjtu_lstm_sequence_inputs,
)
from industrial_phm.features import VibrationFeatureVector, vibration_feature_names
from industrial_phm.models.lstm_autoencoder import (
    FittedLstmAutoencoder,
    fit_lstm_autoencoder,
)
from industrial_phm.models.reconstruction_scoring import (
    ReconstructionScores,
    score_reconstructions,
)
from industrial_phm.preprocessing import (
    PreprocessingError,
    PreprocessingFitProvenance,
    PreprocessingState,
    fit_preprocessing_state,
)

_MANIFEST = "xjtu-sy-lstm-autoencoder-fold-1-development-v1.toml"
_EXPECTED_PARAMETERS: Mapping[str, str | int | float | bool] = {
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


class XjtuLstmDevelopmentError(ValueError):
    """Raised when the frozen XJTU LSTM development execution drifts."""


@dataclass(frozen=True, slots=True)
class XjtuLstmDevelopmentFit:
    """Train-fitted preprocessing, sequence populations, and final-epoch model."""

    config: ExperimentConfig
    preprocessing_state: PreprocessingState
    sequence_inputs: XjtuSequenceInputs
    model: FittedLstmAutoencoder

    def __post_init__(self) -> None:
        if not isinstance(self.config, ExperimentConfig):
            raise XjtuLstmDevelopmentError("config must be an ExperimentConfig")
        if not isinstance(self.preprocessing_state, PreprocessingState):
            raise XjtuLstmDevelopmentError("preprocessing_state must be a PreprocessingState")
        if not isinstance(self.sequence_inputs, XjtuSequenceInputs):
            raise XjtuLstmDevelopmentError("sequence_inputs must be XjtuSequenceInputs")
        if not isinstance(self.model, FittedLstmAutoencoder):
            raise XjtuLstmDevelopmentError("model must be a FittedLstmAutoencoder")
        experiment_ids = {
            self.config.experiment_id,
            self.preprocessing_state.experiment_id,
            self.model.experiment_id,
        }
        if experiment_ids != {XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID}:
            raise XjtuLstmDevelopmentError(
                "configuration, preprocessing state, and model must share the protocol identity"
            )
        if (
            self.preprocessing_state.observation_count
            != self.sequence_inputs.complete_train_acquisition_count
        ):
            raise XjtuLstmDevelopmentError(
                "preprocessing fit population must match complete train sequence provenance"
            )
        if self.model.training.fit_window_count != self.sequence_inputs.reference.window_count:
            raise XjtuLstmDevelopmentError(
                "model fit population must match the constructed reference windows"
            )


@lru_cache(maxsize=1)
def get_xjtu_lstm_development_configuration() -> ExperimentConfig:
    """Return the single code-validated configuration frozen by protocol v1."""
    configs = load_packaged_xjtu_experiment_configs(_MANIFEST)
    if len(configs) != 1:
        raise XjtuLstmDevelopmentError("XJTU LSTM manifest must contain exactly one experiment")
    config = configs[0]
    expected = (
        ("experiment_id", config.experiment_id, XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID),
        ("dataset_id", config.dataset_id, "xjtu-sy"),
        ("split_id", config.split_id, "xjtu-sy-condition-stratified-5fold-v1"),
        ("fold_id", config.fold_id, "fold-1"),
        ("fit_partition", config.fit_partition, FitPartition.TRAIN),
        (
            "reference_strategy",
            config.reference_strategy,
            ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD,
        ),
        ("sampling_policy_id", config.sampling_policy_id, "reference-window-uniform-v1"),
        ("scaling_strategy", config.scaling_strategy, ScalingStrategy.ROBUST),
        ("model_family", config.model_family, ModelFamily.LSTM_AUTOENCODER),
        ("random_seed", config.random_seed, 42),
    )
    for field_name, value, configured in expected:
        if value != configured:
            raise XjtuLstmDevelopmentError(
                f"XJTU LSTM {field_name} must match protocol v1; "
                f"expected {configured!r}, got {value!r}"
            )
    if tuple(config.selected_features) != vibration_feature_names(XJTU_SY_CHANNELS):
        raise XjtuLstmDevelopmentError("XJTU LSTM protocol requires the full 16-feature schema")
    if dict(config.model_parameters) != dict(_EXPECTED_PARAMETERS):
        raise XjtuLstmDevelopmentError(
            "XJTU LSTM model parameters must match the frozen protocol v1 configuration"
        )
    if config.model_parameters["sequence_length"] != XJTU_LSTM_SEQUENCE_SPEC.length:
        raise XjtuLstmDevelopmentError(
            "XJTU LSTM sequence length must match the sequence construction contract"
        )
    return config


def fit_xjtu_lstm_development_model(
    train_vectors: Sequence[VibrationFeatureVector],
    validation_vectors: Sequence[VibrationFeatureVector],
) -> XjtuLstmDevelopmentFit:
    """Fit preprocessing and model from one shared complete-train population."""
    config = get_xjtu_lstm_development_configuration()
    materialized_train = tuple(train_vectors)
    materialized_validation = tuple(validation_vectors)
    _validate_train_feature_schema(config, materialized_train)
    try:
        preprocessing_state = fit_preprocessing_state(
            config,
            PreprocessingFitProvenance(
                dataset_id=config.dataset_id,
                split_id=config.split_id,
                fold_id=config.fold_id,
                fit_partition=config.fit_partition,
                feature_set_id=config.feature_set_id,
            ),
            config.selected_features,
            (vector.values for vector in materialized_train),
        )
    except PreprocessingError as error:
        raise XjtuLstmDevelopmentError(
            f"invalid XJTU LSTM preprocessing fit input: {error}"
        ) from error

    sequence_inputs = prepare_xjtu_lstm_sequence_inputs(
        preprocessing_state,
        materialized_train,
        materialized_validation,
    )
    model = fit_lstm_autoencoder(config, sequence_inputs.reference)
    return XjtuLstmDevelopmentFit(
        config=config,
        preprocessing_state=preprocessing_state,
        sequence_inputs=sequence_inputs,
        model=model,
    )


def score_xjtu_lstm_development_validation(
    fitted: XjtuLstmDevelopmentFit,
) -> ReconstructionScores:
    """Reconstruct and score the frozen validation sequence population."""
    if not isinstance(fitted, XjtuLstmDevelopmentFit):
        raise XjtuLstmDevelopmentError("fitted must be an XjtuLstmDevelopmentFit")
    validation = fitted.sequence_inputs.validation
    reconstructions = fitted.model.reconstruct(validation)
    return score_reconstructions(validation, reconstructions)


def _validate_train_feature_schema(
    config: ExperimentConfig,
    vectors: Sequence[VibrationFeatureVector],
) -> None:
    if not vectors:
        raise XjtuLstmDevelopmentError(
            "XJTU LSTM preprocessing fit requires complete train feature vectors"
        )
    for vector_index, vector in enumerate(vectors):
        if vector.feature_set_id != config.feature_set_id:
            raise XjtuLstmDevelopmentError(
                f"train feature vector {vector_index} feature_set_id does not match config"
            )
        if tuple(vector.feature_names) != tuple(config.selected_features):
            raise XjtuLstmDevelopmentError(
                f"train feature vector {vector_index} schema does not match config"
            )
        if vector.metadata.get("dataset_id") != config.dataset_id:
            raise XjtuLstmDevelopmentError(
                f"train feature vector {vector_index} must preserve dataset_id"
            )
