"""XJTU-owned preparation of dataset-neutral model inputs."""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Sequence
from typing import Literal

from industrial_phm.experiments.config import ExperimentConfig
from industrial_phm.experiments.xjtu import get_xjtu_reference_split
from industrial_phm.features import VibrationFeatureVector
from industrial_phm.models import ModelFitInput, ModelScoringInput
from industrial_phm.preprocessing import PreprocessingError, PreprocessingState

_DATASET_ID = "xjtu-sy"
_ACQUISITION_UNIFORM = "acquisition-uniform-v1"
_BEARING_BALANCED_RESAMPLE = "bearing-balanced-resample-v1"


class XjtuModelInputError(ValueError):
    """Raised when XJTU feature vectors cannot form a valid model input."""


def prepare_xjtu_model_fit_input(
    config: ExperimentConfig,
    preprocessing_state: PreprocessingState,
    vectors: Sequence[VibrationFeatureVector],
) -> ModelFitInput:
    """Prepare XJTU train features for model fitting and apply the configured sampling policy."""
    _validate_shared_context(config, preprocessing_state, vectors)
    _validate_partition_coverage(config, vectors, partition="train")
    if len(vectors) != preprocessing_state.observation_count:
        raise XjtuModelInputError(
            "XJTU train feature-vector count must match the preprocessing fit observation count"
        )

    transformed_rows = _transform_selected_features(config, preprocessing_state, vectors)
    observation_ids = _observation_ids(vectors)

    if config.sampling_policy_id == _ACQUISITION_UNIFORM:
        selected_indices = tuple(range(len(vectors)))
    elif config.sampling_policy_id == _BEARING_BALANCED_RESAMPLE:
        selected_indices = _bearing_balanced_indices(vectors, seed=config.random_seed)
    else:
        raise XjtuModelInputError(
            f"unsupported XJTU sampling policy: {config.sampling_policy_id!r}"
        )

    return ModelFitInput(
        experiment_id=config.experiment_id,
        feature_set_id=preprocessing_state.feature_set_id,
        feature_names=preprocessing_state.feature_names,
        feature_rows=tuple(transformed_rows[index] for index in selected_indices),
        source_observation_ids=tuple(observation_ids[index] for index in selected_indices),
        sampling_policy_id=config.sampling_policy_id,
        random_seed=config.random_seed,
        source_observation_count=len(vectors),
    )


def prepare_xjtu_model_scoring_input(
    config: ExperimentConfig,
    preprocessing_state: PreprocessingState,
    vectors: Sequence[VibrationFeatureVector],
    *,
    partition: Literal["validation", "test"],
) -> ModelScoringInput:
    """Prepare unsampled XJTU validation or test features for model scoring."""
    _validate_shared_context(config, preprocessing_state, vectors)
    _validate_partition_coverage(config, vectors, partition=partition)

    return ModelScoringInput(
        experiment_id=config.experiment_id,
        feature_set_id=preprocessing_state.feature_set_id,
        feature_names=preprocessing_state.feature_names,
        feature_rows=_transform_selected_features(config, preprocessing_state, vectors),
        source_observation_ids=_observation_ids(vectors),
    )


def _validate_shared_context(
    config: ExperimentConfig,
    preprocessing_state: PreprocessingState,
    vectors: Sequence[VibrationFeatureVector],
) -> None:
    if config.dataset_id != _DATASET_ID:
        raise XjtuModelInputError(
            f"XJTU model input requires dataset_id {_DATASET_ID!r}, got {config.dataset_id!r}"
        )

    state_fields = (
        ("experiment_id", preprocessing_state.experiment_id, config.experiment_id),
        ("dataset_id", preprocessing_state.dataset_id, config.dataset_id),
        ("split_id", preprocessing_state.split_id, config.split_id),
        ("fold_id", preprocessing_state.fold_id, config.fold_id),
        ("feature_set_id", preprocessing_state.feature_set_id, config.feature_set_id),
        (
            "feature_names",
            tuple(preprocessing_state.feature_names),
            tuple(config.selected_features),
        ),
    )
    for field_name, value, expected in state_fields:
        if value != expected:
            raise XjtuModelInputError(
                f"preprocessing state {field_name} does not match experiment config"
            )

    if not vectors:
        raise XjtuModelInputError("XJTU model input requires feature vectors")

    source_feature_names = tuple(vectors[0].feature_names)
    for vector_index, vector in enumerate(vectors):
        if vector.feature_set_id != config.feature_set_id:
            raise XjtuModelInputError(
                f"XJTU feature vector {vector_index} feature_set_id does not match experiment config"
            )
        if tuple(vector.feature_names) != source_feature_names:
            raise XjtuModelInputError(
                f"XJTU feature vector {vector_index} feature schema does not match the first vector"
            )
        if vector.metadata.get("dataset_id") != _DATASET_ID:
            raise XjtuModelInputError(
                f"XJTU feature vector {vector_index} must preserve dataset_id {_DATASET_ID!r}"
            )
        _acquisition_index(vector, vector_index=vector_index)

    _observation_ids(vectors)


