from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application import (
    OpcUaEventTimeBasis,
    OpcUaEventTimeEvidence,
    OpcUaEventTimePolicy,
    OpcUaPersistentSessionEvidence,
    OpcUaPersistentSessionPolicy,
    OpcUaPersistentSessionState,
    RegisteredOpcUaDataChangeEvent,
    project_opcua_persistent_data_change_event,
    validate_opcua_persistent_session_transition,
)
from industrial_phm.connectors import (
    OpcUaNodeObservation,
    OpcUaSubscriptionNotification,
)

NOW = datetime(2026, 9, 27, 11, 0, tzinfo=UTC)


def _registered_event(
    *,
    source_timestamp: datetime | None,
    server_timestamp: datetime | None,
    received_at: datetime = NOW,
    replayed: bool = False,
) -> RegisteredOpcUaDataChangeEvent:
    observation = OpcUaNodeObservation(
        channel_id="vibration_x",
        node_id="ns=2;s=VibrationX",
        value=1.25,
        status_code=0,
        status_good=True,
        status_text="Good",
        variant_type="Double",
        source_timestamp=source_timestamp,
        server_timestamp=server_timestamp,
        received_at=received_at,
    )
    return RegisteredOpcUaDataChangeEvent(
        source_id="opcua-source-1",
        asset_id="pump-01",
        endpoint_url="opc.tcp://127.0.0.1:4840",
        measurement_point_id="drive-end",
        collection_index=0,
        notification=OpcUaSubscriptionNotification(
            observation=observation,
            replayed=replayed,
        ),
    )


def test_persistent_session_policy_caps_reconnect_backoff() -> None:
    policy = OpcUaPersistentSessionPolicy(
        reconnect_initial_delay_seconds=1.0,
        reconnect_max_delay_seconds=5.0,
        reconnect_backoff_multiplier=2.0,
    )

    assert tuple(policy.reconnect_delay_seconds(index) for index in range(6)) == (
        1.0,
        2.0,
        4.0,
        5.0,
        5.0,
        5.0,
    )


def test_persistent_session_transition_tracks_epoch_and_reconnect_attempt() -> None:
    disconnected = OpcUaPersistentSessionEvidence(
        source_id="opcua-source-1",
        state=OpcUaPersistentSessionState.DISCONNECTED,
        changed_at=NOW,
    )
    connecting = OpcUaPersistentSessionEvidence(
        source_id="opcua-source-1",
        state=OpcUaPersistentSessionState.CONNECTING,
        changed_at=NOW + timedelta(seconds=1),
    )
    connected = OpcUaPersistentSessionEvidence(
        source_id="opcua-source-1",
        state=OpcUaPersistentSessionState.CONNECTED,
        changed_at=NOW + timedelta(seconds=2),
        connection_epoch=1,
    )
    waiting = OpcUaPersistentSessionEvidence(
        source_id="opcua-source-1",
        state=OpcUaPersistentSessionState.RECONNECT_WAIT,
        changed_at=NOW + timedelta(seconds=3),
        connection_epoch=1,
        detail="transport connection lost",
    )
    reconnecting = OpcUaPersistentSessionEvidence(
        source_id="opcua-source-1",
        state=OpcUaPersistentSessionState.CONNECTING,
        changed_at=NOW + timedelta(seconds=4),
        connection_epoch=1,
        reconnect_attempt_index=1,
    )
    reconnected = OpcUaPersistentSessionEvidence(
        source_id="opcua-source-1",
        state=OpcUaPersistentSessionState.CONNECTED,
        changed_at=NOW + timedelta(seconds=5),
        connection_epoch=2,
        reconnect_attempt_index=1,
    )

    validate_opcua_persistent_session_transition(disconnected, connecting)
    validate_opcua_persistent_session_transition(connecting, connected)
    validate_opcua_persistent_session_transition(connected, waiting)
    validate_opcua_persistent_session_transition(waiting, reconnecting)
    validate_opcua_persistent_session_transition(reconnecting, reconnected)


def test_persistent_session_transition_rejects_implicit_epoch_increment() -> None:
    before = OpcUaPersistentSessionEvidence(
        source_id="opcua-source-1",
        state=OpcUaPersistentSessionState.CONNECTED,
        changed_at=NOW,
        connection_epoch=1,
    )
    after = OpcUaPersistentSessionEvidence(
        source_id="opcua-source-1",
        state=OpcUaPersistentSessionState.RECONNECT_WAIT,
        changed_at=NOW + timedelta(seconds=1),
        connection_epoch=2,
        detail="connection lost",
    )

    with pytest.raises(ValueError, match="connection_epoch"):
        validate_opcua_persistent_session_transition(before, after)


