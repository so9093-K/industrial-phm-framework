"""Presentation helpers for Operations maintenance review workspace."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape

from industrial_phm.application.asset_display import AssetDisplayNames
from industrial_phm.application.maintenance_review import FindingReviewStatus
from industrial_phm.application.operations_investigations import InvestigationQueueItem
from industrial_phm.application.operations_maintenance import MaintenanceQueueItem
from industrial_phm.presentation.operations_locale import (
    DEFAULT_OPERATIONS_LOCALE,
    OperationsLocale,
    format_operations_utc,
    operations_capability_label,
    operations_text,
)
from industrial_phm.presentation.operations_shell import render_asset_title_html


def maintenance_status_label(
    status: FindingReviewStatus,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    key = {
        FindingReviewStatus.OPEN: "common.open",
        FindingReviewStatus.ACKNOWLEDGED: "common.acknowledged",
        FindingReviewStatus.CLOSED: "common.closed",
    }[status]
    return operations_text(key, locale)


def maintenance_capability_label(
    capability_id: str,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    return operations_capability_label(capability_id, locale)


def maintenance_queue_label(
    item: MaintenanceQueueItem,
    asset_names: AssetDisplayNames | None = None,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    asset = item.asset_id if asset_names is None else asset_names.label(item.asset_id)
    return (
        f"{asset} · {maintenance_capability_label(item.capability_id, locale)} · "
        f"{maintenance_status_label(item.status, locale)} · "
        f"{format_operations_utc(item.requested_at, locale)}"
    )


def render_maintenance_summary_html(
    item: MaintenanceQueueItem,
    asset_names: AssetDisplayNames | None = None,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    kicker = escape(operations_text("maintenance.title", locale))
    capability = escape(maintenance_capability_label(item.capability_id, locale))
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
            operations_text("common.status", locale),
            maintenance_status_label(item.status, locale),
        )
        + _fact(
            operations_text("maintenance.requested", locale),
            format_operations_utc(item.requested_at, locale),
        )
        + _fact(
            operations_text("maintenance.last_activity", locale),
            format_operations_utc(item.latest_activity_at, locale),
        )
        + _fact(operations_text("maintenance.notes", locale), str(item.note_count))
        + "</div>"
        "</div>"
        "</section>"
    )


def render_maintenance_evidence_html(
    evidence: InvestigationQueueItem | None,
    *,
    analysis_run_id: str,
    metrics: Sequence[Mapping[str, object]] = (),
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    """Show the analysis evidence referenced by one review workflow item."""

    title = escape(operations_text("maintenance.reviewed_evidence", locale))
    if evidence is None:
        return (
            '<section class="phm-shell">'
            f'<div class="phm-section-title">{title}</div>'
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
    observed = operations_text("common.observed", locale)
    return (
        '<section class="phm-shell">'
        f'<div class="phm-section-title">{title}</div>'
        '<div class="phm-investigation-facts">'
        + _fact(
            f"{observed} · from",
            format_operations_utc(evidence.observed_start_at, locale),
        )
        + _fact(
            f"{observed} · to",
            format_operations_utc(evidence.observed_end_at, locale),
        )
        + _fact(operations_text("common.source", locale), evidence.source_id)
        + _fact(operations_text("common.data_quality", locale), evidence.data_quality.upper())
        + "</div>"
        + metric_table
        + "</section>"
    )


def render_maintenance_timeline_html(
    item: MaintenanceQueueItem,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not item.timeline:
        body = _empty_row(
            3,
            operations_text("maintenance.no_review_activity", locale),
        )
    else:
        body = "".join(
            "<tr>"
            f"<td>{escape(format_operations_utc(event.recorded_at, locale))}</td>"
            f"<td>{escape(event.action.value.title())}</td>"
            f"<td>{escape(event.note or '—')}</td>"
            "</tr>"
            for event in item.timeline
        )
    title = escape(operations_text("maintenance.review_timeline", locale))
    return (
        '<section class="phm-shell">'
        f'<div class="phm-section-title">{title}</div>'
        '<table class="phm-table">'
        "<thead><tr><th>Time</th><th>Action</th><th>Note</th></tr></thead>"
        f"<tbody>{body}</tbody></table></section>"
    )


def render_maintenance_identity_html(
    item: MaintenanceQueueItem,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    rows = (
        (operations_text("common.finding", locale), item.finding_id),
        (operations_text("common.analysis_run", locale), item.analysis_run_id),
        (operations_text("common.capability", locale), item.capability_id),
        (
            operations_text("common.point", locale),
            item.measurement_point_id or operations_text("common.not_recorded", locale),
        ),
    )
    body = "".join(
        f"<tr><td>{escape(label)}</td><td>{escape(value)}</td></tr>"
        for label, value in rows
    )
    title = escape(operations_text("maintenance.review_identity", locale))
    return (
        '<section class="phm-shell">'
        f'<div class="phm-section-title">{title}</div>'
        f'<table class="phm-table"><tbody>{body}</tbody></table>'
        "</section>"
    )


def _fact(label: str, value: str) -> str:
    return (
        "<div>"
        f'<div class="phm-fact-label">{escape(label)}</div>'
        f'<div class="phm-fact-value">{escape(value)}</div>'
        "</div>"
    )


def _empty_row(columns: int, message: str) -> str:
    return (
        f'<tr><td colspan="{columns}" class="phm-card-detail">'
        f"{escape(message)}"
        "</td></tr>"
    )


def _percent(value: object) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.2f}%"
    return "—"
