from industrial_phm.experiments import (
    ExperimentConfig,
    FitPartition,
    ModelFamily,
    ReferenceStrategy,
    ScalingStrategy,
)
from industrial_phm.preprocessing import (
    PreprocessingFitProvenance,
    fit_preprocessing_state,
)


def _config(experiment_id: str, sampling_policy_id: str) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=experiment_id,
        dataset_id="reference-dataset",
        split_id="reference-split-v1",
        fold_id="fold-1",
        fit_partition=FitPartition.TRAIN,
        feature_set_id="reference-features-v1",
        selected_features=("feature.channel.rms",),
        reference_strategy=ReferenceStrategy.ALL_TRAIN_OBSERVATIONS,
        sampling_policy_id=sampling_policy_id,
        scaling_strategy=ScalingStrategy.ROBUST,
        model_family=ModelFamily.ISOLATION_FOREST,
        model_parameters={"n_estimators": 256},
        random_seed=42,
    )


def test_preprocessing_fit_is_independent_of_model_fitting_sampling_policy() -> None:
    provenance = PreprocessingFitProvenance(
        dataset_id="reference-dataset",
        split_id="reference-split-v1",
        fold_id="fold-1",
        fit_partition=FitPartition.TRAIN,
        feature_set_id="reference-features-v1",
    )
    feature_names = ("feature.channel.rms",)
    rows = ((1.0,), (2.0,), (3.0,), (100.0,))

    policy_a = fit_preprocessing_state(
        _config("policy-a-experiment-v1", "policy-a-v1"),
        provenance,
        feature_names,
        rows,
    )
    policy_b = fit_preprocessing_state(
        _config("policy-b-experiment-v1", "policy-b-v1"),
        provenance,
        feature_names,
        rows,
    )

    assert policy_a.experiment_id != policy_b.experiment_id
    assert policy_a.observation_count == policy_b.observation_count == 4
    assert policy_a.fitted_center == policy_b.fitted_center
    assert policy_a.fitted_scale == policy_b.fitted_scale
    assert policy_a.zero_iqr_features == policy_b.zero_iqr_features
