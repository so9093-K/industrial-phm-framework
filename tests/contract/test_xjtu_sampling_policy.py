from collections import Counter
from dataclasses import replace
from statistics import median

import pytest

from industrial_phm.adapters import XJTU_SY_CHANNELS
from industrial_phm.experiments import (
    ExperimentConfig,
    XjtuSamplingPolicyError,
    get_xjtu_isolation_forest_candidates,
    get_xjtu_reference_split,
    prepare_xjtu_model_fit_input,
)
from industrial_phm.experiments.xjtu_characterization_artifacts import (
    XjtuCharacterizationData,
    XjtuCharacterizationRecord,
    XjtuRunLengthSummary,
)
from industrial_phm.features import vibration_feature_names
from industrial_phm.preprocessing import (
    PreprocessingFitProvenance,
    PreprocessingState,
    fit_preprocessing_state,
)


def _candidate(policy_id: str) -> ExperimentConfig:
    return next(
        candidate
        for candidate in get_xjtu_isolation_forest_candidates()
        if candidate.sampling_policy_id == policy_id
        and len(candidate.selected_features) == 14
        and candidate.scaling_strategy.value == "identity"
    )


def _characterization(config: ExperimentConfig) -> XjtuCharacterizationData:
    fold = get_xjtu_reference_split().folds[0]
    source_feature_names = vibration_feature_names(XJTU_SY_CHANNELS)
    records: list[XjtuCharacterizationRecord] = []
    row_number = 0
    for asset_position, asset_id in enumerate(fold.train, start=1):
        acquisition_count = asset_position + (asset_position == len(fold.train))
        for acquisition_index in range(1, acquisition_count + 1):
            row = tuple(
                float(row_number + feature_index)
                for feature_index in range(len(source_feature_names))
            )
            records.append(
                XjtuCharacterizationRecord(
                    asset_id=asset_id,
                    acquisition_index=acquisition_index,
                    operating_condition="reference-condition",
                    values=row,
                )
            )
            row_number += 1

    counts = Counter(record.asset_id for record in records)
    run_lengths = tuple(counts.values())
    return XjtuCharacterizationData(
        feature_set_id=config.feature_set_id,
        split_id=config.split_id,
        fold_id=config.fold_id,
        partition="train",
        feature_names=source_feature_names,
        records=tuple(records),
        run_length_summary=XjtuRunLengthSummary(
            min_acquisitions=min(run_lengths),
            max_acquisitions=max(run_lengths),
            median_acquisitions=float(median(run_lengths)),
            max_to_min_ratio=max(run_lengths) / min(run_lengths),
        ),
        global_correlations=(),
        correlations_by_condition=(),
        lifecycle_runs=(),
    )


def _selected_rows(
    config: ExperimentConfig,
    characterization: XjtuCharacterizationData,
) -> tuple[tuple[float, ...], ...]:
    positions = {
        feature_name: index
        for index, feature_name in enumerate(characterization.feature_names)
    }
    return tuple(
        tuple(record.values[positions[feature_name]] for feature_name in config.selected_features)
        for record in characterization.records
    )


def _state(
    config: ExperimentConfig,
    characterization: XjtuCharacterizationData,
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
        _selected_rows(config, characterization),
    )


def test_acquisition_uniform_preserves_every_transformed_train_observation_once() -> None:
    config = _candidate("acquisition-uniform-v1")
    characterization = _characterization(config)
    state = _state(config, characterization)
    transformed = state.transform(
        config.selected_features,
        _selected_rows(config, characterization),
    )

    prepared = prepare_xjtu_model_fit_input(config, state, characterization)

    assert prepared.rows == transformed
    assert (
        prepared.input_observation_count
        == prepared.output_observation_count
        == len(characterization.records)
    )
    assert prepared.source_observation_ids == tuple(
        f"{record.asset_id}:acquisition-{record.acquisition_index}"
        for record in characterization.records
    )


def test_bearing_balanced_resampling_preserves_size_and_equalizes_bearing_mass() -> None:
    config = _candidate("bearing-balanced-resample-v1")
    characterization = _characterization(config)
    state = _state(config, characterization)

    first = prepare_xjtu_model_fit_input(config, state, characterization)
    repeated = prepare_xjtu_model_fit_input(config, state, characterization)

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
    characterization = _characterization(config)
    state = _state(config, characterization)
    first = prepare_xjtu_model_fit_input(config, state, characterization)

    other_config = replace(config, experiment_id="bearing-balanced-other-seed-v1", random_seed=43)
    other_state = _state(other_config, characterization)
    other = prepare_xjtu_model_fit_input(other_config, other_state, characterization)

    assert first.source_observation_ids != other.source_observation_ids


def test_xjtu_sampling_rejects_state_from_another_experiment() -> None:
    config = _candidate("bearing-balanced-resample-v1")
    characterization = _characterization(config)
    state = _state(config, characterization)
    other_config = replace(config, experiment_id="other-experiment-v1")

    with pytest.raises(XjtuSamplingPolicyError, match="experiment_id"):
        prepare_xjtu_model_fit_input(other_config, state, characterization)


def test_xjtu_sampling_rejects_unknown_policy_identifier() -> None:
    config = replace(
        _candidate("acquisition-uniform-v1"),
        experiment_id="unknown-policy-v1",
        sampling_policy_id="site-balanced-v1",
    )
    characterization = _characterization(config)
    state = _state(config, characterization)

    with pytest.raises(XjtuSamplingPolicyError, match="unsupported XJTU sampling policy"):
        prepare_xjtu_model_fit_input(config, state, characterization)


def test_xjtu_sampling_rejects_characterization_from_another_partition() -> None:
    config = _candidate("acquisition-uniform-v1")
    characterization = _characterization(config)
    state = _state(config, characterization)
    validation_data = replace(characterization, partition="validation")

    with pytest.raises(XjtuSamplingPolicyError, match="partition"):
        prepare_xjtu_model_fit_input(config, state, validation_data)


def test_xjtu_sampling_rejects_invalid_selected_feature_value() -> None:
    config = _candidate("bearing-balanced-resample-v1")
    characterization = _characterization(config)
    state = _state(config, characterization)
    last = characterization.records[-1]
    invalid_last = replace(last, values=(float("nan"), *last.values[1:]))
    invalid_data = replace(
        characterization,
        records=(*characterization.records[:-1], invalid_last),
    )

    with pytest.raises(XjtuSamplingPolicyError, match="invalid XJTU preprocessing input"):
        prepare_xjtu_model_fit_input(config, state, invalid_data)
