from datetime import datetime

import pytest

from industrial_phm.application import (
    AnalysisRun,
    OperationalFinding,
    SourceSnapshotEvidence,
    validate_operational_finding_against_run,
)
from industrial_phm.contracts import DataQualityAssessment


def _analysis_run() -> AnalysisRun:
    return AnalysisRun(
        analysis_run_id="run-001",
        asset_id="pump-01",
        source_id="field-export:pump-01",
        measurement_point_id="drive-end-bearing",
        observed_start_at=datetime.fromisoformat("2026-09-22T10:00:00+09:00"),
        observed_end_at=datetime.fromisoformat("2026-09-22T11:00:00+09:00"),
        started_at=datetime.fromisoformat("2026-09-22T11:05:00+09:00"),
        completed_at=datetime.fromisoformat("2026-09-22T11:05:10+09:00"),
        model_deployment_id="pump-condition-v1",
        source_snapshots=(
            SourceSnapshotEvidence(
                name="segment-001.csv",
                sha256="a" * 64,
                size_bytes=128,
            ),
        ),
        capability_ids=("condition-state",),
        data_quality=DataQualityAssessment(),
    )


def test_analysis_run_preserves_operational_identity_and_provenance() -> None:
    run = _analysis_run()

    assert run.analysis_run_id == "run-001"
    assert run.asset_id == "pump-01"
    assert run.measurement_point_id == "drive-end-bearing"
    assert run.model_deployment_id == "pump-condition-v1"
    assert run.capability_ids == ("condition-state",)
    assert run.source_snapshots[0].sha256 == "a" * 64


def test_analysis_run_rejects_reversed_observation_window() -> None:
    with pytest.raises(ValueError, match="observed start time"):
        AnalysisRun(
            analysis_run_id="run-001",
            asset_id="pump-01",
            source_id="field-export:pump-01",
            observed_start_at=datetime.fromisoformat("2026-09-22T11:00:00+09:00"),
            observed_end_at=datetime.fromisoformat("2026-09-22T10:00:00+09:00"),
            started_at=datetime.fromisoformat("2026-09-22T11:05:00+09:00"),
            completed_at=datetime.fromisoformat("2026-09-22T11:05:10+09:00"),
            data_quality=DataQualityAssessment(),
        )


def test_analysis_run_requires_timezone_aware_operational_times() -> None:
    with pytest.raises(ValueError, match="observed start time must be a timezone-aware datetime"):
        AnalysisRun(
            analysis_run_id="run-001",
            asset_id="pump-01",
            source_id="field-export:pump-01",
            observed_start_at=datetime.fromisoformat("2026-09-22T10:00:00"),
            observed_end_at=datetime.fromisoformat("2026-09-22T11:00:00+09:00"),
            started_at=datetime.fromisoformat("2026-09-22T11:05:00+09:00"),
            completed_at=datetime.fromisoformat("2026-09-22T11:05:10+09:00"),
            data_quality=DataQualityAssessment(),
        )

    with pytest.raises(ValueError, match="execution end time must be a timezone-aware datetime"):
        AnalysisRun(
            analysis_run_id="run-001",
            asset_id="pump-01",
            source_id="field-export:pump-01",
            observed_start_at=datetime.fromisoformat("2026-09-22T10:00:00+09:00"),
            observed_end_at=datetime.fromisoformat("2026-09-22T11:00:00+09:00"),
            started_at=datetime.fromisoformat("2026-09-22T11:05:00+09:00"),
            completed_at=datetime.fromisoformat("2026-09-22T11:05:10"),
            data_quality=DataQualityAssessment(),
        )


def test_analysis_run_rejects_duplicate_source_snapshot_digest() -> None:
    snapshot = SourceSnapshotEvidence(
        name="segment-001.csv",
        sha256="a" * 64,
        size_bytes=128,
    )

    with pytest.raises(ValueError, match="same SHA-256"):
        AnalysisRun(
            analysis_run_id="run-001",
            asset_id="pump-01",
            source_id="field-export:pump-01",
            observed_start_at=datetime.fromisoformat("2026-09-22T10:00:00+09:00"),
            observed_end_at=datetime.fromisoformat("2026-09-22T11:00:00+09:00"),
            started_at=datetime.fromisoformat("2026-09-22T11:05:00+09:00"),
            completed_at=datetime.fromisoformat("2026-09-22T11:05:10+09:00"),
            source_snapshots=(snapshot, snapshot),
            data_quality=DataQualityAssessment(),
        )


