from datetime import UTC, datetime

from industrial_phm.application.maintenance_review import FindingReviewAction, FindingReviewStatus
from industrial_phm.application.operations_v2_maintenance import (
    MaintenanceQueueItem,
    MaintenanceReviewTimelineItem,
)
from industrial_phm.presentation.operations_v2_maintenance import (
    maintenance_queue_label,
    maintenance_status_label,
    maintenance_workspace_css,
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
    assert "severity" not in maintenance_workspace_css().lower()
