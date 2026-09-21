"""Frozen XJTU acquisition-feature Ridge RUL baseline for prognostics protocol v1."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from industrial_phm.adapters import XJTU_SY_CHANNELS
from industrial_phm.experiments.config import (
    ExperimentConfig,
    FitPartition,
    ModelFamily,
    ReferenceStrategy,
    ScalingStrategy,
)
from industrial_phm.experiments.xjtu import load_packaged_xjtu_experiment_configs
from industrial_phm.experiments.xjtu_model_input import (
    XjtuModelInputError,
    fit_xjtu_preprocessing_and_prepare_model_input,
    prepare_xjtu_model_scoring_input,
)
from industrial_phm.experiments.xjtu_rul import (
    XJTU_RUL_TARGET_DEFINITION_ID,
    XJTU_RUL_TARGET_UNIT,
    XjtuRulTargetError,
    get_xjtu_rul_partition_assets,
    validate_xjtu_recorded_end_rul_targets,
)
from industrial_phm.features import VibrationFeatureVector, vibration_feature_names
from industrial_phm.models import (
    FittedRulRidgeRegressor,
    RulRidgeRegressionError,
    fit_rul_ridge_regression,
)
from industrial_phm.preprocessing import PreprocessingState
from industrial_phm.prognostics import (
    RulPredictionObservation,
    RulPredictionSeries,
    RulTargetSeries,
)

XJTU_FEATURE_RIDGE_RUL_METHOD_ID = "xjtu-sy-rul-feature-ridge-fold-1-v1"

_MANIFEST = "xjtu-sy-rul-feature-ridge-fold-1-v1.toml"
_DATASET_ID = "xjtu-sy"
_FOLD_ID = "fold-1"
_EXPECTED_PARAMETERS: dict[str, str | float | bool] = {
    "alpha": 1.0,
    "fit_intercept": True,
    "solver": "svd",
}
_Partition = Literal["train", "validation", "test"]


class XjtuFeatureRulBaselineError(ValueError):
    """Raised when the frozen XJTU feature Ridge baseline contract is violated."""


@dataclass(frozen=True, slots=True)
class XjtuFeatureRulBaselineFit:
    """Train-fitted preprocessing and Ridge model for the feature-only RUL baseline."""

    config: ExperimentConfig
    preprocessing_state: PreprocessingState
    model: FittedRulRidgeRegressor

    def __post_init__(self) -> None:
        if not isinstance(self.config, ExperimentConfig):
            raise XjtuFeatureRulBaselineError("config must be an ExperimentConfig")
        if not isinstance(self.preprocessing_state, PreprocessingState):
            raise XjtuFeatureRulBaselineError("preprocessing_state must be a PreprocessingState")
        if not isinstance(self.model, FittedRulRidgeRegressor):
            raise XjtuFeatureRulBaselineError("model must be a FittedRulRidgeRegressor")

        experiment_ids = {
            self.config.experiment_id,
            self.preprocessing_state.experiment_id,
            self.model.experiment_id,
        }
        if experiment_ids != {XJTU_FEATURE_RIDGE_RUL_METHOD_ID}:
            raise XjtuFeatureRulBaselineError(
                "configuration, preprocessing state, and model must share method identity"
            )
        if self.preprocessing_state.observation_count != self.model.source_observation_count:
            raise XjtuFeatureRulBaselineError(
                "preprocessing fit population must match complete train population"
            )


@lru_cache(maxsize=1)
def get_xjtu_feature_rul_configuration() -> ExperimentConfig:
    """Return the single frozen acquisition-feature Ridge baseline configuration."""
    configs = load_packaged_xjtu_experiment_configs(_MANIFEST)
    if len(configs) != 1:
        raise XjtuFeatureRulBaselineError(
            "XJTU feature RUL manifest must contain exactly one experiment"
        )
    config = configs[0]
    expected = (
        ("experiment_id", config.experiment_id, XJTU_FEATURE_RIDGE_RUL_METHOD_ID),
        ("dataset_id", config.dataset_id, _DATASET_ID),
        ("split_id", config.split_id, "xjtu-sy-condition-stratified-5fold-v1"),
        ("fold_id", config.fold_id, _FOLD_ID),
        ("fit_partition", config.fit_partition, FitPartition.TRAIN),
        (
            "reference_strategy",
            config.reference_strategy,
            ReferenceStrategy.ALL_TRAIN_OBSERVATIONS,
        ),
        (
            "sampling_policy_id",
            config.sampling_policy_id,
            "bearing-balanced-resample-v1",
        ),
        ("scaling_strategy", config.scaling_strategy, ScalingStrategy.ROBUST),
        ("model_family", config.model_family, ModelFamily.RIDGE_REGRESSION),
        ("random_seed", config.random_seed, 42),
    )
    for field_name, value, configured in expected:
        if value != configured:
            raise XjtuFeatureRulBaselineError(
                f"XJTU feature RUL {field_name} must match protocol v1; "
                f"expected {configured!r}, got {value!r}"
            )

    expected_features = vibration_feature_names(XJTU_SY_CHANNELS)
    if tuple(config.selected_features) != expected_features:
        raise XjtuFeatureRulBaselineError(
            "XJTU feature RUL baseline requires the full 16-feature schema"
        )
    if dict(config.model_parameters) != _EXPECTED_PARAMETERS:
        raise XjtuFeatureRulBaselineError(
            "XJTU feature RUL model parameters must match the frozen protocol"
        )
    return config


def fit_xjtu_feature_rul_baseline(
    train_vectors: Sequence[VibrationFeatureVector],
    train_targets: Sequence[RulTargetSeries],
) -> XjtuFeatureRulBaselineFit:
    """Fit train-only preprocessing and Ridge from source-identity aligned RUL targets."""
    config = get_xjtu_feature_rul_configuration()
    ordered_train = _ordered_complete_vectors(train_vectors, partition="train")
    try:
        validated_targets = validate_xjtu_recorded_end_rul_targets(
            train_targets,
            partition="train",
        )
    except XjtuRulTargetError as error:
        raise XjtuFeatureRulBaselineError(
            f"invalid XJTU train RUL targets for feature baseline: {error}"
        ) from error

    target_by_id = {
        observation.source_observation_id: observation.remaining_useful_life
        for series in validated_targets
        for observation in series.observations
    }

    try:
        preprocessing_state, model_input = fit_xjtu_preprocessing_and_prepare_model_input(
            config,
            ordered_train,
        )
    except XjtuModelInputError as error:
        raise XjtuFeatureRulBaselineError(
            f"invalid XJTU feature RUL train input: {error}"
        ) from error

    try:
        target_values = tuple(
            target_by_id[observation_id] for observation_id in model_input.source_observation_ids
        )
    except KeyError as error:
        raise XjtuFeatureRulBaselineError(
            "model-fit source identity is absent from complete train RUL targets"
        ) from error

    try:
        model = fit_rul_ridge_regression(config, model_input, target_values)
    except RulRidgeRegressionError as error:
        raise XjtuFeatureRulBaselineError(
            f"failed to fit XJTU feature RUL Ridge baseline: {error}"
        ) from error

    return XjtuFeatureRulBaselineFit(
        config=config,
        preprocessing_state=preprocessing_state,
        model=model,
    )


def predict_xjtu_feature_rul(
    fitted: XjtuFeatureRulBaselineFit,
    vectors: Sequence[VibrationFeatureVector],
    *,
    partition: _Partition,
) -> tuple[RulPredictionSeries, ...]:
    """Predict one complete partition from current-acquisition vibration features only."""
    if not isinstance(fitted, XjtuFeatureRulBaselineFit):
        raise XjtuFeatureRulBaselineError("fitted must be an XjtuFeatureRulBaselineFit")

    ordered_vectors = _ordered_complete_vectors(vectors, partition=partition)
    try:
        scoring_input = prepare_xjtu_model_scoring_input(
            fitted.config,
            fitted.preprocessing_state,
            ordered_vectors,
            partition=partition,
        )
        predicted_values = fitted.model.predict(scoring_input)
    except (XjtuModelInputError, RulRidgeRegressionError) as error:
        raise XjtuFeatureRulBaselineError(
            f"invalid XJTU feature RUL scoring input: {error}"
        ) from error

    grouped: dict[str, list[RulPredictionObservation]] = defaultdict(list)
    for vector, observation_id, predicted in zip(
        ordered_vectors,
        scoring_input.source_observation_ids,
        predicted_values,
        strict=True,
    ):
        grouped[vector.asset_id].append(
            RulPredictionObservation(
                asset_id=vector.asset_id,
                partition_id=partition,
                source_observation_id=observation_id,
                predicted_remaining_useful_life=predicted,
            )
        )

    return tuple(
        RulPredictionSeries(
            prediction_method_id=fitted.config.experiment_id,
            target_definition_id=XJTU_RUL_TARGET_DEFINITION_ID,
            unit=XJTU_RUL_TARGET_UNIT,
            asset_id=asset_id,
            partition_id=partition,
            observations=tuple(grouped[asset_id]),
        )
        for asset_id in get_xjtu_rul_partition_assets(partition)
    )


def _ordered_complete_vectors(
    vectors: Sequence[VibrationFeatureVector],
    *,
    partition: _Partition,
) -> tuple[VibrationFeatureVector, ...]:
    if not vectors:
        raise XjtuFeatureRulBaselineError(
            f"XJTU feature RUL {partition} input requires feature vectors"
        )

    expected_assets = get_xjtu_rul_partition_assets(partition)
    asset_rank = {asset_id: index for index, asset_id in enumerate(expected_assets)}
    for vector_index, vector in enumerate(vectors):
        if not isinstance(vector, VibrationFeatureVector):
            raise XjtuFeatureRulBaselineError(
                f"XJTU feature RUL vector {vector_index} must be a VibrationFeatureVector"
            )
        if vector.asset_id not in asset_rank:
            raise XjtuFeatureRulBaselineError(
                f"XJTU feature RUL input received asset outside {partition}: {vector.asset_id!r}"
            )

    return tuple(
        sorted(
            vectors,
            key=lambda vector: (
                asset_rank[vector.asset_id],
                _acquisition_index(vector),
            ),
        )
    )


def _acquisition_index(vector: VibrationFeatureVector) -> int:
    value = vector.metadata.get("acquisition_index")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise XjtuFeatureRulBaselineError(
            "XJTU feature RUL vectors require a positive integer acquisition_index"
        )
    return value
