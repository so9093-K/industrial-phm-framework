"""HTML presenters for the Operations V2 asset workspace."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape

from industrial_phm.application.operations_v2_assets import AssetWorkspaceView
from industrial_phm.presentation.operations_v2 import status_label


def render_asset_header_html(view: AssetWorkspaceView) -> str:
    if not isinstance(view, AssetWorkspaceView):
        raise ValueError("view must be an AssetWorkspaceView")
    return (
        '<section class="phm-shell">'
        '<div class="phm-asset-header">'
        '<div>'
        f'<div class="phm-asset-kicker">Asset</div>'
        f'<h2 class="phm-asset-title">{escape(view.asset_id)}</h2>'
        '</div>'
        '<div class="phm-asset-facts">'
        + _fact("Status", status_label(view.status), f"phm-status-{view.status.value}")
        + _fact("Last data", _time_label(view.last_data_at))
        + _fact("Sources", str(view.source_count))
        + _fact("Latest analysis", _time_label(view.latest_analysis_at))
        + _fact("Open reviews", str(view.open_review_count))
        + '</div></div></section>'
    )


def render_asset_overview_html(view: AssetWorkspaceView) -> str:
    if not isinstance(view, AssetWorkspaceView):
        raise ValueError("view must be an AssetWorkspaceView")
    history_summary = (
        "No stored history"
        if view.history_measurement_count == 0
        else f"{view.history_measurement_count:,} stored measurements"
    )
    history_range = (
        "—"
        if view.history_start_at is None or view.history_end_at is None
        else f"{_time_label(view.history_start_at)} → {_time_label(view.history_end_at)}"
    )
    cards = (
        _overview_card(
            "Data",
            status_label(view.status),
            f"Last data {_time_label(view.last_data_at)}",
            view.status.value,
        )
        + _overview_card(
            "History",
            history_summary,
            f"{len(view.history_channels)} channel(s) · {history_range}",
        )
        + _overview_card(
            "Analysis",
            f"{len(view.analyses)} recorded run(s)",
            f"Latest {_time_label(view.latest_analysis_at)}",
        )
        + _overview_card(
            "Reviews",
            f"{view.open_review_count} open",
            f"{view.attention_count} item(s) need attention",
        )
    )
    source_rows = "".join(
        (
            "<tr>"
            f"<td><strong>{escape(source.name)}</strong><br>"
            f'<span class="phm-card-detail">{escape(source.source_id)}</span></td>'
            f"<td>{escape(source.source_type.value.upper())}</td>"
            f'<td class="phm-status-{source.status.value}">'
            f"{escape(status_label(source.status))}</td>"
            f"<td>{escape(_time_label(source.last_data_at))}</td>"
            f"<td>{escape(source.measurement_point_id or '—')}</td>"
            f"<td>{source.channel_count}</td>"
            "</tr>"
        )
        for source in view.sources
    )
    if not source_rows:
        source_rows = (
            '<tr><td colspan="6" class="phm-card-detail">'
            "No active source mapping is recorded for this asset."
            "</td></tr>"
        )
    return (
        '<section class="phm-shell">'
        '<div class="phm-overview-grid">'
        f"{cards}"
        "</div>"
        '<div class="phm-section-title phm-section-space">Sources</div>'
        '<table class="phm-table">'
        "<thead><tr><th>Source</th><th>Type</th><th>Data</th>"
        "<th>Last data</th><th>Point</th><th>Signals</th></tr></thead>"
        f"<tbody>{source_rows}</tbody></table></section>"
    )


def render_asset_analysis_html(view: AssetWorkspaceView) -> str:
    if not isinstance(view, AssetWorkspaceView):
        raise ValueError("view must be an AssetWorkspaceView")
    rows = "".join(
        (
            "<tr>"
            f"<td>{escape(_time_label(item.completed_at))}</td>"
            f"<td><strong>{escape(_capability_label(item.capability_id))}</strong><br>"
            f'<span class="phm-card-detail">{escape(item.capability_id)}</span></td>'
            f"<td>{escape(item.source_id)}</td>"
            f"<td>{escape(item.measurement_point_id or '—')}</td>"
            f"<td>{escape(item.data_quality.upper())}</td>"
            f"<td>{escape(_time_label(item.observed_start_at))} → "
            f"{escape(_time_label(item.observed_end_at))}</td>"
            "</tr>"
        )
        for item in view.analyses
    )
    if not rows:
        rows = (
            '<tr><td colspan="6" class="phm-card-detail">'
            "No analysis has been recorded for this asset yet."
            "</td></tr>"
        )
    return (
        '<section class="phm-shell">'
        '<div class="phm-section-title">Analysis</div>'
        '<table class="phm-table">'
        "<thead><tr><th>Completed</th><th>Capability</th><th>Source</th>"
        "<th>Point</th><th>Data quality</th><th>Observed range</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def render_asset_events_html(view: AssetWorkspaceView) -> str:
    if not isinstance(view, AssetWorkspaceView):
        raise ValueError("view must be an AssetWorkspaceView")
    rows = "".join(
        (
            "<tr>"
            f"<td>{escape(_event_time_label(item.occurred_at))}</td>"
            f"<td><strong>{escape(item.title)}</strong></td>"
            f"<td>{escape(item.detail or '—')}</td>"
            "</tr>"
        )
        for item in view.events
    )
    if not rows:
        rows = (
            '<tr><td colspan="3" class="phm-card-detail">'
            "No operational event is recorded for this asset."
            "</td></tr>"
        )
    return (
        '<section class="phm-shell">'
        '<div class="phm-section-title">Events</div>'
        '<table class="phm-table">'
        "<thead><tr><th>Time</th><th>Event</th><th>Detail</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def render_asset_maintenance_html(view: AssetWorkspaceView) -> str:
    if not isinstance(view, AssetWorkspaceView):
        raise ValueError("view must be an AssetWorkspaceView")
    rows = "".join(
        (
            "<tr>"
            f"<td><strong>{escape(_capability_label(item.capability_id))}</strong><br>"
            f'<span class="phm-card-detail">{escape(item.finding_id)}</span></td>'
            f"<td>{escape(item.status.value.title())}</td>"
            f"<td>{escape(_time_label(item.observed_at))}</td>"
            f"<td>{escape(_time_label(item.latest_event_at))}</td>"
            "</tr>"
        )
        for item in view.reviews
    )
    if not rows:
        rows = (
            '<tr><td colspan="4" class="phm-card-detail">'
            "No maintenance review is recorded for this asset."
            "</td></tr>"
        )
    return (
        '<section class="phm-shell">'
        '<div class="phm-section-title">Maintenance</div>'
        '<table class="phm-table">'
        "<thead><tr><th>Review</th><th>Status</th>"
        "<th>Requested from evidence</th><th>Last review activity</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def asset_workspace_css() -> str:
    return """
