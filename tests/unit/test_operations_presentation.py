from datetime import UTC, datetime

from industrial_phm.application import (
    AnalysisRun,
    AssetDetail,
    AssetEvidenceEvent,
    AssetEvidenceEventKind,
    AssetEvidenceTimeBasis,
    AssetEvidenceTimeline,
    AssetIdentity,
    AssetObservationSummary,
    AssetSourceContext,
    AttentionHandlingState,
    AttentionItem,
    AttentionKind,
    FileSourceConfig,
    OperationalFinding,
    OperationsAttentionQueue,
    OperationsOverview,
    RegisteredSource,
    SourceConnectionState,
    SourceDataFlowState,
    SourceHealthAssessment,
    SourceLifecycleRecord,
    SourceLifecycleState,
    SourceSnapshotEvidence,
)
from industrial_phm.contracts import (
    DataQualityAssessment,
    DataQualityIssue,
    DataQualitySeverity,
)
from industrial_phm.presentation import (
    render_asset_analysis_markdown,
    render_asset_findings_markdown,
    render_asset_sources_markdown,
    render_asset_timeline_markdown,
    render_attention_queue_markdown,
    render_data_quality_issues_markdown,
    render_observation_markdown,
    render_source_data_flow_markdown,
    render_unplaced_asset_evidence_markdown,
)

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)


def _registered_source_for_presentation() -> RegisteredSource:
    return RegisteredSource(
        source_id="source-a",
        name="Source A",
        config=FileSourceConfig(
            source_path="data/source-a.csv",
            asset_id="pump-01",
            measurement_point_id="drive-end",
            channel_columns=("vibration_x",),
            sampling_rate_hz=1_000.0,
        ),
        registered_at=NOW,
    )


def test_asset_analysis_and_finding_presenters_preserve_provenance() -> None:
    snapshot = SourceSnapshotEvidence(
        name="pump.csv",
        sha256="a" * 64,
        size_bytes=128,
    )
    run = AnalysisRun(
        analysis_run_id="analysis-1",
        asset_id="pump-01",
        source_id="source-a",
        measurement_point_id="drive-end",
        observed_start_at=NOW,
        observed_end_at=NOW,
        started_at=NOW,
        completed_at=NOW,
        data_quality=DataQualityAssessment(),
        source_snapshots=(snapshot,),
        capability_ids=("field-vibration-statistical-features-v1",),
    )
    finding = OperationalFinding(
        finding_id="finding-1",
        analysis_run_id=run.analysis_run_id,
        asset_id="pump-01",
        measurement_point_id="drive-end",
        observed_at=NOW,
        capability_id="field-vibration-statistical-features-v1",
        finding_semantics_id="human-review-request-v1",
        state="REVIEW_REQUIRED",
        evidence_refs=("evidence-1",),
    )
    detail = AssetDetail(
        asset_identity=AssetIdentity("pump-01"),
        source_contexts=(),
        latest_observations=(),
        analysis_runs=(run,),
        findings=(finding,),
        review_events=(),
        timeline=AssetEvidenceTimeline(events=(), unplaced_events=()),
    )

    analysis_markdown = render_asset_analysis_markdown(detail)
    findings_markdown = render_asset_findings_markdown(detail)

    assert analysis_markdown is not None
    assert "analysis-1" in analysis_markdown
    assert "field-vibration-statistical-features-v1" in analysis_markdown
    assert "pump.csv" in analysis_markdown
    assert "a" * 64 in analysis_markdown
    assert findings_markdown is not None
    assert "human-review-request-v1" in findings_markdown
    assert "evidence-1" in findings_markdown
    assert "fault/health verdict를 추론하지 않습니다" in findings_markdown


def test_asset_timeline_presenters_separate_comparable_and_unplaced_time() -> None:
    comparable = AssetEvidenceEvent(
        event_id="source:source-a:received",
        kind=AssetEvidenceEventKind.PLATFORM_RECEIVED,
        time_basis=AssetEvidenceTimeBasis.PLATFORM_RECEIPT_TIME,
        event_at=NOW,
        source_id="source-a",
    )
    unplaced = AssetEvidenceEvent(
        event_id="source:source-a:observed",
        kind=AssetEvidenceEventKind.SOURCE_OBSERVED,
        time_basis=AssetEvidenceTimeBasis.SOURCE_TIME,
        event_at=datetime(2026, 9, 27, 9, 59),
        source_id="source-a",
    )
    timeline = AssetEvidenceTimeline(
        events=(comparable,),
        unplaced_events=(unplaced,),
    )

    timeline_markdown = render_asset_timeline_markdown(timeline)
    unplaced_markdown = render_unplaced_asset_evidence_markdown(timeline)

    assert timeline_markdown is not None
    assert "platform-receipt-time" in timeline_markdown
    assert "source-time" not in timeline_markdown
    assert unplaced_markdown is not None
    assert "source-time" in unplaced_markdown
    assert "timezone-naive" in unplaced_markdown


