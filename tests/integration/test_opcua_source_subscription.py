import asyncio
from datetime import datetime
from pathlib import Path

import pytest

import industrial_phm.application.source_subscription as source_subscription_module
from industrial_phm.application import (
    FileSourceConfig,
    JsonSourceRepository,
    OpcUaSourceConfig,
    RegisteredOpcUaSubscription,
    RegisteredSource,
    SourceLifecycleState,
    collect_registered_opcua_source_subscription,
    transition_source_lifecycle,
)
from industrial_phm.connectors import (
    OpcUaNodeMapping,
    OpcUaNodeObservation,
    OpcUaSubscriptionCompletionReason,
    OpcUaSubscriptionConfig,
    OpcUaSubscriptionNotification,
    OpcUaSubscriptionResult,
)


def _opcua_source() -> RegisteredSource:
    return RegisteredSource(
        source_id="opcua-source",
        name="Pump OPC UA",
        config=OpcUaSourceConfig(
            endpoint_url="opc.tcp://plc.example.test:4840",
            asset_id="pump-01",
            measurement_point_id="drive-end",
            node_mappings=(
                OpcUaNodeMapping(
                    channel_id="vibration_x",
                    node_id="ns=2;s=Machine/VibrationX",
                ),
                OpcUaNodeMapping(
                    channel_id="temperature",
                    node_id="ns=2;s=Machine/Temperature",
                ),
            ),
            timeout_seconds=2.5,
        ),
        registered_at=datetime.fromisoformat("2026-09-23T09:00:00+09:00"),
    )


def _repositories(
    tmp_path: Path,
    *,
    activate: bool = True,
) -> tuple[JsonSourceRepository, RegisteredSource]:
    source = _opcua_source()
    repository = JsonSourceRepository(tmp_path / "source-registry.json")
    repository.register(source)
    if activate:
        transition_source_lifecycle(
            repository,
            source.source_id,
            SourceLifecycleState.ACTIVE,
            changed_at=datetime.fromisoformat("2026-09-23T09:30:00+09:00"),
        )
    return repository, source


def _subscription_result() -> OpcUaSubscriptionResult:
    return OpcUaSubscriptionResult(
        endpoint_url="opc.tcp://plc.example.test:4840",
        connected_at=datetime.fromisoformat("2026-09-23T01:00:00+00:00"),
        completed_at=datetime.fromisoformat("2026-09-23T01:00:02+00:00"),
        completion_reason=OpcUaSubscriptionCompletionReason.MAX_EVENTS,
        notifications=(
            OpcUaSubscriptionNotification(
                observation=OpcUaNodeObservation(
                    channel_id="vibration_x",
                    node_id="ns=2;s=Machine/VibrationX",
                    value=12.5,
                    status_code=0,
                    status_good=True,
                    status_text="Good",
                    variant_type="Double",
                    source_timestamp=datetime.fromisoformat(
                        "2026-09-23T00:59:59+00:00"
                    ),
                    server_timestamp=None,
                    received_at=datetime.fromisoformat("2026-09-23T01:00:01+00:00"),
                ),
                replayed=False,
            ),
        ),
    )


def test_registered_opcua_subscription_reuses_registered_mapping_and_runtime_bounds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, source = _repositories(tmp_path)
    assert isinstance(source.config, OpcUaSourceConfig)
    connector_result = _subscription_result()
    captured: OpcUaSubscriptionConfig | None = None

    async def _collect(config: OpcUaSubscriptionConfig) -> OpcUaSubscriptionResult:
        nonlocal captured
        captured = config
        return connector_result

    monkeypatch.setattr(
        source_subscription_module,
        "collect_opcua_subscription_notifications",
        _collect,
    )

    result = asyncio.run(
        collect_registered_opcua_source_subscription(
            repository,
            repository,
            source.source_id,
            publishing_interval_ms=125.0,
            collection_timeout_seconds=2.0,
            max_events=1,
            queue_maxsize=4,
        )
    )

    assert captured is not None
    assert captured.endpoint_url == source.config.endpoint_url
    assert captured.node_mappings == source.config.node_mappings
    assert captured.timeout_seconds == source.config.timeout_seconds
    assert captured.publishing_interval_ms == 125.0
    assert captured.collection_timeout_seconds == 2.0
    assert captured.max_events == 1
    assert captured.queue_maxsize == 4

    assert result.source_id == source.source_id
    assert result.asset_id == source.asset_id
    assert result.endpoint_url == source.config.endpoint_url
    assert result.measurement_point_id == source.measurement_point_id
    assert result.node_mappings == source.config.node_mappings
    assert result.subscription == connector_result
    assert len(result.node_mappings) == 2
    assert len(result.subscription.notifications) == 1


