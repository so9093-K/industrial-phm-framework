from dataclasses import FrozenInstanceError, replace

import pytest

from industrial_phm.experiments import (
    ExperimentConfig,
    FitPartition,
    ModelFamily,
    ReferenceStrategy,
    ScalingStrategy,
)
from industrial_phm.preprocessing import (
    PREPROCESSING_STATE_SCHEMA_ID,
    PreprocessingError,
    PreprocessingFitProvenance,
    fit_preprocessing_state,
)

_FEATURE_NAMES = ("feature.channel.mean", "feature.channel.rms")


def _config(
    *,
    scaling_strategy: ScalingStrategy = ScalingStrategy.IDENTITY,
    sampling_policy_id: str = "acquisition-uniform",
    experiment_id: str = "reference-candidate-v1",
) -> ExperimentConfig:
    return ExperimentConfig(
        experiment_id=experiment_id,
        dataset_id="reference-dataset",
        split_id="reference-split-v1",
        fold_id="fold-1",
        fit_partition=FitPartition.TRAIN,
        feature_set_id="reference-features-v1",
        selected_features=_FEATURE_NAMES,
        reference_strategy=ReferenceStrategy.ALL_TRAIN_OBSERVATIONS,
        sampling_policy_id=sampling_policy_id,
        scaling_strategy=scaling_strategy,
        model_family=ModelFamily.ISOLATION_FOREST,
        model_parameters={"n_estimators": 256},
        random_seed=42,
    )


def _provenance() -> PreprocessingFitProvenance:
    return PreprocessingFitProvenance(
        dataset_id="reference-dataset",
        split_id="reference-split-v1",
        fold_id="fold-1",
        fit_partition=FitPartition.TRAIN,
        feature_set_id="reference-features-v1",
    )


def test_identity_state_preserves_values_and_train_fit_provenance() -> None:
    rows = ((1.0, 10.0), (2.0, 20.0))

    state = fit_preprocessing_state(_config(), _provenance(), _FEATURE_NAMES, rows)

    assert state.schema_id == PREPROCESSING_STATE_SCHEMA_ID
    assert state.experiment_id == "reference-candidate-v1"
    assert state.dataset_id == "reference-dataset"
    assert state.split_id == "reference-split-v1"
    assert state.fold_id == "fold-1"
    assert state.fit_partition is FitPartition.TRAIN
    assert state.reference_strategy is ReferenceStrategy.ALL_TRAIN_OBSERVATIONS
    assert state.feature_set_id == "reference-features-v1"
    assert state.feature_names == _FEATURE_NAMES
    assert state.scaling_strategy is ScalingStrategy.IDENTITY
    assert state.observation_count == 2
    assert state.fitted_center == (0.0, 0.0)
    assert state.fitted_scale == (1.0, 1.0)
    assert state.zero_iqr_features == ()
    assert state.transform(_FEATURE_NAMES, rows) == rows

    with pytest.raises(FrozenInstanceError):
        state.observation_count = 3  # type: ignore[misc]


def test_robust_state_uses_global_train_median_and_linear_iqr() -> None:
    rows = ((1.0, 10.0), (2.0, 10.0), (3.0, 10.0), (4.0, 10.0))

    state = fit_preprocessing_state(
        _config(scaling_strategy=ScalingStrategy.ROBUST),
        _provenance(),
        _FEATURE_NAMES,
        rows,
    )

    assert state.fitted_center == (2.5, 10.0)
    assert state.fitted_scale == (1.5, 1.0)
    assert state.zero_iqr_features == ("feature.channel.rms",)
    transformed = state.transform(_FEATURE_NAMES, rows)
    assert transformed[0] == pytest.approx((-1.0, 0.0))
    assert transformed[1] == pytest.approx((-1.0 / 3.0, 0.0))
    assert transformed[2] == pytest.approx((1.0 / 3.0, 0.0))
    assert transformed[3] == pytest.approx((1.0, 0.0))


def test_robust_v1_preserves_nonzero_near_zero_iqr() -> None:
    rows = (
        (0.0, 10.0),
        (1.0e-12, 20.0),
        (2.0e-12, 30.0),
        (3.0e-12, 40.0),
    )

    state = fit_preprocessing_state(
        _config(scaling_strategy=ScalingStrategy.ROBUST),
        _provenance(),
        _FEATURE_NAMES,
        rows,
    )

    assert state.fitted_scale[0] == pytest.approx(1.5e-12)
    assert "feature.channel.mean" not in state.zero_iqr_features
    transformed = state.transform(_FEATURE_NAMES, rows)
    assert transformed[0][0] == pytest.approx(-1.0)
    assert transformed[-1][0] == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("provenance", "field_name"),
    [
        (replace(_provenance(), dataset_id="other-dataset"), "dataset_id"),
        (replace(_provenance(), split_id="other-split"), "split_id"),
        (replace(_provenance(), fold_id="fold-2"), "fold_id"),
        (replace(_provenance(), feature_set_id="other-features"), "feature_set_id"),
    ],
)
def test_fit_rejects_provenance_outside_configured_train_scope(
    provenance: PreprocessingFitProvenance,
    field_name: str,
) -> None:
    with pytest.raises(PreprocessingError, match=field_name):
        fit_preprocessing_state(_config(), provenance, _FEATURE_NAMES, ((1.0, 2.0),))


def test_fit_provenance_rejects_untyped_partition_value() -> None:
    with pytest.raises(PreprocessingError, match="fit_partition"):
        replace(_provenance(), fit_partition="validation")


@pytest.mark.parametrize(
    ("feature_names", "message"),
    [
        (("feature.channel.rms", "feature.channel.mean"), "feature order"),
        (("feature.channel.mean",), "feature schema"),
        ((*_FEATURE_NAMES, "feature.channel.peak"), "feature schema"),
    ],
)
def test_fit_rejects_feature_schema_drift(
    feature_names: tuple[str, ...],
    message: str,
) -> None:
    with pytest.raises(PreprocessingError, match=message):
        fit_preprocessing_state(_config(), _provenance(), feature_names, ((1.0, 2.0),))


def test_transform_rejects_feature_order_drift() -> None:
    state = fit_preprocessing_state(
        _config(),
        _provenance(),
        _FEATURE_NAMES,
        ((1.0, 2.0),),
    )

    with pytest.raises(PreprocessingError, match="feature order"):
        state.transform(tuple(reversed(_FEATURE_NAMES)), ((2.0, 1.0),))


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ((), "at least one feature row"),
        (((1.0,),), "width must be 2"),
        (((1.0, float("nan")),), "non-finite"),
        (((1.0, True),), "numerical values"),
    ],
)
def test_fit_rejects_invalid_feature_values(
    rows: tuple[tuple[object, ...], ...],
    message: str,
) -> None:
    with pytest.raises(PreprocessingError, match=message):
        fit_preprocessing_state(  # type: ignore[arg-type]
            _config(),
            _provenance(),
            _FEATURE_NAMES,
            rows,
        )
