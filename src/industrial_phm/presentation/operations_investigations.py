"""Presentation helpers for the Operations Investigation workspace."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape

from industrial_phm.application.operations_investigations import (
    InvestigationQueueGroup,
    InvestigationQueueItem,
    InvestigationReviewState,
)


def investigation_capability_label(capability_id: str) -> str:
    return {
        "three-phase-unbalance-v1": "Three-phase unbalance",
        "field-vibration-statistical-features-v1": "Vibration features",
    }.get(capability_id, capability_id)


def investigation_review_label(state: InvestigationReviewState) -> str:
    if not isinstance(state, InvestigationReviewState):
        raise ValueError("state must be an InvestigationReviewState")
    return {
        InvestigationReviewState.NOT_REQUESTED: "Not requested",
        InvestigationReviewState.OPEN: "Open",
        InvestigationReviewState.ACKNOWLEDGED: "Acknowledged",
        InvestigationReviewState.CLOSED: "Closed",
    }[state]


def investigation_group_option_label(group: InvestigationQueueGroup) -> str:
    if not isinstance(group, InvestigationQueueGroup):
        raise ValueError("group must be an InvestigationQueueGroup")
    return (
        f"{group.asset_id} · {investigation_capability_label(group.capability_id)} · "
        f"{investigation_review_label(group.review_state)} · {group.run_count} run(s) · "
        f"latest {_time_label(group.latest.completed_at)}"
    )


def investigation_queue_option_label(item: InvestigationQueueItem) -> str:
    if not isinstance(item, InvestigationQueueItem):
        raise ValueError("item must be an InvestigationQueueItem")
    completed = item.completed_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    return (
        f"{item.asset_id} · {investigation_capability_label(item.capability_id)} · "
        f"{investigation_review_label(item.review_state)} · {completed}"
    )


def render_investigation_summary_html(item: InvestigationQueueItem) -> str:
    if not isinstance(item, InvestigationQueueItem):
        raise ValueError("item must be an InvestigationQueueItem")
    return (
        '<section class="phm-shell">'
        '<div class="phm-investigation-heading">'
        "<div>"
        '<div class="phm-asset-kicker">Investigation</div>'
        f'<h2 class="phm-asset-title">{escape(item.asset_id)}</h2>'
        f'<div class="phm-card-detail">'
        f"{escape(investigation_capability_label(item.capability_id))}"
        "</div>"
        "</div>"
        '<div class="phm-investigation-facts">'
        + _fact("Review", investigation_review_label(item.review_state))
        + _fact("Completed", _time_label(item.completed_at))
        + _fact("Source", item.source_id)
        + _fact("Data quality", item.data_quality.upper())
        + "</div>"
        "</div>"
        '<div class="phm-investigation-scope">'
        f"<strong>Observed</strong> {_time_label(item.observed_start_at)} → "
        f"{_time_label(item.observed_end_at)}"
        f" &nbsp; <strong>Point</strong> {escape(item.measurement_point_id or '—')}"
        "</div>"
        "</section>"
    )


def render_investigation_evidence_identity_html(
    item: InvestigationQueueItem,
) -> str:
    if not isinstance(item, InvestigationQueueItem):
        raise ValueError("item must be an InvestigationQueueItem")
    rows = (
        ("Analysis run", item.analysis_run_id),
        ("Capability", item.capability_id),
        ("Evidence", item.evidence_id),
        ("Source", item.source_id),
        ("Finding", item.finding_id or "Not requested"),
        ("Review updated", _time_label(item.review_updated_at)),
    )
    rendered = "".join(
        f"<tr><td>{escape(label)}</td><td>{escape(value)}</td></tr>" for label, value in rows
    )
    return (
        '<section class="phm-shell">'
        '<div class="phm-section-title">Evidence identity</div>'
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
.phm-queue-help {
  color: var(--phm-muted);
  font-size: .78rem;
  line-height: 1.45;
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


def _time_label(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.utcoffset() is None:
        return "Time not comparable"
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
