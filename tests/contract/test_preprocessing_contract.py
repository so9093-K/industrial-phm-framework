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
        partition="train",
        feature_set_id="reference-features-v1",
    )
    feature_names = ("feature.channel.rms",)
    rows = ((1.0,), (2.0,), (3.0,), (100.0,))

    acquisition_uniform = fit_preprocessing_state(
        _config("policy-a-experiment-v1", "policy-a-v1"),
        provenance,
        feature_names,
        rows,
    )
    bearing_balanced = fit_preprocessing_state(
        _config("policy-b-experiment-v1", "policy-b-v1"),
        provenance,
        feature_names,
        rows,
    )

    assert acquisition_uniform.experiment_id != bearing_balanced.experiment_id
    assert acquisition_uniform.observation_count == bearing_balanced.observation_count == 4
    assert acquisition_uniform.fitted_center == bearing_balanced.fitted_center
    assert acquisition_uniform.fitted_scale == bearing_balanced.fitted_scale
    assert acquisition_uniform.zero_iqr_features == bearing_balanced.zero_iqr_features
