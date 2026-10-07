from datetime import UTC, datetime

from industrial_phm.application.operations_monitor import (
    OperationsAttentionDestination,
    OperationsMonitorAttention,
    OperationsMonitorStatus,
)
from industrial_phm.presentation.operations_locale import OperationsPageId, operations_page_label
from industrial_phm.presentation.operations_shell import (
    OPERATIONS_MAIN_BACKGROUND,
    OPERATIONS_PAGE_OPTIONS,
    data_status_label,
    initial_operations_page,
    monitor_attention_category,
    monitor_context_attention,
    operations_theme_css,
)

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def test_initial_page_routes_empty_workspace_to_stable_page_ids() -> None:
    assert OPERATIONS_PAGE_OPTIONS[0] == OperationsPageId.MONITOR
    assert initial_operations_page(has_registered_sources=False) == OperationsPageId.SETUP
    assert initial_operations_page(has_registered_sources=True) == OperationsPageId.MONITOR
    assert operations_page_label(OperationsPageId.SETUP, "en-US") == "Data connection"
    assert operations_page_label(OperationsPageId.SETUP, "ko-KR") == "데이터 연결"


def test_operations_theme_uses_fixed_main_background() -> None:
    assert OPERATIONS_MAIN_BACKGROUND == "#10151c"
    assert "#10151c" in operations_theme_css()


def test_operations_theme_pins_marimo_dark_palette_regardless_of_marimo_theme() -> None:
    # marimo defaults to its light theme; without these switches its widgets and
    # markdown render light surfaces/dark text over the fixed dark background.
    css = operations_theme_css()
    assert "--lightningcss-light: ;" in css
    assert "--lightningcss-dark: initial;" in css
    assert "--background: #10151c;" in css
    assert "--tw-prose-headings: #f2f1ef;" in css


def test_monitor_attention_is_scoped_to_selected_asset_plus_global_system() -> None:
    attention = (
        OperationsMonitorAttention(
            attention_id="asset-1:data",
            status=OperationsMonitorStatus.DELAYED,
            title="Data delayed",
            detail="No new data.",
            destination=OperationsAttentionDestination.ASSET_SIGNALS,
            occurred_at=NOW,
            asset_id="asset-1",
        ),
        OperationsMonitorAttention(
            attention_id="asset-2:review",
            status=OperationsMonitorStatus.NEEDS_ATTENTION,
            title="Review waiting",
            detail="Review requested.",
            destination=OperationsAttentionDestination.INVESTIGATIONS,
            occurred_at=NOW,
            asset_id="asset-2",
            finding_id="finding-2",
        ),
        OperationsMonitorAttention(
            attention_id="global:system",
            status=OperationsMonitorStatus.ERROR,
            title="System unavailable",
            detail="State read failed.",
            destination=OperationsAttentionDestination.SYSTEM,
            occurred_at=NOW,
        ),
        OperationsMonitorAttention(
            attention_id="asset-1:system",
            status=OperationsMonitorStatus.ERROR,
            title="History writer failed",
            detail="Write failed.",
            destination=OperationsAttentionDestination.SYSTEM,
            occurred_at=NOW,
            asset_id="asset-1",
        ),
    )

    contextual = monitor_context_attention(attention, asset_id="asset-1")

    assert tuple(item.attention_id for item in contextual) == (
        "asset-1:data",
        "global:system",
        "asset-1:system",
    )
    assert monitor_attention_category(contextual[0]) == "Data"
    assert monitor_attention_category(contextual[1]) == "System"


def test_data_status_describes_receipt_without_equipment_health() -> None:
    assert data_status_label(OperationsMonitorStatus.RUNNING) == "Receiving"
