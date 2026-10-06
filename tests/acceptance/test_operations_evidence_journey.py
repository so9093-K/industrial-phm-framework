"""One person's evidence journey keeps the same asset, evidence and display identity.

Monitor -> Signals -> Analysis -> Investigation -> Request review -> Maintenance ->
back to Investigation, on a synthetic fixture so it runs in CI. The packaged app runs
in script mode; the journey uses the same review action, navigation resolver and
renderers the UI calls rather than browser clicks. Live receive, pause, reconnect and
recovery belong to the #388 fault gate and are not repeated here.
"""

import runpy
from datetime import UTC, datetime

import pytest

from industrial_phm.application import (
    ChannelSemanticBinding,
    JsonSourceRepository,
    MeasurementDefinition,
    OpcUaSourceConfig,
    RegisteredSource,
    SqlitePhaseUnbalanceRepository,
)
from industrial_phm.apps import operations_app_path
from industrial_phm.connectors import OpcUaNodeMapping
from industrial_phm.presentation.operations_investigations import (
    render_investigation_summary_html,
)
from industrial_phm.presentation.operations_live import initial_signal_channel
from industrial_phm.presentation.operations_maintenance import (
    maintenance_queue_label,
    render_maintenance_summary_html,
)
from industrial_phm.presentation.operations_navigation import resolve_finding_investigation_route
from industrial_phm.presentation.operations_shell import render_monitor_assets_html
from industrial_phm.runtime import OperationsWorkspace
from tests.support.window_analysis import phase_unbalance_analysis

pytest.importorskip("marimo")

ASSET_ID = "motor-7"
DISPLAY_NAME = "Motor 7 · reference asset"
REGISTERED_AT = datetime(2026, 9, 29, 11, 0, tzinfo=UTC)


def _register_named_source(workspace: OperationsWorkspace) -> None:
    channels = ("reactive_power", "va", "vb", "vc")
    bindings = tuple(
        ChannelSemanticBinding(
            source_id="site-opcua",
            channel_id=channel,
            version="site-semantics-v1",
            definition=MeasurementDefinition(
                "phase voltage",
                scope=f"phase {phase}",
                unit="V",
                unit_evidence="meter commissioning sheet",
            ),
            interpretation_evidence="commissioning record",
        )
        for channel, phase in (("va", "R"), ("vb", "S"), ("vc", "T"))
    )
    JsonSourceRepository(workspace.source_registry_path).register(
        RegisteredSource(
            source_id="site-opcua",
            name="Site OPC UA",
            config=OpcUaSourceConfig(
                endpoint_url="opc.tcp://127.0.0.1:4840",
                asset_id=ASSET_ID,
                node_mappings=tuple(
                    OpcUaNodeMapping(channel, f"ns=2;s={channel}") for channel in channels
                ),
                semantic_bindings=bindings,
                asset_display_name=DISPLAY_NAME,
            ),
            registered_at=REGISTERED_AT,
        )
    )


def _run_operations(workspace: OperationsWorkspace, monkeypatch) -> dict:
    """Open a fresh Operations session the way the packaged app renders it."""
    monkeypatch.setenv("INDUSTRIAL_PHM_OPERATIONS_WORKSPACE", str(workspace.root))
    app = runpy.run_path(str(operations_app_path()))["app"]
    _, defs = app.run()
    return defs


def test_review_journey_keeps_asset_evidence_and_display_identity(tmp_path, monkeypatch):
    workspace = OperationsWorkspace(tmp_path / "workspace")
    analysis = phase_unbalance_analysis()
    SqlitePhaseUnbalanceRepository(workspace.phase_unbalance_state_path).record(analysis)
    _register_named_source(workspace)

    # Monitor: the asset is introduced by its display name, its ID kept underneath.
    first = _run_operations(workspace, monkeypatch)
    names = first["asset_names"]
    assert names.label(ASSET_ID) == DISPLAY_NAME
    (monitor_asset,) = (item for item in first["monitor"].assets if item.asset_id == ASSET_ID)
    assert monitor_asset.pending_review_count == 0
    monitor_html = render_monitor_assets_html(first["monitor"], names)
    assert DISPLAY_NAME in monitor_html and ASSET_ID in monitor_html

    # Signals: the same asset opens on a channel with confirmed meaning, not the
    # alphabetically first unresolved one.
    (source,) = (item for item in first["registered_sources"] if item.asset_id == ASSET_ID)
    channel_ids = tuple(sorted(identity.channel_id for identity in source.channel_identities))
    confirmed = {binding.channel_id for binding in source.config.semantic_bindings}
    assert channel_ids[0] == "reactive_power"
    assert initial_signal_channel(channel_ids, confirmed_channel_ids=confirmed, selected=None) == (
        "va"
    )

    # Analysis -> Investigation: the exact evidence of this asset is selected.
    investigation = first["selected_investigation"]
    result = first["selected_investigation_result"]
    assert investigation.asset_id == ASSET_ID
    assert investigation.analysis_run_id == analysis.run.analysis_run_id
    assert investigation.evidence_id == analysis.evidence.evidence_id
    summary_html = render_investigation_summary_html(investigation, names)
    assert DISPLAY_NAME in summary_html and ASSET_ID in summary_html

    # Request review through the same action the Investigation button calls.
    finding, _ = first["operations_actions"].request_review(result)
    assert finding.evidence_refs == (analysis.evidence.evidence_id,)

    # Maintenance, in a fresh session: same asset, same evidence, same display name.
    second = _run_operations(workspace, monkeypatch)
    maintenance = second["selected_maintenance"]
    assert maintenance.finding_id == finding.finding_id
    assert maintenance.asset_id == ASSET_ID
    assert maintenance.analysis_run_id == analysis.run.analysis_run_id
    evidence = second["maintenance_evidence"]
    assert evidence.evidence_id == analysis.evidence.evidence_id
    assert evidence.observed_start_at == analysis.run.observed_start_at
    assert second["maintenance_evidence_metrics"]
    assert DISPLAY_NAME in maintenance_queue_label(maintenance, second["asset_names"])
    maintenance_html = render_maintenance_summary_html(maintenance, second["asset_names"])
    assert DISPLAY_NAME in maintenance_html and ASSET_ID in maintenance_html
    (reviewed_asset,) = (item for item in second["monitor"].assets if item.asset_id == ASSET_ID)
    assert reviewed_asset.pending_review_count == 1

    # Back to Investigation: the review resolves to the investigation it started from.
    route = resolve_finding_investigation_route(
        finding.finding_id,
        investigation_queue=second["investigation_queue"],
    )
    assert route.page == "Investigations"
    assert route.investigation_id == investigation.investigation_id
    (returned,) = (
        item
        for item in second["investigation_queue"].items
        if item.investigation_id == route.investigation_id
    )
    assert (returned.asset_id, returned.evidence_id) == (ASSET_ID, analysis.evidence.evidence_id)
    assert second["maintenance_open_investigation_button"] is not None
