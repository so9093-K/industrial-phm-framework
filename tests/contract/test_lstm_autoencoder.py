from dataclasses import replace

import pytest

pytest.importorskip("torch", reason="install the deep-learning extra")

from industrial_phm.experiments import (
    ExperimentConfig,
    FitPartition,
    ModelFamily,
    ReferenceStrategy,
    ScalingStrategy,
)
from industrial_phm.models import LstmAutoencoderError, fit_lstm_autoencoder
from industrial_phm.sequences import (
    SequenceFeatureObservation,
    SequenceWindowSpec,
    construct_sequence_windows,
)

_FEATURE_NAMES = ("feature.channel.rms", "feature.channel.crest_factor")
_PARAMETERS: dict[str, str | int | float | bool] = {
    "sequence_length": 3,
    "hidden_size": 4,
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
    "batch_size": 2,
    "epochs": 2,
    "shuffle": True,
    "checkpoint": "final-epoch",
    "numeric_precision": "float32",
    "device": "cpu",
    "deterministic_algorithms": True,
}


def _config(
    parameters: dict[str, str | int | float | bool] | None = None,
) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="lstm-reference-v1",
        dataset_id="reference-dataset",
        split_id="reference-split-v1",
        fold_id="fold-1",
        fit_partition=FitPartition.TRAIN,
        feature_set_id="reference-features-v1",
        selected_features=_FEATURE_NAMES,
        reference_strategy=ReferenceStrategy.ALL_TRAIN_OBSERVATIONS,
        sampling_policy_id="reference-window-uniform-v1",
        scaling_strategy=ScalingStrategy.ROBUST,
        model_family=ModelFamily.LSTM_AUTOENCODER,
        model_parameters=_PARAMETERS if parameters is None else parameters,
        random_seed=42,
    )


def _construction(partition: str = "train", *, stride: int = 1):
    observations = tuple(
        SequenceFeatureObservation(
            sequence_id="run-a",
            asset_id="asset-a",
            partition_id=partition,
            source_observation_id=f"run-a:observation-{position}",
            sequence_position=position,
            feature_values=(float(position) / 10.0, float(position + 1) / 10.0),
        )
        for position in range(8)
    )
    return construct_sequence_windows(
        observations,
        feature_set_id="reference-features-v1",
        feature_names=_FEATURE_NAMES,
        spec=SequenceWindowSpec(length=3, stride=stride),
    )


def test_lstm_fit_and_reconstruction_repeat_exactly_on_cpu() -> None:
    config = _config()
    construction = _construction()

    first = fit_lstm_autoencoder(config, construction)
    second = fit_lstm_autoencoder(config, construction)
    first_reconstruction = first.reconstruct(construction)
    second_reconstruction = second.reconstruct(construction)

    assert first.training == second.training
    assert first_reconstruction == second_reconstruction
    assert first.training.runtime == "pytorch"
    assert first.training.device == "cpu"
    assert first.training.numeric_precision == "float32"
    assert first.training.deterministic_algorithms is True
    assert first.training.random_seed == 42
    assert first.training.fit_window_count == construction.window_count == 6
    assert first.training.parameter_count == 298
    assert first.training.epochs == len(first.training.epoch_losses) == 2
    assert first.training.final_loss == first.training.epoch_losses[-1]
    assert first_reconstruction.window_count == construction.window_count
    assert first_reconstruction.aligned_source_observation_ids == tuple(
        window.aligned_source_observation_id for window in construction.windows
    )
    assert len(first_reconstruction.values[0]) == 3
    assert len(first_reconstruction.values[0][0]) == 2


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        ({key: value for key, value in _PARAMETERS.items() if key != "epochs"}, "missing"),
        ({**_PARAMETERS, "early_stopping": True}, "unknown"),
        ({**_PARAMETERS, "epochs": 0}, "epochs"),
        ({**_PARAMETERS, "optimizer": "sgd"}, "optimizer"),
        ({**_PARAMETERS, "numeric_precision": "float64"}, "numeric_precision"),
        ({**_PARAMETERS, "device": "mps"}, "device"),
        ({**_PARAMETERS, "deterministic_algorithms": False}, "deterministic"),
    ],
)
def test_lstm_rejects_parameter_contract_drift(
    parameters: dict[str, str | int | float | bool],
    message: str,
) -> None:
    with pytest.raises(LstmAutoencoderError, match=message):
        fit_lstm_autoencoder(_config(parameters), _construction())


def test_lstm_fit_rejects_non_train_windows() -> None:
    with pytest.raises(LstmAutoencoderError, match="train reference"):
        fit_lstm_autoencoder(_config(), _construction(partition="validation"))


def test_lstm_model_accepts_dataset_owned_window_stride() -> None:
    construction = _construction(stride=2)

    fitted = fit_lstm_autoencoder(_config(), construction)

    assert fitted.spec.stride == 2
    assert fitted.training.fit_window_count == construction.window_count == 3


def test_lstm_fit_rejects_config_and_window_schema_drift() -> None:
    config = replace(
        _config(),
        selected_features=tuple(reversed(_FEATURE_NAMES)),
    )

    with pytest.raises(LstmAutoencoderError, match="feature schema"):
        fit_lstm_autoencoder(config, _construction())


def test_fitted_lstm_rejects_reconstruction_spec_drift() -> None:
    model = fit_lstm_autoencoder(_config(), _construction())
    observations = tuple(
        SequenceFeatureObservation(
            sequence_id="run-a",
            asset_id="asset-a",
            partition_id="validation",
            source_observation_id=f"run-a:validation-{position}",
            sequence_position=position,
            feature_values=(float(position), float(position + 1)),
        )
        for position in range(8)
    )
    incompatible = construct_sequence_windows(
        observations,
        feature_set_id="reference-features-v1",
        feature_names=_FEATURE_NAMES,
        spec=SequenceWindowSpec(length=4, stride=1),
    )

    with pytest.raises(LstmAutoencoderError, match="window spec"):
        model.reconstruct(incompatible)
