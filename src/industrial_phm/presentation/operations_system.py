"""Presentation helpers for the Operations System workspace."""

from __future__ import annotations

from datetime import UTC, datetime
from html import escape

from industrial_phm.application.operations_monitor import OperationsMonitorStatus
from industrial_phm.application.operations_system import (
    SystemRuntimeService,
    SystemRuntimeView,
)


def render_system_runtime_html(view: SystemRuntimeView) -> str:
    if not isinstance(view, SystemRuntimeView):
        raise ValueError("view must be a SystemRuntimeView")
    cards = "".join(_service_card(item) for item in view.services)
    return (
        '<section class="phm-shell">'
        '<div class="phm-section-title">Runtime</div>'
        f'<div class="phm-system-grid">{cards}</div>'
        "</section>"
    )


def render_system_errors_html(view: SystemRuntimeView) -> str:
    if not isinstance(view, SystemRuntimeView):
        raise ValueError("view must be a SystemRuntimeView")
    if not view.errors:
        return (
            '<section class="phm-shell">'
            '<div class="phm-section-title">Current application errors</div>'
            '<div class="phm-card-detail">No current state-read error is recorded.</div>'
            "</section>"
        )
    body = "".join(
        "<tr>"
        f"<td>{escape(_time_label(item.detected_at))}</td>"
        f"<td><strong>{escape(item.title)}</strong></td>"
        f"<td>{escape(item.detail)}</td>"
        "</tr>"
        for item in view.errors
    )
    return (
        '<section class="phm-shell">'
        '<div class="phm-section-title">Current application errors</div>'
        '<table class="phm-table">'
        "<thead><tr><th>Detected</th><th>Area</th><th>Detail</th></tr></thead>"
        f"<tbody>{body}</tbody></table></section>"
    )


def render_system_diagnostics_html(
    diagnostics: tuple[tuple[str, str], ...],
) -> str:
    body = "".join(
        f"<tr><td>{escape(label)}</td><td><code>{escape(value)}</code></td></tr>"
        for label, value in diagnostics
    )
    return (
        '<section class="phm-shell">'
        '<div class="phm-section-title">Advanced diagnostics</div>'
        '<table class="phm-table">'
        "<thead><tr><th>State</th><th>Path</th></tr></thead>"
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


def _service_card(service: SystemRuntimeService) -> str:
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
        f"{escape(_status_label(service.status))}</div>"
        f'<div class="phm-card-detail">{escape(service.summary)}</div>'
        f'<div class="phm-system-facts">{facts}</div>'
        "</div>"
    )


def _status_label(status: OperationsMonitorStatus) -> str:
    return {
        OperationsMonitorStatus.RUNNING: "Running",
        OperationsMonitorStatus.WAITING: "Waiting",
        OperationsMonitorStatus.DELAYED: "Delayed",
        OperationsMonitorStatus.STOPPED: "Stopped",
        OperationsMonitorStatus.NEEDS_ATTENTION: "Needs attention",
        OperationsMonitorStatus.ERROR: "Error",
        OperationsMonitorStatus.UNAVAILABLE: "Unavailable",
    }[status]


def _time_label(value: datetime) -> str:
    if value.utcoffset() is None:
        return "Time not comparable"
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
