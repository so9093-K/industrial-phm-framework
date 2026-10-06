"""Framework-neutral HTML presenters for the Operations shell."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape

from industrial_phm.application.asset_display import AssetDisplayNames
from industrial_phm.application.operations_assets import AssetWorkspaceView
from industrial_phm.application.operations_monitor import (
    OperationsMonitorAsset,
    OperationsMonitorStage,
    OperationsMonitorStatus,
    OperationsMonitorView,
)

OPERATIONS_MAIN_BACKGROUND = "#292827"
OPERATIONS_PAGE_OPTIONS = (
    "Monitor",
    "Assets",
    "Investigations",
    "Maintenance",
    "System",
    "Setup",
)


def initial_operations_page(*, has_registered_sources: bool) -> str:
    """Choose the first Operations page from durable workspace state."""

    if not isinstance(has_registered_sources, bool):
        raise ValueError("has_registered_sources must be a bool")
    return "Monitor" if has_registered_sources else "Setup"


_STATUS_LABEL = {
    OperationsMonitorStatus.RUNNING: "Running",
    OperationsMonitorStatus.WAITING: "Waiting",
    OperationsMonitorStatus.DELAYED: "Delayed",
    OperationsMonitorStatus.STOPPED: "Stopped",
    OperationsMonitorStatus.NEEDS_ATTENTION: "Needs attention",
    OperationsMonitorStatus.ERROR: "Error",
    OperationsMonitorStatus.UNAVAILABLE: "Unavailable",
}

_DATA_STATUS_LABEL = {
    OperationsMonitorStatus.RUNNING: "Receiving",
    OperationsMonitorStatus.WAITING: "Waiting for data",
    OperationsMonitorStatus.DELAYED: "Delayed",
    OperationsMonitorStatus.STOPPED: "Stopped",
    OperationsMonitorStatus.NEEDS_ATTENTION: "Needs attention",
    OperationsMonitorStatus.ERROR: "Error",
    OperationsMonitorStatus.UNAVAILABLE: "Unavailable",
}


def operations_theme_css() -> str:
    """Return the Operations dark shell tokens without depending on a UI framework."""

    return f"""
<style>
/* marimo colours every widget through light-dark() switches keyed on these
   properties and defaults to its light theme; pin its dark palette so the Operations
   background never sits behind light-theme surfaces or text. */
