"""MIMII-owned preparation of section-level model fitting and scoring inputs."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Literal

from industrial_phm.experiments.config import (
    ExperimentConfig,
    ReferenceStrategy,
    ScalingStrategy,
)
from industrial_phm.experiments.mimii import (
    MIMII_DEVELOPMENT_SECTIONS,
    MIMII_DUE_DATASET_ID,
    MimiiExperimentProtocolError,
    MimiiSectionScope,
    get_mimii_section_scope,
    mimii_expected_train_domain_counts,
)
from industrial_phm.features import AudioFeatureVector, audio_logmel_feature_names
from industrial_phm.models import ModelFitInput, ModelScoringInput
from industrial_phm.preprocessing import (
    PreprocessingError,
    PreprocessingFitProvenance,
    PreprocessingState,
    fit_preprocessing_state,
)

MimiiDomain = Literal["source", "target"]


class MimiiModelInputError(ValueError):
    """Raised when MIMII audio features violate the frozen section-model boundary."""


def fit_mimii_preprocessing_and_prepare_model_input(
    config: ExperimentConfig,
    vectors: Sequence[AudioFeatureVector],
) -> tuple[PreprocessingState, ModelFitInput]:
    """Fit robust preprocessing on one complete section train population."""
    scope = _validate_config(config)
    ordered = _ordered_vectors(vectors)
    _validate_train_population(scope, config, ordered)
    state = _fit_preprocessing_state(config, ordered)
    return state, _prepare_model_fit_input(config, state, ordered)


def prepare_mimii_model_fit_input(
    config: ExperimentConfig,
    preprocessing_state: PreprocessingState,
    vectors: Sequence[AudioFeatureVector],
) -> ModelFitInput:
    """Prepare one complete section train population using an existing fitted state."""
    scope = _validate_config(config)
    ordered = _ordered_vectors(vectors)
    _validate_state(config, preprocessing_state)
    _validate_train_population(scope, config, ordered)
    if len(ordered) != preprocessing_state.observation_count:
        raise MimiiModelInputError(
            "MIMII train feature-vector count must match preprocessing fit observation count"
        )
    return _prepare_model_fit_input(config, preprocessing_state, ordered)


def prepare_mimii_model_scoring_input(
    config: ExperimentConfig,
    preprocessing_state: PreprocessingState,
    vectors: Sequence[AudioFeatureVector],
    *,
    domain: MimiiDomain,
) -> ModelScoringInput:
    """Prepare one label-blind source or target test stratum for scoring."""
    scope = _validate_config(config)
    if domain not in ("source", "target"):
        raise MimiiModelInputError(f"unsupported MIMII scoring domain: {domain!r}")
    ordered = _ordered_vectors(vectors)
    _validate_state(config, preprocessing_state)
    _validate_scoring_population(scope, config, ordered, domain=domain)

    return ModelScoringInput(
        experiment_id=config.experiment_id,
        feature_set_id=preprocessing_state.feature_set_id,
        feature_names=preprocessing_state.feature_names,
        feature_rows=_transform_selected_features(config, preprocessing_state, ordered),
        source_observation_ids=_observation_ids(ordered),
    )


def _validate_config(config: ExperimentConfig) -> MimiiSectionScope:
    try:
        scope = get_mimii_section_scope(config)
    except MimiiExperimentProtocolError as error:
        raise MimiiModelInputError(f"invalid MIMII section configuration: {error}") from error
    if config.reference_strategy is not ReferenceStrategy.ALL_TRAIN_OBSERVATIONS:
        raise MimiiModelInputError("MIMII reference_strategy drift is not allowed")
    if config.scaling_strategy is not ScalingStrategy.ROBUST:
        raise MimiiModelInputError("MIMII scaling_strategy drift is not allowed")
    if config.sampling_policy_id != "clip-uniform-v1":
        raise MimiiModelInputError("MIMII sampling_policy_id drift is not allowed")
    return scope


def _validate_state(
    config: ExperimentConfig,
    preprocessing_state: PreprocessingState,
) -> None:
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
        ("reference_strategy", preprocessing_state.reference_strategy, config.reference_strategy),
        ("scaling_strategy", preprocessing_state.scaling_strategy, config.scaling_strategy),
    )
    for field_name, value, configured in expected:
        if value != configured:
            raise MimiiModelInputError(
                f"MIMII preprocessing state {field_name} does not match section configuration"
            )


def _validate_train_population(
    scope: MimiiSectionScope,
    config: ExperimentConfig,
    vectors: Sequence[AudioFeatureVector],
) -> None:
    _validate_vector_context(scope, config, vectors)
    counts: Counter[str] = Counter()
    for index, vector in enumerate(vectors):
        _require_metadata(vector, index=index, key="split", expected="train")
        _require_metadata(vector, index=index, key="clip_label", expected="normal")
        domain = vector.metadata.get("domain")
        if domain not in ("source", "target"):
            raise MimiiModelInputError(
                f"MIMII train vector {index} requires source/target domain metadata"
            )
        counts[domain] += 1

    expected_source, expected_target = mimii_expected_train_domain_counts(
        scope.machine_type,
        scope.section,
    )
    expected = {"source": expected_source, "target": expected_target}
    if dict(counts) != expected:
        raise MimiiModelInputError(
            f"MIMII {scope.machine_type}/section-{scope.section} train domain counts "
            f"must be {expected}, got {dict(counts)}"
        )


def _validate_scoring_population(
    scope: MimiiSectionScope,
    config: ExperimentConfig,
    vectors: Sequence[AudioFeatureVector],
    *,
    domain: MimiiDomain,
) -> None:
    _validate_vector_context(scope, config, vectors)
    for index, vector in enumerate(vectors):
        _require_metadata(vector, index=index, key="split", expected="test")
        _require_metadata(vector, index=index, key="domain", expected=domain)


def _validate_vector_context(
    scope: MimiiSectionScope,
    config: ExperimentConfig,
    vectors: Sequence[AudioFeatureVector],
) -> None:
    if config.dataset_id != MIMII_DUE_DATASET_ID:
        raise MimiiModelInputError(
            f"MIMII model input requires dataset_id {MIMII_DUE_DATASET_ID!r}"
        )
    if not vectors:
        raise MimiiModelInputError("MIMII model input requires feature vectors")
    if scope.section not in MIMII_DEVELOPMENT_SECTIONS:
        raise MimiiModelInputError("MIMII model input requires a development section")

    expected_schema = audio_logmel_feature_names()
    if tuple(config.selected_features) != expected_schema:
        raise MimiiModelInputError("MIMII config must use the fixed audio feature schema")

    for index, vector in enumerate(vectors):
        if vector.feature_set_id != config.feature_set_id:
            raise MimiiModelInputError(
                f"MIMII feature vector {index} feature_set_id does not match config"
            )
        if tuple(vector.feature_names) != expected_schema:
            raise MimiiModelInputError(
                f"MIMII feature vector {index} must use audio-logmel-statistical-v1"
            )
        if vector.asset_id != scope.asset_id:
            raise MimiiModelInputError(
                f"MIMII feature vector {index} asset_id must be {scope.asset_id!r}"
            )
        _require_metadata(vector, index=index, key="dataset_id", expected=MIMII_DUE_DATASET_ID)
        _require_metadata(vector, index=index, key="source_group", expected="dev")
        _require_metadata(vector, index=index, key="machine_type", expected=scope.machine_type)
        _require_metadata(vector, index=index, key="section", expected=scope.section)
        _source_file(vector, index=index)

    _observation_ids(vectors)


def _fit_preprocessing_state(
    config: ExperimentConfig,
    vectors: Sequence[AudioFeatureVector],
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
            tuple(vector.values for vector in vectors),
        )
    except PreprocessingError as error:
        raise MimiiModelInputError(f"invalid MIMII preprocessing fit input: {error}") from error


def _prepare_model_fit_input(
    config: ExperimentConfig,
    preprocessing_state: PreprocessingState,
    vectors: Sequence[AudioFeatureVector],
) -> ModelFitInput:
    transformed = _transform_selected_features(config, preprocessing_state, vectors)
    observation_ids = _observation_ids(vectors)
    return ModelFitInput(
        experiment_id=config.experiment_id,
        feature_set_id=preprocessing_state.feature_set_id,
        feature_names=preprocessing_state.feature_names,
        feature_rows=transformed,
        source_observation_ids=observation_ids,
        sampling_policy_id=config.sampling_policy_id,
        random_seed=config.random_seed,
        source_observation_count=len(vectors),
        reference_observation_count=len(vectors),
    )


def _transform_selected_features(
    config: ExperimentConfig,
    preprocessing_state: PreprocessingState,
    vectors: Sequence[AudioFeatureVector],
) -> tuple[tuple[float, ...], ...]:
    try:
        return preprocessing_state.transform(
            config.selected_features,
            tuple(vector.values for vector in vectors),
        )
    except PreprocessingError as error:
        raise MimiiModelInputError(f"invalid MIMII preprocessing input: {error}") from error


def _ordered_vectors(
    vectors: Sequence[AudioFeatureVector],
) -> tuple[AudioFeatureVector, ...]:
    return tuple(sorted(vectors, key=lambda vector: _source_file(vector, index=0)))


def _observation_ids(vectors: Sequence[AudioFeatureVector]) -> tuple[str, ...]:
    ids = tuple(_source_file(vector, index=index) for index, vector in enumerate(vectors))
    if len(ids) != len(set(ids)):
        raise MimiiModelInputError("MIMII source observation identities must be unique")
    return ids


def _source_file(vector: AudioFeatureVector, *, index: int) -> str:
    value = vector.metadata.get("source_file")
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise MimiiModelInputError(
            f"MIMII feature vector {index} requires a trimmed source_file identity"
        )
    return value


def _require_metadata(
    vector: AudioFeatureVector,
    *,
    index: int,
    key: str,
    expected: str,
) -> None:
    value = vector.metadata.get(key)
    if value != expected:
        raise MimiiModelInputError(
            f"MIMII feature vector {index} {key} must be {expected!r}, got {value!r}"
        )
