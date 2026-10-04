from datetime import UTC, datetime

from industrial_phm.application import (
    FILE_SNAPSHOT_VIBRATION_FEATURE_CAPABILITY_ID,
    PHASE_UNBALANCE_CAPABILITY_ID,
    AnalysisRun,
    SourceSnapshotEvidence,
)
from industrial_phm.contracts import (
    DataQualityAssessment,
    DataQualityIssue,
    DataQualitySeverity,
)
from industrial_phm.presentation import (
    OperationalAnalysisPresentationKind,
    operational_analysis_presentation_kind,
    render_analysis_quality_markdown,
)

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)


def test_operational_analysis_presentation_dispatch_is_capability_explicit() -> None:
    assert (
        operational_analysis_presentation_kind(FILE_SNAPSHOT_VIBRATION_FEATURE_CAPABILITY_ID)
        == OperationalAnalysisPresentationKind.VIBRATION_FEATURES
    )
    assert (
        operational_analysis_presentation_kind(PHASE_UNBALANCE_CAPABILITY_ID)
        == OperationalAnalysisPresentationKind.PHASE_UNBALANCE
    )
    assert operational_analysis_presentation_kind("future-capability-v1") is None


def test_analysis_quality_presenter_preserves_recorded_scope_and_provenance() -> None:
    issue = DataQualityIssue(
        code="missing-values",
        severity=DataQualitySeverity.WARNING,
        message="missing values were recorded",
    )
    snapshot = SourceSnapshotEvidence(
        name="pump.csv",
        sha256="b" * 64,
        size_bytes=256,
    )
    run = AnalysisRun(
        analysis_run_id="analysis-quality",
        asset_id="pump-01",
        source_id="source-a",
        observed_start_at=NOW,
        observed_end_at=NOW,
        started_at=NOW,
        completed_at=NOW,
        data_quality=DataQualityAssessment((issue,)),
        source_snapshots=(snapshot,),
    )

    rendered = render_analysis_quality_markdown(run)

    assert "WARNING" in rendered
    assert "missing-values" in rendered
    assert "not asset health" in rendered
    assert "pump.csv" in rendered
    assert "b" * 64 in rendered