def test_asset_source_presenter_keeps_source_flow_separate_from_asset_condition() -> None:
    lifecycle = SourceLifecycleRecord(
        source_id="source-a",
        state=SourceLifecycleState.ACTIVE,
        changed_at=NOW,
    )
    health = SourceHealthAssessment(
        source_id="source-a",
        assessed_at=NOW,
        lifecycle=lifecycle,
        connection_state=SourceConnectionState.NOT_INSTRUMENTED,
        data_flow_state=SourceDataFlowState.NO_RECEIPT,
        reason="active source has no accepted receipt evidence",
    )
    source = _registered_source_for_presentation()
    detail = AssetDetail(
        asset_identity=AssetIdentity("pump-01"),
        source_contexts=(AssetSourceContext(source=source, health=health),),
        latest_observations=(),
        analysis_runs=(),
        findings=(),
        review_events=(),
        timeline=AssetEvidenceTimeline(
            events=(),
            unplaced_events=(),
        ),
    )

    rendered = render_asset_sources_markdown(detail)

    assert rendered is not None
    assert "NO_RECEIPT" in rendered
    assert "asset condition verdict가 아닙니다" in rendered


def test_attention_presenter_preserves_category_and_escapes_table_evidence() -> None:
    queue = OperationsAttentionQueue(
        (
            AttentionItem(
                attention_id="system-state-error:runtime",
                kind=AttentionKind.SYSTEM_STATE_ERROR,
                handling_state=AttentionHandlingState.ACTIVE,
                occurred_at=NOW,
                detail="state | read\nfailed",
                system_scope="runtime-backtick-state",
            ),
        )
    )

    rendered = render_attention_queue_markdown(queue)

    assert rendered is not None
    assert "SYSTEM_STATE_ERROR" in rendered
    assert "ACTIVE" in rendered
    assert "state \\| read failed" in rendered
    assert "runtime-backtick-state" in rendered
    assert "Data Quality item은 현재 로드된 observation evidence 범위" in rendered
    assert "risk score" not in rendered.lower()


def test_attention_presenter_returns_none_for_empty_queue() -> None:
    assert render_attention_queue_markdown(OperationsAttentionQueue(())) is None


def test_source_data_flow_presenter_uses_existing_read_model_counts() -> None:
    lifecycle = SourceLifecycleRecord(
        source_id="source-a",
        state=SourceLifecycleState.ACTIVE,
        changed_at=NOW,
    )
    health = SourceHealthAssessment(
        source_id="source-a",
        assessed_at=NOW,
        lifecycle=lifecycle,
        connection_state=SourceConnectionState.NOT_INSTRUMENTED,
        data_flow_state=SourceDataFlowState.NO_RECEIPT,
        reason="active source has no accepted receipt evidence",
    )
    overview = OperationsOverview(
        assessed_at=NOW,
        source_health_assessments=(health,),
        analysis_run_count=0,
        latest_analysis_run=None,
        review_summaries=(),
    )

    rendered = render_source_data_flow_markdown(overview)

    assert "| NO_RECEIPT | 1 |" in rendered
    assert "| FRESH | 0 |" in rendered
    assert "asset health가 아닙니다" in rendered


def test_observation_and_quality_presenters_render_recorded_facts_only() -> None:
    observation = AssetObservationSummary(
        asset_id="pump-backtick-01",
        source_id="source-a",
        measurement_point_id=None,
        channels=("vibration_x", "temperature|housing"),
        sample_count=2,
        observed_start_at=NOW,
        observed_end_at=NOW,
        sampling_rate_hz=None,
        data_quality=DataQualityAssessment(
            (
                DataQualityIssue(
                    code="missing|value",
                    severity=DataQualitySeverity.WARNING,
                    message="missing | value\nrecorded",
                ),
            )
        ),
    )

    observation_markdown = render_observation_markdown(observation)
    quality_markdown = render_data_quality_issues_markdown(observation)

    assert "pump-backtick-01" in observation_markdown
    assert "`Not recorded`" in observation_markdown
    assert "temperature\\|housing" in observation_markdown
    assert "Not declared" in observation_markdown
    assert quality_markdown is not None
    assert "missing|value" in quality_markdown
    assert "missing \\| value recorded" in quality_markdown


def test_quality_presenter_returns_none_without_recorded_issue() -> None:
    observation = AssetObservationSummary(
        asset_id="pump-01",
        source_id="source-a",
        channels=("vibration_x",),
        sample_count=1,
        data_quality=DataQualityAssessment(),
    )

    assert render_data_quality_issues_markdown(observation) is None
