"""XJTU-owned model-fitting sampling policy resolution."""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Sequence

from industrial_phm.experiments.config import ExperimentConfig
from industrial_phm.experiments.xjtu import get_xjtu_reference_split
from industrial_phm.features import VibrationFeatureVector
from industrial_phm.models import ModelFitInput
from industrial_phm.preprocessing import PreprocessingError, PreprocessingState

_DATASET_ID = "xjtu-sy"
_ACQUISITION_UNIFORM = "acquisition-uniform-v1"
_BEARING_BALANCED_RESAMPLE = "bearing-balanced-resample-v1"


class XjtuSamplingPolicyError(ValueError):
    """Raised when XJTU model-fit sampling input violates its experiment contract."""


def prepare_xjtu_model_fit_input(
    config: ExperimentConfig,
    preprocessing_state: PreprocessingState,
    vectors: Sequence[VibrationFeatureVector],
) -> ModelFitInput:
    """Transform XJTU train feature vectors and resolve the configured sampling policy."""
    _validate_context(config, preprocessing_state, vectors)

    source_feature_names = tuple(vectors[0].feature_names)
    selected_rows = _selected_feature_rows(
        source_feature_names,
        vectors,
        config.selected_features,
    )
    try:
        transformed_rows = preprocessing_state.transform(config.selected_features, selected_rows)
    except PreprocessingError as error:
        raise XjtuSamplingPolicyError(f"invalid XJTU preprocessing input: {error}") from error

    observation_ids = tuple(_observation_id(vector) for vector in vectors)
    if len(observation_ids) != len(set(observation_ids)):
        raise XjtuSamplingPolicyError("XJTU pre-sampling observation identities must be unique")

    if config.sampling_policy_id == _ACQUISITION_UNIFORM:
        selected_indices = tuple(range(len(vectors)))
    elif config.sampling_policy_id == _BEARING_BALANCED_RESAMPLE:
        selected_indices = _bearing_balanced_indices(vectors, seed=config.random_seed)
    else:
        raise XjtuSamplingPolicyError(
            f"unsupported XJTU sampling policy: {config.sampling_policy_id!r}"
        )

    return ModelFitInput(
        experiment_id=config.experiment_id,
        feature_set_id=preprocessing_state.feature_set_id,
        feature_names=preprocessing_state.feature_names,
        rows=tuple(transformed_rows[index] for index in selected_indices),
        source_observation_ids=tuple(observation_ids[index] for index in selected_indices),
        sampling_policy_id=config.sampling_policy_id,
        random_seed=config.random_seed,
        input_observation_count=len(vectors),
    )


def _validate_context(
    config: ExperimentConfig,
    preprocessing_state: PreprocessingState,
    vectors: Sequence[VibrationFeatureVector],
) -> None:
    if config.dataset_id != _DATASET_ID:
        raise XjtuSamplingPolicyError(
            f"XJTU sampling requires dataset_id {_DATASET_ID!r}, got {config.dataset_id!r}"
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
            raise XjtuSamplingPolicyError(
                f"preprocessing state {field_name} does not match experiment config"
            )

    if not vectors:
        raise XjtuSamplingPolicyError("XJTU sampling requires train feature vectors")
    if len(vectors) != preprocessing_state.observation_count:
        raise XjtuSamplingPolicyError(
            "XJTU feature-vector count must match the preprocessing fit observation count"
        )

    source_feature_names = tuple(vectors[0].feature_names)
    for index, vector in enumerate(vectors):
        if vector.feature_set_id != config.feature_set_id:
            raise XjtuSamplingPolicyError(
                f"XJTU feature vector {index} feature_set_id does not match experiment config"
            )
        if tuple(vector.feature_names) != source_feature_names:
            raise XjtuSamplingPolicyError(
                f"XJTU feature vector {index} feature schema does not match the first vector"
            )
        if vector.metadata.get("dataset_id") != _DATASET_ID:
            raise XjtuSamplingPolicyError(
                f"XJTU feature vector {index} must preserve dataset_id {_DATASET_ID!r}"
            )
        _acquisition_index(vector, index=index)

    split = get_xjtu_reference_split()
    if split.split_id != config.split_id:
        raise XjtuSamplingPolicyError("XJTU sampling config references an unknown split")
    fold = next(
        (candidate for candidate in split.folds if candidate.fold_id == config.fold_id), None
    )
    if fold is None:
        raise XjtuSamplingPolicyError(
            f"XJTU sampling config references an unknown fold: {config.fold_id!r}"
        )

    expected_assets = set(fold.train)
    observed_assets = {vector.asset_id for vector in vectors}
    if observed_assets != expected_assets:
        missing = sorted(expected_assets - observed_assets)
        unexpected = sorted(observed_assets - expected_assets)
        raise XjtuSamplingPolicyError(
            "XJTU sampling vectors must cover the configured train bearing runs; "
            f"missing={missing}, unexpected={unexpected}"
        )


def _selected_feature_rows(
    source_feature_names: Sequence[str],
    vectors: Sequence[VibrationFeatureVector],
    selected_features: Sequence[str],
) -> tuple[tuple[float, ...], ...]:
    source_names = tuple(source_feature_names)
    positions = {feature_name: index for index, feature_name in enumerate(source_names)}
    missing = [feature_name for feature_name in selected_features if feature_name not in positions]
    if missing:
        raise XjtuSamplingPolicyError(f"XJTU feature vectors are missing feature(s): {missing}")

    selected_positions = tuple(positions[feature_name] for feature_name in selected_features)
    return tuple(
        tuple(vector.values[position] for position in selected_positions) for vector in vectors
    )


def _acquisition_index(vector: VibrationFeatureVector, *, index: int) -> int:
    value = vector.metadata.get("acquisition_index")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise XjtuSamplingPolicyError(
            f"XJTU feature vector {index} requires a positive integer acquisition_index"
        )
    return value


def _observation_id(vector: VibrationFeatureVector) -> str:
    return f"{vector.asset_id}:acquisition-{_acquisition_index(vector, index=0)}"


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
