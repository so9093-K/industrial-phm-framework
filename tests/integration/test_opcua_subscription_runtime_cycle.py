import asyncio
from datetime import datetime
from pathlib import Path

import pytest

import industrial_phm.application.source_subscription as source_subscription_module
from industrial_phm.application import (
    FileSourceConfig,
    JsonSourceRepository,
    JsonSourceRuntimeRepository,
    OpcUaSourceConfig,
    RegisteredOpcUaSubscription,
    RegisteredSource,
    SourceConnectionAttemptOutcome,
    SourceLifecycleState,
    SourceRuntimeCycleFailureScope,
    SourceRuntimeCycleState,
    run_registered_opcua_subscription_cycle,
    transition_source_lifecycle,
)
from industrial_phm.connectors import (
    OpcUaNodeMapping,
    OpcUaNodeObservation,
    OpcUaRuntimeUnavailableError,
    OpcUaSourceError,
    OpcUaSubscriptionCompletionReason,
    OpcUaSubscriptionNotification,
    OpcUaSubscriptionResult,
)


def _source() -> RegisteredSource:
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
            ),
        ),
        registered_at=datetime.fromisoformat("2026-09-23T09:00:00+09:00"),
    )


def _subscription() -> RegisteredOpcUaSubscription:
    return RegisteredOpcUaSubscription(
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
        subscription=OpcUaSubscriptionResult(
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
                    )
                ),
            ),
        ),
    )


def _repositories(
    tmp_path: Path,
    *,
    activate: bool = True,
) -> tuple[JsonSourceRepository, JsonSourceRuntimeRepository, RegisteredSource]:
    source = _source()
    source_repository = JsonSourceRepository(tmp_path / "source-registry.json")
    source_repository.register(source)
    if activate:
        transition_source_lifecycle(
            source_repository,
            source.source_id,
            SourceLifecycleState.ACTIVE,
            changed_at=datetime.fromisoformat("2026-09-23T09:30:00+09:00"),
        )
    runtime_repository = JsonSourceRuntimeRepository(tmp_path / "source-runtime.json")
    return source_repository, runtime_repository, source


def test_registered_opcua_subscription_cycle_records_attempt_without_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)
    subscription = _subscription()

    async def _collect(*args: object, **kwargs: object) -> RegisteredOpcUaSubscription:
        return subscription

    monkeypatch.setattr(
        source_subscription_module,
        "collect_registered_opcua_source_subscription",
        _collect,
    )

    result = asyncio.run(
        run_registered_opcua_subscription_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
            max_events=1,
        )
    )

    assert result.state == SourceRuntimeCycleState.SUCCEEDED
    assert result.subscription == subscription
    assert result.failure_scope is None
    assert result.lifecycle_after.state == SourceLifecycleState.ACTIVE
    assert runtime_repository.get_latest_receipt(source.source_id) is None

    attempt = runtime_repository.get_latest_connection_attempt(source.source_id)
    assert attempt is not None
    assert attempt.outcome == SourceConnectionAttemptOutcome.SUCCEEDED
    assert attempt.connected_at == subscription.subscription.connected_at
    assert attempt.completed_at == subscription.subscription.completed_at
    assert attempt.detail is None


def test_registered_opcua_subscription_cycle_skips_non_active_without_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path, activate=False)

    async def _unexpected(*args: object, **kwargs: object) -> RegisteredOpcUaSubscription:
        raise AssertionError("non-active source must not perform subscription I/O")

    monkeypatch.setattr(
        source_subscription_module,
        "collect_registered_opcua_source_subscription",
        _unexpected,
    )

    result = asyncio.run(
        run_registered_opcua_subscription_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T09:10:00+09:00"),
        )
    )

    assert result.state == SourceRuntimeCycleState.SKIPPED
    assert result.subscription is None
    assert result.failure_scope is None
    assert result.lifecycle_after == result.lifecycle_before
    assert runtime_repository.get_latest_connection_attempt(source.source_id) is None


def test_registered_opcua_subscription_cycle_skips_non_opcua_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    source_repository = JsonSourceRepository(tmp_path / "source-registry.json")
    source_repository.register(source)
    transition_source_lifecycle(
        source_repository,
        source.source_id,
        SourceLifecycleState.ACTIVE,
        changed_at=datetime.fromisoformat("2026-09-23T09:30:00+09:00"),
    )
    runtime_repository = JsonSourceRuntimeRepository(tmp_path / "source-runtime.json")

    async def _unexpected(*args: object, **kwargs: object) -> RegisteredOpcUaSubscription:
        raise AssertionError("non-OPC-UA source must not perform subscription I/O")

    monkeypatch.setattr(
        source_subscription_module,
        "collect_registered_opcua_source_subscription",
        _unexpected,
    )

    result = asyncio.run(
        run_registered_opcua_subscription_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T10:00:00+09:00"),
        )
    )

    assert result.state == SourceRuntimeCycleState.SKIPPED
    assert result.subscription is None
    assert result.failure_scope is None
    assert source_repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE
    assert runtime_repository.get_latest_connection_attempt(source.source_id) is None


