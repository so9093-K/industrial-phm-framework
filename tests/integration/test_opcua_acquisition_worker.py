import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from industrial_phm.application import (
    AcquisitionSpoolFullError,
    ChannelSemanticBinding,
    InMemoryOpcUaPersistentSessionEvidenceSink,
    JsonSourceRepository,
    MeasurementDefinition,
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
    OpcUaSessionLostError,
    OpcUaSubscriptionOverflowError,
    SqliteAcquisitionSpool,
    SqliteAcquisitionSpoolConfig,
    SqliteAcquisitionTelemetryRepository,
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
            semantic_bindings=(
                ChannelSemanticBinding(
                    source_id="opcua-source",
                    channel_id="vibration_x",
                    version="site-a-semantics-v1",
                    definition=MeasurementDefinition(
                        observed_property="vibration velocity",
                        scope="x-axis",
                        unit="mm/s",
                        unit_evidence="site engineering channel map",
                    ),
                    interpretation_evidence="site engineering channel map revision 1",
                ),
                ChannelSemanticBinding(
                    source_id="opcua-source",
                    channel_id="temperature",
                    version="site-a-semantics-v1",
                    definition=MeasurementDefinition(
                        observed_property="temperature",
                        unit="Cel",
                        unit_evidence="site engineering channel map",
                    ),
                    interpretation_evidence="site engineering channel map revision 1",
                ),
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


def test_worker_ends_on_connection_loss_after_persisting_earlier_events(
    tmp_path: Path,
) -> None:
    # Phase 10: asyncua 2.0.1's in-client reconnect, after a long source stall,
    # reactivated the old session but dropped its subscription data. The worker
    # ends instead; the collection service starts a fresh session (new epoch, see
    # test_worker_process_restart_reserves_new_connection_epoch).
    async def _run() -> None:
        repository, source = _repositories(tmp_path)
        spool = SqliteAcquisitionSpool(SqliteAcquisitionSpoolConfig(tmp_path / "spool.sqlite"))
        sink = InMemoryOpcUaPersistentSessionEvidenceSink()
        telemetry = SqliteAcquisitionTelemetryRepository(tmp_path / "acquisition-telemetry.sqlite")
        connector = _FakePersistentConnector()

        worker = asyncio.create_task(
            run_registered_opcua_acquisition_worker(
                repository,
                repository,
                spool,
                sink,
                source.source_id,
                stop_event=asyncio.Event(),
                connector_factory=lambda _config: connector,
                telemetry_recorder=telemetry,
            )
        )
        await connector.started.wait()
        await asyncio.sleep(0)

        await connector.notifications.put(_notification(channel_id="vibration_x", value=1.0))
        await _wait_until(lambda: spool.pending_event_count() == 1)

        lost_at = sink.list_session_evidence()[-1].changed_at + timedelta(seconds=1)
        await connector.states.put(
            OpcUaConnectorStateEvent(OpcUaConnectorConnectionState.RECONNECTING, lost_at)
        )
        with pytest.raises(OpcUaSessionLostError, match="new session"):
            await worker

        assert connector.closed is True
        assert repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE
        evidence = sink.list_session_evidence()
        assert [item.state for item in evidence] == [
            OpcUaPersistentSessionState.DISCONNECTED,
            OpcUaPersistentSessionState.CONNECTING,
            OpcUaPersistentSessionState.CONNECTED,
            OpcUaPersistentSessionState.RECONNECT_WAIT,
            OpcUaPersistentSessionState.STOPPED,
        ]
        assert [item.connection_epoch for item in evidence] == [0, 0, 1, 1, 1]
        assert evidence[-1].detail == "worker-error:OpcUaSessionLostError"
        assert telemetry.get(source.source_id).failure.detail.startswith("OpcUaSessionLostError")


def test_worker_ends_with_explicit_overflow_so_a_fresh_session_restarts(tmp_path: Path) -> None:
    # Phase 10: after a burst overflowed the queue, asyncua's in-client reconnect
    # stayed disconnected indefinitely. The worker now ends explicitly instead.
    async def _run() -> None:
        repository, source = _repositories(tmp_path)
        spool = SqliteAcquisitionSpool(SqliteAcquisitionSpoolConfig(tmp_path / "spool.sqlite"))
        sink = InMemoryOpcUaPersistentSessionEvidenceSink()
        connector = _FakePersistentConnector()

        worker = asyncio.create_task(
            run_registered_opcua_acquisition_worker(
                repository,
                repository,
                spool,
                sink,
                source.source_id,
                stop_event=asyncio.Event(),
                connector_factory=lambda _config: connector,
            )
        )
        await connector.started.wait()
        await _wait_until(
            lambda: sink.list_session_evidence()[-1].state == OpcUaPersistentSessionState.CONNECTED
        )
        now = sink.list_session_evidence()[-1].changed_at
        await connector.overflows.put(OpcUaConnectorQueueOverflow(now))

        with pytest.raises(OpcUaSubscriptionOverflowError, match="notifications were dropped"):
            await worker
        last = sink.list_session_evidence()[-1]
        assert last.state == OpcUaPersistentSessionState.STOPPED
        assert last.detail == "worker-error:OpcUaSubscriptionOverflowError"

    asyncio.run(_run())


def test_worker_stops_and_preserves_active_lifecycle_when_spool_rejects_event(
    tmp_path: Path,
) -> None:
    class _FailingSpool:
        def __init__(self) -> None:
            self.connection_epoch = 0

        def get_last_connection_epoch(self, source_id: str) -> int:
            del source_id
            return self.connection_epoch

        def reserve_next_connection_epoch(
            self,
            source_id: str,
            *,
            expected_previous_epoch: int,
        ) -> int:
            del source_id
            if self.connection_epoch != expected_previous_epoch:
                raise AssertionError("unexpected epoch baseline")
            self.connection_epoch += 1
            return self.connection_epoch

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
        await connector.notifications.put(_notification(channel_id="vibration_x", value=1.0))

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


def test_worker_process_restart_reserves_new_connection_epoch(tmp_path: Path) -> None:
    async def _run() -> None:
        repository, source = _repositories(tmp_path)
        spool_path = tmp_path / "spool.sqlite"

        first_spool = SqliteAcquisitionSpool(SqliteAcquisitionSpoolConfig(spool_path))
        first_sink = InMemoryOpcUaPersistentSessionEvidenceSink()
        first_connector = _FakePersistentConnector()
        first_stop = asyncio.Event()
        first_worker = asyncio.create_task(
            run_registered_opcua_acquisition_worker(
                repository,
                repository,
                first_spool,
                first_sink,
                source.source_id,
                stop_event=first_stop,
                connector_factory=lambda _config: first_connector,
            )
        )
        await first_connector.started.wait()
        await first_connector.notifications.put(_notification(channel_id="vibration_x", value=1.0))
        await _wait_until(lambda: first_spool.pending_event_count() == 1)
        first_stop.set()
        await first_worker

        assert first_spool.get_last_connection_epoch(source.source_id) == 1

        restarted_spool = SqliteAcquisitionSpool(SqliteAcquisitionSpoolConfig(spool_path))
        second_sink = InMemoryOpcUaPersistentSessionEvidenceSink()
        second_connector = _FakePersistentConnector()
        second_stop = asyncio.Event()
        second_worker = asyncio.create_task(
            run_registered_opcua_acquisition_worker(
                repository,
                repository,
                restarted_spool,
                second_sink,
                source.source_id,
                stop_event=second_stop,
                connector_factory=lambda _config: second_connector,
            )
        )
        await second_connector.started.wait()
        await second_connector.notifications.put(
            _notification(channel_id="temperature", value=80.0)
        )
        await _wait_until(lambda: restarted_spool.pending_event_count() == 2)
        second_stop.set()
        await second_worker

        second_evidence = second_sink.list_session_evidence()
        assert second_evidence[0].state == OpcUaPersistentSessionState.DISCONNECTED
        assert second_evidence[0].connection_epoch == 1
        assert (
            next(
                item
                for item in second_evidence
                if item.state == OpcUaPersistentSessionState.CONNECTED
            ).connection_epoch
            == 2
        )
        assert restarted_spool.get_last_connection_epoch(source.source_id) == 2

        batch = restarted_spool.assign_next_batch(
            batch_id="restart-inspect",
            max_events=10,
            created_at=datetime.now(UTC),
        )
        assert batch is not None
        assert [event.local_delivery_identity for event in batch.events] == [
            ("opcua-source", 1, 0),
            ("opcua-source", 2, 0),
        ]

    asyncio.run(_run())


def test_notification_ready_with_connection_loss_is_persisted_before_the_worker_ends(
    tmp_path: Path,
) -> None:
    # A notification already dequeued in the same wakeup as RECONNECTING arrived on the
    # current session; it must not be dropped by ending the worker first.
    async def _run() -> None:
        repository, source = _repositories(tmp_path)
        spool = SqliteAcquisitionSpool(SqliteAcquisitionSpoolConfig(tmp_path / "spool.sqlite"))
        sink = InMemoryOpcUaPersistentSessionEvidenceSink()
        connector = _FakePersistentConnector()
        worker = asyncio.create_task(
            run_registered_opcua_acquisition_worker(
                repository,
                repository,
                spool,
                sink,
                source.source_id,
                stop_event=asyncio.Event(),
                connector_factory=lambda _config: connector,
            )
        )
        await connector.started.wait()
        await _wait_until(
            lambda: sink.list_session_evidence()[-1].state == OpcUaPersistentSessionState.CONNECTED
        )
        lost_at = datetime.now(UTC)
        # Both become ready before the worker's next wakeup.
        connector.notifications.put_nowait(_notification(channel_id="vibration_x", value=7.0))
        connector.states.put_nowait(
            OpcUaConnectorStateEvent(OpcUaConnectorConnectionState.RECONNECTING, lost_at)
        )
        with pytest.raises(OpcUaSessionLostError):
            await worker
        assert spool.pending_event_count() == 1

    asyncio.run(_run())


def test_notification_ready_with_queue_overflow_is_persisted_before_the_worker_ends(
    tmp_path: Path,
) -> None:
    # Overflow already lost notifications; one that was dequeued in the same wakeup
    # is in application ownership and is stored before the worker ends.
    async def _run() -> None:
        repository, source = _repositories(tmp_path)
        spool = SqliteAcquisitionSpool(SqliteAcquisitionSpoolConfig(tmp_path / "spool.sqlite"))
        sink = InMemoryOpcUaPersistentSessionEvidenceSink()
        connector = _FakePersistentConnector()
        worker = asyncio.create_task(
            run_registered_opcua_acquisition_worker(
                repository,
                repository,
                spool,
                sink,
                source.source_id,
                stop_event=asyncio.Event(),
                connector_factory=lambda _config: connector,
            )
        )
        await connector.started.wait()
        await _wait_until(
            lambda: sink.list_session_evidence()[-1].state == OpcUaPersistentSessionState.CONNECTED
        )
        connector.notifications.put_nowait(_notification(channel_id="vibration_x", value=7.0))
        connector.overflows.put_nowait(OpcUaConnectorQueueOverflow(datetime.now(UTC)))
        with pytest.raises(OpcUaSubscriptionOverflowError):
            await worker
        assert spool.pending_event_count() == 1

    asyncio.run(_run())


def test_notification_ready_with_stop_is_persisted_before_graceful_shutdown(
    tmp_path: Path,
) -> None:
    # A notification already dequeued when stop is requested is application-owned
    # and must be durable before the worker reports a graceful STOPPED state.
    async def _run() -> None:
        repository, source = _repositories(tmp_path)
        spool = SqliteAcquisitionSpool(SqliteAcquisitionSpoolConfig(tmp_path / "spool.sqlite"))
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
        await _wait_until(
            lambda: sink.list_session_evidence()[-1].state == OpcUaPersistentSessionState.CONNECTED
        )
        # Make both conditions ready without yielding between them.
        connector.notifications.put_nowait(_notification(channel_id="vibration_x", value=7.0))
        stop_event.set()

        result = await worker

        assert result.accepted_event_count == 1
        assert spool.pending_event_count() == 1
        last = sink.list_session_evidence()[-1]
        assert last.state == OpcUaPersistentSessionState.STOPPED
        assert last.detail == "stop-requested"

    asyncio.run(_run())
