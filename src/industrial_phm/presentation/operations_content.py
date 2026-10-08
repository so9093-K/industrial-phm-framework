"""Reusable content patterns for Operations user-facing recovery states."""

from __future__ import annotations

from html import escape

from industrial_phm.presentation.operations_locale import (
    DEFAULT_OPERATIONS_LOCALE,
    OperationsLocale,
    operations_text,
)


def render_operations_error_html(
    *,
    what_happened: str,
    safety: str,
    next_action: str,
    technical_detail: str | None = None,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    """Render a consistent recovery-oriented error anatomy."""

    values = {
        "what_happened": what_happened,
        "safety": safety,
        "next_action": next_action,
    }
    for name, value in values.items():
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ValueError(f"{name} must be a non-empty trimmed string")
    if technical_detail is not None and (
        not isinstance(technical_detail, str)
        or not technical_detail.strip()
        or technical_detail != technical_detail.strip()
    ):
        raise ValueError("technical_detail must be a non-empty trimmed string or None")

    rows = "".join(
        _error_row(operations_text(label_key, locale), value)
        for label_key, value in (
            ("error.what_happened", what_happened),
            ("error.safety", safety),
            ("error.next_action", next_action),
        )
    )
    detail = ""
    if technical_detail is not None:
        detail = (
            '<details class="phm-error-technical">'
            f"<summary>{escape(operations_text('error.technical_detail', locale))}</summary>"
            f"<code>{escape(technical_detail)}</code>"
            "</details>"
        )
    return f'<section class="phm-error-content" role="alert">{rows}{detail}</section>'


def _error_row(label: str, value: str) -> str:
    return (
        '<div class="phm-error-row">'
        f'<div class="phm-error-label">{escape(label)}</div>'
        f'<div class="phm-error-value">{escape(value)}</div>'
        "</div>"
    )


_RECOVERY_SCENARIOS = frozenset(
    {
        "first_run.sample",
        "setup",
        "setup.diagnostic",
        "setup.mapping",
        "asset.workspace",
        "asset.analysis",
        "investigation.review",
        "maintenance",
    }
)


def render_operations_recovery_html(
    scenario: str,
    *,
    technical_detail: str | None = None,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    """Resolve one known failure context into user recovery copy in the chosen locale."""

    if scenario not in _RECOVERY_SCENARIOS:
        raise ValueError("unsupported Operations recovery scenario")
    return render_operations_error_html(
        what_happened=operations_text(f"{scenario}.failure.what", locale),
        safety=operations_text(f"{scenario}.failure.safety", locale),
        next_action=operations_text(f"{scenario}.failure.next", locale),
        technical_detail=technical_detail,
        locale=locale,
    )


def operations_error_css() -> str:
    """Share one readable error anatomy between marimo page surfaces."""

    return """
<style>
.phm-error-content {
  border: 1px solid var(--phm-error);
  border-radius: 10px;
  background: var(--phm-surface);
  color: var(--phm-text);
  padding: .9rem 1rem;
  display: grid;
  gap: .7rem;
  font-size: .875rem;
  line-height: 1.55;
  overflow-wrap: anywhere;
}
.phm-error-label {
  color: var(--phm-muted);
  font-size: .8rem;
  font-weight: 700;
  margin-bottom: .15rem;
}
.phm-error-value { white-space: pre-wrap; }
.phm-error-technical { border-top: 1px solid var(--phm-border); padding-top: .6rem; }
.phm-error-technical summary { cursor: pointer; font-weight: 600; }
.phm-error-technical code { display: block; white-space: pre-wrap; margin-top: .5rem; }
</style>
"""
