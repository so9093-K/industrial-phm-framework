"""Presentation helpers for the Operations V2 Setup workspace."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape

from industrial_phm.application.operations_v2_setup import (
    SetupSourceView,
    SetupWorkspaceView,
)
from industrial_phm.application.source_lifecycle import SourceLifecycleState
from industrial_phm.application.source_registration import SourceType


def render_setup_sources_html(view: SetupWorkspaceView) -> str:
    if not isinstance(view, SetupWorkspaceView):
        raise ValueError("view must be a SetupWorkspaceView")
    rows = "".join(_source_row(item) for item in view.sources)
    if not rows:
        rows = (
            '<tr><td colspan="7" class="phm-card-detail">'
            "No data source is configured yet."
            "</td></tr>"
        )
    return (
        '<section class="phm-shell">'
        '<div class="phm-section-title">Data sources</div>'
        '<table class="phm-table">'
        "<thead><tr><th>Source</th><th>Type</th><th>Asset</th><th>Point</th>"
        "<th>Use</th><th>Collection</th><th>Meaning</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def render_setup_source_detail_html(source: SetupSourceView) -> str:
    if not isinstance(source, SetupSourceView):
        raise ValueError("source must be a SetupSourceView")
    defined, total = source.semantic_coverage
    return (
        '<section class="phm-shell">'
        '<div class="phm-asset-header">'
        "<div>"
        '<div class="phm-asset-kicker">Data source</div>'
        f'<h2 class="phm-asset-title">{escape(source.name)}</h2>'
        f'<div class="phm-card-detail">{escape(source.source_id)}</div>'
        "</div>"
        '<div class="phm-asset-facts">'
        + _fact("Type", _source_type_label(source.source_type))
        + _fact("Use", _lifecycle_label(source.lifecycle_state))
        + _fact("Asset", source.asset_id)
        + _fact("Point", source.measurement_point_id or "—")
        + _fact("Meaning", f"{defined} / {total}")
        + "</div></div>"
        '<div class="phm-section-title phm-section-space">Connection target</div>'
        f'<div class="phm-card-detail">{escape(source.connection_target)}</div>'
        "</section>"
    )


def render_setup_signals_html(source: SetupSourceView) -> str:
    if not isinstance(source, SetupSourceView):
        raise ValueError("source must be a SetupSourceView")
    rows = "".join(
        (
            "<tr>"
            f"<td><strong>{escape(item.channel_id)}</strong></td>"
            f"<td>{escape(item.source_locator)}</td>"
            f"<td>{escape(item.observed_property or 'Unresolved')}</td>"
            f"<td>{escape(item.scope or '—')}</td>"
            f"<td>{escape(item.statistic or '—')}</td>"
            f"<td>{escape(item.unit or '—')}</td>"
            f"<td>{escape(item.semantic_version or '—')}</td>"
            "</tr>"
        )
        for item in source.signals
    )
    if not rows:
        rows = '<tr><td colspan="7" class="phm-card-detail">No signal mapping recorded.</td></tr>'
    return (
        '<section class="phm-shell">'
        '<div class="phm-section-title">Signal mapping & meaning</div>'
        '<table class="phm-table">'
        "<thead><tr><th>Signal</th><th>Source locator</th><th>Observed property</th>"
        "<th>Scope</th><th>Statistic</th><th>Unit</th><th>Version</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def setup_workspace_css() -> str:
    return """
<style>
.phm-setup-step {
  background: var(--phm-surface);
  border: 1px solid var(--phm-border);
  border-radius: 10px;
  padding: 1rem;
}
.phm-setup-step-title {
  font-size: .82rem;
  font-weight: 700;
  margin-bottom: .65rem;
}
.phm-setup-help {
  color: var(--phm-muted);
  font-size: .78rem;
  line-height: 1.45;
}
</style>
"""


def lifecycle_action_label(state: SourceLifecycleState) -> str:
    if not isinstance(state, SourceLifecycleState):
        raise ValueError("state must be a SourceLifecycleState")
    return {
        SourceLifecycleState.REGISTERED: "Not enabled",
        SourceLifecycleState.ACTIVE: "Enabled",
        SourceLifecycleState.PAUSED: "Paused",
        SourceLifecycleState.ERROR: "Needs attention",
    }[state]


def _source_row(source: SetupSourceView) -> str:
    defined, total = source.semantic_coverage
    collection = (
        "Not applicable"
        if source.source_type == SourceType.FILE
        else (
            "Not requested"
            if source.collection_desired_state is None
            else source.collection_desired_state.value.title()
        )
    )
    return (
        "<tr>"
        f"<td><strong>{escape(source.name)}</strong><br>"
        f'<span class="phm-card-detail">{escape(source.source_id)}</span></td>'
        f"<td>{escape(_source_type_label(source.source_type))}</td>"
        f"<td>{escape(source.asset_id)}</td>"
        f"<td>{escape(source.measurement_point_id or '—')}</td>"
        f"<td>{escape(_lifecycle_label(source.lifecycle_state))}</td>"
        f"<td>{escape(collection)}</td>"
        f"<td>{defined} / {total}</td>"
        "</tr>"
    )


def _fact(label: str, value: str) -> str:
    return (
        "<div>"
        f'<div class="phm-fact-label">{escape(label)}</div>'
        f'<div class="phm-fact-value">{escape(value)}</div>'
        "</div>"
    )


def _source_type_label(source_type: SourceType) -> str:
    return {
        SourceType.FILE: "File",
        SourceType.OPCUA: "OPC UA",
    }[source_type]


def _lifecycle_label(state: SourceLifecycleState) -> str:
    return lifecycle_action_label(state)


def _time_label(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.utcoffset() is None:
        return "Time not comparable"
    return value.astimezone(UTC).isoformat()
