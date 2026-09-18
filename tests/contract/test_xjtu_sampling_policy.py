from collections import Counter
from dataclasses import replace

import pytest

from industrial_phm.experiments import (
    ExperimentConfig,
    XjtuSamplingPolicyError,
    get_xjtu_isolation_forest_candidates,
    get_xjtu_reference_split,
    prepare_xjtu_model_fit_input,
)
from industrial_phm.experiments.xjtu_characterization_artifacts import (
    XjtuCharacterizationRecord,
)
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


def _records_and_rows(
    config: ExperimentConfig,
) -> tuple[tuple[XjtuCharacterizationRecord, ...], tuple[tuple[float, ...], ...]]:
    fold = get_xjtu_reference_split().folds[0]
    records: list[XjtuCharacterizationRecord] = []
    rows: list[tuple[float, ...]] = []
    row_number = 0
    for asset_position, asset_id in enumerate(fold.train, start=1):
        acquisition_count = asset_position + (asset_position == len(fold.train))
        for acquisition_index in range(1, acquisition_count + 1):
            row = tuple(float(row_number + feature_index) for feature_index in range(14))
            records.append(
                XjtuCharacterizationRecord(
                    asset_id=asset_id,
                    acquisition_index=acquisition_index,
                    operating_condition="reference-condition",
                    values=row,
                )
            )
            rows.append(row)
            row_number += 1
    assert len(config.selected_features) == 14
    return tuple(records), tuple(rows)


def _state_and_transformed(
    config: ExperimentConfig,
    rows: tuple[tuple[float, ...], ...],
) -> tuple[PreprocessingState, tuple[tuple[float, ...], ...]]:
    state = fit_preprocessing_state(
        config,
        PreprocessingFitProvenance(
            dataset_id=config.dataset_id,
            split_id=config.split_id,
            fold_id=config.fold_id,
            partition="train",
            feature_set_id=config.feature_set_id,
        ),
        config.selected_features,
        rows,
    )
    return state, state.transform(config.selected_features, rows)


def test_acquisition_uniform_preserves_every_transformed_train_observation_once() -> None:
    config = _candidate("acquisition-uniform")
    records, rows = _records_and_rows(config)
    state, transformed = _state_and_transformed(config, rows)

    prepared = prepare_xjtu_model_fit_input(config, state, records, transformed)

    assert prepared.rows == transformed
    assert prepared.input_observation_count == prepared.output_observation_count == len(records)
    assert prepared.source_observation_ids == tuple(
        f"{record.asset_id}:acquisition-{record.acquisition_index}" for record in records
    )


def test_bearing_balanced_resampling_preserves_size_and_equalizes_bearing_mass() -> None:
    config = _candidate("bearing-balanced")
    records, rows = _records_and_rows(config)
    state, transformed = _state_and_transformed(config, rows)

    first = prepare_xjtu_model_fit_input(config, state, records, transformed)
    repeated = prepare_xjtu_model_fit_input(config, state, records, transformed)

    assert first == repeated
    assert first.input_observation_count == first.output_observation_count == 46
    counts = Counter(
        identity.split(":", maxsplit=1)[0] for identity in first.source_observation_ids
    )
    assert max(counts.values()) - min(counts.values()) == 1
    assert set(counts.values()) == {5, 6}
    assert len(set(first.source_observation_ids)) < first.output_observation_count


def test_bearing_balanced_resampling_uses_experiment_seed() -> None:
    config = _candidate("bearing-balanced")
    records, rows = _records_and_rows(config)
    state, transformed = _state_and_transformed(config, rows)
    first = prepare_xjtu_model_fit_input(config, state, records, transformed)

    other_config = replace(config, experiment_id="bearing-balanced-other-seed-v1", random_seed=43)
    other_state, other_transformed = _state_and_transformed(other_config, rows)
    other = prepare_xjtu_model_fit_input(
        other_config,
        other_state,
        records,
        other_transformed,
    )

    assert first.source_observation_ids != other.source_observation_ids


def test_xjtu_sampling_rejects_state_from_another_experiment() -> None:
    config = _candidate("bearing-balanced")
    records, rows = _records_and_rows(config)
    state, transformed = _state_and_transformed(config, rows)
    other_config = replace(config, experiment_id="other-experiment-v1")

    with pytest.raises(XjtuSamplingPolicyError, match="experiment_id"):
        prepare_xjtu_model_fit_input(other_config, state, records, transformed)


def test_xjtu_sampling_rejects_unknown_policy_identifier() -> None:
    config = replace(
        _candidate("acquisition-uniform"),
        experiment_id="unknown-policy-v1",
        sampling_policy_id="site-balanced",
    )
    records, rows = _records_and_rows(config)
    state, transformed = _state_and_transformed(config, rows)

    with pytest.raises(XjtuSamplingPolicyError, match="unsupported XJTU sampling policy"):
        prepare_xjtu_model_fit_input(config, state, records, transformed)


def test_xjtu_sampling_validates_every_transformed_row_before_selection() -> None:
    config = _candidate("bearing-balanced")
    records, rows = _records_and_rows(config)
    state, transformed = _state_and_transformed(config, rows)
    invalid_rows = list(transformed)
    invalid_rows[-1] = (*invalid_rows[-1][:-1], float("nan"))

    with pytest.raises(XjtuSamplingPolicyError, match="finite numerical values"):
        prepare_xjtu_model_fit_input(config, state, records, invalid_rows)
