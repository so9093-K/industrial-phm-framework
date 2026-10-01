import asyncio
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

asyncua = pytest.importorskip("asyncua")
ua = asyncua.ua

from industrial_phm.application import (  # noqa: E402
    InMemoryOpcUaPersistentSessionEvidenceSink,
    JsonSourceRepository,
    OpcUaPersistentSessionPolicy,
    OpcUaPersistentSessionState,
    OpcUaSourceConfig,
    RegisteredSource,
    SourceLifecycleState,
    transition_source_lifecycle,
)
from industrial_phm.connectors import OpcUaNodeMapping  # noqa: E402
from industrial_phm.runtime import (  # noqa: E402
    SqliteAcquisitionSpool,
    SqliteAcquisitionSpoolConfig,
    run_registered_opcua_acquisition_worker,
)


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_until(predicate, *, timeout: float = 5.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() >= deadline:
            raise AssertionError("condition was not reached before timeout")
        await asyncio.sleep(0.01)


def test_persistent_worker_collects_real_asyncua_datachange_to_durable_spool(
    tmp_path: Path,
) -> None:
    async def _run() -> None:
        port = _free_tcp_port()
        endpoint = f"opc.tcp://127.0.0.1:{port}/industrial-phm-persistent/"
        server = asyncua.Server()
        await server.init()
        server.set_endpoint(endpoint)
        namespace = await server.register_namespace("urn:industrial-phm:persistent-test")
        machine = await server.nodes.objects.add_object(namespace, "Machine")
        vibration = await machine.add_variable(namespace, "VibrationX", 0.0)

        source = RegisteredSource(
            source_id="persistent-opcua",
            name="Persistent OPC UA",
            config=OpcUaSourceConfig(
                endpoint_url=endpoint,
                asset_id="pump-01",
                measurement_point_id="drive-end",
                node_mappings=(
                    OpcUaNodeMapping(
                        "vibration_x",
                        vibration.nodeid.to_string(),
                    ),
                ),
                timeout_seconds=1.0,
            ),
            registered_at=datetime(2026, 9, 28, 0, 0, tzinfo=UTC),
        )
        repository = JsonSourceRepository(tmp_path / "source-registry.json")
        repository.register(source)
        transition_source_lifecycle(
            repository,
            source.source_id,
            SourceLifecycleState.ACTIVE,
            changed_at=datetime(2026, 9, 28, 0, 0, 1, tzinfo=UTC),
        )
        spool = SqliteAcquisitionSpool(SqliteAcquisitionSpoolConfig(tmp_path / "spool.sqlite"))
        sink = InMemoryOpcUaPersistentSessionEvidenceSink()
        stop_event = asyncio.Event()

        async with server:
            worker = asyncio.create_task(
                run_registered_opcua_acquisition_worker(
                    repository,
                    repository,
                    spool,
                    sink,
                    source.source_id,
                    stop_event=stop_event,
                    session_policy=OpcUaPersistentSessionPolicy(
                        publishing_interval_ms=50.0,
                        queue_maxsize=16,
                        reconnect_max_delay_seconds=1.0,
                    ),
                )
            )
            await _wait_until(
                lambda: any(
                    item.state == OpcUaPersistentSessionState.CONNECTED
                    for item in sink.list_session_evidence()
                )
            )
            await _wait_until(lambda: spool.pending_event_count() >= 1)
            baseline_count = spool.pending_event_count()

            source_at = datetime(2026, 9, 28, 0, 1, tzinfo=UTC)
            await vibration.write_value(
                ua.DataValue(
                    ua.Variant(42.5, ua.VariantType.Double),
                    StatusCode=ua.StatusCode(ua.StatusCodes.Good),
                    SourceTimestamp=source_at,
                    ServerTimestamp=source_at + timedelta(milliseconds=1),
                )
            )
            await _wait_until(lambda: spool.pending_event_count() > baseline_count)

            stop_event.set()
            result = await worker

        assert result.accepted_event_count >= baseline_count + 1
        assert result.queue_overflow_count == 0
        assert sink.list_session_evidence()[-1].state == OpcUaPersistentSessionState.STOPPED

        batch = spool.assign_next_batch(
            batch_id="inspect-real",
            max_events=100,
            created_at=datetime.now(UTC),
        )
        assert batch is not None
        matching = [
            event for event in batch.events if event.event.notification.observation.value == 42.5
        ]
        assert len(matching) == 1
        event = matching[0]
        assert event.connection_epoch == 1
        assert event.event_time.source_timestamp == source_at
        assert event.event_time.event_at == source_at
        assert event.event.notification.replayed is False

    asyncio.run(_run())


async def _server_with_variables(count: int):
    port = _free_tcp_port()
    endpoint = f"opc.tcp://127.0.0.1:{port}/industrial-phm-burst/"
    server = asyncua.Server()
    await server.init()
    server.set_endpoint(endpoint)
    namespace = await server.register_namespace("urn:industrial-phm:burst-test")
    machine = await server.nodes.objects.add_object(namespace, "Machine")
    variables = [await machine.add_variable(namespace, f"V{index}", 0.0) for index in range(count)]
    return server, endpoint, variables


def _registered(tmp_path: Path, endpoint: str, variables) -> tuple[JsonSourceRepository, str]:
    source = RegisteredSource(
        source_id="burst-opcua",
        name="Burst OPC UA",
        config=OpcUaSourceConfig(
            endpoint_url=endpoint,
            asset_id="pump-01",
            node_mappings=tuple(
                OpcUaNodeMapping(f"v{index}", variable.nodeid.to_string())
                for index, variable in enumerate(variables)
            ),
            timeout_seconds=1.0,
        ),
        registered_at=datetime(2026, 9, 28, 0, 0, tzinfo=UTC),
    )
    repository = JsonSourceRepository(tmp_path / "source-registry.json")
    repository.register(source)
    transition_source_lifecycle(
        repository,
        source.source_id,
        SourceLifecycleState.ACTIVE,
        changed_at=datetime(2026, 9, 28, 0, 0, 1, tzinfo=UTC),
    )
    return repository, source.source_id


def test_arrival_time_and_pipeline_metrics_follow_each_real_notification(tmp_path: Path) -> None:
    from industrial_phm.runtime.pipeline_metrics import PipelineMetrics

    async def _run() -> None:
        server, endpoint, variables = await _server_with_variables(5)
        repository, source_id = _registered(tmp_path, endpoint, variables)
        spool = SqliteAcquisitionSpool(SqliteAcquisitionSpoolConfig(tmp_path / "spool.sqlite"))
        metrics = PipelineMetrics()
        stop = asyncio.Event()
        async with server:
            worker = asyncio.create_task(
                run_registered_opcua_acquisition_worker(
                    repository,
                    repository,
                    spool,
                    InMemoryOpcUaPersistentSessionEvidenceSink(),
                    source_id,
                    stop_event=stop,
                    session_policy=OpcUaPersistentSessionPolicy(publishing_interval_ms=50.0),
                    metrics=metrics,
                )
            )
            await _wait_until(lambda: spool.pending_event_count() >= 5)
            for index, variable in enumerate(variables):
                await variable.write_value(float(index + 1))
            await _wait_until(lambda: spool.pending_event_count() >= 10)
            stop.set()
            await worker
        report = metrics.take()
        assert report["counts"]["arrived"] == report["counts"]["dequeued"] >= 10
        assert report["latency"]["arrival_to_dequeue"]["n"] >= 10
        assert report["queue"]["maxsize"] == 4096
        batch = spool.assign_next_batch(
            batch_id="inspect", max_events=100, created_at=datetime.now(UTC)
        )
        for event in batch.events:
            # received_at is the client arrival, not later than durable acceptance.
            assert event.event.notification.observation.received_at <= event.event_time.ingested_at

    asyncio.run(_run())


def test_queue_overflow_ends_the_worker_instead_of_wedging_the_client(tmp_path: Path) -> None:
    # Phase 10: a burst overflowed the subscription queue and asyncua's in-client
    # reconnect then stayed disconnected indefinitely. Now the worker ends explicitly.
    from industrial_phm.runtime import OpcUaSubscriptionOverflowError

    async def _run() -> None:
        server, endpoint, variables = await _server_with_variables(20)
        repository, source_id = _registered(tmp_path, endpoint, variables)
        spool = SqliteAcquisitionSpool(SqliteAcquisitionSpoolConfig(tmp_path / "spool.sqlite"))
        sink = InMemoryOpcUaPersistentSessionEvidenceSink()
        async with server:
            worker = asyncio.create_task(
                run_registered_opcua_acquisition_worker(
                    repository,
                    repository,
                    spool,
                    sink,
                    source_id,
                    stop_event=asyncio.Event(),
                    session_policy=OpcUaPersistentSessionPolicy(
                        publishing_interval_ms=50.0, queue_maxsize=4
                    ),
                )
            )
            # The initial values of 20 monitored items already exceed a queue of 4.
            with pytest.raises(OpcUaSubscriptionOverflowError):
                await asyncio.wait_for(worker, timeout=10)
        assert sink.list_session_evidence()[-1].state == OpcUaPersistentSessionState.STOPPED

    asyncio.run(_run())