:root:root, .marimo {{
  --csstools-color-scheme--light: ;
  --lightningcss-light: ;
  --lightningcss-dark: initial;
  --background: {OPERATIONS_MAIN_BACKGROUND};
  color-scheme: dark;
}}
/* Markdown prose switches to its inverted palette only under a .dark class. */
.markdown.prose {{
  --tw-prose-body: #f2f1ef;
  --tw-prose-headings: #f2f1ef;
  --tw-prose-lead: #aaa7a2;
  --tw-prose-links: #8caac5;
  --tw-prose-bold: #f2f1ef;
  --tw-prose-counters: #aaa7a2;
  --tw-prose-bullets: #aaa7a2;
  --tw-prose-hr: rgba(255,255,255,.08);
  --tw-prose-quotes: #f2f1ef;
  --tw-prose-quote-borders: rgba(255,255,255,.08);
  --tw-prose-captions: #aaa7a2;
  --tw-prose-code: #f2f1ef;
  --tw-prose-th-borders: rgba(255,255,255,.14);
  --tw-prose-td-borders: rgba(255,255,255,.08);
}}
.markdown.prose tr {{
  background: transparent !important;
}}
:root {{
  color-scheme: dark;
  --phm-bg: {OPERATIONS_MAIN_BACKGROUND};
  --phm-surface: #323130;
  --phm-surface-raised: #373634;
  --phm-border: rgba(255,255,255,.08);
  --phm-text: #f2f1ef;
  --phm-muted: #aaa7a2;
  --phm-running: #8fbf9a;
  --phm-attention: #d5aa62;
  --phm-error: #d87878;
  --phm-info: #8caac5;
}}
body, #root, .marimo {{
  background: var(--phm-bg) !important;
  color: var(--phm-text) !important;
}}
.phm-shell {{
  background: var(--phm-bg);
  color: var(--phm-text);
}}
.phm-section-title {{
  margin: 0 0 .8rem 0;
  font-size: .78rem;
  font-weight: 700;
  letter-spacing: .09em;
  text-transform: uppercase;
  color: var(--phm-muted);
}}
.phm-flow {{
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: .7rem;
}}
.phm-card {{
  background: var(--phm-surface);
  border: 1px solid var(--phm-border);
  border-radius: 10px;
  padding: 1rem;
  min-height: 108px;
}}
.phm-card-title {{
  color: var(--phm-muted);
  font-size: .78rem;
  margin-bottom: .55rem;
}}
.phm-card-status {{
  font-size: 1.05rem;
  font-weight: 650;
  margin-bottom: .35rem;
}}
.phm-card-detail {{
  color: var(--phm-muted);
  font-size: .82rem;
  line-height: 1.35;
}}
.phm-status-running {{ color: var(--phm-running); }}
.phm-status-needs-attention,
.phm-status-delayed {{ color: var(--phm-attention); }}
.phm-status-error {{ color: var(--phm-error); }}
.phm-status-unavailable,
.phm-status-stopped,
.phm-status-waiting {{ color: var(--phm-muted); }}
.phm-table {{
  width: 100%;
  border-collapse: collapse;
  background: var(--phm-surface);
  border: 1px solid var(--phm-border);
  border-radius: 10px;
  overflow: hidden;
}}
.phm-table th, .phm-table td {{
  padding: .72rem .85rem;
  text-align: left;
  border-bottom: 1px solid var(--phm-border);
  font-size: .84rem;
}}
.phm-table th {{
  color: var(--phm-muted);
  font-size: .73rem;
  text-transform: uppercase;
  letter-spacing: .06em;
}}
.phm-table tr:last-child td {{ border-bottom: none; }}
.phm-monitor-context {{
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 1.5rem;
  padding: .25rem 0 1rem 0;
  border-bottom: 1px solid var(--phm-border);
}}
.phm-monitor-eyebrow {{
  color: var(--phm-muted);
  font-size: .72rem;
  font-weight: 700;
  letter-spacing: .09em;
  text-transform: uppercase;
  margin-bottom: .35rem;
}}
.phm-monitor-title {{
  margin: 0;
  color: var(--phm-text);
  font-size: 1.55rem;
  font-weight: 700;
  line-height: 1.15;
}}
.phm-monitor-id {{
  margin-top: .32rem;
  color: var(--phm-muted);
  font-size: .78rem;
}}
.phm-monitor-facts {{
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: .65rem 1.1rem;
}}
.phm-monitor-fact {{
  min-width: 92px;
}}
.phm-monitor-fact-label {{
  color: var(--phm-muted);
  font-size: .7rem;
  text-transform: uppercase;
  letter-spacing: .06em;
}}
.phm-monitor-fact-value {{
  margin-top: .2rem;
  color: var(--phm-text);
  font-size: .9rem;
  font-weight: 600;
}}
@media (max-width: 980px) {{
  .phm-flow {{ grid-template-columns: 1fr 1fr; }}
  .phm-monitor-context {{
    align-items: start;
    flex-direction: column;
  }}
  .phm-monitor-facts {{ justify-content: flex-start; }}
}}
</style>
"""


def render_monitor_asset_context_html(
    view: AssetWorkspaceView,
    asset_names: AssetDisplayNames | None = None,
    *,
    as_of: datetime,
) -> str:
    """Render selected-asset observation context without inventing asset condition."""

    if not isinstance(view, AssetWorkspaceView):
        raise ValueError("view must be an AssetWorkspaceView")
    if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
        raise ValueError("as_of must be a timezone-aware datetime")

    name = None if asset_names is None else asset_names.name(view.asset_id)
    title = view.asset_id if name is None else name
    asset_id = "" if name is None else (
        f'<div class="phm-monitor-id">{escape(view.asset_id)}</div>'
    )
    data_state = data_status_label(view.status)
    last_observation = _relative_hint(view.last_data_at, as_of=as_of)
    signal_count = len(view.history_channels)
    signal_label = "signal" if signal_count == 1 else "signals"
    attention = f"{view.attention_count} attention"
    reviews = f"{view.open_review_count} open reviews"

    return (
        '<section class="phm-shell phm-monitor-context">'
        "<div>"
        '<div class="phm-monitor-eyebrow">Observed asset</div>'
        f'<h2 class="phm-monitor-title">{escape(title)}</h2>'
        f"{asset_id}"
        "</div>"
        '<div class="phm-monitor-facts">'
        + _monitor_fact(
            "Data",
            data_state,
            css_class=f"phm-status-{view.status.value}",
        )
        + _monitor_fact("Last observation", last_observation)
        + _monitor_fact("Signals", f"{signal_count} {signal_label}")
        + _monitor_fact("Attention", attention)
        + _monitor_fact("Reviews", reviews)
        + "</div></section>"
    )


def _monitor_fact(label: str, value: str, *, css_class: str | None = None) -> str:
    value_class = "phm-monitor-fact-value"
    if css_class is not None:
        value_class += f" {escape(css_class)}"
    return (
        '<div class="phm-monitor-fact">'
        f'<div class="phm-monitor-fact-label">{escape(label)}</div>'
        f'<div class="{value_class}">{escape(value)}</div>'
        "</div>"
    )


def render_monitor_flow_html(view: OperationsMonitorView) -> str:
    if not isinstance(view, OperationsMonitorView):
        raise ValueError("view must be an OperationsMonitorView")
    cards = "".join(_render_stage(stage) for stage in view.stages)
    return (
        '<section class="phm-shell">'
        '<div class="phm-section-title">System data flow</div>'
        f'<div class="phm-flow">{cards}</div>'
        "</section>"
    )


def render_asset_title_html(asset_id: str, names: AssetDisplayNames | None = None) -> str:
    """Display name as the title, the stable asset ID kept underneath for traceability."""
    name = None if names is None else names.name(asset_id)
    if name is None:
        return f'<h2 class="phm-asset-title">{escape(asset_id)}</h2>'
    return (
        f'<h2 class="phm-asset-title">{escape(name)}</h2>'
        f'<div class="phm-asset-id">{escape(asset_id)}</div>'
    )


def render_monitor_assets_html(
    view: OperationsMonitorView,
    asset_names: AssetDisplayNames | None = None,
) -> str:
    if not isinstance(view, OperationsMonitorView):
        raise ValueError("view must be an OperationsMonitorView")
    rows = "".join(
        _render_asset(asset, as_of=view.assessed_at, names=asset_names) for asset in view.assets
    )
    if not rows:
        rows = (
            '<tr><td colspan="6" class="phm-card-detail">'
            "No asset is available yet. Add a data source in Setup."
            "</td></tr>"
        )
    return (
        '<section class="phm-shell">'
        '<div class="phm-section-title">Assets</div>'
        '<table class="phm-table">'
        "<thead><tr>"
        "<th>Asset</th><th>Data status</th><th>Last data</th>"
        "<th>Last analysis</th><th>Reviews</th><th>Attention</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def status_label(status: OperationsMonitorStatus) -> str:
    if not isinstance(status, OperationsMonitorStatus):
        raise ValueError("status must be an OperationsMonitorStatus")
    return _STATUS_LABEL[status]


def data_status_label(status: OperationsMonitorStatus) -> str:
    """Label source/asset data-flow state without implying asset condition."""
    if not isinstance(status, OperationsMonitorStatus):
        raise ValueError("status must be an OperationsMonitorStatus")
    return _DATA_STATUS_LABEL[status]


def _render_stage(stage: OperationsMonitorStage) -> str:
    status = escape(status_label(stage.status))
    return (
        '<div class="phm-card">'
        f'<div class="phm-card-title">{escape(stage.title)}</div>'
        f'<div class="phm-card-status phm-status-{stage.status.value}">{status}</div>'
        f'<div class="phm-card-detail">{escape(stage.summary)}</div>'
        "</div>"
    )


def _render_asset(
    asset: OperationsMonitorAsset,
    *,
    as_of: datetime,
    names: AssetDisplayNames | None,
) -> str:
    name = None if names is None else names.name(asset.asset_id)
    asset_cell = (
        f"<strong>{escape(asset.asset_id)}</strong>"
        if name is None
        else f'<strong>{escape(name)}</strong><div class="phm-asset-id">'
        f"{escape(asset.asset_id)}</div>"
    )
    return (
        "<tr>"
        f"<td>{asset_cell}</td>"
        f'<td class="phm-status-{asset.status.value}">'
        f"{escape(data_status_label(asset.status))}</td>"
        f"<td>{escape(_relative_hint(asset.last_data_at, as_of=as_of))}</td>"
        f"<td>{escape(_relative_hint(asset.latest_analysis_at, as_of=as_of))}</td>"
        f"<td>{asset.pending_review_count}</td>"
        f"<td>{asset.attention_count}</td>"
        "</tr>"
    )


def _relative_hint(value: datetime | None, *, as_of: datetime) -> str:
    if value is None:
        return "—"
    if value.utcoffset() is None or as_of.utcoffset() is None:
        return "Time not comparable"
    age = (as_of - value).total_seconds()
    if age < -1:
        relative = f"{abs(age):.0f}s in future"
    elif age < 1:
        relative = "now"
    elif age < 60:
        relative = f"{age:.0f}s ago"
    elif age < 3600:
        relative = f"{age / 60:.1f}m ago"
    elif age < 86400:
        relative = f"{age / 3600:.1f}h ago"
    else:
        relative = f"{age / 86400:.1f}d ago"
    exact = value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    return f"{relative} · {exact}"
