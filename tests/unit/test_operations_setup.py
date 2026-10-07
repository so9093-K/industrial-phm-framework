from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application.collection_control import (
    CollectionControlRecord,
    CollectionDesiredState,
)
from industrial_phm.application.measurement_semantics import (
    ChannelSemanticBinding,
    MeasurementDefinition,
)
from industrial_phm.application.operations_setup import (
    build_setup_workspace,
    setup_data_flow_confirmed,
)
from industrial_phm.application.source_freshness import SourceFreshnessPolicy
from industrial_phm.application.source_health import assess_source_health
from industrial_phm.application.source_lifecycle import (
    SourceLifecycleRecord,
    SourceLifecycleState,
)
from industrial_phm.application.source_receipt import SourceReceiptEvidence
from industrial_phm.application.source_registration import (
    FileSourceConfig,
    OpcUaSourceConfig,
    RegisteredSource,
)
from industrial_phm.connectors import OpcUaNodeMapping

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def test_setup_workspace_projects_file_and_opcua_configuration_without_health() -> None:
    file_source = RegisteredSource(
        source_id="file-a",
        name="Snapshot",
        config=FileSourceConfig(
            source_path="data/snapshot.csv",
            asset_id="motor-01",
            measurement_point_id="drive-end",
            channel_columns=("velocity", "temperature"),
            timestamp_column="timestamp",
        ),
        registered_at=NOW - timedelta(days=1),
    )
    binding = ChannelSemanticBinding(
        source_id="opc-a",
        channel_id="Voltage_L1",
        version="site-v1",
        definition=MeasurementDefinition(
            observed_property="phase voltage",
            scope="phase R",
            unit="V",
            unit_evidence="meter data sheet",
        ),
        interpretation_evidence="commissioning map",
    )
    opcua_source = RegisteredSource(
        source_id="opc-a",
        name="Main panel",
        config=OpcUaSourceConfig(
            endpoint_url="opc.tcp://127.0.0.1:4840",
            asset_id="boiler-01",
            measurement_point_id="panel-main",
            node_mappings=(
                OpcUaNodeMapping("Current_L1", "ns=2;s=CurrentL1"),
                OpcUaNodeMapping("Voltage_L1", "ns=2;s=VoltageL1"),
            ),
            semantic_bindings=(binding,),
        ),
        registered_at=NOW,
    )
    lifecycles = (
        SourceLifecycleRecord(
            source_id="file-a",
            state=SourceLifecycleState.REGISTERED,
            changed_at=file_source.registered_at,
        ),
        SourceLifecycleRecord(
            source_id="opc-a",
            state=SourceLifecycleState.ACTIVE,
            changed_at=NOW,
        ),
    )
    collection = CollectionControlRecord(
        source_id="opc-a",
        desired_state=CollectionDesiredState.RUNNING,
        generation=2,
        requested_at=NOW,
    )

    freshness = SourceFreshnessPolicy(
        source_id="opc-a",
        max_observation_age_seconds=30.0,
        changed_at=NOW,
    )
    view = build_setup_workspace(
        sources=(opcua_source, file_source),
        lifecycle_records=lifecycles,
        collection_records=(collection,),
        freshness_policies=(freshness,),
    )

    assert tuple(item.source_id for item in view.sources) == ("file-a", "opc-a")

    file_view = view.sources[0]
    assert file_view.connection_target == "data/snapshot.csv"
    assert file_view.collection_desired_state is None
    assert file_view.semantic_coverage == (0, 2)

    opcua_view = view.sources[1]
    assert opcua_view.connection_target == "opc.tcp://127.0.0.1:4840"
    assert opcua_view.collection_desired_state == CollectionDesiredState.RUNNING
    assert opcua_view.freshness_max_age_seconds == 30.0
    assert opcua_view.freshness_changed_at == NOW
    assert opcua_view.semantic_coverage == (1, 2)
    voltage = next(item for item in opcua_view.signals if item.channel_id == "Voltage_L1")
    assert voltage.observed_property == "phase voltage"
    assert voltage.scope == "phase R"
    assert voltage.unit == "V"
    assert voltage.semantic_version == "site-v1"


def test_setup_workspace_rejects_collection_for_unknown_source() -> None:
    source = RegisteredSource(
        source_id="file-a",
        name="Snapshot",
        config=FileSourceConfig(
            source_path="data/snapshot.csv",
            asset_id="motor-01",
            channel_columns=("velocity",),
            sampling_rate_hz=1.0,
        ),
        registered_at=NOW,
    )
    lifecycle = SourceLifecycleRecord(
        source_id="file-a",
        state=SourceLifecycleState.REGISTERED,
        changed_at=NOW,
    )
    collection = CollectionControlRecord(
        source_id="missing",
        desired_state=CollectionDesiredState.STOPPED,
        generation=1,
        requested_at=NOW,
    )

    with pytest.raises(ValueError, match="unregistered sources"):
        build_setup_workspace(
            sources=(source,),
            lifecycle_records=(lifecycle,),
            collection_records=(collection,),
        )


def test_setup_workspace_rejects_freshness_policy_for_unknown_source() -> None:
    source = RegisteredSource(
        source_id="file-a",
        name="Snapshot",
        config=FileSourceConfig(
            source_path="data/snapshot.csv",
            asset_id="motor-01",
            channel_columns=("velocity",),
            sampling_rate_hz=1.0,
        ),
        registered_at=NOW,
    )
    lifecycle = SourceLifecycleRecord(
        source_id="file-a",
        state=SourceLifecycleState.REGISTERED,
        changed_at=NOW,
    )
    freshness = SourceFreshnessPolicy(
        source_id="missing",
        max_observation_age_seconds=15.0,
        changed_at=NOW,
    )

    with pytest.raises(ValueError, match="freshness_policies reference unregistered sources"):
        build_setup_workspace(
            sources=(source,),
            lifecycle_records=(lifecycle,),
            freshness_policies=(freshness,),
        )

def test_setup_data_flow_requires_receipt_for_current_active_source() -> None:
    lifecycle = SourceLifecycleRecord(
        source_id="opc-a",
        state=SourceLifecycleState.ACTIVE,
        changed_at=NOW,
    )
    waiting = assess_source_health(
        lifecycle,
        None,
        None,
        as_of=NOW + timedelta(seconds=10),
    )
    assert setup_data_flow_confirmed(waiting) is False

    confirmed = assess_source_health(
        lifecycle,
        SourceReceiptEvidence(
            source_id="opc-a",
            received_at=NOW + timedelta(seconds=5),
            observed_at=NOW + timedelta(seconds=4),
        ),
        None,
        as_of=NOW + timedelta(seconds=10),
    )
    assert setup_data_flow_confirmed(confirmed) is True


def test_setup_data_flow_does_not_accept_receipt_from_before_current_activation() -> None:
    lifecycle = SourceLifecycleRecord(
        source_id="opc-a",
        state=SourceLifecycleState.ACTIVE,
        changed_at=NOW,
    )
    assessment = assess_source_health(
        lifecycle,
        SourceReceiptEvidence(
            source_id="opc-a",
            received_at=NOW - timedelta(seconds=1),
            observed_at=NOW - timedelta(seconds=2),
        ),
        None,
        as_of=NOW + timedelta(seconds=10),
    )

    assert setup_data_flow_confirmed(assessment) is False

