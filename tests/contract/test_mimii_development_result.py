import json
from dataclasses import replace
from pathlib import Path

import pytest

from industrial_phm.data import get_dataset
from industrial_phm.experiments.binary_ranking import (
    BinaryRankingEvaluation,
    harmonic_mean_unit_interval,
)
from industrial_phm.experiments.mimii import (
    get_mimii_section_configuration,
    iter_mimii_development_section_scopes,
    mimii_expected_train_domain_counts,
)
from industrial_phm.experiments.mimii_development import (
    MIMII_DEVELOPMENT_RESULT_SCHEMA_ID,
    MimiiDevelopmentResultError,
    MimiiSectionDevelopmentEvidence,
    MimiiSectionDevelopmentInput,
    build_mimii_development_result,
    evaluate_mimii_section_development,
    write_mimii_development_result,
)
from industrial_phm.features import AudioFeatureVector, audio_logmel_feature_names

_FEATURE_NAMES = audio_logmel_feature_names()
_CODE_REVISION = "1" * 40


def _vector(
    *,
    machine_type: str = "fan",
    section: str = "00",
    domain: str,
    split: str,
    source_file_number: int,
    clip_label: str,
    offset: float,
) -> AudioFeatureVector:
    directory = "train" if split == "train" else f"{domain}_test"
    return AudioFeatureVector(
        feature_set_id="audio-logmel-statistical-v1",
        asset_id=f"{machine_type}/section-{section}",
        feature_names=_FEATURE_NAMES,
        values=tuple(offset + feature_index * 0.001 for feature_index in range(128)),
        metadata={
            "dataset_id": "mimii-due",
            "source_group": "dev",
            "machine_type": machine_type,
            "section": section,
            "domain": domain,
            "split": split,
            "clip_label": clip_label,
            "source_file_number": source_file_number,
            "source_file": (
                f"dev/{machine_type}/{directory}/"
                f"section_{section}_{domain}_{split}_{clip_label}_{source_file_number:04d}.wav"
            ),
        },
    )


@pytest.fixture(scope="module")
def fan_section_input() -> MimiiSectionDevelopmentInput:
    train = tuple(
        _vector(
            domain="source",
            split="train",
            source_file_number=index,
            clip_label="normal",
            offset=float(index),
        )
        for index in range(1_000)
    ) + tuple(
        _vector(
            domain="target",
            split="train",
            source_file_number=index,
            clip_label="normal",
            offset=10_000.0 + index,
        )
        for index in range(3)
    )
    source_test = tuple(
        _vector(
            domain="source",
            split="test",
            source_file_number=index,
            clip_label="normal" if index < 2 else "anomaly",
            offset=20_000.0 + index * 1_000.0,
        )
        for index in range(4)
    )
    target_test = tuple(
        _vector(
            domain="target",
            split="test",
            source_file_number=index,
            clip_label="normal" if index < 2 else "anomaly",
            offset=30_000.0 + index * 1_000.0,
        )
        for index in range(4)
    )
    return MimiiSectionDevelopmentInput(
        machine_type="fan",
        section="00",
        train_vectors=train,
        source_test_vectors=source_test,
        target_test_vectors=target_test,
    )


def test_mimii_section_development_fits_scores_then_late_binds_labels(
    fan_section_input: MimiiSectionDevelopmentInput,
) -> None:
    evidence = evaluate_mimii_section_development(fan_section_input)

    assert (
        evidence.experiment_id
        == get_mimii_section_configuration(
            "fan",
            "00",
        ).experiment_id
    )
    assert evidence.source_train_count == 1_000
    assert evidence.target_train_count == 3
    assert evidence.preprocessing_fit_count == 1_003
    assert evidence.reference_count == 1_003
    assert evidence.model_fit_count == 1_003
    assert evidence.source_scoring_count == 4
    assert evidence.target_scoring_count == 4
    assert evidence.source_evaluation.normal_count == 2
    assert evidence.source_evaluation.anomaly_count == 2
    assert evidence.target_evaluation.normal_count == 2
    assert evidence.target_evaluation.anomaly_count == 2
    assert 0.0 <= evidence.source_evaluation.roc_auc <= 1.0
    assert 0.0 <= evidence.target_evaluation.partial_roc_auc <= 1.0


def _synthetic_section_evidence(
    machine_type: str,
    section: str,
) -> MimiiSectionDevelopmentEvidence:
    source_train_count, target_train_count = mimii_expected_train_domain_counts(
        machine_type,
        section,
    )
    return MimiiSectionDevelopmentEvidence(
        machine_type=machine_type,
        section=section,
        experiment_id=get_mimii_section_configuration(machine_type, section).experiment_id,
        source_train_count=source_train_count,
        target_train_count=target_train_count,
        preprocessing_fit_count=source_train_count + target_train_count,
        reference_count=source_train_count + target_train_count,
        model_fit_count=source_train_count + target_train_count,
        fitted_center=(0.0,) * 128,
        fitted_scale=(1.0,) * 128,
        zero_iqr_features=(),
        source_scoring_count=4,
        target_scoring_count=4,
        source_evaluation=BinaryRankingEvaluation(
            observation_count=4,
            normal_count=2,
            anomaly_count=2,
            roc_auc=0.8,
            partial_roc_auc=0.7,
            max_false_positive_rate=0.1,
        ),
        target_evaluation=BinaryRankingEvaluation(
            observation_count=4,
            normal_count=2,
            anomaly_count=2,
            roc_auc=0.6,
            partial_roc_auc=0.55,
            max_false_positive_rate=0.1,
        ),
    )


