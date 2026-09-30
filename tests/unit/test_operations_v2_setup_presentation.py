from datetime import UTC, datetime

from industrial_phm.application.collection_control import CollectionDesiredState
from industrial_phm.application.operations_v2_setup import (
    SetupSignalView,
    SetupSourceView,
    SetupWorkspaceView,
)
from industrial_phm.application.source_lifecycle import SourceLifecycleState
from industrial_phm.application.source_registration import SourceType
from industrial_phm.presentation.operations_v2_setup import (
    render_setup_signals_html,
    render_setup_source_detail_html,
    render_setup_sources_html,
    setup_workspace_css,
)

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def _source() -> SetupSourceView:
    return SetupSourceView(
        source_id="opc-a",
        name="Main panel",
        source_type=SourceType.OPCUA,
        asset_id="boiler-01",
        measurement_point_id="panel-main",
        lifecycle_state=SourceLifecycleState.ACTIVE,
        registered_at=NOW,
        connection_target="opc.tcp://127.0.0.1:4840",
        collection_desired_state=CollectionDesiredState.RUNNING,
        collection_requested_at=NOW,
        freshness_max_age_seconds=30.0,
        freshness_changed_at=NOW,
        signals=(
            SetupSignalView(
                channel_id="Current_L1",
                source_locator="ns=2;s=CurrentL1",
                observed_property=None,
                scope=None,
                statistic=None,
                unit=None,
                semantic_version=None,
                interpretation_evidence=None,
            ),
            SetupSignalView(
                channel_id="Voltage_L1",
                source_locator="ns=2;s=VoltageL1",
                observed_property="phase voltage",
                scope="phase R",
                statistic=None,
                unit="V",
                semantic_version="site-v1",
                interpretation_evidence="commissioning map",
            ),
        ),
    )


def test_setup_primary_surfaces_use_user_language() -> None:
    source = _source()
    list_html = render_setup_sources_html(SetupWorkspaceView((source,)))
    detail_html = render_setup_source_detail_html(source)
    signals_html = render_setup_signals_html(source)

    assert "Main panel" in list_html
    assert "OPC UA" in list_html
    assert "Enabled" in detail_html
    assert "Running" in list_html
    assert "phase voltage" in signals_html
    assert "Data age limit" in detail_html
    assert "30 s" in detail_html
    assert "Unresolved" in signals_html
    for rendered in (list_html, detail_html, signals_html):
        assert "control-plane" not in rendered
        assert "lifecycle" not in rendered.lower()


def test_setup_css_reuses_v2_tokens() -> None:
    css = setup_workspace_css()

    assert "var(--phm-surface)" in css
    assert "var(--phm-border)" in css
