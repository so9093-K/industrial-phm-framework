"""Framework-neutral HTML presenters for the Operations V2 shell."""

from __future__ import annotations

from datetime import datetime
from html import escape

from industrial_phm.application.operations_v2 import (
    OperationsMonitorAsset,
    OperationsMonitorStage,
    OperationsMonitorStatus,
    OperationsMonitorView,
)

OPERATIONS_V2_MAIN_BACKGROUND = "#292827"


_STATUS_LABEL = {
    OperationsMonitorStatus.RUNNING: "Running",
    OperationsMonitorStatus.WAITING: "Waiting",
    OperationsMonitorStatus.DELAYED: "Delayed",
    OperationsMonitorStatus.STOPPED: "Stopped",
    OperationsMonitorStatus.NEEDS_ATTENTION: "Needs attention",
    OperationsMonitorStatus.ERROR: "Error",
    OperationsMonitorStatus.UNAVAILABLE: "Unavailable",
}


def operations_v2_theme_css() -> str:
    """Return the V2 dark shell tokens without depending on a UI framework."""

    return f"""
<style>
:root {{
  color-scheme: dark;
  --phm-bg: {OPERATIONS_V2_MAIN_BACKGROUND};
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
@media (max-width: 980px) {{
  .phm-flow {{ grid-template-columns: 1fr 1fr; }}
}}
</style>
"""


def render_monitor_flow_html(view: OperationsMonitorView) -> str:
    if not isinstance(view, OperationsMonitorView):
        raise ValueError("view must be an OperationsMonitorView")
    cards = "".join(_render_stage(stage) for stage in view.stages)
    return (
        '<section class="phm-shell">'
        '<div class="phm-section-title">Data flow</div>'
        f'<div class="phm-flow">{cards}</div>'
        "</section>"
    )


def render_monitor_assets_html(view: OperationsMonitorView) -> str:
    if not isinstance(view, OperationsMonitorView):
        raise ValueError("view must be an OperationsMonitorView")
    rows = "".join(_render_asset(asset) for asset in view.assets)
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
        "<th>Asset</th><th>Status</th><th>Last data</th>"
        "<th>Last analysis</th><th>Reviews</th><th>Attention</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def status_label(status: OperationsMonitorStatus) -> str:
    if not isinstance(status, OperationsMonitorStatus):
        raise ValueError("status must be an OperationsMonitorStatus")
    return _STATUS_LABEL[status]


def _render_stage(stage: OperationsMonitorStage) -> str:
    status = escape(status_label(stage.status))
    return (
        '<div class="phm-card">'
        f'<div class="phm-card-title">{escape(stage.title)}</div>'
        f'<div class="phm-card-status phm-status-{stage.status.value}">{status}</div>'
        f'<div class="phm-card-detail">{escape(stage.summary)}</div>'
        "</div>"
    )


def _render_asset(asset: OperationsMonitorAsset) -> str:
    return (
        "<tr>"
        f"<td><strong>{escape(asset.asset_id)}</strong></td>"
        f'<td class="phm-status-{asset.status.value}">{escape(status_label(asset.status))}</td>'
        f"<td>{escape(_relative_hint(asset.last_data_at))}</td>"
        f"<td>{escape(_relative_hint(asset.latest_analysis_at))}</td>"
        f"<td>{asset.pending_review_count}</td>"
        f"<td>{asset.attention_count}</td>"
        "</tr>"
    )


def _relative_hint(value: datetime | None) -> str:
    # The app owns a live clock; the pure presenter only preserves an absolute timestamp.
    return "—" if value is None else value.isoformat()
