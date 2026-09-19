from dataclasses import replace

import pytest

from industrial_phm.experiments import ReferenceStrategy
from industrial_phm.experiments.mimii import get_mimii_section_configuration
from industrial_phm.experiments.mimii_model_input import (
    MimiiModelInputError,
    fit_mimii_preprocessing_and_prepare_model_input,
    prepare_mimii_model_scoring_input,
)
from industrial_phm.features import AudioFeatureVector, audio_logmel_feature_names

_FEATURE_NAMES = audio_logmel_feature_names()


def _vector(
    *,
    machine_type: str = "fan",
    section: str = "00",
    domain: str,
    split: str,
    source_file_number: int,
    clip_label: str,
    offset: float = 0.0,
) -> AudioFeatureVector:
    source_file = (
        f"dev/{machine_type}/"
        f"{'train' if split == 'train' else domain + '_test'}/"
        f"section_{section}_{domain}_{split}_{clip_label}_{source_file_number:04d}.wav"
    )
    return AudioFeatureVector(
        feature_set_id="audio-logmel-statistical-v1",
        asset_id=f"{machine_type}/section-{section}",
        feature_names=_FEATURE_NAMES,
        values=tuple(offset + feature_index * 0.01 for feature_index in range(128)),
        metadata={
            "dataset_id": "mimii-due",
            "source_group": "dev",
            "machine_type": machine_type,
            "section": section,
            "domain": domain,
            "split": split,
            "clip_label": clip_label,
            "source_file_number": source_file_number,
            "source_file": source_file,
        },
    )


@pytest.fixture(scope="module")
def fan_section_00_train_vectors() -> tuple[AudioFeatureVector, ...]:
    source = tuple(
        _vector(
            domain="source",
            split="train",
            source_file_number=index,
            clip_label="normal",
            offset=float(index),
        )
        for index in range(1_000)
    )
    target = tuple(
        _vector(
            domain="target",
            split="train",
            source_file_number=index,
            clip_label="normal",
            offset=10_000.0 + index,
        )
        for index in range(3)
    )
    return (*source, *target)


def test_mimii_section_model_fit_preserves_complete_train_population(
    fan_section_00_train_vectors: tuple[AudioFeatureVector, ...],
) -> None:
    config = get_mimii_section_configuration("fan", "00")

    state, model_input = fit_mimii_preprocessing_and_prepare_model_input(
        config,
        tuple(reversed(fan_section_00_train_vectors)),
    )

    assert state.observation_count == 1_003
    assert state.scaling_strategy.value == "robust"
    assert model_input.source_observation_count == 1_003
    assert model_input.reference_observation_count == 1_003
    assert model_input.fit_observation_count == 1_003
    assert model_input.sampling_policy_id == "clip-uniform-v1"
    assert tuple(model_input.source_observation_ids) == tuple(
        sorted(model_input.source_observation_ids)
    )


def test_mimii_section_model_fit_rejects_incomplete_target_train_population(
    fan_section_00_train_vectors: tuple[AudioFeatureVector, ...],
) -> None:
    config = get_mimii_section_configuration("fan", "00")
    incomplete = tuple(
        vector
        for vector in fan_section_00_train_vectors
        if not (
            vector.metadata["domain"] == "target"
            and vector.metadata["source_file_number"] == 2
        )
    )

    with pytest.raises(MimiiModelInputError, match="train domain counts"):
        fit_mimii_preprocessing_and_prepare_model_input(config, incomplete)


def test_mimii_section_model_fit_rejects_non_normal_train_clip(
    fan_section_00_train_vectors: tuple[AudioFeatureVector, ...],
) -> None:
    config = get_mimii_section_configuration("fan", "00")
    changed = list(fan_section_00_train_vectors)
    changed[0] = _vector(
        domain="source",
        split="train",
        source_file_number=0,
        clip_label="anomaly",
        offset=1.0,
    )

    with pytest.raises(MimiiModelInputError, match="clip_label must be 'normal'"):
        fit_mimii_preprocessing_and_prepare_model_input(config, tuple(changed))


def test_mimii_scoring_input_is_independent_of_test_clip_label(
    fan_section_00_train_vectors: tuple[AudioFeatureVector, ...],
) -> None:
    config = get_mimii_section_configuration("fan", "00")
    state, _ = fit_mimii_preprocessing_and_prepare_model_input(
        config,
        fan_section_00_train_vectors,
    )
    normal_labels = tuple(
        _vector(
            domain="source",
            split="test",
            source_file_number=index,
            clip_label="normal",
            offset=20_000.0 + index,
        )
        for index in range(4)
    )
    anomaly_labels = tuple(
        AudioFeatureVector(
            feature_set_id=vector.feature_set_id,
            asset_id=vector.asset_id,
            feature_names=vector.feature_names,
            values=vector.values,
            metadata={**dict(vector.metadata), "clip_label": "anomaly"},
        )
        for vector in normal_labels
    )

    normal_input = prepare_mimii_model_scoring_input(
        config,
        state,
        normal_labels,
        domain="source",
    )
    anomaly_input = prepare_mimii_model_scoring_input(
        config,
        state,
        anomaly_labels,
        domain="source",
    )

    assert normal_input == anomaly_input


def test_mimii_model_input_rejects_derived_config_drift() -> None:
    config = replace(
        get_mimii_section_configuration("fan", "00"),
        reference_strategy=ReferenceStrategy.TRAIN_BEARING_EARLY_THIRD,
    )

    with pytest.raises(MimiiModelInputError, match="invalid MIMII section configuration"):
        fit_mimii_preprocessing_and_prepare_model_input(config, ())
