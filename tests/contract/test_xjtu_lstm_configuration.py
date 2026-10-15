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


def test_packaged_xjtu_lstm_configuration_exposes_protocol_axes() -> None:
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
