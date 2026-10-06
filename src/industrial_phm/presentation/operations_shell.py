"""Framework-neutral HTML presenters for the Operations shell."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from html import escape

from industrial_phm.application.asset_display import AssetDisplayNames
from industrial_phm.application.operations_assets import AssetWorkspaceView
from industrial_phm.application.operations_monitor import (
    OperationsAttentionDestination,
    OperationsMonitorAsset,
    OperationsMonitorAttention,
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
.phm-signal-board {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  border-top: 1px solid var(--phm-border);
  border-left: 1px solid var(--phm-border);
}}
.phm-signal-row {{
  min-width: 0;
  padding: .78rem .9rem;
  border-right: 1px solid var(--phm-border);
  border-bottom: 1px solid var(--phm-border);
  background: rgba(255,255,255,.012);
}}
.phm-signal-row-selected {{
  box-shadow: inset 3px 0 0 var(--phm-info);
  background: rgba(140,170,197,.06);
}}
.phm-signal-row-issue {{
  box-shadow: inset 3px 0 0 var(--phm-attention);
}}
.phm-signal-head {{
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: .75rem;
}}
.phm-signal-name {{
  min-width: 0;
  font-size: .86rem;
  font-weight: 650;
  overflow-wrap: anywhere;
}}
.phm-signal-channel {{
  margin-top: .18rem;
  color: var(--phm-muted);
  font-size: .7rem;
  overflow-wrap: anywhere;
}}
.phm-signal-value {{
  white-space: nowrap;
  font-size: 1.05rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}}
.phm-signal-meta {{
  display: flex;
  flex-wrap: wrap;
  gap: .3rem .8rem;
  margin-top: .55rem;
  color: var(--phm-muted);
  font-size: .73rem;
}}
.phm-signal-meta-issue {{
  color: var(--phm-attention);
}}
.phm-signal-more {{
  margin-top: .65rem;
  color: var(--phm-muted);
}}
.phm-signal-more summary {{
  cursor: pointer;
  font-size: .78rem;
  user-select: none;
  margin-bottom: .65rem;
}}
.phm-attention-summary {{
  border-left: 1px solid var(--phm-border);
  padding-left: .85rem;
}}
.phm-attention-summary-head {{
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: .75rem;
}}
.phm-attention-summary-title {{
  font-size: .82rem;
  font-weight: 700;
  color: var(--phm-text);
}}
.phm-attention-summary-total {{
  color: var(--phm-attention);
  font-size: 1.05rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}}
.phm-attention-summary-grid {{
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: .45rem;
  margin-top: .6rem;
}}
.phm-attention-summary-cell {{
  border-top: 1px solid var(--phm-border);
  padding-top: .4rem;
}}
.phm-attention-summary-label {{
  color: var(--phm-muted);
  font-size: .66rem;
  text-transform: uppercase;
  letter-spacing: .05em;
}}
.phm-attention-summary-value {{
  margin-top: .12rem;
  font-size: .88rem;
  font-weight: 650;
  font-variant-numeric: tabular-nums;
}}
.phm-attention-summary-note {{
  margin-top: .6rem;
  color: var(--phm-muted);
  font-size: .7rem;
  line-height: 1.35;
}}
@media (max-width: 980px) {{
  .phm-flow {{ grid-template-columns: 1fr 1fr; }}
  .phm-monitor-context {{
    align-items: start;
    flex-direction: column;
  }}
  .phm-monitor-facts {{ justify-content: flex-start; }}
  .phm-signal-board {{ grid-template-columns: 1fr; }}
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
    asset_id = (
        "" if name is None else (f'<div class="phm-monitor-id">{escape(view.asset_id)}</div>')
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
        + _monitor_fact("Stored signals", f"{signal_count} {signal_label}")
        + _monitor_fact("Attention", attention)
        + _monitor_fact("Reviews", reviews)
        + "</div></section>"
    )


def monitor_context_attention(
    attention: Sequence[OperationsMonitorAttention],
    *,
    asset_id: str,
) -> tuple[OperationsMonitorAttention, ...]:
    """Keep selected-asset attention plus global System issues in Monitor context."""

    if not isinstance(asset_id, str) or not asset_id.strip() or asset_id != asset_id.strip():
        raise ValueError("asset_id must be a non-empty trimmed string")
    values = tuple(attention)
    if any(not isinstance(item, OperationsMonitorAttention) for item in values):
        raise ValueError("attention must contain OperationsMonitorAttention values")
    return tuple(
        item
        for item in values
        if item.asset_id == asset_id
        or (item.asset_id is None and item.destination == OperationsAttentionDestination.SYSTEM)
    )


def monitor_attention_category(attention: OperationsMonitorAttention) -> str:
    """Operator-facing factual category, not severity or alarm priority."""

    if not isinstance(attention, OperationsMonitorAttention):
        raise ValueError("attention must be an OperationsMonitorAttention")
    return {
        OperationsAttentionDestination.ASSET_SIGNALS: "Data",
        OperationsAttentionDestination.INVESTIGATIONS: "Review",
        OperationsAttentionDestination.SYSTEM: "System",
    }[attention.destination]


def render_monitor_attention_summary_html(
    attention: Sequence[OperationsMonitorAttention],
) -> str:
    """Render contextual attention counts without implying severity or asset health."""

    values = tuple(attention)
    if any(not isinstance(item, OperationsMonitorAttention) for item in values):
        raise ValueError("attention must contain OperationsMonitorAttention values")
    counts = {
        category: sum(monitor_attention_category(item) == category for item in values)
        for category in ("Data", "Review", "System")
    }
    return (
        '<section class="phm-shell phm-attention-summary">'
        '<div class="phm-attention-summary-head">'
        '<div class="phm-attention-summary-title">Attention</div>'
        f'<div class="phm-attention-summary-total">{len(values)}</div>'
        "</div>"
        '<div class="phm-attention-summary-grid">'
        + "".join(
            '<div class="phm-attention-summary-cell">'
            f'<div class="phm-attention-summary-label">{escape(category)}</div>'
            f'<div class="phm-attention-summary-value">{count}</div>'
            "</div>"
            for category, count in counts.items()
        )
        + "</div>"
        '<div class="phm-attention-summary-note">'
        "Current evidence requiring inspection. Counts are not alarm severity "
        "or asset-health scores."
        "</div></section>"
    )


def monitor_signal_channels(
    rows: Sequence[Mapping[str, object]],
    *,
    selected_channel: str | None = None,
    limit: int = 6,
) -> tuple[str, ...]:
    """Choose a bounded signal set using the same attention order as the overview."""

    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 8:
        raise ValueError("limit must be an integer from 1 to 8")
    ordered = _ordered_monitor_signal_rows(rows, selected_channel=selected_channel)
    result: list[str] = []
    for row in ordered:
        channel = _monitor_row_text(row, "channel")
        if channel and channel not in result:
            result.append(channel)
        if len(result) == limit:
            break
    return tuple(result)


def render_monitor_signal_overview_html(
    rows: Sequence[Mapping[str, object]],
    *,
    selected_channel: str | None = None,
    primary_limit: int = 8,
) -> str:
    """Render factual latest observations across one asset without collapsing identities."""

    if isinstance(primary_limit, bool) or not isinstance(primary_limit, int) or primary_limit < 1:
        raise ValueError("primary_limit must be a positive integer")
    if primary_limit > 24:
        raise ValueError("primary_limit must not exceed 24")
    if selected_channel is not None and (
        not isinstance(selected_channel, str) or not selected_channel.strip()
    ):
        raise ValueError("selected_channel must be non-empty when provided")

    ordered = _ordered_monitor_signal_rows(rows, selected_channel=selected_channel)
    if not ordered:
        return (
            '<section class="phm-shell">'
            '<div class="phm-section-title">Latest stored observations</div>'
            '<div class="phm-card-detail">No stored observation is available yet.</div>'
            "</section>"
        )

    primary = ordered[:primary_limit]
    remainder = ordered[primary_limit:]
    body = _render_monitor_signal_board(primary, selected_channel=selected_channel)
    if remainder:
        body += (
            '<details class="phm-signal-more">'
            f"<summary>Show {len(remainder)} more stored observations</summary>"
            + _render_monitor_signal_board(remainder, selected_channel=selected_channel)
            + "</details>"
        )
    return (
        '<section class="phm-shell">'
        '<div class="phm-section-title">Latest stored observations</div>' + body + "</section>"
    )


def _ordered_monitor_signal_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    selected_channel: str | None,
) -> tuple[Mapping[str, object], ...]:
    return tuple(
        sorted(
            tuple(rows),
            key=lambda row: (
                _monitor_row_text(row, "channel") != selected_channel
                if selected_channel is not None
                else False,
                not _monitor_row_has_issue(row),
                _monitor_row_text(row, "channel"),
                _monitor_row_text(row, "source"),
                _monitor_row_text(row, "measurement_point"),
            ),
        )
    )


def _monitor_row_has_issue(row: Mapping[str, object]) -> bool:
    quality = _monitor_row_text(row, "quality")
    event_state = _monitor_row_text(row, "event_time_state")
    return quality != "no recorded issue" or event_state not in {"", "recorded"}


def _render_monitor_signal_board(
    rows: Sequence[Mapping[str, object]],
    *,
    selected_channel: str | None,
) -> str:
    return (
        '<div class="phm-signal-board">'
        + "".join(
            _render_monitor_signal_row(row, selected_channel=selected_channel) for row in rows
        )
        + "</div>"
    )


def _render_monitor_signal_row(
    row: Mapping[str, object],
    *,
    selected_channel: str | None,
) -> str:
    channel = _monitor_row_text(row, "channel", fallback="unknown-signal")
    observed_property = _monitor_row_text(row, "observed_property")
    scope = _monitor_row_text(row, "scope")
    label = channel if observed_property in {"", "unresolved"} else observed_property
    if scope:
        label = f"{label} · {scope}"

    value = _monitor_value(row.get("value"))
    unit = _monitor_row_text(row, "unit")
    if unit in {"", "unknown"}:
        unit = ""
    value_text = value if not unit else f"{value} {unit}"

    quality = _monitor_row_text(row, "quality", fallback="unknown")
    age = _monitor_age(row.get("history_age_seconds"))
    source = _monitor_row_text(row, "source")
    measurement_point = _monitor_row_text(row, "measurement_point")
    source_point = source
    if measurement_point:
        source_point += f" / {measurement_point}"

    classes = ["phm-signal-row"]
    if selected_channel == channel:
        classes.append("phm-signal-row-selected")
    issue = _monitor_row_has_issue(row)
    if issue:
        classes.append("phm-signal-row-issue")
    quality_class = "phm-signal-meta-issue" if issue else ""

    return (
        f'<div class="{" ".join(classes)}">'
        '<div class="phm-signal-head">'
        "<div>"
        f'<div class="phm-signal-name">{escape(label)}</div>'
        f'<div class="phm-signal-channel">{escape(channel)}</div>'
        "</div>"
        f'<div class="phm-signal-value">{escape(value_text)}</div>'
        "</div>"
        '<div class="phm-signal-meta">'
        f'<span class="{quality_class}">{escape(quality)}</span>'
        f"<span>{escape(age)}</span>"
        f"<span>{escape(source_point)}</span>"
        "</div></div>"
    )


def _monitor_row_text(
    row: Mapping[str, object],
    key: str,
    *,
    fallback: str = "",
) -> str:
    value = row.get(key)
    if value is None:
        return fallback
    return str(value)


def _monitor_value(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{float(value):.6g}"
    return str(value)


def _monitor_age(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "time unavailable"
    seconds = float(value)
    if seconds < 0:
        return f"{abs(seconds):.0f}s in future"
    if seconds < 60:
        return f"{seconds:.0f}s ago"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m ago"
    if seconds < 86400:
        return f"{seconds / 3600:.1f}h ago"
    return f"{seconds / 86400:.1f}d ago"


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
