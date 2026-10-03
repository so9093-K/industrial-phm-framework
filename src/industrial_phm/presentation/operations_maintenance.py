"""Presentation helpers for Operations maintenance review workspace."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape

from industrial_phm.application.maintenance_review import FindingReviewStatus
from industrial_phm.application.operations_maintenance import MaintenanceQueueItem


def maintenance_status_label(status: FindingReviewStatus) -> str:
    return {
        FindingReviewStatus.OPEN: "Open",
        FindingReviewStatus.ACKNOWLEDGED: "Acknowledged",
        FindingReviewStatus.CLOSED: "Closed",
    }[status]


def maintenance_capability_label(capability_id: str) -> str:
    return {
        "three-phase-unbalance-v1": "Three-phase unbalance",
        "field-vibration-statistical-features-v1": "Vibration features",
    }.get(capability_id, capability_id)


def maintenance_queue_label(item: MaintenanceQueueItem) -> str:
    return (
        f"{item.asset_id} · {maintenance_capability_label(item.capability_id)} · "
        f"{maintenance_status_label(item.status)} · {_time_label(item.requested_at)}"
    )


def render_maintenance_summary_html(item: MaintenanceQueueItem) -> str:
    return (
        '<section class="phm-shell">'
        '<div class="phm-investigation-heading">'
        "<div>"
        '<div class="phm-asset-kicker">Maintenance review</div>'
        f'<h2 class="phm-asset-title">{escape(item.asset_id)}</h2>'
        f'<div class="phm-card-detail">'
        f"{escape(maintenance_capability_label(item.capability_id))}</div>"
        "</div>"
        '<div class="phm-investigation-facts">'
        + _fact("Status", maintenance_status_label(item.status))
        + _fact("Requested", _time_label(item.requested_at))
        + _fact("Last activity", _time_label(item.latest_activity_at))
        + _fact("Notes", str(item.note_count))
        + "</div>"
        "</div>"
        "</section>"
    )


def render_maintenance_timeline_html(item: MaintenanceQueueItem) -> str:
    if not item.timeline:
        body = (
            '<tr><td colspan="3" class="phm-card-detail">'
            "No review activity has been recorded yet."
            "</td></tr>"
        )
    else:
        body = "".join(
            "<tr>"
            f"<td>{escape(_time_label(event.recorded_at))}</td>"
            f"<td>{escape(event.action.value.title())}</td>"
            f"<td>{escape(event.note or '—')}</td>"
            "</tr>"
            for event in item.timeline
        )
    return (
        '<section class="phm-shell">'
        '<div class="phm-section-title">Review timeline</div>'
        '<table class="phm-table">'
        "<thead><tr><th>Time</th><th>Action</th><th>Note</th></tr></thead>"
        f"<tbody>{body}</tbody></table></section>"
    )


def render_maintenance_identity_html(item: MaintenanceQueueItem) -> str:
    rows = (
        ("Finding", item.finding_id),
        ("Analysis run", item.analysis_run_id),
        ("Capability", item.capability_id),
        ("Measurement point", item.measurement_point_id or "Not recorded"),
    )
    body = "".join(
        f"<tr><td>{escape(label)}</td><td>{escape(value)}</td></tr>" for label, value in rows
    )
    return (
        '<section class="phm-shell">'
        '<div class="phm-section-title">Review identity</div>'
        f'<table class="phm-table"><tbody>{body}</tbody></table>'
        "</section>"
    )


def maintenance_workspace_css() -> str:
    return """
<style>
.phm-maintenance-counts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: .65rem;
}
.phm-maintenance-actions {
  background: var(--phm-surface);
  border: 1px solid var(--phm-border);
  border-radius: 10px;
  padding: 1rem;
}
</style>
"""


def _fact(label: str, value: str) -> str:
    return (
        "<div>"
        f'<div class="phm-fact-label">{escape(label)}</div>'
        f'<div class="phm-fact-value">{escape(value)}</div>'
        "</div>"
    )


def _time_label(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.utcoffset() is None:
        return "Time not comparable"
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
