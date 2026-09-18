from dataclasses import replace

import pytest

from industrial_phm.experiments import (
    XJTU_FINALIZED_CONFIGURATION_ID,
    ReferenceStrategy,
    ScalingStrategy,
    XjtuFinalizedConfigurationError,
    get_xjtu_finalized_configuration,
    get_xjtu_isolation_forest_candidates,
    get_xjtu_reference_hypotheses,
)
from industrial_phm.experiments import xjtu_finalized as module

_SELECTED_V2 = "xjtu-sy-iforest-fold-1-acquisition-uniform-full-16-identity-v2"


def _selected_candidate():
    return next(
        candidate
        for candidate in get_xjtu_isolation_forest_candidates()
        if candidate.experiment_id == _SELECTED_V2
    )


def test_finalized_configuration_is_exactly_one_configuration() -> None:
    config = get_xjtu_finalized_configuration()

    assert config.experiment_id == XJTU_FINALIZED_CONFIGURATION_ID
    assert config.fold_id == "fold-1"


def test_finalized_configuration_keeps_every_axis_development_did_not_change() -> None:
    config = get_xjtu_finalized_configuration()
    selected = _selected_candidate()

    for axis in (
        "dataset_id",
        "split_id",
        "fold_id",
        "fit_partition",
        "feature_set_id",
        "sampling_policy_id",
        "scaling_strategy",
        "model_family",
        "random_seed",
    ):
        assert getattr(config, axis) == getattr(selected, axis)
    assert tuple(config.selected_features) == tuple(selected.selected_features)
    assert dict(config.model_parameters) == dict(selected.model_parameters)


def test_finalized_configuration_carries_the_adopted_reference_strategy() -> None:
    config = get_xjtu_finalized_configuration()
    adopted = next(
        hypothesis
        for hypothesis in get_xjtu_reference_hypotheses()
        if hypothesis.reference_strategy is ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD
    )

    assert config.reference_strategy is ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD
    assert config.reference_strategy is adopted.reference_strategy
    assert config.reference_strategy is not _selected_candidate().reference_strategy


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"reference_strategy": ReferenceStrategy.ALL_TRAIN_OBSERVATIONS}, "adopted"),
        ({"scaling_strategy": ScalingStrategy.ROBUST}, "scaling_strategy"),
        ({"sampling_policy_id": "bearing-balanced-resample-v1"}, "sampling_policy_id"),
        ({"random_seed": 7}, "random_seed"),
        ({"fold_id": "fold-2"}, "fold-1 only"),
        ({"experiment_id": "some-other-configuration"}, "finalized experiment_id"),
    ],
)
def test_finalized_configuration_rejects_axis_drift(
    monkeypatch: pytest.MonkeyPatch,
    changes: dict[str, object],
    message: str,
) -> None:
    config = get_xjtu_finalized_configuration()
    monkeypatch.setattr(
        module,
        "load_packaged_xjtu_experiment_configs",
        lambda _: (replace(config, **changes),),
    )
    module.get_xjtu_finalized_configuration.cache_clear()

    with pytest.raises(XjtuFinalizedConfigurationError, match=message):
        module.get_xjtu_finalized_configuration()

    module.get_xjtu_finalized_configuration.cache_clear()


def test_finalized_configuration_rejects_a_reopened_grid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = get_xjtu_finalized_configuration()
    monkeypatch.setattr(
        module,
        "load_packaged_xjtu_experiment_configs",
        lambda _: (config, replace(config, experiment_id="second-configuration")),
    )
    module.get_xjtu_finalized_configuration.cache_clear()

    with pytest.raises(XjtuFinalizedConfigurationError, match="exactly one experiment"):
        module.get_xjtu_finalized_configuration()

    module.get_xjtu_finalized_configuration.cache_clear()


def test_finalized_configuration_is_the_adopted_hypothesis_promoted() -> None:
    """Every effective axis must equal the adopted H1; only the identity is new."""
    config = get_xjtu_finalized_configuration()
    adopted = next(
        hypothesis
        for hypothesis in get_xjtu_reference_hypotheses()
        if hypothesis.reference_strategy is ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD
    )

    assert config.experiment_id != adopted.experiment_id
    for axis in (
        "dataset_id",
        "split_id",
        "fold_id",
        "fit_partition",
        "feature_set_id",
        "reference_strategy",
        "sampling_policy_id",
        "scaling_strategy",
        "model_family",
        "random_seed",
    ):
        assert getattr(config, axis) == getattr(adopted, axis), axis
    assert tuple(config.selected_features) == tuple(adopted.selected_features)
    assert dict(config.model_parameters) == dict(adopted.model_parameters)


def test_comparison_manifests_are_preserved_as_historical_evidence() -> None:
    assert len(get_xjtu_isolation_forest_candidates()) == 4
    assert len(get_xjtu_reference_hypotheses()) == 2
    assert get_xjtu_finalized_configuration().experiment_id not in {
        candidate.experiment_id for candidate in get_xjtu_isolation_forest_candidates()
    } | {hypothesis.experiment_id for hypothesis in get_xjtu_reference_hypotheses()}
