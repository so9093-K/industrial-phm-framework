from datetime import UTC, datetime
from pathlib import Path

import pytest

from industrial_phm.application import (
    AnalysisRun,
    FIELD_VIBRATION_FEATURE_CAPABILITY_ID,
    OperationalVibrationFeatureEvidence,
    RegisteredFieldFeatureAnalysis,
    SourceSnapshotEvidence,
)
from industrial_phm.application.field_analysis_state import (
    FieldAnalysisHistoryFormatError,
    JsonFieldFeatureAnalysisRepository,
)
from industrial_phm.contracts import (
    DataQualityAssessment,
    DataQualityIssue,
    DataQualitySeverity,
)


def _result(*, run_id: str, completed_minute: int) -> RegisteredFieldFeatureAnalysis:
    snapshot = SourceSnapshotEvidence(
        name="bearing.csv",
        sha256="a" * 64,
        size_bytes=128,
    )
    run = AnalysisRun(
        analysis_run_id=run_id,
        asset_id="bearing-01",
        source_id="field-bearing-01",
        measurement_point_id="de",
        observed_start_at=datetime(2026, 9, 27, 1, 0, tzinfo=UTC),
        observed_end_at=datetime(2026, 9, 27, 1, 0, 2, tzinfo=UTC),
        started_at=datetime(2026, 9, 27, 1, completed_minute, tzinfo=UTC),
        completed_at=datetime(2026, 9, 27, 1, completed_minute, 1, tzinfo=UTC),
        data_quality=DataQualityAssessment(
            (
                DataQualityIssue(
                    code="irregular-sampling",
                    severity=DataQualitySeverity.WARNING,
                    message="recorded warning",
                ),
            )
        ),
        source_snapshots=(snapshot,),
        capability_ids=(FIELD_VIBRATION_FEATURE_CAPABILITY_ID,),
    )
    evidence = OperationalVibrationFeatureEvidence(
        evidence_id=f"evidence-{run_id}",
        analysis_run_id=run_id,
        capability_id=FIELD_VIBRATION_FEATURE_CAPABILITY_ID,
        feature_set_id="vibration-statistical-v1",
        feature_names=("rms", "peak"),
        values=(1.25, 2.5),
        source_snapshot_sha256=snapshot.sha256,
    )
    return RegisteredFieldFeatureAnalysis(run=run, evidence=evidence)


def test_field_analysis_history_round_trips_and_orders_results(tmp_path: Path) -> None:
    repository = JsonFieldFeatureAnalysisRepository(tmp_path / "field-analysis.json")
    later = _result(run_id="analysis-run-2", completed_minute=12)
    earlier = _result(run_id="analysis-run-1", completed_minute=11)

    repository.record(later)
    repository.record(earlier)

    results = repository.list_results()
    assert results == (earlier, later)
    assert results[0].run.data_quality.issues[0].severity == DataQualitySeverity.WARNING
    assert results[0].run.source_snapshots[0].sha256 == "a" * 64


def test_field_analysis_history_accepts_exact_idempotent_replay(tmp_path: Path) -> None:
    repository = JsonFieldFeatureAnalysisRepository(tmp_path / "field-analysis.json")
    result = _result(run_id="analysis-run-1", completed_minute=11)

    repository.record(result)
    repository.record(result)

    assert repository.list_results() == (result,)


def test_field_analysis_history_rejects_conflicting_run_identity(tmp_path: Path) -> None:
    repository = JsonFieldFeatureAnalysisRepository(tmp_path / "field-analysis.json")
    first = _result(run_id="analysis-run-1", completed_minute=11)
    repository.record(first)
    conflicting = RegisteredFieldFeatureAnalysis(
        run=first.run,
        evidence=OperationalVibrationFeatureEvidence(
            evidence_id="different-evidence",
            analysis_run_id=first.run.analysis_run_id,
            capability_id=first.evidence.capability_id,
            feature_set_id=first.evidence.feature_set_id,
            feature_names=first.evidence.feature_names,
            values=(9.0, 9.0),
            source_snapshot_sha256=first.evidence.source_snapshot_sha256,
        ),
    )

    with pytest.raises(ValueError, match="different persisted evidence"):
        repository.record(conflicting)


def test_field_analysis_history_rejects_unsupported_schema(tmp_path: Path) -> None:
    path = tmp_path / "field-analysis.json"
    path.write_text(
        '{"schema":"industrial-phm-field-feature-analysis-v999","results":[]}\n',
        encoding="utf-8",
    )

    with pytest.raises(
        FieldAnalysisHistoryFormatError,
        match="unsupported field analysis history schema",
    ):
        JsonFieldFeatureAnalysisRepository(path).list_results()
