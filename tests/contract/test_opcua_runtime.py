import asyncio
import socket
from datetime import UTC, datetime

import pytest

asyncua = pytest.importorskip("asyncua")
ua = asyncua.ua

from industrial_phm.connectors import (  # noqa: E402
    OpcUaEndpointProbeConfig,
    OpcUaNodeMapping,
    OpcUaReadConfig,
    probe_opcua_endpoint,
    read_opcua_snapshot,
)


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_opcua_extra_reads_real_asyncua_datavalues() -> None:
    async def _run() -> None:
        port = _free_tcp_port()
        endpoint = f"opc.tcp://127.0.0.1:{port}/industrial-phm/"
        server = asyncua.Server()
        await server.init()
        server.set_endpoint(endpoint)
        namespace = await server.register_namespace("urn:industrial-phm:test")
        machine = await server.nodes.objects.add_object(namespace, "Machine")
        vibration = await machine.add_variable(namespace, "VibrationX", 0.0)
        temperature = await machine.add_variable(namespace, "Temperature", 0.0)

        source_at = datetime(2026, 9, 23, 1, 0, 0, tzinfo=UTC)
        server_at = datetime(2026, 9, 23, 1, 0, 1, tzinfo=UTC)
        await vibration.write_value(
            ua.DataValue(
                ua.Variant(12.5, ua.VariantType.Double),
                StatusCode=ua.StatusCode(ua.StatusCodes.Good),
                SourceTimestamp=source_at,
                ServerTimestamp=server_at,
            )
        )
        await temperature.write_value(
            ua.DataValue(
                ua.Variant(88.0, ua.VariantType.Double),
                StatusCode=ua.StatusCode(ua.StatusCodes.BadSensorFailure),
                SourceTimestamp=source_at,
                ServerTimestamp=server_at,
            )
        )

        async with server:
            probe = await probe_opcua_endpoint(
                OpcUaEndpointProbeConfig(endpoint_url=endpoint)
            )
            snapshot = await read_opcua_snapshot(
                OpcUaReadConfig(
                    endpoint_url=endpoint,
                    node_mappings=(
                        OpcUaNodeMapping("vibration_x", vibration.nodeid.to_string()),
                        OpcUaNodeMapping("temperature", temperature.nodeid.to_string()),
                    ),
                )
            )

        assert probe.endpoint_url == endpoint
        assert probe.connected_at.utcoffset() is not None
        assert probe.disconnected_at >= probe.connected_at

        assert len(snapshot.observations) == 2
        good, bad = snapshot.observations
        assert good.value == 12.5
        assert good.status_good is True
        assert good.status_code == ua.StatusCodes.Good
        assert good.source_timestamp == source_at
        assert good.server_timestamp is not None
        assert good.server_timestamp.utcoffset() is not None
        assert snapshot.connected_at <= good.received_at <= snapshot.completed_at

        assert bad.value is None
        assert bad.status_good is False
        assert bad.status_code == ua.StatusCodes.BadSensorFailure
        assert bad.source_timestamp == source_at
        assert bad.server_timestamp is not None
        assert bad.server_timestamp.utcoffset() is not None
        assert snapshot.connected_at <= bad.received_at <= snapshot.completed_at

    asyncio.run(_run())
