"""Presentation helpers for the Operations System workspace."""

from __future__ import annotations

from html import escape

from industrial_phm.application.operations_monitor import OperationsMonitorStatus
from industrial_phm.application.operations_system import SystemRuntimeService, SystemRuntimeView
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
        f"<td><strong>{escape(item.title)}</strong></td>"
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
        f'<div class="phm-system-fact-label">{escape(item.label)}</div>'
        f'<div class="phm-system-fact-value">{escape(item.value)}</div>'
        "</div>"
        for item in service.facts
    )
    return (
        '<div class="phm-card">'
        f'<div class="phm-card-title">{escape(service.title)}</div>'
        f'<div class="phm-card-status phm-status-{service.status.value}">'
        f"{escape(_status_label(service.status, locale))}</div>"
        f'<div class="phm-card-detail">{escape(service.summary)}</div>'
        f'<div class="phm-system-facts">{facts}</div>'
        "</div>"
    )


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
