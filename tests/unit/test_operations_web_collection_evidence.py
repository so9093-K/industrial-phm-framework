"""Web collection evidence is not a health verdict or a collection request acknowledgment."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from industrial_phm.application.acquisition_telemetry import (
    AcquisitionHistoryTelemetry,
    AcquisitionLastReceiptTelemetry,
    AcquisitionSessionTelemetry,
    AcquisitionSpoolTelemetrySnapshot,
    AcquisitionTelemetrySnapshot,
    AcquisitionTelemetrySurface,
    CollectionServiceRuntimeState,
    CollectionServiceRuntimeTelemetry,
)
from industrial_phm.application.collection_control import (
    CollectionControlRecord,
    CollectionDesiredState,
)
from industrial_phm.application.opcua_persistent import OpcUaPersistentSessionState
from industrial_phm.application.operations_attention import SystemStateErrorEvidence
from industrial_phm.application.source_registration import OpcUaSourceConfig, RegisteredSource
from industrial_phm.connectors.opcua import OpcUaNodeMapping
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_app_composition import load_operations_app_snapshot
from industrial_phm.runtime.operations_web_setup import project_web_source_setup

_AT = datetime(2026, 10, 9, 4, 0, tzinfo=UTC)
_SOURCE = "opcua-pump-01"


def _payload(tmp_path: Path, *, at: datetime = _AT) -> object:
    workspace = OperationsWorkspace(tmp_path / "web-collection")
    initialize_operations_workspace(workspace)
    snapshot = load_operations_app_snapshot(
        environ={"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(workspace.root)},
        assessed_at=at,
    )
    source = RegisteredSource(
        source_id=_SOURCE,
        name="Pump OPC UA",
        config=OpcUaSourceConfig(
            endpoint_url="opc.tcp://127.0.0.1:4840/",
            asset_id="pump-01",
            node_mappings=(OpcUaNodeMapping(channel_id="phase-R", node_id="ns=2;i=1"),),
        ),
        registered_at=at - timedelta(hours=1),
    )
    service = CollectionServiceRuntimeTelemetry(
        state=CollectionServiceRuntimeState.RUNNING,
        started_at=at - timedelta(minutes=5),
        heartbeat_at=at - timedelta(seconds=3),
        reconcile_count=15,
        owned_source_count=1,
    )
    session = AcquisitionSessionTelemetry(
        source_id=_SOURCE,
        worker_started_at=at - timedelta(minutes=4),
        state=OpcUaPersistentSessionState.CONNECTED,
        state_changed_at=at - timedelta(seconds=25),
        connection_epoch=1,
        reconnect_attempt_index=0,
        callback_queue_overflow_count=0,
        connected_since=at - timedelta(seconds=25),
    )
    received = AcquisitionLastReceiptTelemetry(
        source_id=_SOURCE,
        received_at=at - timedelta(seconds=8),
        source_timestamp=at - timedelta(seconds=9),
        delivery_identity=(_SOURCE, 1, 1),
    )
    history = AcquisitionHistoryTelemetry(
        source_id=_SOURCE,
        batch_id="batch-1",
        snapshot_id=7,
        batch_event_count=3,
        source_event_count=2,
        committed_at=at - timedelta(seconds=20),
        acknowledged_at=at - timedelta(seconds=19),
        recovered_existing_commit=False,
    )
    surface = AcquisitionTelemetrySurface(
        source=AcquisitionTelemetrySnapshot(
            source_id=_SOURCE,
            session=session,
            last_receipt=received,
            history=history,
        ),
        spool=AcquisitionSpoolTelemetrySnapshot(
            sampled_at=at,
            pending_event_count=0,
            payload_bytes=0,
            oldest_accepted_at=None,
        ),
    )
    request = CollectionControlRecord(
        source_id=_SOURCE,
        desired_state=CollectionDesiredState.RUNNING,
        generation=2,
        requested_at=at - timedelta(minutes=7),
    )
    return replace(
        snapshot,
        registered_sources=(source,),
        acquisition_surfaces=(surface,),
        collection_service=service,
        collection_records=(request,),
    )


def _source(payload: object) -> dict[str, object]:
    from industrial_phm.runtime.operations_app_composition import OperationsAppSnapshot

    assert isinstance(payload, OperationsAppSnapshot)
    result = project_web_source_setup(payload)
    items = result["sources"]
    assert isinstance(items, dict)
    row = items["items"][0]
    assert isinstance(row, dict)
    return row


def test_web_distinguishes_requested_running_live_events_and_history(tmp_path: Path) -> None:
    row = _source(_payload(tmp_path))
    assert row["collection_desired_state"] == "running"
    assert row["collection_service_state"] == "running"
    assert row["collection_service_heartbeat_fresh"] is True
    assert row["opcua_session_last_state"] == "CONNECTED"
    assert row["recent_connected_evidence"] is True
    assert row["last_live_received_at"] == (_AT - timedelta(seconds=8)).isoformat()
    assert row["last_live_receive_age_seconds"] == 8
    assert row["last_live_receive_fresh"] is True
    assert row["last_live_history_snapshot_id"] == 7
    assert row["last_live_history_batch_event_count"] == 2
    assert row["receipt_confirmed"] is False  # independent one-shot diagnostic store
    assert "opc.tcp" not in str(row)
    assert "batch-1" not in str(row)


def test_historical_connected_session_and_receipt_do_not_prove_live_now(
    tmp_path: Path,
) -> None:
    snapshot = _payload(tmp_path)
    from industrial_phm.runtime.operations_app_composition import OperationsAppSnapshot

    assert isinstance(snapshot, OperationsAppSnapshot)
    later = replace(snapshot, assessed_at=_AT + timedelta(minutes=3))
    row = _source(later)
    assert row["collection_desired_state"] == "running"
    assert row["collection_service_state"] == "running"
    assert row["collection_service_heartbeat_fresh"] is False
    assert row["opcua_session_last_state"] == "CONNECTED"
    assert row["recent_connected_evidence"] is False
    assert row["last_live_receive_fresh"] is False
    assert row["last_live_history_snapshot_id"] == 7

    # A restarted service must not inherit a prior worker's CONNECTED state.
    assert snapshot.collection_service is not None
    fresh_service = replace(snapshot.collection_service, started_at=_AT - timedelta(seconds=5))
    reboot = replace(snapshot, collection_service=fresh_service)
    assert _source(reboot)["recent_connected_evidence"] is False


def test_no_live_telemetry_and_store_error_remain_unverified(tmp_path: Path) -> None:
    from industrial_phm.runtime.operations_app_composition import OperationsAppSnapshot

    snapshot = _payload(tmp_path)
    assert isinstance(snapshot, OperationsAppSnapshot)
    unavailable = replace(
        snapshot,
        acquisition_surfaces=(),
        collection_service=None,
        system_errors=(
            SystemStateErrorEvidence(
                scope=f"live-data:{_SOURCE}",
                detail="test-internal failure",
                detected_at=_AT,
            ),
        ),
    )
    result = project_web_source_setup(unavailable)
    assert result["read_error_scopes"] == [f"live-data:{_SOURCE}"]
    row = _source(unavailable)
    assert row["live_telemetry_read_error"] is True
    assert row["collection_service_state"] is None
    assert row["recent_connected_evidence"] is False
    assert row["last_live_received_at"] is None
    assert row["last_live_history_snapshot_id"] is None


def test_future_dated_heartbeat_and_receipt_are_not_fresh(tmp_path: Path) -> None:
    from industrial_phm.runtime.operations_app_composition import OperationsAppSnapshot

    snapshot = _payload(tmp_path)
    assert isinstance(snapshot, OperationsAppSnapshot)
    early = replace(snapshot, assessed_at=_AT - timedelta(seconds=10))
    row = _source(early)
    assert row["collection_service_heartbeat_fresh"] is False
    assert row["last_live_receive_age_seconds"] is None
    assert row["last_live_receive_fresh"] is False
    assert row["recent_connected_evidence"] is False