def test_registered_opcua_subscription_requires_active_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, source = _repositories(tmp_path, activate=False)

    async def _unexpected(_config: OpcUaSubscriptionConfig) -> OpcUaSubscriptionResult:
        raise AssertionError("non-active source must not perform subscription I/O")

    monkeypatch.setattr(
        source_subscription_module,
        "collect_opcua_subscription_notifications",
        _unexpected,
    )

    with pytest.raises(ValueError, match="active source lifecycle"):
        asyncio.run(
            collect_registered_opcua_source_subscription(
                repository,
                repository,
                source.source_id,
            )
        )


def test_registered_opcua_subscription_rejects_non_opcua_source(tmp_path: Path) -> None:
    source = RegisteredSource(
        source_id="file-source",
        name="Prepared file",
        config=FileSourceConfig(
            source_path="prepared.csv",
            asset_id="pump-01",
            channel_columns=("vibration_x",),
            sampling_rate_hz=1.0,
        ),
        registered_at=datetime.fromisoformat("2026-09-23T09:00:00+09:00"),
    )
    repository = JsonSourceRepository(tmp_path / "source-registry.json")
    repository.register(source)
    transition_source_lifecycle(
        repository,
        source.source_id,
        SourceLifecycleState.ACTIVE,
        changed_at=datetime.fromisoformat("2026-09-23T09:30:00+09:00"),
    )

    with pytest.raises(ValueError, match="OpcUaSourceConfig"):
        asyncio.run(
            collect_registered_opcua_source_subscription(
                repository,
                repository,
                source.source_id,
            )
        )


def test_registered_opcua_subscription_transport_failure_keeps_active(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository, source = _repositories(tmp_path)

    async def _fail(_config: OpcUaSubscriptionConfig) -> OpcUaSubscriptionResult:
        raise ConnectionRefusedError("OPC UA endpoint connection refused")

    monkeypatch.setattr(
        source_subscription_module,
        "collect_opcua_subscription_notifications",
        _fail,
    )

    with pytest.raises(ConnectionRefusedError, match="connection refused"):
        asyncio.run(
            collect_registered_opcua_source_subscription(
                repository,
                repository,
                source.source_id,
            )
        )

    assert repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE


def test_registered_opcua_subscription_rejects_notification_outside_registered_mapping() -> None:
    connector_result = OpcUaSubscriptionResult(
        endpoint_url="opc.tcp://plc.example.test:4840",
        connected_at=datetime.fromisoformat("2026-09-23T01:00:00+00:00"),
        completed_at=datetime.fromisoformat("2026-09-23T01:00:02+00:00"),
        completion_reason=OpcUaSubscriptionCompletionReason.MAX_EVENTS,
        notifications=(
            OpcUaSubscriptionNotification(
                observation=OpcUaNodeObservation(
                    channel_id="temperature",
                    node_id="ns=2;s=Machine/Temperature",
                    value=80.0,
                    status_code=0,
                    status_good=True,
                    status_text="Good",
                    variant_type="Double",
                    source_timestamp=None,
                    server_timestamp=None,
                    received_at=datetime.fromisoformat("2026-09-23T01:00:01+00:00"),
                )
            ),
        ),
    )

    with pytest.raises(ValueError, match="registered OPC UA mapping"):
        RegisteredOpcUaSubscription(
            source_id="opcua-source",
            asset_id="pump-01",
            endpoint_url="opc.tcp://plc.example.test:4840",
            measurement_point_id="drive-end",
            node_mappings=(
                OpcUaNodeMapping(
                    channel_id="vibration_x",
                    node_id="ns=2;s=Machine/VibrationX",
                ),
            ),
            subscription=connector_result,
        )
