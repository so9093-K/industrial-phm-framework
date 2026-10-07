from datetime import UTC, datetime

from industrial_phm.application.asset_detail import AssetEvidenceEventKind
from industrial_phm.application.live_window_analysis import WindowAnalysisState
from industrial_phm.application.maintenance_review import FindingReviewStatus
from industrial_phm.application.operations_assets import (
    AssetWorkspaceAnalysis,
    AssetWorkspaceAnalysisAttempt,
    AssetWorkspaceEvent,
    AssetWorkspaceReview,
    AssetWorkspaceSource,
    AssetWorkspaceView,
)
from industrial_phm.application.operations_monitor import OperationsMonitorStatus
from industrial_phm.application.source_registration import SourceType
from industrial_phm.presentation.operations_assets import (
    asset_workspace_css,
    render_asset_analysis_html,
    render_asset_events_html,
    render_asset_header_html,
    render_asset_maintenance_html,
    render_asset_overview_html,
)

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def _view() -> AssetWorkspaceView:
    return AssetWorkspaceView(
        asset_id="boiler-01",
        status=OperationsMonitorStatus.RUNNING,
        source_count=1,
        attention_count=1,
        last_data_at=NOW,
        history_start_at=NOW.replace(day=1),
        history_end_at=NOW,
        history_measurement_count=1200,
        history_channels=("voltage-r", "voltage-s"),
        analyses=(
            AssetWorkspaceAnalysis(
                analysis_run_id="run-1",
                capability_id="three-phase-unbalance-v1",
                evidence_id="evidence-1",
                source_id="source-a",
                measurement_point_id="panel-main",
                observed_start_at=NOW.replace(minute=40),
                observed_end_at=NOW.replace(minute=50),
                completed_at=NOW,
                data_quality="good",
            ),
        ),
        reviews=(
            AssetWorkspaceReview(
                finding_id="finding-1",
                analysis_run_id="run-1",
                capability_id="three-phase-unbalance-v1",
                observed_at=NOW.replace(minute=50),
                status=FindingReviewStatus.ACKNOWLEDGED,
                latest_event_at=NOW,
            ),
        ),
        sources=(
            AssetWorkspaceSource(
                source_id="source-a",
                name="Line A power",
                source_type=SourceType.FILE,
                status=OperationsMonitorStatus.RUNNING,
                last_data_at=NOW,
                measurement_point_id="panel-main",
                channel_count=3,
            ),
        ),
        analysis_attempts=(
            AssetWorkspaceAnalysisAttempt(
                asset_id="boiler-01",
                state=WindowAnalysisState.SKIPPED,
                capability_id="three-phase-unbalance-v1",
                source_id="source-a",
                measurement_point_id="panel-main",
                observed_start_at=NOW.replace(minute=51),
                observed_end_at=NOW.replace(minute=52),
                recorded_at=NOW.replace(minute=53),
                window_id="window-2",
                reason="missing phase T",
            ),
        ),
        events=(
            AssetWorkspaceEvent(
                event_id="event-1",
                kind=AssetEvidenceEventKind.ANALYSIS_EXECUTED,
                title="Analysis completed",
                occurred_at=NOW,
                detail=None,
            ),
            AssetWorkspaceEvent(
                event_id="event-naive",
                kind=AssetEvidenceEventKind.SOURCE_OBSERVED,
                title="Source data observed",
                occurred_at=datetime(2026, 9, 30, 9, 0),
                detail=None,
            ),
        ),
    )

def test_asset_workspace_presenters_keep_operator_language() -> None:
    view = _view()

    header = render_asset_header_html(view)
    overview = render_asset_overview_html(view)
    analysis = render_asset_analysis_html(view)
    maintenance = render_asset_maintenance_html(view)

    assert "boiler-01" in header
    assert "Data status" in header
    assert "Receiving" in header
    assert "1,200 stored measurements" in overview
    assert "Line A power" in overview
    assert "three-phase-unbalance-v1" in analysis
    assert "Recent analysis attempts" in analysis
    assert "Skipped" in analysis
    assert "missing phase T" in analysis
    assert "2026-09-30 12:53:00 UTC" in analysis
    assert "T12:53:00" not in analysis
    assert "Acknowledged" in maintenance
    for rendered in (header, overview, analysis, maintenance):
        assert "control-plane" not in rendered
        assert "watermark" not in rendered


def test_events_preserve_non_comparable_time_without_guessing_timezone() -> None:
    rendered = render_asset_events_html(_view())

    assert "Analysis completed" in rendered
    assert "Time not comparable" in rendered


def test_asset_css_uses_existing_v2_tokens() -> None:
    css = asset_workspace_css()

    assert "var(--phm-border)" in css
    assert "var(--phm-muted)" in css

def test_asset_workspace_presenters_localize_labels_without_changing_identity() -> None:
    view = _view()

    overview = render_asset_overview_html(view, "ko-KR")
    analysis = render_asset_analysis_html(view, "ko-KR")
    maintenance = render_asset_maintenance_html(view, "ko-KR")

    assert "저장 측정값 1,200개" in overview
    assert "채널 2개" in overview
    assert "최근 분석 시도" in analysis
    assert "건너뜀" in analysis
    assert "three-phase-unbalance-v1" in analysis
    assert "source-a" in analysis
    assert "확인됨" in maintenance
    assert "finding-1" in maintenance
