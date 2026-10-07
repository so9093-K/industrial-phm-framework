"""Presentation helpers for the Operations Setup workspace."""

from __future__ import annotations

from html import escape

from industrial_phm.application.operations_setup import (
    SetupSourceView,
    SetupWorkspaceView,
)
from industrial_phm.application.source_lifecycle import SourceLifecycleState
from industrial_phm.application.source_registration import SourceType
from industrial_phm.presentation.operations_locale import (
    DEFAULT_OPERATIONS_LOCALE,
    OperationsLocale,
    operations_text,
)


def render_setup_sources_html(
    view: SetupWorkspaceView,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(view, SetupWorkspaceView):
        raise ValueError("view must be a SetupWorkspaceView")
    rows = "".join(_source_row(item, locale) for item in view.sources)
    if not rows:
        rows = (
            '<tr><td colspan="7" class="phm-card-detail">'
            operations_text("setup.no_sources", locale)
            "</td></tr>"
        )
    return (
        '<section class="phm-shell">'
        f'<div class="phm-section-title">{escape(operations_text("setup.data_sources", locale))}</div>'
        '<table class="phm-table">'
        "<thead><tr>"
        f"<th>{escape(operations_text('common.source', locale))}</th>"
        f"<th>{escape(operations_text('setup.type', locale))}</th>"
        f"<th>{escape(operations_text('setup.asset', locale))}</th>"
        f"<th>{escape(operations_text('setup.point', locale))}</th>"
        f"<th>{escape(operations_text('setup.use', locale))}</th>"
        f"<th>{escape(operations_text('setup.collection_request', locale))}</th>"
        f"<th>{escape(operations_text('setup.meaning', locale))}</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def render_setup_source_detail_html(
    source: SetupSourceView,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(source, SetupSourceView):
        raise ValueError("source must be a SetupSourceView")
    defined, total = source.semantic_coverage
    return (
        '<section class="phm-shell">'
        '<div class="phm-asset-header">'
        "<div>"
        f'<div class="phm-asset-kicker">{escape(operations_text("setup.data_source", locale))}</div>'
        f'<h2 class="phm-asset-title">{escape(source.name)}</h2>'
        f'<div class="phm-card-detail">{escape(source.source_id)}</div>'
        "</div>"
        '<div class="phm-asset-facts">'
        + _fact(operations_text("setup.type", locale), _source_type_label(source.source_type))
        + _fact(operations_text("setup.use", locale), _lifecycle_label(source.lifecycle_state, locale))
        + _fact(operations_text("setup.asset", locale), source.asset_id)
        + _fact(operations_text("setup.point", locale), source.measurement_point_id or "—")
        + _fact(operations_text("setup.meaning", locale), f"{defined} / {total}")
        + _fact(
            operations_text("setup.data_age_limit", locale),
            (
                operations_text("common.not_configured", locale)
                if source.freshness_max_age_seconds is None
                else f"{source.freshness_max_age_seconds:g} s"
            ),
        )
        + "</div></div>"
        f'<div class="phm-section-title phm-section-space">{escape(operations_text("setup.connection_target", locale))}</div>'
        f'<div class="phm-card-detail">{escape(source.connection_target)}</div>'
        "</section>"
    )


def render_setup_signals_html(
    source: SetupSourceView,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(source, SetupSourceView):
        raise ValueError("source must be a SetupSourceView")
    rows = "".join(
        (
            "<tr>"
            f"<td><strong>{escape(item.channel_id)}</strong></td>"
            f"<td>{escape(item.source_locator)}</td>"
            f"<td>{escape(item.observed_property or operations_text('common.unresolved', locale))}</td>"
            f"<td>{escape(item.scope or '—')}</td>"
            f"<td>{escape(item.statistic or '—')}</td>"
            f"<td>{escape(item.unit or '—')}</td>"
            f"<td>{escape(item.semantic_version or '—')}</td>"
            "</tr>"
        )
        for item in source.signals
    )
    if not rows:
        rows = (
            '<tr><td colspan="7" class="phm-card-detail">'
            + escape(operations_text("setup.no_signal_mapping", locale))
            + "</td></tr>"
        )
    return (
        '<section class="phm-shell">'
        f'<div class="phm-section-title">{escape(operations_text("setup.signal_mapping", locale))}</div>'
        '<table class="phm-table">'
        "<thead><tr>"
        f"<th>{escape(operations_text('setup.signal', locale))}</th>"
        f"<th>{escape(operations_text('setup.source_locator', locale))}</th>"
        f"<th>{escape(operations_text('setup.observed_property', locale))}</th>"
        f"<th>{escape(operations_text('setup.scope', locale))}</th>"
        f"<th>{escape(operations_text('setup.statistic', locale))}</th>"
        f"<th>{escape(operations_text('setup.unit', locale))}</th>"
        f"<th>{escape(operations_text('setup.version', locale))}</th>"
        "</tr></thead>"
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


def lifecycle_action_label(
    state: SourceLifecycleState,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(state, SourceLifecycleState):
        raise ValueError("state must be a SourceLifecycleState")
    key = {
        SourceLifecycleState.REGISTERED: "setup.not_enabled",
        SourceLifecycleState.ACTIVE: "setup.enabled",
        SourceLifecycleState.PAUSED: "setup.paused",
        SourceLifecycleState.ERROR: "setup.needs_attention",
    }[state]
    return operations_text(key, locale)


def _source_row(
    source: SetupSourceView,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    defined, total = source.semantic_coverage
    collection = (
        operations_text("setup.not_applicable", locale)
        if source.source_type == SourceType.FILE
        else (
            operations_text("common.not_requested", locale)
            if source.collection_desired_state is None
            else f"Requested: {source.collection_desired_state.value.title()}"
        )
    )
    return (
        "<tr>"
        f"<td><strong>{escape(source.name)}</strong><br>"
        f'<span class="phm-card-detail">{escape(source.source_id)}</span></td>'
        f"<td>{escape(_source_type_label(source.source_type))}</td>"
        f"<td>{escape(source.asset_id)}</td>"
        f"<td>{escape(source.measurement_point_id or '—')}</td>"
        f"<td>{escape(_lifecycle_label(source.lifecycle_state, locale))}</td>"
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


def _lifecycle_label(
    state: SourceLifecycleState,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    return lifecycle_action_label(state, locale)
