import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from industrial_phm.application import (
    AcquisitionSpoolFullError,
    InMemoryOpcUaPersistentSessionEvidenceSink,
    JsonSourceRepository,
    OpcUaPersistentSessionPolicy,
    OpcUaPersistentSessionState,
    OpcUaSourceConfig,
    RegisteredSource,
    SourceLifecycleState,
    transition_source_lifecycle,
)
from industrial_phm.connectors import (
    OpcUaConnectorConnectionState,
    OpcUaConnectorQueueOverflow,
    OpcUaConnectorStateEvent,
    OpcUaNodeMapping,
    OpcUaNodeObservation,
    OpcUaSubscriptionNotification,
)
from industrial_phm.runtime import (
    SqliteAcquisitionSpool,
    SqliteAcquisitionSpoolConfig,
    run_registered_opcua_acquisition_worker,
)

BASE = datetime(2026, 1, 1, tzinfo=UTC)


class _FakePersistentConnector:
    def __init__(self) -> None:
        self.states: asyncio.Queue[OpcUaConnectorStateEvent] = asyncio.Queue()
        self.notifications: asyncio.Queue[OpcUaSubscriptionNotification | None] = asyncio.Queue()
        self.overflows: asyncio.Queue[OpcUaConnectorQueueOverflow] = asyncio.Queue()
        self.started = asyncio.Event()
        self.closed = False

    async def start(self) -> None:
        self.started.set()

    async def next_state(self, timeout: float | None = None) -> OpcUaConnectorStateEvent:
        del timeout
        return await self.states.get()

    async def next_notification(
        self,
        timeout: float | None = None,
    ) -> OpcUaSubscriptionNotification | None:
        del timeout
        return await self.notifications.get()

    async def next_queue_overflow(self) -> OpcUaConnectorQueueOverflow:
        return await self.overflows.get()

    async def close(self) -> None:
        self.closed = True


def _repositories(tmp_path: Path) -> tuple[JsonSourceRepository, RegisteredSource]:
    source = RegisteredSource(
        source_id="opcua-source",
        name="Pump OPC UA",
        config=OpcUaSourceConfig(
            endpoint_url="opc.tcp://plc.example.test:4840",
            asset_id="pump-01",
            measurement_point_id="drive-end",
            node_mappings=(
                OpcUaNodeMapping("vibration_x", "ns=2;s=Machine/VibrationX"),
                OpcUaNodeMapping("temperature", "ns=2;s=Machine/Temperature"),
            ),
        ),
        registered_at=BASE,
    )
    repository = JsonSourceRepository(tmp_path / "source-registry.json")
    repository.register(source)
    transition_source_lifecycle(
        repository,
        source.source_id,
        SourceLifecycleState.ACTIVE,
        changed_at=BASE + timedelta(seconds=1),
    )
    return repository, source


def _notification(
    *,
    channel_id: str,
    value: float,
    replayed: bool = False,
) -> OpcUaSubscriptionNotification:
    received_at = datetime.now(UTC) - timedelta(milliseconds=5)
    node_name = "VibrationX" if channel_id == "vibration_x" else "Temperature"
    return OpcUaSubscriptionNotification(
        observation=OpcUaNodeObservation(
            channel_id=channel_id,
            node_id=f"ns=2;s=Machine/{node_name}",
            value=value,
            status_code=0,
            status_good=True,
            status_text="Good",
            variant_type="Double",
            source_timestamp=received_at - timedelta(milliseconds=20),
            server_timestamp=received_at - timedelta(milliseconds=10),
            received_at=received_at,
        ),
        replayed=replayed,
    )