def _complete_synthetic_evidence() -> tuple[MimiiSectionDevelopmentEvidence, ...]:
    return tuple(
        _synthetic_section_evidence(scope.machine_type, scope.section)
        for scope in iter_mimii_development_section_scopes()
    )


def test_mimii_development_result_aggregates_thirty_strata_without_dcase_claim() -> None:
    result = build_mimii_development_result(
        tuple(reversed(_complete_synthetic_evidence())),
        code_revision=_CODE_REVISION,
        source_clip_count=36_433,
    )

    assert len(result.section_results) == 15
    assert tuple((item.machine_type, item.section) for item in result.section_results) == tuple(
        (scope.machine_type, scope.section) for scope in iter_mimii_development_section_scopes()
    )
    assert len(result.machine_summaries) == 5
    assert all(item.stratum_count == 6 for item in result.machine_summaries)
    assert tuple(item.stratum_count for item in result.domain_summaries) == (15, 15)
    assert result.overall_summary.stratum_count == 30
    assert result.overall_summary.roc_auc_harmonic_mean == pytest.approx(
        harmonic_mean_unit_interval((0.8, 0.6))
    )
    assert result.overall_summary.partial_roc_auc_harmonic_mean == pytest.approx(
        harmonic_mean_unit_interval((0.7, 0.55))
    )
    assert result.mimii_domain_shift_summary == pytest.approx(
        harmonic_mean_unit_interval((0.8, 0.7, 0.6, 0.55))
    )


def test_mimii_development_result_requires_all_fifteen_section_scopes() -> None:
    with pytest.raises(MimiiDevelopmentResultError, match="cover all development scopes"):
        build_mimii_development_result(
            _complete_synthetic_evidence()[:-1],
            code_revision=_CODE_REVISION,
            source_clip_count=36_433,
        )


def test_mimii_development_result_writes_deterministic_provenance_json(tmp_path: Path) -> None:
    result = build_mimii_development_result(
        _complete_synthetic_evidence(),
        code_revision=_CODE_REVISION,
        source_clip_count=36_433,
    )
    output_path = tmp_path / "mimii-development.json"

    write_mimii_development_result(result, output_path)

    document = json.loads(output_path.read_text(encoding="utf-8"))
    assert document["schema_id"] == MIMII_DEVELOPMENT_RESULT_SCHEMA_ID
    assert document["provenance"]["code_revision"] == _CODE_REVISION
    source_record = get_dataset("mimii-due")
    assert document["source_scope"]["dataset_record"] == {
        "version": source_record.version,
        "provider": source_record.provider,
        "source_url": source_record.source_url,
        "citation_doi": source_record.citation_doi,
        "license": source_record.license_name,
    }
    assert document["source_scope"]["verified_source_clip_count"] == 36_433
    assert document["representation"]["feature_set_id"] == "audio-logmel-statistical-v1"
    assert document["representation"]["feature_count"] == 128
    assert len(document["section_models"]) == 15
    assert document["evaluation"]["stratum_unit"] == "machine-type-x-section-x-domain"
    assert document["evaluation"]["dcase_official_score"] is False
    assert "thresholded-state-detection" in document["capability"]["unsupported"]


def test_mimii_development_result_rejects_dataset_record_drift() -> None:
    result = build_mimii_development_result(
        _complete_synthetic_evidence(),
        code_revision=_CODE_REVISION,
        source_clip_count=36_433,
    )

    with pytest.raises(MimiiDevelopmentResultError, match="dataset_version"):
        replace(result, dataset_version="drifted-version")


def test_mimii_section_evidence_rejects_non_protocol_partial_auc_boundary() -> None:
    evidence = _synthetic_section_evidence("fan", "00")
    invalid_source_evaluation = replace(
        evidence.source_evaluation,
        max_false_positive_rate=0.2,
    )

    with pytest.raises(MimiiDevelopmentResultError, match="max_false_positive_rate"):
        replace(evidence, source_evaluation=invalid_source_evaluation)


def test_mimii_development_result_rejects_summary_drift() -> None:
    result = build_mimii_development_result(
        _complete_synthetic_evidence(),
        code_revision=_CODE_REVISION,
        source_clip_count=36_433,
    )
    drifted_overall = replace(
        result.overall_summary,
        roc_auc_harmonic_mean=result.overall_summary.roc_auc_harmonic_mean + 0.01,
    )

    with pytest.raises(MimiiDevelopmentResultError, match="overall summary"):
        replace(result, overall_summary=drifted_overall)
