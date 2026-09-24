import asyncio
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

asyncua = pytest.importorskip("asyncua")
ua = asyncua.ua

from industrial_phm.application import (  # noqa: E402
    JsonSourceRepository,
    JsonSourceRuntimeRepository,
    OpcUaSourceConfig,
    RegisteredSource,
    SourceConnectionAttemptOutcome,
    SourceLifecycleState,
    SourcePollingPolicy,
    SourceRuntimeCycleState,
    collect_registered_opcua_source_subscription,
    poll_registered_source,
    receive_registered_opcua_source_observation,
    run_registered_opcua_subscription_cycle,
    transition_source_lifecycle,
)
from industrial_phm.connectors import (  # noqa: E402
    OpcUaBrowseConfig,
    OpcUaEndpointProbeConfig,
    OpcUaNodeMapping,
    OpcUaReadConfig,
    OpcUaSubscriptionCompletionReason,
    OpcUaSubscriptionConfig,
    browse_opcua_variables,
    collect_opcua_subscription_notifications,
    probe_opcua_endpoint,
    read_opcua_snapshot,
)


def _free_tcp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def test_opcua_extra_reads_real_asyncua_datavalues(tmp_path: Path) -> None:
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
        bearing = await machine.add_object(namespace, "Bearing")
        bearing_temperature = await bearing.add_variable(namespace, "BearingTemperature", 0.0)

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

        registered_source = RegisteredSource(
            source_id="ci-opcua",
            name="CI OPC UA",
            config=OpcUaSourceConfig(
                endpoint_url=endpoint,
                asset_id="ci-pump-01",
                measurement_point_id="drive-end",
                node_mappings=(
                    OpcUaNodeMapping("vibration_x", vibration.nodeid.to_string()),
                    OpcUaNodeMapping("temperature", temperature.nodeid.to_string()),
                ),
            ),
            registered_at=datetime(2026, 9, 23, 0, 59, 0, tzinfo=UTC),
        )

        assert isinstance(registered_source.config, OpcUaSourceConfig)

        source_repository = JsonSourceRepository(tmp_path / "source-registry.json")
        runtime_repository = JsonSourceRuntimeRepository(tmp_path / "source-runtime.json")
        source_repository.register(registered_source)
        transition_source_lifecycle(
            source_repository,
            registered_source.source_id,
            SourceLifecycleState.ACTIVE,
            changed_at=datetime(2026, 9, 23, 0, 59, 30, tzinfo=UTC),
        )

        async with server:
            probe = await probe_opcua_endpoint(OpcUaEndpointProbeConfig(endpoint_url=endpoint))
            browse = await browse_opcua_variables(
                OpcUaBrowseConfig(
                    endpoint_url=endpoint,
                    start_node_id=machine.nodeid.to_string(),
                    max_depth=2,
                    max_nodes=16,
                )
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
            received = await receive_registered_opcua_source_observation(registered_source)
            subscription_result = await collect_opcua_subscription_notifications(
                OpcUaSubscriptionConfig(
                    endpoint_url=endpoint,
                    node_mappings=(
                        OpcUaNodeMapping("vibration_x", vibration.nodeid.to_string()),
                        OpcUaNodeMapping("temperature", temperature.nodeid.to_string()),
                    ),
                    publishing_interval_ms=50.0,
                    collection_timeout_seconds=2.0,
                    max_events=2,
                    queue_maxsize=16,
                )
            )
            registered_subscription = await collect_registered_opcua_source_subscription(
                source_repository,
                source_repository,
                registered_source.source_id,
                publishing_interval_ms=50.0,
                collection_timeout_seconds=2.0,
                max_events=2,
                queue_maxsize=16,
            )
            subscription_cycle = await run_registered_opcua_subscription_cycle(
                source_repository,
                source_repository,
                runtime_repository,
                registered_source.source_id,
                publishing_interval_ms=50.0,
                collection_timeout_seconds=2.0,
                max_events=2,
                queue_maxsize=16,
            )
            subscription_attempt = runtime_repository.get_latest_connection_attempt(
                registered_source.source_id
            )
            subscription_receipt = runtime_repository.get_latest_receipt(
                registered_source.source_id
            )

            poll_results = await asyncio.to_thread(
                lambda: tuple(
                    poll_registered_source(
                        source_repository,
                        source_repository,
                        runtime_repository,
                        registered_source.source_id,
                        SourcePollingPolicy(interval_seconds=0.001, max_cycles=2),
                        sleep_fn=lambda _seconds: None,
                    )
                )
            )

        assert probe.endpoint_url == endpoint
        assert probe.connected_at.utcoffset() is not None
        assert probe.disconnected_at >= probe.connected_at

        assert browse.endpoint_url == endpoint
        assert browse.truncated is False
        assert browse.connected_at.utcoffset() is not None
        assert browse.completed_at >= browse.connected_at
        variables_by_id = {item.node_id: item for item in browse.variables}
        assert vibration.nodeid.to_string() in variables_by_id
        assert temperature.nodeid.to_string() in variables_by_id
        assert bearing_temperature.nodeid.to_string() in variables_by_id
        assert variables_by_id[vibration.nodeid.to_string()].browse_path == ("VibrationX",)
        assert variables_by_id[bearing_temperature.nodeid.to_string()].browse_path == (
            "Bearing",
            "BearingTemperature",
        )

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

        assert received.observation.source_id == "ci-opcua"
        assert received.observation.asset_id == "ci-pump-01"
        assert received.observation.channels == ("vibration_x", "temperature")
        assert received.observation.observed_at == source_at
        assert received.receipt.observed_at == source_at
        assert received.receipt.received_at >= received.observation.snapshot.completed_at

        assert subscription_result.completion_reason == OpcUaSubscriptionCompletionReason.MAX_EVENTS
        assert len(subscription_result.notifications) == 2
        notifications_by_channel = {
            item.observation.channel_id: item for item in subscription_result.notifications
        }
        assert set(notifications_by_channel) == {"vibration_x", "temperature"}
        assert notifications_by_channel["vibration_x"].observation.value == 12.5
        assert notifications_by_channel["vibration_x"].observation.status_good is True
        assert notifications_by_channel["temperature"].observation.value is None
        assert notifications_by_channel["temperature"].observation.status_good is False
        assert all(item.replayed is False for item in subscription_result.notifications)

        assert registered_subscription.source_id == registered_source.source_id
        assert registered_subscription.asset_id == registered_source.asset_id
        assert registered_subscription.endpoint_url == registered_source.config.endpoint_url
        assert (
            registered_subscription.measurement_point_id == registered_source.measurement_point_id
        )
        assert registered_subscription.node_mappings == registered_source.config.node_mappings
        assert (
            registered_subscription.subscription.completion_reason
            == OpcUaSubscriptionCompletionReason.MAX_EVENTS
        )
        assert len(registered_subscription.subscription.notifications) == 2
        assert tuple(event.collection_index for event in registered_subscription.events) == (0, 1)
        assert {event.channel_id for event in registered_subscription.events} == {
            "vibration_x",
            "temperature",
        }
        assert all(
            event.source_id == registered_source.source_id
            for event in registered_subscription.events
        )
        assert registered_subscription.coverage.configured_channel_ids == (
            "vibration_x",
            "temperature",
        )
        assert registered_subscription.coverage.missing_channel_ids == ()
        assert registered_subscription.coverage.has_full_channel_coverage is True

        assert subscription_cycle.state == SourceRuntimeCycleState.SUCCEEDED
        assert subscription_cycle.subscription is not None
        assert subscription_cycle.subscription.coverage.has_full_channel_coverage is True
        assert subscription_attempt is not None
        assert subscription_attempt.outcome == SourceConnectionAttemptOutcome.SUCCEEDED
        assert subscription_attempt.connected_at is not None
        assert subscription_attempt.completed_at >= subscription_attempt.connected_at
        assert subscription_receipt is None

        assert [result.state for result in poll_results] == [
            SourceRuntimeCycleState.SUCCEEDED,
            SourceRuntimeCycleState.SUCCEEDED,
        ]
        persisted_receipt = runtime_repository.get_latest_receipt(registered_source.source_id)
        assert persisted_receipt is not None
        persisted_attempt = runtime_repository.get_latest_connection_attempt(
            registered_source.source_id
        )
        assert persisted_attempt is not None
        assert persisted_attempt.outcome == SourceConnectionAttemptOutcome.SUCCEEDED
        assert persisted_attempt.connected_at is not None
        assert persisted_attempt.completed_at >= persisted_attempt.connected_at

    asyncio.run(_run())
