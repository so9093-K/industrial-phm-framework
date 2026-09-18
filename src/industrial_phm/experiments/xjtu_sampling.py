"""XJTU-owned model-fitting sampling policy resolution."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Sequence

from industrial_phm.experiments.config import ExperimentConfig
from industrial_phm.experiments.xjtu import get_xjtu_reference_split
from industrial_phm.experiments.xjtu_characterization_artifacts import (
    XjtuCharacterizationRecord,
)
from industrial_phm.models import ModelFitInput
from industrial_phm.preprocessing import PreprocessingState

_DATASET_ID = "xjtu-sy"
_ACQUISITION_UNIFORM = "acquisition-uniform"
_BEARING_BALANCED = "bearing-balanced"


class XjtuSamplingPolicyError(ValueError):
    """Raised when XJTU model-fit sampling input violates its experiment contract."""


def prepare_xjtu_model_fit_input(
    config: ExperimentConfig,
    preprocessing_state: PreprocessingState,
    records: Sequence[XjtuCharacterizationRecord],
    transformed_rows: Sequence[Sequence[float]],
) -> ModelFitInput:
    """Resolve an XJTU sampling policy into dataset-neutral model-fit rows."""
    _validate_context(config, preprocessing_state, records, transformed_rows)
    observation_ids = tuple(
        f"{record.asset_id}:acquisition-{record.acquisition_index}" for record in records
    )
    if len(observation_ids) != len(set(observation_ids)):
        raise XjtuSamplingPolicyError("XJTU pre-sampling observation identities must be unique")

    if config.sampling_policy_id == _ACQUISITION_UNIFORM:
        selected_indices = tuple(range(len(records)))
    elif config.sampling_policy_id == _BEARING_BALANCED:
        selected_indices = _bearing_balanced_indices(records, seed=config.random_seed)
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
        input_observation_count=len(records),
    )


def _validate_context(
    config: ExperimentConfig,
    preprocessing_state: PreprocessingState,
    records: Sequence[XjtuCharacterizationRecord],
    transformed_rows: Sequence[Sequence[float]],
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

    if not records:
        raise XjtuSamplingPolicyError("XJTU sampling requires train observations")
    if len(records) != preprocessing_state.observation_count:
        raise XjtuSamplingPolicyError(
            "XJTU record count must match the preprocessing fit observation count"
        )
    if len(transformed_rows) != len(records):
        raise XjtuSamplingPolicyError(
            "transformed rows and XJTU records must contain the same number of observations"
        )
    expected_width = len(preprocessing_state.feature_names)
    for row_index, row in enumerate(transformed_rows):
        if len(row) != expected_width:
            raise XjtuSamplingPolicyError(
                f"transformed row {row_index} width must be {expected_width}, got {len(row)}"
            )
        for row_value in row:
            if (
                isinstance(row_value, bool)
                or not isinstance(row_value, int | float)
                or not math.isfinite(float(row_value))
            ):
                raise XjtuSamplingPolicyError(
                    f"transformed row {row_index} must contain finite numerical values"
                )

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
    observed_assets = {record.asset_id for record in records}
    if observed_assets != expected_assets:
        missing = sorted(expected_assets - observed_assets)
        unexpected = sorted(observed_assets - expected_assets)
        raise XjtuSamplingPolicyError(
            "XJTU sampling records must cover the configured train bearing runs; "
            f"missing={missing}, unexpected={unexpected}"
        )


def _bearing_balanced_indices(
    records: Sequence[XjtuCharacterizationRecord],
    *,
    seed: int,
) -> tuple[int, ...]:
    indices_by_asset: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        indices_by_asset[record.asset_id].append(index)

    asset_ids = sorted(indices_by_asset)
    target_size = len(records)
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