<style>
.phm-asset-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1.5rem;
  padding: 1.1rem 0 1.25rem;
  border-bottom: 1px solid var(--phm-border);
}
.phm-asset-kicker {
  color: var(--phm-muted);
  font-size: .72rem;
  text-transform: uppercase;
  letter-spacing: .08em;
}
.phm-asset-title {
  margin: .25rem 0 0;
  font-size: 1.75rem;
  font-weight: 650;
}
.phm-asset-facts {
  display: grid;
  grid-template-columns: repeat(5, minmax(92px, auto));
  gap: .9rem;
}
.phm-fact-label {
  color: var(--phm-muted);
  font-size: .7rem;
  text-transform: uppercase;
  letter-spacing: .05em;
}
.phm-fact-value {
  margin-top: .2rem;
  font-size: .86rem;
  font-weight: 600;
}
.phm-overview-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: .7rem;
}
.phm-section-space {
  margin-top: 1.3rem;
}
@media (max-width: 1100px) {
  .phm-asset-header { align-items: flex-start; flex-direction: column; }
  .phm-asset-facts { grid-template-columns: repeat(3, minmax(110px, 1fr)); width: 100%; }
  .phm-overview-grid { grid-template-columns: 1fr 1fr; }
}
</style>
"""


def _capability_label(capability_id: str) -> str:
    return {
        "three-phase-unbalance-v1": "Three-phase unbalance",
        "field-vibration-statistical-features-v1": "Vibration features",
    }.get(capability_id, capability_id)


def _fact(label: str, value: str, class_name: str = "") -> str:
    classes = "phm-fact-value" + (f" {class_name}" if class_name else "")
    return (
        "<div>"
        f'<div class="phm-fact-label">{escape(label)}</div>'
        f'<div class="{classes}">{escape(value)}</div>'
        "</div>"
    )


def _overview_card(
    title: str,
    value: str,
    detail: str,
    status: str | None = None,
) -> str:
    status_class = "" if status is None else f" phm-status-{status}"
    return (
        '<div class="phm-card">'
        f'<div class="phm-card-title">{escape(title)}</div>'
        f'<div class="phm-card-status{status_class}">{escape(value)}</div>'
        f'<div class="phm-card-detail">{escape(detail)}</div>'
        "</div>"
    )


def _time_label(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.utcoffset() is None:
        return "Time not comparable"
    return value.astimezone(UTC).isoformat()


def _event_time_label(value: datetime | None) -> str:
    if value is None or value.utcoffset() is None:
        return "Time not comparable"
    return value.astimezone(UTC).isoformat()
