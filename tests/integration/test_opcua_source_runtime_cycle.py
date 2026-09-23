import asyncio
from datetime import datetime
from pathlib import Path

import pytest

import industrial_phm.application.source_cycle as source_cycle_module
from industrial_phm.application import (
    JsonSourceRepository,
    JsonSourceRuntimeRepository,
    OpcUaSourceConfig,
    ReceivedRegisteredOpcUaObservation,
    RegisteredOpcUaObservation,
    RegisteredSource,
    SourceLifecycleState,
    SourceReceiptEvidence,
    SourceRuntimeCycleFailureScope,
    SourceRuntimeCycleState,
    run_registered_opcua_source_cycle,
    transition_source_lifecycle,
)
from industrial_phm.connectors import (
    OpcUaNodeMapping,
    OpcUaRuntimeUnavailableError,
    OpcUaSourceError,
    OpcUaNodeObservation,
    OpcUaReadSnapshot,
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


def _received() -> ReceivedRegisteredOpcUaObservation:
    snapshot = OpcUaReadSnapshot(
        endpoint_url="opc.tcp://plc.example.test:4840",
        connected_at=datetime.fromisoformat("2026-09-23T01:00:00+00:00"),
        completed_at=datetime.fromisoformat("2026-09-23T01:00:01+00:00"),
        observations=(
            OpcUaNodeObservation(
                channel_id="vibration_x",
                node_id="ns=2;s=Machine/VibrationX",
                value=12.5,
                status_code=0,
                status_good=True,
                status_text="Good",
                variant_type="Double",
                source_timestamp=datetime.fromisoformat("2026-09-23T00:59:59+00:00"),
                server_timestamp=None,
                received_at=datetime.fromisoformat("2026-09-23T01:00:01+00:00"),
            ),
        ),
    )
    return ReceivedRegisteredOpcUaObservation(
        observation=RegisteredOpcUaObservation(
            source_id="opcua-source",
            asset_id="pump-01",
            measurement_point_id="drive-end",
            snapshot=snapshot,
        ),
        receipt=SourceReceiptEvidence(
            source_id="opcua-source",
            received_at=datetime.fromisoformat("2026-09-23T01:00:02+00:00"),
            observed_at=datetime.fromisoformat("2026-09-23T00:59:59+00:00"),
        ),
    )


def _repositories(
    tmp_path: Path,
) -> tuple[JsonSourceRepository, JsonSourceRuntimeRepository, RegisteredSource]:
    source = _source()
    source_repository = JsonSourceRepository(tmp_path / "source-registry.json")
    source_repository.register(source)
    transition_source_lifecycle(
        source_repository,
        source.source_id,
        SourceLifecycleState.ACTIVE,
        changed_at=datetime.fromisoformat("2026-09-23T09:30:00+09:00"),
    )
    runtime_repository = JsonSourceRuntimeRepository(tmp_path / "source-runtime.json")
    return source_repository, runtime_repository, source


def test_registered_opcua_source_cycle_records_receipt_and_keeps_active(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)
    received = _received()

    async def _receive(
        _source: RegisteredSource,
        *,
        received_at: datetime | None = None,
    ) -> ReceivedRegisteredOpcUaObservation:
        assert _source == source
        assert received_at is None
        return received

    monkeypatch.setattr(
        source_cycle_module,
        "receive_registered_opcua_source_observation",
        _receive,
    )

    result = asyncio.run(
        run_registered_opcua_source_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
        )
    )

    assert result.state == SourceRuntimeCycleState.SUCCEEDED
    assert result.received == received
    assert result.failure_scope is None
    assert result.lifecycle_after.state == SourceLifecycleState.ACTIVE
    assert runtime_repository.get_latest_receipt(source.source_id) == received.receipt


def test_registered_opcua_source_cycle_marks_connector_failure_as_source_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)

    async def _fail(
        _source: RegisteredSource,
        *,
        received_at: datetime | None = None,
    ) -> ReceivedRegisteredOpcUaObservation:
        raise OpcUaSourceError("configured OPC UA node read failed")

    monkeypatch.setattr(
        source_cycle_module,
        "receive_registered_opcua_source_observation",
        _fail,
    )

    result = asyncio.run(
        run_registered_opcua_source_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
        )
    )

    assert result.state == SourceRuntimeCycleState.FAILED
    assert result.received is None
    assert result.failure_scope == SourceRuntimeCycleFailureScope.SOURCE
    assert "configured OPC UA node read failed" in (result.message or "")
    lifecycle = source_repository.get_lifecycle(source.source_id)
    assert lifecycle.state == SourceLifecycleState.ERROR
    assert lifecycle.detail == result.message
    assert runtime_repository.get_latest_receipt(source.source_id) is None






