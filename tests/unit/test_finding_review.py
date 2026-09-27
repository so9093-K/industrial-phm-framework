from datetime import UTC, datetime
from pathlib import Path

import pytest

from industrial_phm.application import (
    FIELD_VIBRATION_FEATURE_CAPABILITY_ID,
    AnalysisRun,
    OperationalVibrationFeatureEvidence,
    RegisteredFieldFeatureAnalysis,
    SourceSnapshotEvidence,
)
from industrial_phm.application.finding_review import (
    HUMAN_REVIEW_FINDING_SEMANTICS_ID,
    HUMAN_REVIEW_FINDING_STATE,
    JsonOperationalFindingRepository,
    OperationalFindingHistoryFormatError,
    create_human_review_finding,
)
from industrial_phm.contracts import DataQualityAssessment


def _analysis_result() -> RegisteredFieldFeatureAnalysis:
    snapshot = SourceSnapshotEvidence(
        name="bearing.csv",
        sha256="a" * 64,
        size_bytes=128,
    )
    run = AnalysisRun(
        analysis_run_id="analysis-run-1",
        asset_id="bearing-01",
        source_id="field-bearing-01",
        measurement_point_id="de",
        observed_start_at=datetime(2026, 9, 27, 1, 0, tzinfo=UTC),
        observed_end_at=datetime(2026, 9, 27, 1, 0, 2, tzinfo=UTC),
        started_at=datetime(2026, 9, 27, 1, 5, tzinfo=UTC),
        completed_at=datetime(2026, 9, 27, 1, 5, 1, tzinfo=UTC),
        data_quality=DataQualityAssessment(),
        source_snapshots=(snapshot,),
        capability_ids=(FIELD_VIBRATION_FEATURE_CAPABILITY_ID,),
    )
    evidence = OperationalVibrationFeatureEvidence(
        evidence_id="evidence-1",
        analysis_run_id=run.analysis_run_id,
        capability_id=FIELD_VIBRATION_FEATURE_CAPABILITY_ID,
        feature_set_id="vibration-statistical-v1",
        feature_names=("rms", "peak"),
        values=(1.25, 2.5),
        source_snapshot_sha256=snapshot.sha256,
    )
    return RegisteredFieldFeatureAnalysis(run=run, evidence=evidence)


def test_create_human_review_finding_links_feature_evidence_without_fault_claim() -> None:
    result = _analysis_result()

    finding = create_human_review_finding(result)

    assert finding.finding_id == "finding-review-analysis-run-1"
    assert finding.analysis_run_id == result.run.analysis_run_id
    assert finding.asset_id == result.run.asset_id
    assert finding.measurement_point_id == result.run.measurement_point_id
    assert finding.observed_at == result.run.observed_end_at
    assert finding.capability_id == FIELD_VIBRATION_FEATURE_CAPABILITY_ID
    assert finding.finding_semantics_id == HUMAN_REVIEW_FINDING_SEMANTICS_ID
    assert finding.state == HUMAN_REVIEW_FINDING_STATE
    assert finding.evidence_refs == (result.evidence.evidence_id,)


def test_operational_finding_repository_round_trips_and_is_idempotent(
    tmp_path: Path,
) -> None:
    repository = JsonOperationalFindingRepository(tmp_path / "findings.json")
    finding = create_human_review_finding(_analysis_result())

    repository.record(finding)
    repository.record(finding)

    assert repository.list_findings() == (finding,)


def test_operational_finding_repository_rejects_conflicting_identity(
    tmp_path: Path,
) -> None:
    repository = JsonOperationalFindingRepository(tmp_path / "findings.json")
    finding = create_human_review_finding(_analysis_result())
    repository.record(finding)
    conflicting = type(finding)(
        finding_id=finding.finding_id,
        analysis_run_id=finding.analysis_run_id,
        asset_id=finding.asset_id,
        measurement_point_id=finding.measurement_point_id,
        observed_at=finding.observed_at,
        capability_id=finding.capability_id,
        finding_semantics_id=finding.finding_semantics_id,
        state="DIFFERENT_STATE",
        evidence_refs=finding.evidence_refs,
    )

    with pytest.raises(ValueError, match="different persisted evidence"):
        repository.record(conflicting)


def test_operational_finding_repository_rejects_unsupported_schema(
    tmp_path: Path,
) -> None:
    path = tmp_path / "findings.json"
    path.write_text(
        '{"schema":"industrial-phm-operational-findings-v999","findings":[]}\n',
        encoding="utf-8",
    )

    with pytest.raises(
        OperationalFindingHistoryFormatError,
        match="unsupported operational finding history schema",
    ):
        JsonOperationalFindingRepository(path).list_findings()
