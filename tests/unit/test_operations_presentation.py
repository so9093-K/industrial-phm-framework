from datetime import UTC, datetime

from industrial_phm.application import (
    AssetObservationSummary,
    AttentionHandlingState,
    AttentionItem,
    AttentionKind,
    OperationsAttentionQueue,
    OperationsOverview,
    SourceConnectionState,
    SourceDataFlowState,
    SourceHealthAssessment,
    SourceLifecycleRecord,
    SourceLifecycleState,
)
from industrial_phm.contracts import (
    DataQualityAssessment,
    DataQualityIssue,
    DataQualitySeverity,
)
from industrial_phm.presentation import (
    render_attention_queue_markdown,
    render_data_quality_issues_markdown,
    render_observation_markdown,
    render_source_data_flow_markdown,
)

NOW = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)


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