def test_operational_finding_preserves_semantics_and_evidence_refs() -> None:
    finding = OperationalFinding(
        finding_id="finding-001",
        analysis_run_id="run-001",
        asset_id="pump-01",
        measurement_point_id="drive-end-bearing",
        observed_at=datetime.fromisoformat("2026-09-22T10:30:00+09:00"),
        capability_id="condition-state",
        finding_semantics_id="pump-condition-state-v1",
        state="attention",
        evidence_refs=("condition-evidence:segment-001",),
    )

    assert finding.state == "attention"
    assert finding.capability_id == "condition-state"
    assert finding.evidence_refs == ("condition-evidence:segment-001",)


def test_operational_finding_requires_evidence_reference() -> None:
    with pytest.raises(ValueError, match="at least one"):
        OperationalFinding(
            finding_id="finding-001",
            analysis_run_id="run-001",
            asset_id="pump-01",
            observed_at=datetime.fromisoformat("2026-09-22T10:30:00+09:00"),
            capability_id="condition-state",
            finding_semantics_id="pump-condition-state-v1",
            state="attention",
            evidence_refs=(),
        )


def test_operational_finding_requires_timezone_aware_observed_at() -> None:
    with pytest.raises(ValueError, match="observed_at must be a timezone-aware datetime"):
        OperationalFinding(
            finding_id="finding-001",
            analysis_run_id="run-001",
            asset_id="pump-01",
            observed_at=datetime.fromisoformat("2026-09-22T10:30:00"),
            capability_id="condition-state",
            finding_semantics_id="pump-condition-state-v1",
            state="attention",
            evidence_refs=("condition-evidence:segment-001",),
        )


def test_operational_finding_validates_against_analysis_run() -> None:
    run = _analysis_run()
    finding = OperationalFinding(
        finding_id="finding-001",
        analysis_run_id=run.analysis_run_id,
        asset_id=run.asset_id,
        measurement_point_id=run.measurement_point_id,
        observed_at=datetime.fromisoformat("2026-09-22T10:30:00+09:00"),
        capability_id="condition-state",
        finding_semantics_id="pump-condition-state-v1",
        state="attention",
        evidence_refs=("condition-evidence:segment-001",),
    )

    validate_operational_finding_against_run(finding, run)


def test_operational_finding_rejects_mismatched_asset() -> None:
    run = _analysis_run()
    finding = OperationalFinding(
        finding_id="finding-001",
        analysis_run_id=run.analysis_run_id,
        asset_id="pump-02",
        measurement_point_id=run.measurement_point_id,
        observed_at=datetime.fromisoformat("2026-09-22T10:30:00+09:00"),
        capability_id="condition-state",
        finding_semantics_id="pump-condition-state-v1",
        state="attention",
        evidence_refs=("condition-evidence:segment-001",),
    )

    with pytest.raises(ValueError, match="asset_id"):
        validate_operational_finding_against_run(finding, run)


def test_operational_finding_rejects_capability_not_declared_by_run() -> None:
    run = _analysis_run()
    finding = OperationalFinding(
        finding_id="finding-001",
        analysis_run_id=run.analysis_run_id,
        asset_id=run.asset_id,
        measurement_point_id=run.measurement_point_id,
        observed_at=datetime.fromisoformat("2026-09-22T10:30:00+09:00"),
        capability_id="bearing-rul",
        finding_semantics_id="bearing-rul-state-v1",
        state="attention",
        evidence_refs=("prognostics-evidence:segment-001",),
    )

    with pytest.raises(ValueError, match="capability_id"):
        validate_operational_finding_against_run(finding, run)


def test_operational_finding_rejects_time_outside_analysis_window() -> None:
    run = _analysis_run()
    finding = OperationalFinding(
        finding_id="finding-001",
        analysis_run_id=run.analysis_run_id,
        asset_id=run.asset_id,
        measurement_point_id=run.measurement_point_id,
        observed_at=datetime.fromisoformat("2026-09-22T12:00:00+09:00"),
        capability_id="condition-state",
        finding_semantics_id="pump-condition-state-v1",
        state="attention",
        evidence_refs=("condition-evidence:segment-001",),
    )

    with pytest.raises(ValueError, match="outside"):
        validate_operational_finding_against_run(finding, run)
