from datetime import UTC, datetime

from industrial_phm.application.maintenance_review import FindingReviewAction, FindingReviewStatus
from industrial_phm.application.operations_investigations import (
    InvestigationQueueItem,
    InvestigationReviewState,
)
from industrial_phm.application.operations_maintenance import (
    MaintenanceQueueItem,
    MaintenanceReviewTimelineItem,
)
from industrial_phm.presentation.operations_maintenance import (
    maintenance_queue_label,
    maintenance_status_label,
    render_maintenance_evidence_html,
    render_maintenance_identity_html,
    render_maintenance_summary_html,
    render_maintenance_timeline_html,
)

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def _item() -> MaintenanceQueueItem:
    return MaintenanceQueueItem(
        finding_id="finding-1",
        analysis_run_id="run-1",
        asset_id="boiler-01",
        capability_id="three-phase-unbalance-v1",
        measurement_point_id="panel-main",
        requested_at=NOW,
        status=FindingReviewStatus.ACKNOWLEDGED,
        latest_activity_at=NOW,
        note_count=1,
        timeline=(
            MaintenanceReviewTimelineItem(
                event_id="event-1",
                action=FindingReviewAction.NOTE,
                recorded_at=NOW,
                note="현장 점검 예정",
            ),
        ),
    )


def test_maintenance_presenters_keep_workflow_language_primary() -> None:
    item = _item()

    label = maintenance_queue_label(item)
    summary = render_maintenance_summary_html(item)
    timeline = render_maintenance_timeline_html(item)

    assert "boiler-01" in label
    assert "Acknowledged" in label
    assert "Three-phase unbalance" in label
    assert "finding-1" not in label
    assert "Acknowledged" in summary
    assert "현장 점검 예정" in timeline


def test_identity_keeps_internal_ids_in_progressive_disclosure() -> None:
    rendered = render_maintenance_identity_html(_item())

    assert "finding-1" in rendered
    assert "run-1" in rendered
    assert "panel-main" in rendered


def test_maintenance_status_labels_and_css_are_explicit() -> None:
    assert maintenance_status_label(FindingReviewStatus.OPEN) == "Open"
    assert maintenance_status_label(FindingReviewStatus.CLOSED) == "Closed"


def test_reviewed_evidence_is_read_from_the_referenced_analysis() -> None:
    evidence = InvestigationQueueItem(
        investigation_id="run-1:three-phase-unbalance-v1",
        analysis_run_id="run-1",
        asset_id="boiler-01",
        source_id="replay-source",
        measurement_point_id=None,
        capability_id="three-phase-unbalance-v1",
        evidence_id="evidence-1",
        observed_start_at=NOW,
        observed_end_at=NOW,
        completed_at=NOW,
        data_quality="pass",
        review_state=InvestigationReviewState.OPEN,
        finding_id="finding-1",
        review_updated_at=NOW,
    )
    rendered = render_maintenance_evidence_html(
        evidence,
        analysis_run_id="run-1",
        metrics=(
            {
                "quantity": "전류",
                "median_percent": 4.736,
                "p95_percent": 6.696,
                "max_percent": None,
            },
        ),
    )

    assert "Reviewed evidence" in rendered
    assert "replay-source" in rendered
    assert "PASS" in rendered
    assert "4.74%" in rendered and "6.70%" in rendered and "—" in rendered

    missing = render_maintenance_evidence_html(None, analysis_run_id="run-gone")
    assert "run-gone" in missing
    assert "not in the loaded analysis results" in missing

def test_maintenance_presenters_localize_review_copy_without_changing_ids() -> None:
    item = _item()
    timeline = render_maintenance_timeline_html(item, "ko-KR")
    missing = render_maintenance_evidence_html(
        None,
        analysis_run_id="run-gone",
        locale="ko-KR",
    )

    assert "검토 이력" in timeline
    assert "메모" in timeline
    assert "현장 점검 예정" in timeline
    assert "run-gone" in missing
    assert "현재 로드된 분석 결과에서 찾을 수 없습니다" in missing

