from collections import Counter
from dataclasses import replace

import pytest

from industrial_phm.adapters import XJTU_SY_CHANNELS
from industrial_phm.experiments import (
    ExperimentConfig,
    XjtuSamplingPolicyError,
    get_xjtu_isolation_forest_candidates,
    get_xjtu_reference_split,
    prepare_xjtu_model_fit_input,
)
from industrial_phm.features import VibrationFeatureVector, vibration_feature_names
from industrial_phm.preprocessing import (
    PreprocessingFitProvenance,
    PreprocessingState,
    fit_preprocessing_state,
)


def _candidate(policy_id: str) -> ExperimentConfig:
    return next(
        candidate
        for candidate in get_xjtu_isolation_forest_candidates()
        if candidate.sampling_policy_id == policy_id and len(candidate.selected_features) == 14
    )


def _vectors(config: ExperimentConfig) -> tuple[VibrationFeatureVector, ...]:
    fold = get_xjtu_reference_split().folds[0]
    feature_names = vibration_feature_names(XJTU_SY_CHANNELS)
    vectors: list[VibrationFeatureVector] = []
    row_number = 0
    for asset_position, asset_id in enumerate(fold.train, start=1):
        acquisition_count = asset_position + (asset_position == len(fold.train))
        for acquisition_index in range(1, acquisition_count + 1):
            values = tuple(
                float(row_number + feature_index) for feature_index in range(len(feature_names))
            )
            vectors.append(
                VibrationFeatureVector(
                    feature_set_id=config.feature_set_id,
                    asset_id=asset_id,
                    feature_names=feature_names,
                    values=values,
                    metadata={
                        "dataset_id": "xjtu-sy",
                        "operating_condition": "reference-condition",
                        "acquisition_index": acquisition_index,
                    },
                )
            )
            row_number += 1
    return tuple(vectors)


def _selected_rows(
    config: ExperimentConfig,
    vectors: tuple[VibrationFeatureVector, ...],
) -> tuple[tuple[float, ...], ...]:
    positions = {feature_name: index for index, feature_name in enumerate(vectors[0].feature_names)}
    return tuple(
        tuple(vector.values[positions[feature_name]] for feature_name in config.selected_features)
        for vector in vectors
    )


def _state(
    config: ExperimentConfig,
    vectors: tuple[VibrationFeatureVector, ...],
) -> PreprocessingState:
    return fit_preprocessing_state(
        config,
        PreprocessingFitProvenance(
            dataset_id=config.dataset_id,
            split_id=config.split_id,
            fold_id=config.fold_id,
            partition="train",
            feature_set_id=config.feature_set_id,
        ),
        config.selected_features,
        _selected_rows(config, vectors),
    )


def test_acquisition_uniform_preserves_every_transformed_train_observation_once() -> None:
    config = _candidate("acquisition-uniform-v1")
    vectors = _vectors(config)
    state = _state(config, vectors)
    transformed = state.transform(config.selected_features, _selected_rows(config, vectors))

    prepared = prepare_xjtu_model_fit_input(config, state, vectors)

    assert prepared.rows == transformed
    assert prepared.input_observation_count == prepared.output_observation_count == len(vectors)
    assert prepared.source_observation_ids == tuple(
        f"{vector.asset_id}:acquisition-{vector.metadata['acquisition_index']}"
        for vector in vectors
    )


def test_bearing_balanced_resampling_preserves_size_and_equalizes_bearing_mass() -> None:
    config = _candidate("bearing-balanced-resample-v1")
    vectors = _vectors(config)
    state = _state(config, vectors)

    first = prepare_xjtu_model_fit_input(config, state, vectors)
    repeated = prepare_xjtu_model_fit_input(config, state, vectors)

    assert first == repeated
    assert first.input_observation_count == first.output_observation_count == 46
    counts = Counter(
        identity.split(":", maxsplit=1)[0] for identity in first.source_observation_ids
    )
    assert max(counts.values()) - min(counts.values()) == 1
    assert set(counts.values()) == {5, 6}
    assert len(set(first.source_observation_ids)) < first.output_observation_count


def test_bearing_balanced_resampling_uses_experiment_seed() -> None:
    config = _candidate("bearing-balanced-resample-v1")
    vectors = _vectors(config)
    state = _state(config, vectors)
    first = prepare_xjtu_model_fit_input(config, state, vectors)

    other_config = replace(config, experiment_id="bearing-balanced-other-seed-v2", random_seed=43)
    other_state = _state(other_config, vectors)
    other = prepare_xjtu_model_fit_input(other_config, other_state, vectors)

    assert first.source_observation_ids != other.source_observation_ids


def test_xjtu_sampling_rejects_state_from_another_experiment() -> None:
    config = _candidate("bearing-balanced-resample-v1")
    vectors = _vectors(config)
    state = _state(config, vectors)
    other_config = replace(config, experiment_id="other-experiment-v2")

    with pytest.raises(XjtuSamplingPolicyError, match="experiment_id"):
        prepare_xjtu_model_fit_input(other_config, state, vectors)


def test_xjtu_sampling_rejects_unknown_policy_identifier() -> None:
    config = replace(
        _candidate("acquisition-uniform-v1"),
        experiment_id="unknown-policy-v2",
        sampling_policy_id="site-balanced-v1",
    )
    vectors = _vectors(config)
    state = _state(config, vectors)

    with pytest.raises(XjtuSamplingPolicyError, match="unsupported XJTU sampling policy"):
        prepare_xjtu_model_fit_input(config, state, vectors)


def test_xjtu_sampling_requires_adapter_provenance_on_feature_vectors() -> None:
    config = _candidate("acquisition-uniform-v1")
    vectors = _vectors(config)
    state = _state(config, vectors)
    invalid_first = replace(vectors[0], metadata={"dataset_id": "xjtu-sy"})
    invalid_vectors = (invalid_first, *vectors[1:])

    with pytest.raises(XjtuSamplingPolicyError, match="acquisition_index"):
        prepare_xjtu_model_fit_input(config, state, invalid_vectors)
