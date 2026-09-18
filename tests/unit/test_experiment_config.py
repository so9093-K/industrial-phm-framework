from textwrap import dedent

import pytest

from industrial_phm.experiments import (
    ExperimentConfigError,
    ExperimentContext,
    FitPartition,
    ModelFamily,
    ReferenceStrategy,
    ScalingStrategy,
    load_experiment_configs,
)


def _config_toml(
    *,
    fold_id: str = "fold-1",
    fit_partition: str = "train",
    selected_feature: str = "feature.channel.rms",
    sampling_policy_id: str = "reference-uniform-v1",
    include_seed: bool = True,
) -> str:
    seed = "random_seed = 42" if include_seed else ""
    return dedent(
        f"""
        schema_id = "experiment-config-v1"

        [[experiment]]
        experiment_id = "reference-candidate-v1"
        dataset_id = "reference-dataset"
        split_id = "reference-split-v1"
        fold_id = "{fold_id}"
        fit_partition = "{fit_partition}"
        feature_set_id = "reference-features-v1"
        selected_features = ["{selected_feature}"]
        reference_strategy = "all-train-observations"
        sampling_policy_id = "{sampling_policy_id}"
        scaling_strategy = "identity"
        model_family = "isolation-forest"
        {seed}

        [experiment.model_parameters]
        n_estimators = 256
        max_samples = "auto"
        contamination = "auto"
        max_features = 1.0
        bootstrap = false
        """
    )


def _context() -> ExperimentContext:
    return ExperimentContext(
        dataset_id="reference-dataset",
        split_id="reference-split-v1",
        fold_ids=("fold-1", "fold-2"),
        feature_set_id="reference-features-v1",
        feature_names=("feature.channel.rms", "feature.channel.mean"),
        supported_sampling_policy_ids=("reference-uniform-v1",),
    )


def test_load_experiment_config_resolves_typed_immutable_candidate() -> None:
    (config,) = load_experiment_configs(_config_toml(), context=_context())

    assert config.fit_partition is FitPartition.TRAIN
    assert config.reference_strategy is ReferenceStrategy.ALL_TRAIN_OBSERVATIONS
    assert config.sampling_policy_id == "reference-uniform-v1"
    assert config.scaling_strategy is ScalingStrategy.IDENTITY
    assert config.model_family is ModelFamily.ISOLATION_FOREST
    assert config.selected_features == ("feature.channel.rms",)
    assert dict(config.model_parameters) == {
        "n_estimators": 256,
        "max_samples": "auto",
        "contamination": "auto",
        "max_features": 1.0,
        "bootstrap": False,
    }
    assert config.random_seed == 42


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (_config_toml(fit_partition="test"), "unsupported fit_partition"),
        (_config_toml(include_seed=False), "missing=\\['random_seed'\\]"),
    ],
)
def test_config_parser_rejects_unsupported_or_incomplete_invariants(
    content: str,
    message: str,
) -> None:
    with pytest.raises(ExperimentConfigError, match=message):
        load_experiment_configs(content)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (_config_toml(fold_id="fold-9"), "unknown fold_id"),
        (_config_toml(selected_feature="feature.channel.unknown"), "unknown selected feature"),
        (
            _config_toml(sampling_policy_id="unsupported-policy-v1"),
            "unknown sampling_policy_id",
        ),
    ],
)
def test_config_context_rejects_unknown_split_owned_references(
    content: str,
    message: str,
) -> None:
    with pytest.raises(ExperimentConfigError, match=message):
        load_experiment_configs(content, context=_context())


def test_config_parser_rejects_duplicate_experiment_ids() -> None:
    first = _config_toml()
    experiment_table = first.split("[[experiment]]", maxsplit=1)[1]
    duplicated = f"{first}\n[[experiment]]{experiment_table}"

    with pytest.raises(ExperimentConfigError, match="experiment_id values must be unique"):
        load_experiment_configs(duplicated)