def _validate_partition_coverage(
    config: ExperimentConfig,
    vectors: Sequence[VibrationFeatureVector],
    *,
    partition: Literal["train", "validation", "test"],
) -> None:
    split = get_xjtu_reference_split()
    if split.split_id != config.split_id:
        raise XjtuModelInputError("XJTU model input config references an unknown split")
    fold = next(
        (candidate for candidate in split.folds if candidate.fold_id == config.fold_id), None
    )
    if fold is None:
        raise XjtuModelInputError(
            f"XJTU model input config references an unknown fold: {config.fold_id!r}"
        )

    expected_assets = set(getattr(fold, partition))
    observed_assets = {vector.asset_id for vector in vectors}
    if observed_assets != expected_assets:
        missing = sorted(expected_assets - observed_assets)
        unexpected = sorted(observed_assets - expected_assets)
        raise XjtuModelInputError(
            f"XJTU model input must cover the configured {partition} bearing runs; "
            f"missing={missing}, unexpected={unexpected}"
        )


def _transform_selected_features(
    config: ExperimentConfig,
    preprocessing_state: PreprocessingState,
    vectors: Sequence[VibrationFeatureVector],
) -> tuple[tuple[float, ...], ...]:
    source_feature_names = tuple(vectors[0].feature_names)
    positions = {feature_name: index for index, feature_name in enumerate(source_feature_names)}
    missing = [
        feature_name for feature_name in config.selected_features if feature_name not in positions
    ]
    if missing:
        raise XjtuModelInputError(f"XJTU feature vectors are missing feature(s): {missing}")

    selected_positions = tuple(positions[feature_name] for feature_name in config.selected_features)
    selected_rows = tuple(
        tuple(vector.values[position] for position in selected_positions) for vector in vectors
    )
    try:
        return preprocessing_state.transform(config.selected_features, selected_rows)
    except PreprocessingError as error:
        raise XjtuModelInputError(f"invalid XJTU preprocessing input: {error}") from error


def _observation_ids(vectors: Sequence[VibrationFeatureVector]) -> tuple[str, ...]:
    observation_ids = tuple(
        f"{vector.asset_id}:acquisition-{_acquisition_index(vector, vector_index=index)}"
        for index, vector in enumerate(vectors)
    )
    if len(observation_ids) != len(set(observation_ids)):
        raise XjtuModelInputError("XJTU source observation identities must be unique")
    return observation_ids


def _acquisition_index(
    vector: VibrationFeatureVector,
    *,
    vector_index: int,
) -> int:
    value = vector.metadata.get("acquisition_index")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise XjtuModelInputError(
            f"XJTU feature vector {vector_index} requires a positive integer acquisition_index"
        )
    return value


def _bearing_balanced_indices(
    vectors: Sequence[VibrationFeatureVector],
    *,
    seed: int,
) -> tuple[int, ...]:
    indices_by_asset: dict[str, list[int]] = defaultdict(list)
    for index, vector in enumerate(vectors):
        indices_by_asset[vector.asset_id].append(index)

    asset_ids = sorted(indices_by_asset)
    target_size = len(vectors)
    base_quota, remainder = divmod(target_size, len(asset_ids))
    randomizer = random.Random(seed)
    remainder_order = asset_ids.copy()
    randomizer.shuffle(remainder_order)
    extra_assets = set(remainder_order[:remainder])

    selected: list[int] = []
    for asset_id in asset_ids:
        source_indices = indices_by_asset[asset_id]
        quota = base_quota + (asset_id in extra_assets)
        if len(source_indices) >= quota:
            selected.extend(randomizer.sample(source_indices, quota))
        else:
            selected.extend(source_indices)
            selected.extend(randomizer.choices(source_indices, k=quota - len(source_indices)))

    randomizer.shuffle(selected)
    return tuple(selected)
