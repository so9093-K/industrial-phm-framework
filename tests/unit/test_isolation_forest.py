from dataclasses import FrozenInstanceError, replace

import pytest

from industrial_phm.experiments import (
    ExperimentConfig,
    FitPartition,
    ModelFamily,
    ReferenceStrategy,
    ScalingStrategy,
)
from industrial_phm.models import (
    AnomalyScores,
    AnomalyScoresError,
    IsolationForestError,
    ModelFitInput,
    ModelScoringInput,
    fit_isolation_forest,
)

_FEATURE_NAMES = ("feature.channel.rms", "feature.channel.crest_factor")
_PARAMETERS: dict[str, str | int | float | bool] = {
    "n_estimators": 64,
    "max_samples": "auto",
    "contamination": "auto",
    "max_features": 1.0,
    "bootstrap": False,
}


def _config(
    parameters: dict[str, str | int | float | bool] | None = None,
) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="isolation-forest-candidate-v1",
        dataset_id="reference-dataset",
        split_id="reference-split-v1",
        fold_id="fold-1",
        fit_partition=FitPartition.TRAIN,
        feature_set_id="reference-features-v1",
        selected_features=_FEATURE_NAMES,
        reference_strategy=ReferenceStrategy.ALL_TRAIN_OBSERVATIONS,
        sampling_policy_id="reference-policy-v1",
        scaling_strategy=ScalingStrategy.IDENTITY,
        model_family=ModelFamily.ISOLATION_FOREST,
        model_parameters=_PARAMETERS if parameters is None else parameters,
        random_seed=42,
    )


def _fit_input(config: ExperimentConfig) -> ModelFitInput:
    rows = tuple((index / 20.0, (index % 3) / 20.0) for index in range(-20, 21))
    return ModelFitInput(
        experiment_id=config.experiment_id,
        feature_set_id=config.feature_set_id,
        feature_names=config.selected_features,
        feature_rows=rows,
        source_observation_ids=tuple(f"train-{index}" for index in range(len(rows))),
        sampling_policy_id=config.sampling_policy_id,
        random_seed=config.random_seed,
        source_observation_count=len(rows),
        reference_observation_count=len(rows),
    )


def _scoring_input(config: ExperimentConfig) -> ModelScoringInput:
    return ModelScoringInput(
        experiment_id=config.experiment_id,
        feature_set_id=config.feature_set_id,
        feature_names=config.selected_features,
        feature_rows=((0.0, 0.0), (20.0, 20.0), (-0.25, 0.05)),
        source_observation_ids=("normal", "extreme", "reference"),
    )


def test_isolation_forest_scores_are_reproducible_and_higher_for_anomaly() -> None:
    config = _config()
    model_input = _fit_input(config)
    scoring_input = _scoring_input(config)

    first_model = fit_isolation_forest(config, model_input)
    second_model = fit_isolation_forest(config, model_input)
    first_scores = first_model.score(scoring_input)
    second_scores = second_model.score(scoring_input)

    assert first_scores == second_scores
    assert first_scores.experiment_id == config.experiment_id
    assert first_scores.source_observation_ids == scoring_input.source_observation_ids
    assert first_scores.observation_count == scoring_input.observation_count
    assert first_scores.higher_is_more_anomalous is True
    assert first_scores.scores[1] > first_scores.scores[0]
    assert first_model.sampling_policy_id == model_input.sampling_policy_id
    assert first_model.source_observation_count == model_input.source_observation_count
    assert first_model.fit_observation_count == model_input.fit_observation_count

    with pytest.raises(FrozenInstanceError):
        first_scores.scores = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        first_model.random_seed = 43  # type: ignore[misc]


@pytest.mark.parametrize(
    ("parameters", "message"),
    [
        ({key: value for key, value in _PARAMETERS.items() if key != "bootstrap"}, "missing"),
        ({**_PARAMETERS, "warm_start": False}, "unknown"),
        ({**_PARAMETERS, "n_estimators": True}, "n_estimators"),
        ({**_PARAMETERS, "max_samples": 0.0}, "max_samples"),
        ({**_PARAMETERS, "contamination": 0.0}, "contamination"),
        ({**_PARAMETERS, "max_features": 0}, "max_features"),
        ({**_PARAMETERS, "bootstrap": 0}, "bootstrap"),
    ],
)
def test_isolation_forest_rejects_invalid_model_parameters(
    parameters: dict[str, str | int | float | bool],
    message: str,
) -> None:
    config = _config(parameters)

    with pytest.raises(IsolationForestError, match=message):
        fit_isolation_forest(config, _fit_input(config))


def test_isolation_forest_rejects_integer_max_features_above_schema_width() -> None:
    config = _config({**_PARAMETERS, "max_features": 3})

    with pytest.raises(IsolationForestError, match="feature count"):
        fit_isolation_forest(config, _fit_input(config))


def test_isolation_forest_rejects_integer_max_samples_above_fit_count() -> None:
    config = _config({**_PARAMETERS, "max_samples": 42})

    with pytest.raises(IsolationForestError, match="observation count"):
        fit_isolation_forest(config, _fit_input(config))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"experiment_id": "other-experiment-v1"}, "experiment_id"),
        ({"feature_set_id": "other-features-v1"}, "feature_set_id"),
        ({"selected_features": tuple(reversed(_FEATURE_NAMES))}, "feature_names"),
        ({"sampling_policy_id": "other-policy-v1"}, "sampling_policy_id"),
        ({"random_seed": 43}, "random_seed"),
    ],
)
def test_isolation_forest_rejects_config_and_fit_input_drift(
    changes: dict[str, object],
    message: str,
) -> None:
    config = _config()
    model_input = _fit_input(config)
    changed_config = replace(config, **changes)  # type: ignore[arg-type]

    with pytest.raises(IsolationForestError, match=message):
        fit_isolation_forest(changed_config, model_input)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"experiment_id": "other-experiment-v1"}, "experiment_id"),
        ({"feature_set_id": "other-features-v1"}, "feature_set_id"),
        ({"feature_names": tuple(reversed(_FEATURE_NAMES))}, "feature schema"),
    ],
)
def test_fitted_isolation_forest_rejects_scoring_input_drift(
    changes: dict[str, object],
    message: str,
) -> None:
    config = _config()
    model = fit_isolation_forest(config, _fit_input(config))
    scoring_input = replace(_scoring_input(config), **changes)  # type: ignore[arg-type]

    with pytest.raises(IsolationForestError, match=message):
        model.score(scoring_input)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"source_observation_ids": ()}, "at least one"),
        ({"source_observation_ids": ("observation-1", "observation-1")}, "unique"),
        ({"scores": (0.1,)}, "same number"),
        ({"scores": (0.1, float("nan"))}, "finite"),
    ],
)
def test_anomaly_scores_reject_invalid_contract_values(
    changes: dict[str, object],
    message: str,
) -> None:
    values: dict[str, object] = {
        "experiment_id": "candidate-v1",
        "source_observation_ids": ("observation-1", "observation-2"),
        "scores": (0.1, 0.2),
    }
    values.update(changes)

    with pytest.raises(AnomalyScoresError, match=message):
        AnomalyScores(**values)  # type: ignore[arg-type]
