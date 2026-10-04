from datetime import UTC, datetime

from industrial_phm.application.operations_monitor import (
    OperationsMonitorAsset,
    OperationsMonitorAttention,
    OperationsMonitorStage,
    OperationsMonitorStageKind,
    OperationsMonitorStatus,
    OperationsMonitorView,
)
from industrial_phm.presentation.operations_shell import (
    OPERATIONS_MAIN_BACKGROUND,
    OPERATIONS_PAGE_OPTIONS,
    data_status_label,
    initial_operations_page,
    operations_theme_css,
    render_monitor_assets_html,
    render_monitor_flow_html,
)

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def test_initial_page_routes_empty_workspace_to_setup() -> None:
    assert OPERATIONS_PAGE_OPTIONS[0] == "Monitor"
    assert initial_operations_page(has_registered_sources=False) == "Setup"
    assert initial_operations_page(has_registered_sources=True) == "Monitor"


def _view() -> OperationsMonitorView:
    stages = tuple(
        OperationsMonitorStage(
            kind=kind,
            status=OperationsMonitorStatus.RUNNING,
            title=kind.value.title(),
            summary=f"{kind.value} current",
        )
        for kind in OperationsMonitorStageKind
    )
    return OperationsMonitorView(
        assessed_at=NOW,
        stages=stages,
        assets=(
            OperationsMonitorAsset(
                asset_id="boiler-01",
                status=OperationsMonitorStatus.DELAYED,
                source_count=1,
                last_data_at=NOW,
                latest_analysis_at=None,
                pending_review_count=1,
                attention_count=1,
            ),
        ),
        attention=(
            OperationsMonitorAttention(
                attention_id="stale:boiler-01",
                status=OperationsMonitorStatus.DELAYED,
                title="Data is delayed",
                detail="Latest data exceeded its configured age.",
                occurred_at=NOW,
                asset_id="boiler-01",
            ),
        ),
        activities=(),
    )


def test_operations_theme_uses_fixed_main_background() -> None:
    assert OPERATIONS_MAIN_BACKGROUND == "#292827"
    assert "#292827" in operations_theme_css()


def test_operations_theme_pins_marimo_dark_palette_regardless_of_marimo_theme() -> None:
    # marimo defaults to its light theme; without these switches its widgets and
    # markdown render light surfaces/dark text over the fixed dark background.
    css = operations_theme_css()
    assert "--lightningcss-light: ;" in css
    assert "--lightningcss-dark: initial;" in css
    assert "--background: #292827;" in css
    assert "--tw-prose-headings: #f2f1ef;" in css


def test_monitor_presenters_use_operator_vocabulary() -> None:
    view = _view()
    flow = render_monitor_flow_html(view)
    assets = render_monitor_assets_html(view)

    assert "System data flow" in flow
    assert "Running" in flow
    assert "boiler-01" in assets
    assert "Data status" in assets
    assert "Delayed" in assets
    assert "now · 2026-09-30 12:00:00 UTC" in assets
    assert data_status_label(OperationsMonitorStatus.RUNNING) == "Receiving"
    assert "control-plane" not in flow
    assert "receipt" not in assets