def test_initial_disconnected_session_accepts_durable_epoch_baseline() -> None:
    disconnected = OpcUaPersistentSessionEvidence(
        source_id="opcua-source-1",
        state=OpcUaPersistentSessionState.DISCONNECTED,
        changed_at=NOW,
        connection_epoch=7,
    )
    connecting = OpcUaPersistentSessionEvidence(
        source_id="opcua-source-1",
        state=OpcUaPersistentSessionState.CONNECTING,
        changed_at=NOW + timedelta(seconds=1),
        connection_epoch=7,
    )
    connected = OpcUaPersistentSessionEvidence(
        source_id="opcua-source-1",
        state=OpcUaPersistentSessionState.CONNECTED,
        changed_at=NOW + timedelta(seconds=2),
        connection_epoch=8,
    )

    validate_opcua_persistent_session_transition(disconnected, connecting)
    validate_opcua_persistent_session_transition(connecting, connected)


def test_initial_disconnected_session_resets_reconnect_attempt() -> None:
    with pytest.raises(ValueError, match="zero reconnect attempt"):
        OpcUaPersistentSessionEvidence(
            source_id="opcua-source-1",
            state=OpcUaPersistentSessionState.DISCONNECTED,
            changed_at=NOW,
            connection_epoch=7,
            reconnect_attempt_index=1,
        )


def test_unavailable_event_time_rejects_available_source_timestamp() -> None:
    with pytest.raises(ValueError, match="source_timestamp"):
        OpcUaEventTimeEvidence(
            basis=OpcUaEventTimeBasis.UNAVAILABLE,
            source_timestamp=NOW - timedelta(seconds=1),
            server_timestamp=None,
            received_at=NOW,
            ingested_at=NOW,
            event_at=None,
        )


def test_persistent_event_prefers_source_timestamp_and_preserves_all_clocks() -> None:
    source_timestamp = NOW - timedelta(seconds=3)
    server_timestamp = NOW - timedelta(seconds=2)
    event = _registered_event(
        source_timestamp=source_timestamp,
        server_timestamp=server_timestamp,
    )

    projected = project_opcua_persistent_data_change_event(
        event,
        connection_epoch=2,
        event_index=7,
        ingested_at=NOW + timedelta(milliseconds=50),
        event_time_policy=OpcUaEventTimePolicy(
            allow_server_timestamp_fallback=True,
        ),
    )

    assert projected.event_time.basis == OpcUaEventTimeBasis.SOURCE_TIMESTAMP
    assert projected.event_time.event_at == source_timestamp
    assert projected.event_time.source_timestamp == source_timestamp
    assert projected.event_time.server_timestamp == server_timestamp
    assert projected.event_time.received_at == NOW
    assert projected.event_time.ingested_at == NOW + timedelta(milliseconds=50)
    assert projected.local_delivery_identity == ("opcua-source-1", 2, 7)


def test_server_timestamp_fallback_is_explicit_opt_in() -> None:
    server_timestamp = NOW - timedelta(seconds=2)
    event = _registered_event(
        source_timestamp=None,
        server_timestamp=server_timestamp,
    )

    default_projection = project_opcua_persistent_data_change_event(
        event,
        connection_epoch=1,
        event_index=0,
        ingested_at=NOW,
    )
    fallback_projection = project_opcua_persistent_data_change_event(
        event,
        connection_epoch=1,
        event_index=0,
        ingested_at=NOW,
        event_time_policy=OpcUaEventTimePolicy(
            allow_server_timestamp_fallback=True,
        ),
    )

    assert default_projection.event_time.basis == OpcUaEventTimeBasis.UNAVAILABLE
    assert default_projection.event_time.event_at is None
    assert default_projection.event_time.server_timestamp == server_timestamp
    assert fallback_projection.event_time.basis == OpcUaEventTimeBasis.SERVER_TIMESTAMP
    assert fallback_projection.event_time.event_at == server_timestamp


def test_received_at_is_never_silently_promoted_to_event_time() -> None:
    event = _registered_event(
        source_timestamp=None,
        server_timestamp=None,
    )

    projected = project_opcua_persistent_data_change_event(
        event,
        connection_epoch=1,
        event_index=0,
        ingested_at=NOW + timedelta(milliseconds=1),
    )

    assert projected.event_time.basis == OpcUaEventTimeBasis.UNAVAILABLE
    assert projected.event_time.event_at is None
    assert projected.event_time.received_at == NOW


def test_persistent_event_rejects_ingestion_before_connector_receipt() -> None:
    event = _registered_event(
        source_timestamp=NOW - timedelta(seconds=1),
        server_timestamp=None,
    )

    with pytest.raises(ValueError, match="ingested_at must not be before received_at"):
        project_opcua_persistent_data_change_event(
            event,
            connection_epoch=1,
            event_index=0,
            ingested_at=NOW - timedelta(milliseconds=1),
        )


def test_local_delivery_identity_does_not_claim_server_sequence() -> None:
    event = _registered_event(
        source_timestamp=NOW - timedelta(seconds=1),
        server_timestamp=None,
        replayed=True,
    )

    projected = project_opcua_persistent_data_change_event(
        event,
        connection_epoch=3,
        event_index=12,
        ingested_at=NOW,
    )

    assert projected.local_delivery_identity == ("opcua-source-1", 3, 12)
    assert projected.event.notification.replayed is True
    assert not hasattr(projected, "server_sequence")
