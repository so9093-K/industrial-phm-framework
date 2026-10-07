"""Presentation helpers for the Operations System workspace."""

from __future__ import annotations

import re
from html import escape

from industrial_phm.application.operations_monitor import OperationsMonitorStatus
from industrial_phm.application.operations_system import (
    SystemRuntimeKind,
    SystemRuntimeService,
    SystemRuntimeView,
)
from industrial_phm.presentation.operations_locale import (
    DEFAULT_OPERATIONS_LOCALE,
    OperationsLocale,
    format_operations_utc,
    operations_text,
)


def render_system_runtime_html(
    view: SystemRuntimeView,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(view, SystemRuntimeView):
        raise ValueError("view must be a SystemRuntimeView")
    cards = "".join(_service_card(item, locale) for item in view.services)
    title = escape(operations_text("system.runtime", locale))
    return (
        '<section class="phm-shell">'
        f'<div class="phm-section-title">{title}</div>'
        f'<div class="phm-system-grid">{cards}</div>'
        "</section>"
    )


def render_system_errors_html(
    view: SystemRuntimeView,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    if not isinstance(view, SystemRuntimeView):
        raise ValueError("view must be a SystemRuntimeView")
    title = escape(operations_text("system.errors", locale))
    if not view.errors:
        detail = escape(operations_text("system.no_errors", locale))
        return (
            '<section class="phm-shell">'
            f'<div class="phm-section-title">{title}</div>'
            f'<div class="phm-card-detail">{detail}</div>'
            "</section>"
        )
    body = "".join(
        "<tr>"
        f"<td>{escape(format_operations_utc(item.detected_at, locale))}</td>"
        f"<td><strong>{escape(_error_title(item.scope, item.title, locale))}</strong></td>"
        f"<td>{escape(item.detail)}</td>"
        "</tr>"
        for item in view.errors
    )
    headers = (
        operations_text("system.detected", locale),
        operations_text("system.area", locale),
        operations_text("system.detail", locale),
    )
    return (
        '<section class="phm-shell">'
        f'<div class="phm-section-title">{title}</div>'
        '<table class="phm-table">'
        f"<thead><tr>{_headers(headers)}</tr></thead>"
        f"<tbody>{body}</tbody></table></section>"
    )


def render_system_diagnostics_html(
    diagnostics: tuple[tuple[str, str], ...],
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    body = "".join(
        f"<tr><td>{escape(label)}</td><td><code>{escape(value)}</code></td></tr>"
        for label, value in diagnostics
    )
    title = escape(operations_text("system.advanced_diagnostics", locale))
    headers = (
        operations_text("system.state", locale),
        operations_text("system.path", locale),
    )
    return (
        '<section class="phm-shell">'
        f'<div class="phm-section-title">{title}</div>'
        '<table class="phm-table">'
        f"<thead><tr>{_headers(headers)}</tr></thead>"
        f"<tbody>{body}</tbody></table></section>"
    )


def system_workspace_css() -> str:
    return """
<style>
.phm-system-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: .75rem;
}
.phm-system-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: .55rem .9rem;
  margin-top: .85rem;
  padding-top: .75rem;
  border-top: 1px solid var(--phm-border);
}
.phm-system-fact-label {
  color: var(--phm-muted);
  font-size: .69rem;
  text-transform: uppercase;
  letter-spacing: .04em;
}
.phm-system-fact-value {
  margin-top: .15rem;
  font-size: .8rem;
  overflow-wrap: anywhere;
}
@media (max-width: 980px) {
  .phm-system-grid { grid-template-columns: 1fr; }
}
</style>
"""


def _service_card(
    service: SystemRuntimeService,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    facts = "".join(
        "<div>"
        f'<div class="phm-system-fact-label">{escape(_fact_label(item.label, locale))}</div>'
        f'<div class="phm-system-fact-value">{escape(_fact_value(item.value, locale))}</div>'
        "</div>"
        for item in service.facts
    )
    return (
        '<div class="phm-card">'
        f'<div class="phm-card-title">{escape(_service_title(service.kind, locale))}</div>'
        f'<div class="phm-card-status phm-status-{service.status.value}">'
        f"{escape(_status_label(service.status, locale))}</div>"
        f'<div class="phm-card-detail">{escape(_service_summary(service.summary, locale))}</div>'
        f'<div class="phm-system-facts">{facts}</div>'
        "</div>"
    )


_SERVICE_TITLE_KEY = {
    SystemRuntimeKind.ACQUISITION: "system.service.acquisition",
    SystemRuntimeKind.HISTORY: "system.service.history",
    SystemRuntimeKind.ANALYSIS: "system.service.analysis",
    SystemRuntimeKind.APPLICATION: "system.service.application",
}

_FACT_LABEL_KEY = {
    "Collection service": "system.fact.collection_service",
    "Service heartbeat": "system.fact.service_heartbeat",
    "Configured live sources": "system.fact.configured_live_sources",
    "Connected sessions": "system.fact.connected_sessions",
    "Connecting / reconnecting": "system.fact.reconnecting",
    "Stopped / disconnected": "system.fact.stopped",
    "Last received data": "system.fact.last_received",
    "Waiting to store": "system.fact.waiting_store",
    "Oldest waiting age": "system.fact.oldest_waiting",
    "Latest commit": "system.fact.latest_commit",
    "Latest finalized input": "system.fact.latest_finalized",
    "Finalized windows": "system.fact.finalized_windows",
    "Heartbeat": "system.fact.heartbeat",
    "Completed analyses": "system.fact.completed_analyses",
    "Skipped inputs": "system.fact.skipped_inputs",
    "Last result": "system.fact.last_result",
    "Last skip": "system.fact.last_skip",
    "Last skip reason": "system.fact.last_skip_reason",
    "Last failure": "system.fact.last_failure",
    "Current read errors": "system.fact.current_read_errors",
    "Last refresh": "system.fact.last_refresh",
    "Process heartbeat": "system.fact.process_heartbeat",
    "Last update": "system.fact.last_update",
}

_ERROR_TITLE_KEY = {
    "source-settings": "system.error.source_settings",
    "source-runtime": "system.error.source_runtime",
    "field-analysis-results": "system.error.vibration_analysis",
    "phase-analysis-results": "system.error.phase_analysis",
    "review-requests": "system.error.review_requests",
    "maintenance-review": "system.error.maintenance_review",
    "live-data": "system.error.live_data",
    "analysis-service": "system.error.analysis_service",
    "analysis-attempts": "system.error.analysis_attempts",
    "asset-history": "system.error.asset_history",
}

_SUMMARY_EXACT_KEY = {
    "No live OPC UA source is configured": "system.summary.no_live_source",
    "Live acquisition telemetry is unavailable": "system.summary.telemetry_unavailable",
    "Collection enabled; waiting for live session evidence": "system.summary.collection_waiting",
    "Collection is not enabled": "system.summary.collection_disabled",
    "No live storage telemetry available": "system.summary.storage_unavailable",
    "History current": "system.summary.history_current",
    "Waiting for collected data": "system.summary.waiting_collected",
    "Analysis service status unavailable": "system.summary.analysis_unavailable",
    "Analysis service failed": "system.summary.analysis_failed",
    "Analysis service stopped": "system.summary.analysis_stopped",
    "Analysis service running; waiting for analyzable data": "system.summary.analysis_waiting",
    "Current Operations state read succeeded": "system.summary.application_ok",
}


def _service_title(
    kind: SystemRuntimeKind,
    locale: OperationsLocale | str,
) -> str:
    return operations_text(_SERVICE_TITLE_KEY[kind], locale)


def _fact_label(label: str, locale: OperationsLocale | str) -> str:
    key = _FACT_LABEL_KEY.get(label)
    return label if key is None else operations_text(key, locale)


def _fact_value(value: str, locale: OperationsLocale | str) -> str:
    exact = {
        "Unavailable": "system.value.unavailable",
        "None": "system.value.none",
        "Not instrumented": "system.value.not_instrumented",
        "Running": "system.value.running",
        "Stopped": "system.value.stopped",
    }
    key = exact.get(value)
    if key is not None:
        return operations_text(key, locale)
    match = re.fullmatch(r"Not responding \(last reported (.+)\)", value)
    if match is not None:
        return operations_text("system.value.not_responding", locale).format(
            state=_fact_value(match.group(1).capitalize(), locale)
        )
    match = re.fullmatch(r"Unknown \(last report (\d+) / (\d+)\)", value)
    if match is not None:
        return operations_text("system.value.unknown_last_report", locale).format(
            current=match.group(1),
            total=match.group(2),
        )
    return value


def _service_summary(summary: str, locale: OperationsLocale | str) -> str:
    key = _SUMMARY_EXACT_KEY.get(summary)
    if key is not None:
        return operations_text(key, locale)

    patterns = (
        (r"(\d+) collection worker failure\(s\)", "system.summary.worker_failures"),
        (
            r"(\d+) live source session\(s\) connected",
            "system.summary.connected",
        ),
        (r"(\d+) history writer failure\(s\)", "system.summary.history_failures"),
        (r"(\d+) event\(s\) waiting to store", "system.summary.waiting_store"),
        (
            r"(\d+) event\(s\) waiting for first history commit",
            "system.summary.waiting_first_commit",
        ),
        (
            r"(\d+) analysis-input preparation failure\(s\)",
            "system.summary.analysis_input_failures",
        ),
        (r"(\d+) analysis result\(s\) recorded", "system.summary.analysis_results"),
        (r"(\d+) current state-read error\(s\)", "system.summary.application_errors"),
    )
    for pattern, resource_key in patterns:
        match = re.fullmatch(pattern, summary)
        if match is not None:
            return operations_text(resource_key, locale).format(count=match.group(1))

    reconnect = re.fullmatch(
        r"(\d+) live source session\(s\) reconnecting(?: · (\d+) connected)?",
        summary,
    )
    if reconnect is not None:
        connected = (
            ""
            if reconnect.group(2) is None
            else operations_text("system.summary.connected_clause", locale).format(
                count=reconnect.group(2)
            )
        )
        return operations_text("system.summary.reconnecting", locale).format(
            count=reconnect.group(1),
            connected=connected,
        )

    heartbeat = re.fullmatch(r"Analysis service heartbeat is (.+) old", summary)
    if heartbeat is not None:
        return operations_text("system.summary.analysis_heartbeat_old", locale).format(
            age=heartbeat.group(1)
        )
    return summary


def _error_title(
    scope: str,
    fallback: str,
    locale: OperationsLocale | str,
) -> str:
    key = (
        "system.error.live_data"
        if scope.startswith("live-data:")
        else _ERROR_TITLE_KEY.get(scope, "system.error.application")
    )
    localized = operations_text(key, locale)
    return fallback if localized == "Application state" and scope not in _ERROR_TITLE_KEY else localized


def _status_label(
    status: OperationsMonitorStatus,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    key = {
        OperationsMonitorStatus.RUNNING: "system.status.running",
        OperationsMonitorStatus.WAITING: "system.status.waiting",
        OperationsMonitorStatus.DELAYED: "system.status.delayed",
        OperationsMonitorStatus.STOPPED: "system.status.stopped",
        OperationsMonitorStatus.NEEDS_ATTENTION: "system.status.needs_attention",
        OperationsMonitorStatus.ERROR: "system.status.error",
        OperationsMonitorStatus.UNAVAILABLE: "system.status.unavailable",
    }[status]
    return operations_text(key, locale)


def _headers(labels: tuple[str, ...]) -> str:
    return "".join(f"<th>{escape(label)}</th>" for label in labels)
