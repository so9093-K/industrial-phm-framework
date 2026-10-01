from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from industrial_phm.application import (
    AcquisitionSpoolFullError,
    AcquisitionSpoolStateError,
    ChannelSemanticBinding,
    MeasurementDefinition,
    OpcUaEventTimePolicy,
    RegisteredOpcUaDataChangeEvent,
)
from industrial_phm.connectors import (
    OpcUaNodeObservation,
    OpcUaSubscriptionNotification,
)
from industrial_phm.runtime import SqliteAcquisitionSpool, SqliteAcquisitionSpoolConfig

BASE = datetime(2026, 9, 28, 2, 0, tzinfo=UTC)


def _registered_event(
    *,
    channel_id: str = "vibration_x",
    collection_index: int = 0,
    received_at: datetime | None = None,
    value: float = 1.25,
) -> RegisteredOpcUaDataChangeEvent:
    received = BASE + timedelta(seconds=1) if received_at is None else received_at
    observation = OpcUaNodeObservation(
        channel_id=channel_id,
        node_id=f"ns=2;s={channel_id}",
        value=value,
        status_code=0,
        status_good=True,
        status_text="Good",
        variant_type="Double",
        source_timestamp=received - timedelta(milliseconds=20),
        server_timestamp=received - timedelta(milliseconds=10),
        received_at=received,
    )
    return RegisteredOpcUaDataChangeEvent(
        source_id="source-a",
        asset_id="pump-01",
        endpoint_url="opc.tcp://127.0.0.1:4840",
        measurement_point_id="drive-end",
        collection_index=collection_index,
        notification=OpcUaSubscriptionNotification(
            observation=observation,
            replayed=False,
        ),
        semantic_binding=ChannelSemanticBinding(
            source_id="source-a",
            channel_id=channel_id,
            version="site-a-semantics-v1",
            definition=MeasurementDefinition(
                observed_property="test measurement",
                unit="unit",
                unit_evidence="synthetic test mapping",
            ),
            interpretation_evidence="synthetic test mapping",
        ),
    )


def _spool(path: Path, *, max_events: int = 8) -> SqliteAcquisitionSpool:
    return SqliteAcquisitionSpool(
        SqliteAcquisitionSpoolConfig(
            path=path,
            max_events=max_events,
        )
    )


def test_spool_restores_pending_event_and_stable_active_batch_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "ingress.sqlite"
    first_spool = _spool(path)
    first_spool.initialize()
    accepted = first_spool.accept_opcua_event(
        _registered_event(collection_index=0),
        connection_epoch=1,
        event_index=0,
        accepted_at=BASE + timedelta(seconds=2),
        event_time_policy=OpcUaEventTimePolicy(),
    )
    batch = first_spool.assign_next_batch(
        batch_id="batch-001",
        max_events=16,
        created_at=BASE + timedelta(seconds=3),
    )

    assert batch is not None
    assert batch.events == (accepted,)
    assert first_spool.pending_event_count() == 1

    restored_spool = _spool(path)
    restored_spool.initialize()
    restored = restored_spool.get_active_batch()

    assert restored == batch
    restored_binding = restored.events[0].event.semantic_binding
    assert restored_binding is not None
    assert restored_binding.version == "site-a-semantics-v1"

    same_batch = restored_spool.assign_next_batch(
        batch_id="new-id-must-not-replace-active",
        max_events=16,
        created_at=BASE + timedelta(seconds=4),
    )
    assert same_batch == batch

    acknowledged = restored_spool.acknowledge_batch(
        "batch-001",
        acknowledged_at=BASE + timedelta(seconds=5),
    )
    assert acknowledged == 1
    assert restored_spool.pending_event_count() == 0
    assert restored_spool.get_active_batch() is None


def test_spool_assigns_oldest_unassigned_events_in_bounded_batch(tmp_path: Path) -> None:
    spool = _spool(tmp_path / "ingress.sqlite")
    events = []
    for index in range(3):
        events.append(
            spool.accept_opcua_event(
                _registered_event(
                    channel_id=f"channel-{index}",
                    collection_index=index,
                    received_at=BASE + timedelta(seconds=index + 1),
                    value=float(index),
                ),
                connection_epoch=1,
                event_index=index,
                accepted_at=BASE + timedelta(seconds=index + 2),
            )
        )

    batch = spool.assign_next_batch(
        batch_id="batch-001",
        max_events=2,
        created_at=BASE + timedelta(seconds=10),
    )
    assert batch is not None
    assert batch.events == tuple(events[:2])
    assert spool.pending_event_count() == 3

    spool.acknowledge_batch(
        "batch-001",
        acknowledged_at=BASE + timedelta(seconds=11),
    )
    second = spool.assign_next_batch(
        batch_id="batch-002",
        max_events=2,
        created_at=BASE + timedelta(seconds=12),
    )
    assert second is not None
    assert second.events == (events[2],)