async def _wait_until(predicate, *, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() >= deadline:
            raise AssertionError("condition was not reached before timeout")
        await asyncio.sleep(0.001)


def test_worker_persists_events_across_reconnect_epochs_and_preserves_replay(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        repository, source = _repositories(tmp_path)
        spool = SqliteAcquisitionSpool(
            SqliteAcquisitionSpoolConfig(tmp_path / "spool.sqlite")
        )
        sink = InMemoryOpcUaPersistentSessionEvidenceSink()
        connector = _FakePersistentConnector()
        stop_event = asyncio.Event()

        worker = asyncio.create_task(
            run_registered_opcua_acquisition_worker(
                repository,
                repository,
                spool,
                sink,
                source.source_id,
                stop_event=stop_event,
                connector_factory=lambda _config: connector,
            )
        )
        await connector.started.wait()
        await asyncio.sleep(0)

        await connector.notifications.put(
            _notification(channel_id="vibration_x", value=1.0)
        )
        await _wait_until(lambda: spool.pending_event_count() == 1)

        now = datetime.now(UTC)
        await connector.states.put(
            OpcUaConnectorStateEvent(
                OpcUaConnectorConnectionState.RECONNECTING,
                now,
            )
        )
        await connector.states.put(
            OpcUaConnectorStateEvent(
                OpcUaConnectorConnectionState.CONNECTING,
                now + timedelta(milliseconds=1),
            )
        )
        await connector.states.put(
            OpcUaConnectorStateEvent(
                OpcUaConnectorConnectionState.CONNECTED,
                now + timedelta(milliseconds=2),
            )
        )
        await _wait_until(
            lambda: sink.list_session_evidence()[-1].state
            == OpcUaPersistentSessionState.CONNECTED
            and sink.list_session_evidence()[-1].connection_epoch == 2
        )

        await connector.notifications.put(
            _notification(channel_id="temperature", value=80.0, replayed=True)
        )
        await _wait_until(lambda: spool.pending_event_count() == 2)

        stop_event.set()
        result = await worker

        assert result.accepted_event_count == 2
        assert result.replayed_event_count == 1
        assert result.queue_overflow_count == 0
        assert connector.closed is True
        assert repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE

        evidence = sink.list_session_evidence()
        assert [item.state for item in evidence] == [
            OpcUaPersistentSessionState.DISCONNECTED,
            OpcUaPersistentSessionState.CONNECTING,
            OpcUaPersistentSessionState.CONNECTED,
            OpcUaPersistentSessionState.RECONNECT_WAIT,
            OpcUaPersistentSessionState.CONNECTING,
            OpcUaPersistentSessionState.CONNECTED,
            OpcUaPersistentSessionState.STOPPED,
        ]
        assert [item.connection_epoch for item in evidence] == [0, 0, 1, 1, 1, 2, 2]
        assert [item.reconnect_attempt_index for item in evidence] == [
            0,
            0,
            0,
            0,
            1,
            1,
            1,
        ]

        batch = spool.assign_next_batch(
            batch_id="inspect",
            max_events=10,
            created_at=datetime.now(UTC),
        )
        assert batch is not None
        assert [event.local_delivery_identity for event in batch.events] == [
            ("opcua-source", 1, 0),
            ("opcua-source", 2, 0),
        ]
        assert batch.events[1].event.notification.replayed is True

    asyncio.run(_run())


def test_worker_records_queue_overflow_before_reconnect(tmp_path: Path) -> None:
    async def _run() -> None:
        repository, source = _repositories(tmp_path)
        spool = SqliteAcquisitionSpool(
            SqliteAcquisitionSpoolConfig(tmp_path / "spool.sqlite")
        )
        sink = InMemoryOpcUaPersistentSessionEvidenceSink()
        connector = _FakePersistentConnector()
        stop_event = asyncio.Event()

        worker = asyncio.create_task(
            run_registered_opcua_acquisition_worker(
                repository,
                repository,
                spool,
                sink,
                source.source_id,
                stop_event=stop_event,
                connector_factory=lambda _config: connector,
            )
        )
        await connector.started.wait()
        await asyncio.sleep(0)

        now = datetime.now(UTC)
        await connector.overflows.put(OpcUaConnectorQueueOverflow(now))
        await connector.states.put(
            OpcUaConnectorStateEvent(
                OpcUaConnectorConnectionState.RECONNECTING,
                now + timedelta(milliseconds=1),
            )
        )
        await connector.states.put(
            OpcUaConnectorStateEvent(
                OpcUaConnectorConnectionState.CONNECTING,
                now + timedelta(milliseconds=2),
            )
        )
        await connector.states.put(
            OpcUaConnectorStateEvent(
                OpcUaConnectorConnectionState.CONNECTED,
                now + timedelta(milliseconds=3),
            )
        )
        await _wait_until(
            lambda: any(
                item.state == OpcUaPersistentSessionState.CONNECTED
                and item.connection_epoch == 2
                for item in sink.list_session_evidence()
            )
        )
        stop_event.set()
        result = await worker

        assert result.queue_overflow_count == 1
        reconnect_wait = next(
            item
            for item in sink.list_session_evidence()
            if item.state == OpcUaPersistentSessionState.RECONNECT_WAIT
        )
        assert reconnect_wait.detail == "subscription-queue-overflow"

    asyncio.run(_run())


def test_worker_stops_and_preserves_active_lifecycle_when_spool_rejects_event(
    tmp_path: Path,
) -> None:
    class _FailingSpool:
        def accept_opcua_event(self, *args, **kwargs):
            del args, kwargs
            raise AcquisitionSpoolFullError("spool full")

        def assign_next_batch(self, **kwargs):
            del kwargs
            raise AssertionError("not used")

        def pending_event_count(self) -> int:
            return 0

        def get_active_batch(self):
            return None

        def acknowledge_batch(self, batch_id: str, *, acknowledged_at: datetime) -> int:
            del batch_id, acknowledged_at
            raise AssertionError("not used")

    async def _run() -> None:
        repository, source = _repositories(tmp_path)
        sink = InMemoryOpcUaPersistentSessionEvidenceSink()
        connector = _FakePersistentConnector()
        stop_event = asyncio.Event()

        worker = asyncio.create_task(
            run_registered_opcua_acquisition_worker(
                repository,
                repository,
                _FailingSpool(),
                sink,
                source.source_id,
                stop_event=stop_event,
                connector_factory=lambda _config: connector,
            )
        )
        await connector.started.wait()
        await connector.notifications.put(
            _notification(channel_id="vibration_x", value=1.0)
        )

        with pytest.raises(AcquisitionSpoolFullError, match="spool full"):
            await worker

        assert connector.closed is True
        assert sink.list_session_evidence()[-1].state == OpcUaPersistentSessionState.STOPPED
        assert sink.list_session_evidence()[-1].detail == "worker-error:AcquisitionSpoolFullError"
        assert repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE

    asyncio.run(_run())


def test_worker_rejects_reconnect_policy_asyncua_cannot_honor(tmp_path: Path) -> None:
    repository, source = _repositories(tmp_path)
    spool = SqliteAcquisitionSpool(SqliteAcquisitionSpoolConfig(tmp_path / "spool.sqlite"))
    sink = InMemoryOpcUaPersistentSessionEvidenceSink()

    with pytest.raises(ValueError, match="reconnect_initial_delay_seconds"):
        asyncio.run(
            run_registered_opcua_acquisition_worker(
                repository,
                repository,
                spool,
                sink,
                source.source_id,
                stop_event=asyncio.Event(),
                session_policy=OpcUaPersistentSessionPolicy(
                    reconnect_initial_delay_seconds=0.5,
                ),
                connector_factory=lambda _config: _FakePersistentConnector(),
            )
        )