def test_registered_opcua_source_cycle_marks_transport_oserror_as_source_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)

    async def _fail(
        _source: RegisteredSource,
        *,
        received_at: datetime | None = None,
    ) -> ReceivedRegisteredOpcUaObservation:
        raise ConnectionRefusedError("OPC UA endpoint connection refused")

    monkeypatch.setattr(
        source_cycle_module,
        "receive_registered_opcua_source_observation",
        _fail,
    )

    result = asyncio.run(
        run_registered_opcua_source_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
        )
    )

    assert result.state == SourceRuntimeCycleState.FAILED
    assert result.failure_scope == SourceRuntimeCycleFailureScope.SOURCE
    assert result.received is None
    assert "connection refused" in (result.message or "")
    assert source_repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ERROR


def test_registered_opcua_source_cycle_keeps_active_when_runtime_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)

    async def _fail(
        _source: RegisteredSource,
        *,
        received_at: datetime | None = None,
    ) -> ReceivedRegisteredOpcUaObservation:
        raise OpcUaRuntimeUnavailableError("OPC UA runtime is not installed")

    monkeypatch.setattr(
        source_cycle_module,
        "receive_registered_opcua_source_observation",
        _fail,
    )

    result = asyncio.run(
        run_registered_opcua_source_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
        )
    )

    assert result.state == SourceRuntimeCycleState.FAILED
    assert result.failure_scope == SourceRuntimeCycleFailureScope.PLATFORM
    assert result.received is None
    assert "runtime is not installed" in (result.message or "")
    assert source_repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE


def test_registered_opcua_source_cycle_keeps_active_on_caller_contract_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)

    async def _fail(
        _source: RegisteredSource,
        *,
        received_at: datetime | None = None,
    ) -> ReceivedRegisteredOpcUaObservation:
        raise ValueError("received_at must not be before OPC UA snapshot completion")

    monkeypatch.setattr(
        source_cycle_module,
        "receive_registered_opcua_source_observation",
        _fail,
    )

    result = asyncio.run(
        run_registered_opcua_source_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
        )
    )

    assert result.state == SourceRuntimeCycleState.FAILED
    assert result.failure_scope == SourceRuntimeCycleFailureScope.PLATFORM
    assert result.received is None
    assert source_repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE


def test_registered_opcua_source_cycle_keeps_active_on_unexpected_internal_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_repository, runtime_repository, source = _repositories(tmp_path)

    async def _fail(
        _source: RegisteredSource,
        *,
        received_at: datetime | None = None,
    ) -> ReceivedRegisteredOpcUaObservation:
        raise RuntimeError("unexpected connector integration failure")

    monkeypatch.setattr(
        source_cycle_module,
        "receive_registered_opcua_source_observation",
        _fail,
    )

    result = asyncio.run(
        run_registered_opcua_source_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
        )
    )

    assert result.state == SourceRuntimeCycleState.FAILED
    assert result.failure_scope == SourceRuntimeCycleFailureScope.PLATFORM
    assert result.received is None
    assert source_repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE


def test_registered_opcua_source_cycle_keeps_active_on_runtime_persistence_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_repository, _, source = _repositories(tmp_path)
    received = _received()

    async def _receive(
        _source: RegisteredSource,
        *,
        received_at: datetime | None = None,
    ) -> ReceivedRegisteredOpcUaObservation:
        return received

    monkeypatch.setattr(
        source_cycle_module,
        "receive_registered_opcua_source_observation",
        _receive,
    )
    runtime_path = tmp_path / "runtime-as-directory"
    runtime_path.mkdir()
    runtime_repository = JsonSourceRuntimeRepository(runtime_path)

    result = asyncio.run(
        run_registered_opcua_source_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
        )
    )

    assert result.state == SourceRuntimeCycleState.FAILED
    assert result.received == received
    assert result.failure_scope == SourceRuntimeCycleFailureScope.PLATFORM
    assert "not a file" in (result.message or "")
    assert source_repository.get_lifecycle(source.source_id).state == SourceLifecycleState.ACTIVE


def test_registered_opcua_source_cycle_skips_non_active_source_without_connector_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _source()
    source_repository = JsonSourceRepository(tmp_path / "source-registry.json")
    source_repository.register(source)
    runtime_repository = JsonSourceRuntimeRepository(tmp_path / "source-runtime.json")

    async def _unexpected(*args: object, **kwargs: object) -> ReceivedRegisteredOpcUaObservation:
        raise AssertionError("non-active OPC UA source must not perform connector I/O")

    monkeypatch.setattr(
        source_cycle_module,
        "receive_registered_opcua_source_observation",
        _unexpected,
    )

    result = asyncio.run(
        run_registered_opcua_source_cycle(
            source_repository,
            source_repository,
            runtime_repository,
            source.source_id,
            executed_at=datetime.fromisoformat("2026-09-23T10:00:05+09:00"),
        )
    )

    assert result.state == SourceRuntimeCycleState.SKIPPED
    assert result.received is None
    assert result.failure_scope is None
    assert result.lifecycle_after.state == SourceLifecycleState.REGISTERED
    assert runtime_repository.list_latest_receipts() == ()
