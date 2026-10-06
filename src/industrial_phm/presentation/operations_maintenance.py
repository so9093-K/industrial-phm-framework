"""Presentation helpers for Operations maintenance review workspace."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from html import escape

from industrial_phm.application.asset_display import AssetDisplayNames
from industrial_phm.application.maintenance_review import FindingReviewStatus
from industrial_phm.application.operations_investigations import InvestigationQueueItem
from industrial_phm.application.operations_maintenance import MaintenanceQueueItem
from industrial_phm.presentation.operations_shell import render_asset_title_html


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


def maintenance_queue_label(
    item: MaintenanceQueueItem,
    asset_names: AssetDisplayNames | None = None,
) -> str:
    asset = item.asset_id if asset_names is None else asset_names.label(item.asset_id)
    return (
        f"{asset} · {maintenance_capability_label(item.capability_id)} · "
        f"{maintenance_status_label(item.status)} · {_time_label(item.requested_at)}"
    )


def render_maintenance_summary_html(
    item: MaintenanceQueueItem,
    asset_names: AssetDisplayNames | None = None,
) -> str:
    return (
        '<section class="phm-shell">'
        '<div class="phm-investigation-heading">'
        "<div>"
        '<div class="phm-asset-kicker">Maintenance review</div>'
        + render_asset_title_html(item.asset_id, asset_names)
        + '<div class="phm-card-detail">'
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


def render_maintenance_evidence_html(
    evidence: InvestigationQueueItem | None,
    *,
    analysis_run_id: str,
    metrics: Sequence[Mapping[str, object]] = (),
) -> str:
    """Show the analysis evidence a review references, read from the evidence itself.

    The review record keeps only references; observed range, quality and values are
    taken from the loaded analysis result so they cannot drift from the evidence.
    """
    if evidence is None:
        return (
            '<section class="phm-shell">'
            '<div class="phm-section-title">Reviewed evidence</div>'
            '<div class="phm-card-detail">'
            f"Analysis run {escape(analysis_run_id)} is not in the loaded analysis results."
            "</div></section>"
        )
    metric_table = ""
    if metrics:
        body = "".join(
            "<tr>"
            f"<td>{escape(str(row['quantity']))}</td>"
            f"<td>{escape(_percent(row.get('median_percent')))}</td>"
            f"<td>{escape(_percent(row.get('p95_percent')))}</td>"
            f"<td>{escape(_percent(row.get('max_percent')))}</td>"
            "</tr>"
            for row in metrics
        )
        metric_table = (
            '<table class="phm-table">'
            "<thead><tr><th>Quantity</th><th>Median</th><th>P95</th><th>Max</th></tr></thead>"
            f"<tbody>{body}</tbody></table>"
        )
    return (
        '<section class="phm-shell">'
        '<div class="phm-section-title">Reviewed evidence</div>'
        '<div class="phm-investigation-facts">'
        + _fact("Observed from", _time_label(evidence.observed_start_at))
        + _fact("Observed to", _time_label(evidence.observed_end_at))
        + _fact("Source", evidence.source_id)
        + _fact("Data quality", evidence.data_quality.upper())
        + "</div>"
        + metric_table
        + "</section>"
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


def _percent(value: object) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.2f}%"
    return "—"


def _time_label(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.utcoffset() is None:
        return "Time not comparable"
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
