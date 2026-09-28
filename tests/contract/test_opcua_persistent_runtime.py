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