def test_registered_opcua_subscription_cycle_marks_data_contract_failure_as_source_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)

    async def _fail(*args: object, **kwargs: object) -> RegisteredOpcUaSubscription:
        raise OpcUaSourceError("subscription DataValue is invalid")

    monkeypatch.setattr(
        source_subscription_module,
        "collect_registered_opcua_source_subscription",
        _fail,
    )

    result = asyncio.run(
        run_registered_opcua_subscription_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
        )
    )

    assert result.state == SourceRuntimeCycleState.FAILED
    assert result.failure_scope == SourceRuntimeCycleFailureScope.SOURCE
    assert result.subscription is None
    assert result.lifecycle_after.state == SourceLifecycleState.ERROR
    assert "subscription DataValue is invalid" in (result.message or "")

    attempt = runtime_repository.get_latest_connection_attempt(source.source_id)
    assert attempt is not None
    assert attempt.outcome == SourceConnectionAttemptOutcome.FAILED
    assert attempt.connected_at is None
    assert "subscription DataValue is invalid" in (attempt.detail or "")
    assert runtime_repository.get_latest_receipt(source.source_id) is None


def test_registered_opcua_subscription_cycle_preserves_active_on_transport_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)

    async def _fail(*args: object, **kwargs: object) -> RegisteredOpcUaSubscription:
        raise ConnectionRefusedError("OPC UA endpoint connection refused")

    monkeypatch.setattr(
        source_subscription_module,
        "collect_registered_opcua_source_subscription",
        _fail,
    )

    result = asyncio.run(
        run_registered_opcua_subscription_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
        )
    )

    assert result.state == SourceRuntimeCycleState.FAILED
    assert result.failure_scope == SourceRuntimeCycleFailureScope.SOURCE
    assert result.subscription is None
    assert result.lifecycle_after == result.lifecycle_before
    assert source_repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE

    attempt = runtime_repository.get_latest_connection_attempt(source.source_id)
    assert attempt is not None
    assert attempt.outcome == SourceConnectionAttemptOutcome.FAILED
    assert attempt.connected_at is None
    assert "connection refused" in (attempt.detail or "")


def test_registered_opcua_subscription_cycle_keeps_active_on_platform_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)

    async def _fail(*args: object, **kwargs: object) -> RegisteredOpcUaSubscription:
        raise OpcUaRuntimeUnavailableError("OPC UA runtime is not installed")

    monkeypatch.setattr(
        source_subscription_module,
        "collect_registered_opcua_source_subscription",
        _fail,
    )

    result = asyncio.run(
        run_registered_opcua_subscription_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
        )
    )

    assert result.state == SourceRuntimeCycleState.FAILED
    assert result.failure_scope == SourceRuntimeCycleFailureScope.PLATFORM
    assert result.subscription is None
    assert result.lifecycle_after == result.lifecycle_before
    assert source_repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE
    assert runtime_repository.get_latest_connection_attempt(source.source_id) is None


def test_registered_opcua_subscription_cycle_retains_result_when_attempt_persistence_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)
    subscription = _subscription()

    async def _collect(*args: object, **kwargs: object) -> RegisteredOpcUaSubscription:
        return subscription

    def _fail_persistence(_attempt: object) -> None:
        raise OSError("runtime state write failed")

    monkeypatch.setattr(
        source_subscription_module,
        "collect_registered_opcua_source_subscription",
        _collect,
    )
    monkeypatch.setattr(
        runtime_repository,
        "record_connection_attempt",
        _fail_persistence,
    )

    result = asyncio.run(
        run_registered_opcua_subscription_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
        )
    )

    assert result.state == SourceRuntimeCycleState.FAILED
    assert result.failure_scope == SourceRuntimeCycleFailureScope.PLATFORM
    assert result.subscription == subscription
    assert result.lifecycle_after == result.lifecycle_before
    assert "runtime state write failed" in (result.message or "")
    assert runtime_repository.get_latest_receipt(source.source_id) is None
