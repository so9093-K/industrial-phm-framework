from datetime import UTC, datetime

from industrial_phm.application.operations_v2 import (
    OperationsMonitorAsset,
    OperationsMonitorAttention,
    OperationsMonitorStage,
    OperationsMonitorStageKind,
    OperationsMonitorStatus,
    OperationsMonitorView,
)
from industrial_phm.presentation.operations_v2 import (
    OPERATIONS_V2_MAIN_BACKGROUND,
    operations_v2_theme_css,
    render_monitor_assets_html,
    render_monitor_flow_html,
)

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


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


def test_v2_theme_uses_fixed_main_background() -> None:
    assert OPERATIONS_V2_MAIN_BACKGROUND == "#292827"
    assert "#292827" in operations_v2_theme_css()


def test_monitor_presenters_use_operator_vocabulary() -> None:
    view = _view()
    flow = render_monitor_flow_html(view)
    assets = render_monitor_assets_html(view)

    assert "Data flow" in flow
    assert "Running" in flow
    assert "boiler-01" in assets
    assert "Delayed" in assets
    assert "control-plane" not in flow
    assert "receipt" not in assets
