from datetime import UTC, datetime

from industrial_phm.application.operations_assets import AssetWorkspaceView
from industrial_phm.application.operations_monitor import (
    OperationsAttentionDestination,
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
    monitor_attention_category,
    monitor_context_attention,
    monitor_signal_channels,
    operations_theme_css,
    render_monitor_asset_context_html,
    render_monitor_assets_html,
    render_monitor_attention_summary_html,
    render_monitor_flow_html,
    render_monitor_signal_overview_html,
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
                destination=OperationsAttentionDestination.ASSET_SIGNALS,
                occurred_at=NOW,
                asset_id="boiler-01",
            ),
        ),
        activities=(),
    )


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


def test_monitor_asset_context_prioritizes_observation_facts() -> None:
    workspace = AssetWorkspaceView(
        asset_id="boiler-01",
        status=OperationsMonitorStatus.DELAYED,
        source_count=1,
        attention_count=1,
        last_data_at=NOW,
        history_start_at=NOW,
        history_end_at=NOW,
        history_measurement_count=20,
        history_channels=("current-r", "temperature"),
        analyses=(),
        reviews=(),
        sources=(),
        events=(),
    )

    rendered = render_monitor_asset_context_html(workspace, as_of=NOW)

    assert "Observed asset" in rendered
    assert "boiler-01" in rendered
    assert "Latest source activity" in rendered
    assert "now · 2026-09-30 12:00:00 UTC" in rendered
    assert "2 signals" in rendered
    assert "Delayed" in rendered
    assert "System data flow" not in rendered
    assert "Recent activity" not in rendered


def test_monitor_signal_overview_prioritizes_selected_and_quality_issue() -> None:
    rows = [
        {
            "channel": "temperature",
            "observed_property": "temperature",
            "scope": None,
            "value": 72.4,
            "unit": "degC",
            "quality": "no recorded issue",
            "event_time_state": "recorded",
            "history_age_seconds": 2.0,
            "source": "source-a",
            "measurement_point": "panel-main",
        },
        {
            "channel": "current-t",
            "observed_property": "phase current",
            "scope": "phase T",
            "value": None,
            "unit": "A",
            "quality": "null",
            "event_time_state": "recorded",
            "history_age_seconds": 5.0,
            "source": "source-a",
            "measurement_point": "panel-main",
        },
        {
            "channel": "vibration",
            "observed_property": "vibration",
            "scope": None,
            "value": 4.81,
            "unit": "mm/s",
            "quality": "no recorded issue",
            "event_time_state": "recorded",
            "history_age_seconds": 1.0,
            "source": "source-a",
            "measurement_point": "bearing-1",
        },
    ]

    rendered = render_monitor_signal_overview_html(
        rows,
        selected_channel="vibration",
        primary_limit=2,
    )

    assert "Latest stored observations" in rendered
    assert "phm-signal-row-selected" in rendered
    assert "phm-signal-row-issue" in rendered
    assert "vibration" in rendered
    assert "4.81 mm/s" in rendered
    assert "phase current · phase T" in rendered
    assert "Show 1 more stored observations" in rendered
    assert "asset health" not in rendered.lower()


def test_monitor_signal_channels_use_selected_then_issue_order() -> None:
    rows = (
        {"channel": "temperature", "quality": "no recorded issue", "source": "a"},
        {"channel": "current-t", "quality": "null", "source": "a"},
        {"channel": "vibration", "quality": "no recorded issue", "source": "a"},
        {"channel": "pressure", "quality": "source status non-good", "source": "a"},
        {
            "channel": "speed",
            "quality": "no recorded issue",
            "event_time_state": "future-timestamp",
            "source": "a",
        },
    )

    channels = monitor_signal_channels(
        rows,
        selected_channel="vibration",
        limit=4,
    )

    assert channels == ("vibration", "current-t", "pressure", "speed")


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


def test_monitor_attention_summary_is_factual_not_severity_scoring() -> None:
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
            attention_id="asset-1:review",
            status=OperationsMonitorStatus.NEEDS_ATTENTION,
            title="Review waiting",
            detail="Review requested.",
            destination=OperationsAttentionDestination.INVESTIGATIONS,
            occurred_at=NOW,
            asset_id="asset-1",
            finding_id="finding-1",
        ),
        OperationsMonitorAttention(
            attention_id="global:system",
            status=OperationsMonitorStatus.ERROR,
            title="System unavailable",
            detail="State read failed.",
            destination=OperationsAttentionDestination.SYSTEM,
            occurred_at=NOW,
        ),
    )

    rendered = render_monitor_attention_summary_html(attention)

    assert "Attention" in rendered
    assert "Data" in rendered
    assert "Review" in rendered
    assert "System" in rendered
    assert ">3<" in rendered
    assert "alarm severity" in rendered
    assert "asset-health scores" in rendered


def test_monitor_signal_channels_lead_with_confirmed_meaning_before_raw_channels() -> None:
    # AI-Hub raw names sort R상무효전력 before R상전압 and push T상전류 off the first view.
    rows = (
        {
            "channel": "R상무효전력",
            "observed_property": "unresolved",
            "quality": "no recorded issue",
            "source": "a",
        },
        {
            "channel": "R상역률",
            "observed_property": "unresolved",
            "quality": "no recorded issue",
            "source": "a",
        },
        {
            "channel": "R상전류",
            "observed_property": "phase current",
            "quality": "no recorded issue",
            "source": "a",
        },
        {
            "channel": "S상전류",
            "observed_property": "phase current",
            "quality": "no recorded issue",
            "source": "a",
        },
        {
            "channel": "T상전류",
            "observed_property": "phase current",
            "quality": "no recorded issue",
            "source": "a",
        },
        {
            "channel": "R상전압",
            "observed_property": "phase voltage",
            "quality": "no recorded issue",
            "source": "a",
        },
    )

    channels = monitor_signal_channels(rows, selected_channel=None, limit=4)

    assert channels == ("R상전류", "R상전압", "S상전류", "T상전류")
    # An explicit selection and a data issue still come first.
    issue = {"channel": "R상역률", "observed_property": "unresolved", "quality": "null"}
    assert monitor_signal_channels((*rows[2:], issue), selected_channel=None, limit=2) == (
        "R상역률",
        "R상전류",
    )
