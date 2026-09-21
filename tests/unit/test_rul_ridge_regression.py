from dataclasses import replace

import pytest

from industrial_phm.experiments import (
    ExperimentConfig,
    FitPartition,
    ModelFamily,
    ReferenceStrategy,
    ScalingStrategy,
)
from industrial_phm.models import (
    ModelFitInput,
    ModelScoringInput,
    RulRidgeRegressionError,
    fit_rul_ridge_regression,
)


def _config() -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id="ridge-rul-test-v1",
        dataset_id="reference-dataset",
        split_id="reference-split",
        fold_id="fold-1",
        fit_partition=FitPartition.TRAIN,
        feature_set_id="reference-features",
        selected_features=("feature.x",),
        reference_strategy=ReferenceStrategy.ALL_TRAIN_OBSERVATIONS,
        sampling_policy_id="reference-uniform-v1",
        scaling_strategy=ScalingStrategy.IDENTITY,
        model_family=ModelFamily.RIDGE_REGRESSION,
        model_parameters={
            "alpha": 0.0,
            "fit_intercept": True,
            "solver": "svd",
        },
        random_seed=42,
    )


def _fit_input() -> ModelFitInput:
    return ModelFitInput(
        experiment_id="ridge-rul-test-v1",
        feature_set_id="reference-features",
        feature_names=("feature.x",),
        feature_rows=((0.0,), (1.0,), (2.0,), (3.0,)),
        source_observation_ids=("o1", "o2", "o3", "o4"),
        sampling_policy_id="reference-uniform-v1",
        random_seed=42,
        source_observation_count=4,
        reference_observation_count=4,
    )


def test_rul_ridge_regression_fits_and_predicts_prepared_rows() -> None:
    fitted = fit_rul_ridge_regression(
        _config(),
        _fit_input(),
        (2.0, 5.0, 8.0, 11.0),
    )
    scoring = ModelScoringInput(
        experiment_id="ridge-rul-test-v1",
        feature_set_id="reference-features",
        feature_names=("feature.x",),
        feature_rows=((4.0,), (5.0,)),
        source_observation_ids=("s1", "s2"),
    )

    predictions = fitted.predict(scoring)

    assert predictions == pytest.approx((14.0, 17.0))
    assert fitted.fit_observation_count == 4
    assert fitted.alpha == 0.0
    assert fitted.solver == "svd"


def test_rul_ridge_regression_rejects_target_count_drift() -> None:
    with pytest.raises(RulRidgeRegressionError, match="target_values count"):
        fit_rul_ridge_regression(
            _config(),
            _fit_input(),
            (2.0, 5.0, 8.0),
        )


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf")])
def test_rul_ridge_regression_rejects_invalid_training_target(value: float) -> None:
    targets = (2.0, 5.0, 8.0, value)

    with pytest.raises(RulRidgeRegressionError, match="finite non-negative"):
        fit_rul_ridge_regression(
            _config(),
            _fit_input(),
            targets,
        )


def test_rul_ridge_regression_rejects_model_family_drift() -> None:
    config = replace(_config(), model_family=ModelFamily.ISOLATION_FOREST)

    with pytest.raises(RulRidgeRegressionError, match="model_family"):
        fit_rul_ridge_regression(
            config,
            _fit_input(),
            (2.0, 5.0, 8.0, 11.0),
        )


def test_rul_ridge_regression_rejects_scoring_schema_drift() -> None:
    fitted = fit_rul_ridge_regression(
        _config(),
        _fit_input(),
        (2.0, 5.0, 8.0, 11.0),
    )
    scoring = ModelScoringInput(
        experiment_id="ridge-rul-test-v1",
        feature_set_id="reference-features",
        feature_names=("feature.other",),
        feature_rows=((4.0,),),
        source_observation_ids=("s1",),
    )

    with pytest.raises(RulRidgeRegressionError, match="feature schema"):
        fitted.predict(scoring)
