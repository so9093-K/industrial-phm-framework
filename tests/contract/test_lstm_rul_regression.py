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
from industrial_phm.models import LstmRulRegressionError, fit_lstm_rul_regression
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
        experiment_id="lstm-rul-reference-v1",
        dataset_id="reference-dataset",
        split_id="reference-split-v1",
        fold_id="fold-1",
        fit_partition=FitPartition.TRAIN,
        feature_set_id="reference-features-v1",
        selected_features=_FEATURE_NAMES,
        reference_strategy=ReferenceStrategy.ALL_TRAIN_OBSERVATIONS,
        sampling_policy_id="sequence-window-uniform-v1",
        scaling_strategy=ScalingStrategy.ROBUST,
        model_family=ModelFamily.LSTM_REGRESSION,
        model_parameters=_PARAMETERS if parameters is None else parameters,
        random_seed=42,
    )


def _construction(partition: str = "train", *, length: int = 3):
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
        spec=SequenceWindowSpec(length=length, stride=1),
    )


def _targets() -> tuple[float, ...]:
    return (5.0, 4.0, 3.0, 2.0, 1.0, 0.0)


def test_lstm_rul_fit_and_prediction_repeat_exactly_on_cpu() -> None:
    config = _config()
    train = _construction()
    validation = _construction(partition="validation")

    first = fit_lstm_rul_regression(config, train, _targets())
    second = fit_lstm_rul_regression(config, train, _targets())
    first_predictions = first.predict(validation)
    second_predictions = second.predict(validation)

    assert first.training == second.training
    assert first_predictions == second_predictions
    assert first.training.runtime == "pytorch"
    assert first.training.device == "cpu"
    assert first.training.numeric_precision == "float32"
    assert first.training.deterministic_algorithms is True
    assert first.training.random_seed == 42
    assert first.training.fit_window_count == train.window_count == 6
    assert first.training.parameter_count == 133
    assert first.training.epochs == len(first.training.epoch_losses) == 2
    assert first.training.final_epoch_mean_training_loss == first.training.epoch_losses[-1]
    assert len(first_predictions) == validation.window_count == 6


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
def test_lstm_rul_rejects_parameter_contract_drift(
    parameters: dict[str, str | int | float | bool],
    message: str,
) -> None:
    with pytest.raises(LstmRulRegressionError, match=message):
        fit_lstm_rul_regression(_config(parameters), _construction(), _targets())


def test_lstm_rul_fit_rejects_sampling_policy_drift() -> None:
    config = replace(_config(), sampling_policy_id="acquisition-uniform-v1")

    with pytest.raises(LstmRulRegressionError, match="sampling_policy_id"):
        fit_lstm_rul_regression(config, _construction(), _targets())


def test_lstm_rul_fit_rejects_non_train_windows() -> None:
    with pytest.raises(LstmRulRegressionError, match="train windows"):
        fit_lstm_rul_regression(
            _config(),
            _construction(partition="validation"),
            _targets(),
        )


def test_lstm_rul_fit_rejects_target_count_drift() -> None:
    with pytest.raises(LstmRulRegressionError, match="count must be 6"):
        fit_lstm_rul_regression(_config(), _construction(), _targets()[:-1])


def test_lstm_rul_fit_rejects_config_and_window_schema_drift() -> None:
    config = replace(
        _config(),
        selected_features=tuple(reversed(_FEATURE_NAMES)),
    )

    with pytest.raises(LstmRulRegressionError, match="feature schema"):
        fit_lstm_rul_regression(config, _construction(), _targets())


def test_fitted_lstm_rul_rejects_prediction_spec_drift() -> None:
    model = fit_lstm_rul_regression(_config(), _construction(), _targets())

    with pytest.raises(LstmRulRegressionError, match="window spec"):
        model.predict(_construction(partition="validation", length=4))
