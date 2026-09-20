import json
from pathlib import Path
from typing import cast

import pytest

from industrial_phm.experiments.binary_ranking import BinaryRankingEvaluation
from industrial_phm.experiments.mimii import (
    get_mimii_section_configuration,
    iter_mimii_development_section_scopes,
    mimii_expected_train_domain_counts,
)
from industrial_phm.experiments.mimii_development import (
    MimiiSectionDevelopmentEvidence,
    build_mimii_development_result,
    write_mimii_development_result,
)
from industrial_phm.experiments.result_inspection import (
    ExperimentResultInspectionError,
    inspect_experiment_result,
    render_experiment_inspection_text,
)

_STAGES = (
    "Source",
    "Canonical",
    "Feature",
    "Preprocessing",
    "Reference",
    "Sequence Construction",
    "Population",
    "Model",
    "Scoring",
    "Evaluation",
    "Capability",
    "Provenance",
)
_CODE_REVISION = "a" * 40


def test_mimii_development_inspection_exposes_domain_shift_evidence_boundary(
    tmp_path: Path,
) -> None:
    result_path = _write_mimii_result(tmp_path)

    inspection = inspect_experiment_result(result_path)
    summary = render_experiment_inspection_text(inspection)

    assert tuple(stage.name for stage in inspection.stages) == _STAGES
    assert "Schema: mimii-due-domain-shift-development-result-v1" in summary
    assert "Status: completed" in summary
    assert "Dataset: mimii-due" in summary
    assert "Source group: dev" in summary
    assert "Selected feature count: 128" in summary
    assert "Section models: 15" in summary
    assert "Model unit: machine-type-x-section" in summary
    assert "Label access: evaluator edge only" in summary
    assert "Strata: 30" in summary
    assert "DCASE official score: false" in summary
    assert "Selection or threshold calibration: none" in summary
    assert "Unsupported: thresholded-state-detection" in summary
    assert "sections 03-05 external evaluation is not included" in summary

    sequence_stage = next(
        stage for stage in inspection.stages if stage.name == "Sequence Construction"
    )
    assert sequence_stage.status == "not applicable"
    assert tuple((fact.label, fact.value) for fact in sequence_stage.facts) == (
        ("Reason", "model consumes one fixed feature vector per audio clip"),
    )


def test_mimii_development_inspection_rejects_aggregate_drift(tmp_path: Path) -> None:
    result_path = _write_mimii_result(tmp_path)
    document = _read_object(result_path)
    evaluation = cast(dict[str, object], document["evaluation"])
    overall = cast(dict[str, object], evaluation["overall_summary"])
    overall["roc_auc_harmonic_mean"] = 0.123
    drifted = tmp_path / "mimii-aggregate-drift.json"
    drifted.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        ExperimentResultInspectionError,
        match=r"evaluation.overall_summary.roc_auc_harmonic_mean",
    ):
        inspect_experiment_result(drifted)


def test_mimii_development_inspection_rejects_dcase_official_score_claim(
    tmp_path: Path,
) -> None:
    result_path = _write_mimii_result(tmp_path)
    document = _read_object(result_path)
    evaluation = cast(dict[str, object], document["evaluation"])
    evaluation["dcase_official_score"] = True
    drifted = tmp_path / "mimii-dcase-claim-drift.json"
    drifted.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        ExperimentResultInspectionError,
        match=r"evaluation.dcase_official_score",
    ):
        inspect_experiment_result(drifted)


def test_mimii_development_inspection_rejects_section_population_drift(
    tmp_path: Path,
) -> None:
    result_path = _write_mimii_result(tmp_path)
    document = _read_object(result_path)
    sections = cast(list[dict[str, object]], document["section_models"])
    population = cast(dict[str, object], sections[0]["population_flow"])
    population["target_train_clip_count"] = 2
    drifted = tmp_path / "mimii-population-drift.json"
    drifted.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        ExperimentResultInspectionError,
        match=r"section_models\[0\]\.population_flow\.target_train_clip_count",
    ):
        inspect_experiment_result(drifted)


def _write_mimii_result(tmp_path: Path) -> Path:
    result = build_mimii_development_result(
        tuple(
            _synthetic_section_evidence(scope.machine_type, scope.section)
            for scope in iter_mimii_development_section_scopes()
        ),
        code_revision=_CODE_REVISION,
        source_clip_count=36_433,
    )
    output = tmp_path / "mimii-development.json"
    write_mimii_development_result(result, output)
    return output


def _synthetic_section_evidence(
    machine_type: str,
    section: str,
) -> MimiiSectionDevelopmentEvidence:
    source_train, target_train = mimii_expected_train_domain_counts(
        machine_type,
        section,
    )
    total_train = source_train + target_train
    source_evaluation = _evaluation(roc_auc=0.8, partial_roc_auc=0.7)
    target_evaluation = _evaluation(roc_auc=0.6, partial_roc_auc=0.55)
    return MimiiSectionDevelopmentEvidence(
        machine_type=machine_type,
        section=section,
        experiment_id=get_mimii_section_configuration(machine_type, section).experiment_id,
        source_train_count=source_train,
        target_train_count=target_train,
        preprocessing_fit_count=total_train,
        reference_count=total_train,
        model_fit_count=total_train,
        fitted_center=(0.0,) * 128,
        fitted_scale=(1.0,) * 128,
        zero_iqr_features=(),
        source_scoring_count=4,
        target_scoring_count=4,
        source_evaluation=source_evaluation,
        target_evaluation=target_evaluation,
    )


def _evaluation(
    *,
    roc_auc: float,
    partial_roc_auc: float,
) -> BinaryRankingEvaluation:
    return BinaryRankingEvaluation(
        observation_count=4,
        normal_count=2,
        anomaly_count=2,
        roc_auc=roc_auc,
        partial_roc_auc=partial_roc_auc,
        max_false_positive_rate=0.1,
    )


def _read_object(path: Path) -> dict[str, object]:
    value = cast(object, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(value, dict):
        raise AssertionError("test fixture must be a JSON object")
    return cast(dict[str, object], value)
