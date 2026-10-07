"""Presentation helpers for the Operations Investigation workspace."""

from __future__ import annotations

from html import escape

from industrial_phm.application.asset_display import AssetDisplayNames
from industrial_phm.application.operations_investigations import (
    InvestigationQueueGroup,
    InvestigationQueueItem,
    InvestigationReviewState,
)
from industrial_phm.presentation.operations_locale import (
    DEFAULT_OPERATIONS_LOCALE,
    OperationsLocale,
    format_operations_utc,
    operations_capability_label,
    operations_text,
)
from industrial_phm.presentation.operations_shell import render_asset_title_html


def investigation_capability_label(
    capability_id: str,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    return operations_capability_label(capability_id, locale)


def investigation_review_label(
    state: InvestigationReviewState,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(state, InvestigationReviewState):
        raise ValueError("state must be an InvestigationReviewState")
    key = {
        InvestigationReviewState.NOT_REQUESTED: "common.not_requested",
        InvestigationReviewState.OPEN: "common.open",
        InvestigationReviewState.ACKNOWLEDGED: "common.acknowledged",
        InvestigationReviewState.CLOSED: "common.closed",
    }[state]
    return operations_text(key, locale)


def investigation_group_option_label(
    group: InvestigationQueueGroup,
    asset_names: AssetDisplayNames | None = None,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(group, InvestigationQueueGroup):
        raise ValueError("group must be an InvestigationQueueGroup")
    asset = group.asset_id if asset_names is None else asset_names.label(group.asset_id)
    capability = investigation_capability_label(group.capability_id, locale)
    review = investigation_review_label(group.review_state, locale)
    completed = format_operations_utc(group.latest.completed_at, locale)
    return f"{asset} · {capability} · {review} · {group.run_count} run(s) · latest {completed}"


def investigation_queue_option_label(
    item: InvestigationQueueItem,
    asset_names: AssetDisplayNames | None = None,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(item, InvestigationQueueItem):
        raise ValueError("item must be an InvestigationQueueItem")
    completed = format_operations_utc(item.completed_at, locale)
    asset = item.asset_id if asset_names is None else asset_names.label(item.asset_id)
    capability = investigation_capability_label(item.capability_id, locale)
    review = investigation_review_label(item.review_state, locale)
    return f"{asset} · {capability} · {review} · {completed}"


def render_investigation_summary_html(
    item: InvestigationQueueItem,
    asset_names: AssetDisplayNames | None = None,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(item, InvestigationQueueItem):
        raise ValueError("item must be an InvestigationQueueItem")
    kicker = escape(operations_text("investigation.title", locale))
    capability = escape(investigation_capability_label(item.capability_id, locale))
    observed = escape(operations_text("common.observed", locale))
    point = escape(operations_text("common.point", locale))
    return (
        '<section class="phm-shell">'
        '<div class="phm-investigation-heading">'
        "<div>"
        f'<div class="phm-asset-kicker">{kicker}</div>'
        + render_asset_title_html(item.asset_id, asset_names)
        + f'<div class="phm-card-detail">{capability}</div>'
        "</div>"
        '<div class="phm-investigation-facts">'
        + _fact(
            operations_text("common.review", locale),
            investigation_review_label(item.review_state, locale),
        )
        + _fact(
            operations_text("common.completed", locale),
            format_operations_utc(item.completed_at, locale),
        )
        + _fact(operations_text("common.source", locale), item.source_id)
        + _fact(operations_text("common.data_quality", locale), item.data_quality.upper())
        + "</div>"
        "</div>"
        '<div class="phm-investigation-scope">'
        f"<strong>{observed}</strong> "
        f"{format_operations_utc(item.observed_start_at, locale)} → "
        f"{format_operations_utc(item.observed_end_at, locale)}"
        f" &nbsp; <strong>{point}</strong> {escape(item.measurement_point_id or '—')}"
        "</div>"
        "</section>"
    )


def render_investigation_evidence_identity_html(
    item: InvestigationQueueItem,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(item, InvestigationQueueItem):
        raise ValueError("item must be an InvestigationQueueItem")
    rows = (
        (operations_text("common.analysis_run", locale), item.analysis_run_id),
        (operations_text("common.capability", locale), item.capability_id),
        (operations_text("common.evidence", locale), item.evidence_id),
        (operations_text("common.source", locale), item.source_id),
        (
            operations_text("common.finding", locale),
            item.finding_id or operations_text("common.not_requested", locale),
        ),
        (
            operations_text("common.review_updated", locale),
            format_operations_utc(item.review_updated_at, locale),
        ),
    )
    rendered = "".join(
        f"<tr><td>{escape(label)}</td><td>{escape(value)}</td></tr>"
        for label, value in rows
    )
    title = escape(operations_text("investigation.evidence_identity", locale))
    return (
        '<section class="phm-shell">'
        f'<div class="phm-section-title">{title}</div>'
        '<table class="phm-table">'
        f"<tbody>{rendered}</tbody>"
        "</table>"
        "</section>"
    )


def investigation_workspace_css() -> str:
    return """
<style>
.phm-investigation-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1.4rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid var(--phm-border);
}
.phm-investigation-facts {
  display: grid;
  grid-template-columns: repeat(4, minmax(100px, auto));
  gap: 1rem;
}
.phm-investigation-scope {
  margin-top: .85rem;
  color: var(--phm-muted);
  font-size: .82rem;
}
.phm-investigation-heading,
.phm-investigation-scope,
.phm-shell {
  min-width: 0;
  max-width: 100%;
}
.phm-shell svg {
  display: block;
  max-width: 100%;
  height: auto;
  background: transparent !important;
}
.phm-shell table {
  max-width: 100%;
}
@media (max-width: 1100px) {
  .phm-investigation-heading {
    align-items: flex-start;
    flex-direction: column;
  }
  .phm-investigation-facts {
    grid-template-columns: 1fr 1fr;
    width: 100%;
  }
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
