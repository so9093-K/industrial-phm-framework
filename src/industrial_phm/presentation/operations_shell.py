"""Framework-neutral HTML presenters for the Operations shell."""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from industrial_phm.application.asset_display import AssetDisplayNames
from industrial_phm.application.operations_monitor import (
    OperationsAttentionDestination,
    OperationsMonitorAttention,
    OperationsMonitorStatus,
)
from industrial_phm.presentation.operations_locale import (
    DEFAULT_OPERATIONS_LOCALE,
    OPERATIONS_PAGE_IDS,
    OperationsLocale,
    OperationsPageId,
    operations_status_label,
)

OPERATIONS_MAIN_BACKGROUND = "#10151c"
OPERATIONS_PAGE_OPTIONS = OPERATIONS_PAGE_IDS


def initial_operations_page(*, has_registered_sources: bool) -> OperationsPageId:
    """Choose the first Operations page from durable workspace state."""

    if not isinstance(has_registered_sources, bool):
        raise ValueError("has_registered_sources must be a bool")
    return OperationsPageId.MONITOR if has_registered_sources else OperationsPageId.SETUP


def operations_theme_css(
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    """Return locale-aware Operations shell typography and dark-theme tokens."""

    resolved = locale if isinstance(locale, OperationsLocale) else OperationsLocale(locale)
    label_transform = "none" if resolved == OperationsLocale.KO_KR else "uppercase"
    label_tracking = "0" if resolved == OperationsLocale.KO_KR else ".06em"
    label_tracking_wide = "0" if resolved == OperationsLocale.KO_KR else ".09em"
    copy_word_break = "keep-all" if resolved == OperationsLocale.KO_KR else "normal"
    return f"""
<style>
/* marimo colours every widget through light-dark() switches keyed on these
   properties and defaults to its light theme; pin its dark palette so the Operations
   background never sits behind light-theme surfaces or text. */
:root:root, .marimo {{
  --csstools-color-scheme--light: ;
  --lightningcss-light: ;
  --lightningcss-dark: initial;
  --background: {OPERATIONS_MAIN_BACKGROUND};
  color-scheme: dark;
}}
/* Markdown prose switches to its inverted palette only under a .dark class. */
.markdown.prose {{
  --tw-prose-body: #f2f1ef;
  --tw-prose-headings: #f2f1ef;
  --tw-prose-lead: #aaa7a2;
  --tw-prose-links: #8caac5;
  --tw-prose-bold: #f2f1ef;
  --tw-prose-counters: #aaa7a2;
  --tw-prose-bullets: #aaa7a2;
  --tw-prose-hr: rgba(255,255,255,.08);
  --tw-prose-quotes: #f2f1ef;
  --tw-prose-quote-borders: rgba(255,255,255,.08);
  --tw-prose-captions: #aaa7a2;
  --tw-prose-code: #f2f1ef;
  --tw-prose-th-borders: rgba(255,255,255,.14);
  --tw-prose-td-borders: rgba(255,255,255,.08);
}}
.markdown.prose tr {{
  background: transparent !important;
}}
:root {{
  color-scheme: dark;
  --phm-bg: {OPERATIONS_MAIN_BACKGROUND};
  --phm-surface: #1c222c;
  --phm-surface-raised: #252d39;
  --phm-border: rgba(255,255,255,.08);
  --phm-text: #f2f1ef;
  --phm-muted: #aaa7a2;
  --phm-running: #8fbf9a;
  --phm-attention: #d5aa62;
  --phm-error: #d87878;
  --phm-info: #8caac5;
  --phm-font-ui: "Apple SD Gothic Neo", "Noto Sans KR", "Malgun Gothic",
    system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  --phm-label-transform: {label_transform};
  --phm-label-tracking: {label_tracking};
  --phm-label-tracking-wide: {label_tracking_wide};
  --phm-copy-word-break: {copy_word_break};
}}
body, #root, .marimo {{
  background: var(--phm-bg) !important;
  color: var(--phm-text) !important;
  font-family: var(--phm-font-ui);
  font-size: 15px;
  line-height: 1.5;
}}
.markdown.prose, .phm-shell {{
  font-family: var(--phm-font-ui);
}}
/* marimo stacks default to min-width:auto, so the widest content inside (a fact row,
   a wide table, a fixed-width chart) widened every enclosing stack past the viewport.
   Let any stack around Operations content shrink to its column instead. */
div:has(.phm-shell) {{
  min-width: 0;
}}
.phm-shell {{
  background: var(--phm-bg);
  color: var(--phm-text);
}}
.phm-section-title {{
  margin: 0 0 .8rem 0;
  font-size: .875rem;
  font-weight: 700;
  letter-spacing: var(--phm-label-tracking-wide);
  text-transform: var(--phm-label-transform);
  line-height: 1.4;
  word-break: var(--phm-copy-word-break);
  color: var(--phm-muted);
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
  font-size: .875rem;
  line-height: 1.45;
  margin-bottom: .55rem;
}}
.phm-card-status {{
  font-size: 1.0625rem;
  font-weight: 650;
  margin-bottom: .35rem;
}}
.phm-card-detail {{
  color: var(--phm-muted);
  font-size: .875rem;
  line-height: 1.5;
  overflow-wrap: break-word;
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
  font-size: .875rem;
  vertical-align: top;
  overflow-wrap: anywhere;
}}
.phm-table th {{
  color: var(--phm-muted);
  font-size: .8125rem;
  text-transform: var(--phm-label-transform);
  letter-spacing: var(--phm-label-tracking);
  line-height: 1.4;
  word-break: var(--phm-copy-word-break);
}}
.phm-table tr:last-child td {{ border-bottom: none; }}
.phm-chart-workspace {{ border-top: 1px solid var(--phm-border); padding-top: .7rem; }}
.phm-chart-workspace svg {{ width: 100%; height: auto; }}
</style>
"""


def monitor_context_attention(
    attention: Sequence[OperationsMonitorAttention],
    *,
    asset_id: str,
) -> tuple[OperationsMonitorAttention, ...]:
    """Keep selected-asset attention plus global System issues in Monitor context."""

    if not isinstance(asset_id, str) or not asset_id.strip() or asset_id != asset_id.strip():
        raise ValueError("asset_id must be a non-empty trimmed string")
    values = tuple(attention)
    if any(not isinstance(item, OperationsMonitorAttention) for item in values):
        raise ValueError("attention must contain OperationsMonitorAttention values")
    return tuple(
        item
        for item in values
        if item.asset_id == asset_id
        or (item.asset_id is None and item.destination == OperationsAttentionDestination.SYSTEM)
    )


def monitor_attention_category(
    attention: OperationsMonitorAttention,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    """Operator-facing factual category, not severity or alarm priority."""

    if not isinstance(attention, OperationsMonitorAttention):
        raise ValueError("attention must be an OperationsMonitorAttention")
    labels = {
        OperationsLocale.EN_US: {
            OperationsAttentionDestination.ASSET_SIGNALS: "Data",
            OperationsAttentionDestination.INVESTIGATIONS: "Review",
            OperationsAttentionDestination.SYSTEM: "System",
        },
        OperationsLocale.KO_KR: {
            OperationsAttentionDestination.ASSET_SIGNALS: "데이터",
            OperationsAttentionDestination.INVESTIGATIONS: "검토",
            OperationsAttentionDestination.SYSTEM: "시스템",
        },
    }
    resolved = OperationsLocale(locale)
    return labels[resolved][attention.destination]


def render_asset_title_html(asset_id: str, names: AssetDisplayNames | None = None) -> str:
    """Display name as the title, the stable asset ID kept underneath for traceability."""
    name = None if names is None else names.name(asset_id)
    if name is None:
        return f'<h2 class="phm-asset-title">{escape(asset_id)}</h2>'
    return (
        f'<h2 class="phm-asset-title">{escape(name)}</h2>'
        f'<div class="phm-asset-id">{escape(asset_id)}</div>'
    )


def data_status_label(
    status: OperationsMonitorStatus,
    locale: OperationsLocale | str = DEFAULT_OPERATIONS_LOCALE,
) -> str:
    """Label source/asset data-flow state without implying asset condition."""

    return operations_status_label(status, locale)
