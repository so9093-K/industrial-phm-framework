"""HTML presenters for the Operations asset workspace."""

from __future__ import annotations

from html import escape

from industrial_phm.application.asset_display import AssetDisplayNames
from industrial_phm.application.operations_assets import AssetWorkspaceView
from industrial_phm.presentation.operations_locale import (
    DEFAULT_OPERATIONS_LOCALE,
    OperationsLocale,
    format_operations_utc,
    operations_capability_label,
    operations_text,
)
from industrial_phm.presentation.operations_shell import data_status_label, render_asset_title_html


def render_asset_header_html(
    view: AssetWorkspaceView,
    asset_names: AssetDisplayNames | None = None,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(view, AssetWorkspaceView):
        raise ValueError("view must be an AssetWorkspaceView")
    kicker = escape(operations_text("asset.title", locale))
    return (
        '<section class="phm-shell">'
        '<div class="phm-asset-header">'
        "<div>"
        f'<div class="phm-asset-kicker">{kicker}</div>'
        + render_asset_title_html(view.asset_id, asset_names)
        + "</div>"
        '<div class="phm-asset-facts">'
        + _fact(
            operations_text("asset.data_status", locale),
            data_status_label(view.status, locale),
            f"phm-status-{view.status.value}",
        )
        + _fact(
            operations_text("asset.last_data", locale),
            format_operations_utc(view.last_data_at, locale),
        )
        + _fact(operations_text("asset.sources", locale), str(view.source_count))
        + _fact(
            operations_text("asset.latest_analysis", locale),
            format_operations_utc(view.latest_analysis_at, locale),
        )
        + _fact(operations_text("asset.open_reviews", locale), str(view.open_review_count))
        + "</div></div></section>"
    )


def render_asset_overview_html(
    view: AssetWorkspaceView,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(view, AssetWorkspaceView):
        raise ValueError("view must be an AssetWorkspaceView")
    history_summary = (
        operations_text("asset.no_history", locale)
        if view.history_measurement_count == 0
        else f"{view.history_measurement_count:,} stored measurements"
    )
    history_range = (
        "—"
        if view.history_start_at is None or view.history_end_at is None
        else (
            f"{format_operations_utc(view.history_start_at, locale)} → "
            f"{format_operations_utc(view.history_end_at, locale)}"
        )
    )
    cards = (
        _overview_card(
            operations_text("asset.data_status", locale),
            data_status_label(view.status, locale),
            f"{operations_text('asset.last_data', locale)} "
            f"{format_operations_utc(view.last_data_at, locale)}",
            view.status.value,
        )
        + _overview_card(
            operations_text("asset.history", locale),
            history_summary,
            f"{len(view.history_channels)} channel(s) · {history_range}",
        )
        + _overview_card(
            operations_text("asset.analysis", locale),
            f"{len(view.analyses)} recorded run(s)",
            f"{operations_text('asset.latest_analysis', locale)} "
            f"{format_operations_utc(view.latest_analysis_at, locale)}",
        )
        + _overview_card(
            operations_text("asset.reviews", locale),
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
            f"{escape(data_status_label(source.status, locale))}</td>"
            f"<td>{escape(format_operations_utc(source.last_data_at, locale))}</td>"
            f"<td>{escape(source.measurement_point_id or '—')}</td>"
            f"<td>{source.channel_count}</td>"
            "</tr>"
        )
        for source in view.sources
    )
    if not source_rows:
        source_rows = _empty_row(6, operations_text("asset.no_source_mapping", locale))
    section_title = escape(operations_text("asset.sources", locale))
    return (
        '<section class="phm-shell">'
        '<div class="phm-overview-grid">'
        f"{cards}"
        "</div>"
        f'<div class="phm-section-title phm-section-space">{section_title}</div>'
        '<table class="phm-table">'
        "<thead><tr><th>Source</th><th>Type</th><th>Data</th>"
        "<th>Last data</th><th>Point</th><th>Signals</th></tr></thead>"
        f"<tbody>{source_rows}</tbody></table></section>"
    )


def render_asset_analysis_html(
    view: AssetWorkspaceView,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(view, AssetWorkspaceView):
        raise ValueError("view must be an AssetWorkspaceView")

    attempt_rows = "".join(
        (
            "<tr>"
            f"<td>{escape(format_operations_utc(item.recorded_at, locale))}</td>"
            f"<td>{escape(item.state.value.title())}</td>"
            "<td><strong>"
            f"{escape(operations_capability_label(item.capability_id, locale))}"
            "</strong></td>"
            f"<td>{escape(item.source_id)}</td>"
            f"<td>{escape(format_operations_utc(item.observed_start_at, locale))} → "
            f"{escape(format_operations_utc(item.observed_end_at, locale))}</td>"
            f"<td>{escape(item.reason or '—')}</td>"
            "</tr>"
        )
        for item in view.analysis_attempts[:50]
    )
    if not attempt_rows:
        attempt_rows = _empty_row(6, operations_text("asset.no_analysis_attempt", locale))

    rows = "".join(
        (
            "<tr>"
            f"<td>{escape(format_operations_utc(item.completed_at, locale))}</td>"
            "<td><strong>"
            f"{escape(operations_capability_label(item.capability_id, locale))}"
            "</strong><br>"
            f'<span class="phm-card-detail">{escape(item.capability_id)}</span></td>'
            f"<td>{escape(item.source_id)}</td>"
            f"<td>{escape(item.measurement_point_id or '—')}</td>"
            f"<td>{escape(item.data_quality.upper())}</td>"
            f"<td>{escape(format_operations_utc(item.observed_start_at, locale))} → "
            f"{escape(format_operations_utc(item.observed_end_at, locale))}</td>"
            "</tr>"
        )
        for item in view.analyses
    )
    if not rows:
        rows = _empty_row(6, operations_text("asset.no_analysis_evidence", locale))
    return (
        '<section class="phm-shell">'
        '<div class="phm-section-title">Recent analysis attempts</div>'
        '<table class="phm-table">'
        "<thead><tr><th>Time</th><th>Outcome</th><th>Capability</th><th>Source</th>"
        "<th>Observed range</th><th>Why no result</th></tr></thead>"
        f"<tbody>{attempt_rows}</tbody></table>"
        '<div class="phm-section-title phm-section-space">Recorded analysis evidence</div>'
        '<table class="phm-table">'
        "<thead><tr><th>Completed</th><th>Capability</th><th>Source</th>"
        "<th>Point</th><th>Data quality</th><th>Observed range</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def render_asset_events_html(
    view: AssetWorkspaceView,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(view, AssetWorkspaceView):
        raise ValueError("view must be an AssetWorkspaceView")
    rows = "".join(
        (
            "<tr>"
            f"<td>{escape(format_operations_utc(item.occurred_at, locale))}</td>"
            f"<td><strong>{escape(item.title)}</strong></td>"
            f"<td>{escape(item.detail or '—')}</td>"
            "</tr>"
        )
        for item in view.events
    )
    if not rows:
        rows = _empty_row(3, operations_text("asset.no_event", locale))
    section_title = escape(operations_text("asset.events", locale))
    return (
        '<section class="phm-shell">'
        f'<div class="phm-section-title">{section_title}</div>'
        '<table class="phm-table">'
        "<thead><tr><th>Time</th><th>Event</th><th>Detail</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def render_asset_maintenance_html(
    view: AssetWorkspaceView,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(view, AssetWorkspaceView):
        raise ValueError("view must be an AssetWorkspaceView")
    rows = "".join(
        (
            "<tr>"
            "<td><strong>"
            f"{escape(operations_capability_label(item.capability_id, locale))}"
            "</strong><br>"
            f'<span class="phm-card-detail">{escape(item.finding_id)}</span></td>'
            f"<td>{escape(item.status.value.title())}</td>"
            f"<td>{escape(format_operations_utc(item.observed_at, locale))}</td>"
            f"<td>{escape(format_operations_utc(item.latest_event_at, locale))}</td>"
            "</tr>"
        )
        for item in view.reviews
    )
    if not rows:
        rows = _empty_row(4, operations_text("asset.no_maintenance_review", locale))
    section_title = escape(operations_text("asset.maintenance", locale))
    return (
        '<section class="phm-shell">'
        f'<div class="phm-section-title">{section_title}</div>'
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
.phm-asset-id {
  margin-top: .15rem;
  color: var(--phm-muted);
  font-size: .78rem;
  font-family: var(--phm-mono, ui-monospace, monospace);
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


def _empty_row(columns: int, message: str) -> str:
    return f'<tr><td colspan="{columns}" class="phm-card-detail">{escape(message)}</td></tr>'
