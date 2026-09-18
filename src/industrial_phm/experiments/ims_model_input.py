"""IMS-owned preparation of dataset-neutral model fitting and scoring inputs."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Literal

from industrial_phm.experiments.config import ExperimentConfig
from industrial_phm.experiments.ims import (
    IMS_BEARING_COUNT,
    IMS_DATASET_ID,
    IMS_EVALUATION_ACQUISITION_COUNT,
    IMS_EVALUATION_ARCHIVE_SCOPE,
    IMS_EVALUATION_TEST_ID,
    IMS_RADIAL_LOAD_LB,
    IMS_ROTATIONAL_SPEED_RPM,
    IMS_TRAIN_ACQUISITION_COUNT,
    IMS_TRAIN_TEST_ID,
    get_ims_cross_test_configuration,
)
from industrial_phm.features import VibrationFeatureVector
from industrial_phm.models import ModelFitInput, ModelScoringInput
from industrial_phm.preprocessing import (
    PreprocessingError,
    PreprocessingFitProvenance,
    PreprocessingState,
    fit_preprocessing_state,
)

_Partition = Literal["train", "evaluation"]


class ImsModelInputError(ValueError):
    """Raised when IMS feature vectors violate the fixed cross-test input contract."""


def fit_ims_preprocessing_and_prepare_model_input(
    config: ExperimentConfig,
    vectors: Sequence[VibrationFeatureVector],
) -> tuple[PreprocessingState, ModelFitInput]:
    """Fit preprocessing on complete Set 2 and prepare the fixed model-fit population."""
    _validate_fixed_config(config)
    _validate_vector_context(config, vectors)
    _validate_partition_coverage(vectors, partition="train")
    preprocessing_state = _fit_preprocessing_state(config, vectors)
    return preprocessing_state, _prepare_model_fit_input(config, preprocessing_state, vectors)


def prepare_ims_model_fit_input(
    config: ExperimentConfig,
    preprocessing_state: PreprocessingState,
    vectors: Sequence[VibrationFeatureVector],
) -> ModelFitInput:
    """Prepare complete Set 2 after preprocessing without reference filtering or resampling."""
    _validate_fixed_config(config)
    _validate_shared_context(config, preprocessing_state, vectors)
    _validate_partition_coverage(vectors, partition="train")
    if len(vectors) != preprocessing_state.observation_count:
        raise ImsModelInputError(
            "IMS train feature-vector count must match preprocessing fit observation count"
        )
    return _prepare_model_fit_input(config, preprocessing_state, vectors)


def prepare_ims_model_scoring_input(
    config: ExperimentConfig,
    preprocessing_state: PreprocessingState,
    vectors: Sequence[VibrationFeatureVector],
) -> ModelScoringInput:
    """Prepare the complete README-documented Set 3 scope for one-time scoring."""
    _validate_fixed_config(config)
    _validate_shared_context(config, preprocessing_state, vectors)
    _validate_partition_coverage(vectors, partition="evaluation")
    return ModelScoringInput(
        experiment_id=config.experiment_id,
        feature_set_id=preprocessing_state.feature_set_id,
        feature_names=preprocessing_state.feature_names,
        feature_rows=_transform_selected_features(config, preprocessing_state, vectors),
        source_observation_ids=_observation_ids(vectors),
    )


def _prepare_model_fit_input(
    config: ExperimentConfig,
    preprocessing_state: PreprocessingState,
    vectors: Sequence[VibrationFeatureVector],
) -> ModelFitInput:
    transformed_rows = _transform_selected_features(config, preprocessing_state, vectors)
    observation_ids = _observation_ids(vectors)
    return ModelFitInput(
        experiment_id=config.experiment_id,
        feature_set_id=preprocessing_state.feature_set_id,
        feature_names=preprocessing_state.feature_names,
        feature_rows=transformed_rows,
        source_observation_ids=observation_ids,
        sampling_policy_id=config.sampling_policy_id,
        random_seed=config.random_seed,
        source_observation_count=len(vectors),
        reference_observation_count=len(vectors),
    )


def _validate_fixed_config(config: ExperimentConfig) -> None:
    canonical = get_ims_cross_test_configuration()
    for axis in (
        "experiment_id",
        "dataset_id",
        "split_id",
        "fold_id",
        "fit_partition",
        "feature_set_id",
        "reference_strategy",
        "sampling_policy_id",
        "scaling_strategy",
        "model_family",
        "random_seed",
    ):
        if getattr(config, axis) != getattr(canonical, axis):
            raise ImsModelInputError(f"IMS cross-test config {axis} drift is not allowed")
    if tuple(config.selected_features) != tuple(canonical.selected_features):
        raise ImsModelInputError("IMS cross-test selected_features drift is not allowed")
    if dict(config.model_parameters) != dict(canonical.model_parameters):
        raise ImsModelInputError("IMS cross-test model_parameters drift is not allowed")


def _validate_shared_context(
    config: ExperimentConfig,
    preprocessing_state: PreprocessingState,
    vectors: Sequence[VibrationFeatureVector],
) -> None:
    _validate_vector_context(config, vectors)
    expected = (
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
    for field_name, value, configured in expected:
        if value != configured:
            raise ImsModelInputError(
                f"IMS preprocessing state {field_name} does not match experiment config"
            )


def _validate_vector_context(
    config: ExperimentConfig,
    vectors: Sequence[VibrationFeatureVector],
) -> None:
    if config.dataset_id != IMS_DATASET_ID:
        raise ImsModelInputError(
            f"IMS model input requires dataset_id {IMS_DATASET_ID!r}, got {config.dataset_id!r}"
        )
    if not vectors:
        raise ImsModelInputError("IMS model input requires feature vectors")

    expected_schema = tuple(config.selected_features)
    for vector_index, vector in enumerate(vectors):
        if vector.feature_set_id != config.feature_set_id:
            raise ImsModelInputError(
                f"IMS feature vector {vector_index} feature_set_id does not match config"
            )
        if tuple(vector.feature_names) != expected_schema:
            raise ImsModelInputError(
                f"IMS feature vector {vector_index} must use the fixed single-channel schema"
            )
        if vector.metadata.get("dataset_id") != IMS_DATASET_ID:
            raise ImsModelInputError(
                f"IMS feature vector {vector_index} must preserve dataset_id {IMS_DATASET_ID!r}"
            )
        _acquisition_index(vector, vector_index=vector_index)

    _observation_ids(vectors)


def _validate_partition_coverage(
    vectors: Sequence[VibrationFeatureVector],
    *,
    partition: _Partition,
) -> None:
    if partition == "train":
        test_id = IMS_TRAIN_TEST_ID
        acquisition_count = IMS_TRAIN_ACQUISITION_COUNT
        archive_scope = "readme-documented"
    else:
        test_id = IMS_EVALUATION_TEST_ID
        acquisition_count = IMS_EVALUATION_ACQUISITION_COUNT
        archive_scope = IMS_EVALUATION_ARCHIVE_SCOPE

    expected_assets = {f"{test_id}-bearing-{number}" for number in range(1, IMS_BEARING_COUNT + 1)}
    observed_assets = {vector.asset_id for vector in vectors}
    if observed_assets != expected_assets:
        raise ImsModelInputError(
            f"IMS {partition} must cover exactly {sorted(expected_assets)}; "
            f"missing={sorted(expected_assets - observed_assets)}, "
            f"unexpected={sorted(observed_assets - expected_assets)}"
        )
    expected_total = acquisition_count * IMS_BEARING_COUNT
    if len(vectors) != expected_total:
        raise ImsModelInputError(
            f"IMS {partition} must contain {expected_total} bearing-acquisition vectors, "
            f"got {len(vectors)}"
        )

    by_asset: dict[str, set[int]] = defaultdict(set)
    for vector_index, vector in enumerate(vectors):
        if vector.metadata.get("test_id") != test_id:
            raise ImsModelInputError(
                f"IMS {partition} vector {vector_index} must preserve test_id {test_id!r}"
            )
        if vector.metadata.get("archive_scope") != archive_scope:
            raise ImsModelInputError(
                f"IMS {partition} vector {vector_index} must use archive_scope {archive_scope!r}"
            )
        _require_context_number(
            vector,
            vector_index=vector_index,
            key="rotational_speed_rpm",
            expected=IMS_ROTATIONAL_SPEED_RPM,
        )
        _require_context_number(
            vector,
            vector_index=vector_index,
            key="radial_load_lb",
            expected=IMS_RADIAL_LOAD_LB,
        )
        by_asset[vector.asset_id].add(_acquisition_index(vector, vector_index=vector_index))

    expected_indices = set(range(1, acquisition_count + 1))
    for asset_id in sorted(expected_assets):
        observed_indices = by_asset[asset_id]
        if observed_indices != expected_indices:
            missing = sorted(expected_indices - observed_indices)
            unexpected = sorted(observed_indices - expected_indices)
            raise ImsModelInputError(
                f"IMS {partition} must cover complete acquisition sequence for {asset_id}; "
                f"expected=1..{acquisition_count}, missing={missing[:10]}, "
                f"unexpected={unexpected[:10]}"
            )


def _fit_preprocessing_state(
    config: ExperimentConfig,
    vectors: Sequence[VibrationFeatureVector],
) -> PreprocessingState:
    try:
        return fit_preprocessing_state(
            config,
            PreprocessingFitProvenance(
                dataset_id=config.dataset_id,
                split_id=config.split_id,
                fold_id=config.fold_id,
                fit_partition=config.fit_partition,
                feature_set_id=config.feature_set_id,
            ),
            config.selected_features,
            _selected_feature_rows(config, vectors),
        )
    except PreprocessingError as error:
        raise ImsModelInputError(f"invalid IMS preprocessing fit input: {error}") from error


def _transform_selected_features(
    config: ExperimentConfig,
    preprocessing_state: PreprocessingState,
    vectors: Sequence[VibrationFeatureVector],
) -> tuple[tuple[float, ...], ...]:
    rows = _selected_feature_rows(config, vectors)
    try:
        return preprocessing_state.transform(config.selected_features, rows)
    except PreprocessingError as error:
        raise ImsModelInputError(f"invalid IMS preprocessing input: {error}") from error


def _selected_feature_rows(
    config: ExperimentConfig,
    vectors: Sequence[VibrationFeatureVector],
) -> tuple[tuple[float, ...], ...]:
    expected_schema = tuple(config.selected_features)
    rows: list[tuple[float, ...]] = []
    for vector in vectors:
        if tuple(vector.feature_names) != expected_schema:
            raise ImsModelInputError("IMS feature schema drift is not allowed")
        rows.append(tuple(vector.values))
    return tuple(rows)


def _observation_ids(vectors: Sequence[VibrationFeatureVector]) -> tuple[str, ...]:
    ids = tuple(
        f"{vector.asset_id}:acquisition-{_acquisition_index(vector, vector_index=index)}"
        for index, vector in enumerate(vectors)
    )
    if len(ids) != len(set(ids)):
        raise ImsModelInputError("IMS source observation identities must be unique")
    return ids


def _acquisition_index(
    vector: VibrationFeatureVector,
    *,
    vector_index: int,
) -> int:
    value = vector.metadata.get("acquisition_index")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ImsModelInputError(
            f"IMS feature vector {vector_index} requires a positive integer acquisition_index"
        )
    return value


def _require_context_number(
    vector: VibrationFeatureVector,
    *,
    vector_index: int,
    key: str,
    expected: float,
) -> None:
    value = vector.metadata.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ImsModelInputError(f"IMS feature vector {vector_index} requires numeric {key}")
    if float(value) != expected:
        raise ImsModelInputError(
            f"IMS feature vector {vector_index} {key} must be {expected:g}, got {value!r}"
        )
