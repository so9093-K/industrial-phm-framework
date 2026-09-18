from dataclasses import replace

import pytest

from industrial_phm.adapters import XJTU_SY_CHANNELS
from industrial_phm.experiments import (
    XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID,
    ModelFamily,
    ReferenceStrategy,
    ScalingStrategy,
    XjtuLstmDevelopmentError,
    get_xjtu_lstm_development_configuration,
)
from industrial_phm.experiments import xjtu_lstm as module
from industrial_phm.features import vibration_feature_names


def test_packaged_xjtu_lstm_configuration_matches_protocol_v1() -> None:
    config = get_xjtu_lstm_development_configuration()

    assert config.experiment_id == XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID
    assert config.dataset_id == "xjtu-sy"
    assert config.fold_id == "fold-1"
    assert len(config.selected_features) == 16
    assert config.reference_strategy is ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD
    assert config.sampling_policy_id == "reference-window-uniform-v1"
    assert config.scaling_strategy is ScalingStrategy.ROBUST
    assert config.model_family is ModelFamily.LSTM_AUTOENCODER
    assert config.random_seed == 42
    assert dict(config.model_parameters) == {
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


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"experiment_id": "another-experiment"}, "experiment_id"),
        ({"model_family": ModelFamily.ISOLATION_FOREST}, "model_family"),
        ({"scaling_strategy": ScalingStrategy.IDENTITY}, "scaling_strategy"),
        ({"sampling_policy_id": "acquisition-uniform-v1"}, "sampling_policy_id"),
        (
            {"selected_features": tuple(reversed(vibration_feature_names(XJTU_SY_CHANNELS)))},
            "16-feature",
        ),
        ({"random_seed": 7}, "random_seed"),
    ],
)
def test_xjtu_lstm_configuration_rejects_protocol_axis_drift(
    monkeypatch: pytest.MonkeyPatch,
    changes: dict[str, object],
    message: str,
) -> None:
    config = get_xjtu_lstm_development_configuration()
    monkeypatch.setattr(
        module,
        "load_packaged_xjtu_experiment_configs",
        lambda _: (replace(config, **changes),),
    )
    module.get_xjtu_lstm_development_configuration.cache_clear()

    with pytest.raises(XjtuLstmDevelopmentError, match=message):
        module.get_xjtu_lstm_development_configuration()

    module.get_xjtu_lstm_development_configuration.cache_clear()


def test_xjtu_lstm_configuration_rejects_parameter_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = get_xjtu_lstm_development_configuration()
    changed = replace(
        config,
        model_parameters={**config.model_parameters, "epochs": 49},
    )
    monkeypatch.setattr(
        module,
        "load_packaged_xjtu_experiment_configs",
        lambda _: (changed,),
    )
    module.get_xjtu_lstm_development_configuration.cache_clear()

    with pytest.raises(XjtuLstmDevelopmentError, match="parameters"):
        module.get_xjtu_lstm_development_configuration()

    module.get_xjtu_lstm_development_configuration.cache_clear()