def test_duplicate_local_delivery_is_idempotent_but_conflict_is_rejected(tmp_path: Path) -> None:
    spool = _spool(tmp_path / "ingress.sqlite")
    registered = _registered_event(collection_index=0)
    accepted_at = BASE + timedelta(seconds=2)

    first = spool.accept_opcua_event(
        registered,
        connection_epoch=1,
        event_index=0,
        accepted_at=accepted_at,
    )
    repeated = spool.accept_opcua_event(
        registered,
        connection_epoch=1,
        event_index=0,
        accepted_at=accepted_at + timedelta(seconds=10),
    )

    assert repeated == first
    assert repeated.event_time.ingested_at == accepted_at
    assert spool.pending_event_count() == 1

    with pytest.raises(
        AcquisitionSpoolStateError,
        match="conflicting durable payload",
    ):
        spool.accept_opcua_event(
            _registered_event(collection_index=0, value=9.5),
            connection_epoch=1,
            event_index=0,
            accepted_at=accepted_at,
        )


def test_spool_capacity_is_bounded_without_rejecting_idempotent_retry(tmp_path: Path) -> None:
    spool = _spool(tmp_path / "ingress.sqlite", max_events=1)
    registered = _registered_event(collection_index=0)
    accepted_at = BASE + timedelta(seconds=2)
    spool.accept_opcua_event(
        registered,
        connection_epoch=1,
        event_index=0,
        accepted_at=accepted_at,
    )

    same = spool.accept_opcua_event(
        registered,
        connection_epoch=1,
        event_index=0,
        accepted_at=accepted_at,
    )
    assert same.local_delivery_identity == ("source-a", 1, 0)

    with pytest.raises(AcquisitionSpoolFullError, match="max_events=1"):
        spool.accept_opcua_event(
            _registered_event(channel_id="temperature", collection_index=1),
            connection_epoch=1,
            event_index=1,
            accepted_at=BASE + timedelta(seconds=3),
        )

    assert spool.pending_event_count() == 1


def test_failed_downstream_path_keeps_active_batch_until_explicit_ack(tmp_path: Path) -> None:
    path = tmp_path / "ingress.sqlite"
    spool = _spool(path)
    event = spool.accept_opcua_event(
        _registered_event(),
        connection_epoch=1,
        event_index=0,
        accepted_at=BASE + timedelta(seconds=2),
    )
    batch = spool.assign_next_batch(
        batch_id="batch-001",
        max_events=10,
        created_at=BASE + timedelta(seconds=3),
    )
    assert batch is not None and batch.events == (event,)

    # Simulate writer/process failure by dropping the object without acknowledgement.
    recovered = _spool(path)
    assert recovered.get_active_batch() == batch
    assert recovered.pending_event_count() == 1


def test_acknowledge_rejects_unknown_batch(tmp_path: Path) -> None:
    spool = _spool(tmp_path / "ingress.sqlite")
    spool.initialize()

    with pytest.raises(AcquisitionSpoolStateError, match="does not exist"):
        spool.acknowledge_batch(
            "missing",
            acknowledged_at=BASE + timedelta(seconds=1),
        )


def test_connection_epoch_reservation_persists_across_spool_restart(tmp_path: Path) -> None:
    path = tmp_path / "ingress.sqlite"
    first = _spool(path)

    assert first.get_last_connection_epoch("source-a") == 0
    assert (
        first.reserve_next_connection_epoch(
            "source-a",
            expected_previous_epoch=0,
        )
        == 1
    )
    assert first.get_last_connection_epoch("source-a") == 1

    restarted = _spool(path)
    assert restarted.get_last_connection_epoch("source-a") == 1
    assert (
        restarted.reserve_next_connection_epoch(
            "source-a",
            expected_previous_epoch=1,
        )
        == 2
    )

    with pytest.raises(AcquisitionSpoolStateError, match="changed concurrently"):
        first.reserve_next_connection_epoch(
            "source-a",
            expected_previous_epoch=1,
        )

    assert restarted.get_last_connection_epoch("source-a") == 2
    assert restarted.get_last_connection_epoch("other-source") == 0


def test_backlog_reads_stay_consistent_while_events_are_accepted(tmp_path: Path) -> None:
    # Phase 10 E3: after a 20 s collector stall the writer read "0 pending" and then an
    # oldest_accepted_at from a just-committed event, and the invariant check stopped
    # the whole collection service. Stats are now read in one transaction.
    import threading

    config = SqliteAcquisitionSpoolConfig(tmp_path / "spool.sqlite")
    writer = SqliteAcquisitionSpool(config)
    reader = SqliteAcquisitionSpool(config)
    writer.pending_event_count()  # create schema
    stop = threading.Event()
    errors: list[Exception] = []

    def _read() -> None:
        while not stop.is_set():
            try:
                reader.pending_unassigned_stats()
                reader.telemetry_snapshot(sampled_at=BASE + timedelta(days=1))
            except Exception as error:
                errors.append(error)
                return

    thread = threading.Thread(target=_read)
    thread.start()
    try:
        for index in range(300):
            writer.accept_opcua_event(
                _registered_event(collection_index=index),
                connection_epoch=1,
                event_index=index,
                accepted_at=BASE + timedelta(seconds=2 + index),
            )
            if index % 50 == 49:
                batch = writer.assign_next_batch(
                    batch_id=f"batch-{index}", max_events=50, created_at=BASE
                )
                assert batch is not None
                writer.acknowledge_batch(batch.batch_id, acknowledged_at=BASE)
    finally:
        stop.set()
        thread.join()
    assert errors == []
