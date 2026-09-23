import asyncio
from datetime import datetime

import pytest

import industrial_phm.application.source_receipt as source_receipt_module
from industrial_phm.application import (
    OpcUaSourceConfig,
    RegisteredSource,
    receive_registered_opcua_source_observation,
)
from industrial_phm.connectors import (
    OpcUaNodeMapping,
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
                OpcUaNodeMapping(
                    channel_id="temperature",
                    node_id="ns=2;s=Machine/Temperature",
                ),
            ),
        ),
        registered_at=datetime.fromisoformat("2026-09-23T09:00:00+09:00"),
    )


def _snapshot(*, second_source_timestamp: datetime | None) -> OpcUaReadSnapshot:
    first_source_timestamp = datetime.fromisoformat("2026-09-23T01:00:00+00:00")
    received_at = datetime.fromisoformat("2026-09-23T01:00:02+00:00")
    return OpcUaReadSnapshot(
        endpoint_url="opc.tcp://plc.example.test:4840",
        connected_at=datetime.fromisoformat("2026-09-23T01:00:01+00:00"),
        completed_at=received_at,
        observations=(
            OpcUaNodeObservation(
                channel_id="vibration_x",
                node_id="ns=2;s=Machine/VibrationX",
                value=12.5,
                status_code=0,
                status_good=True,
                status_text="Good",
                variant_type="Double",
                source_timestamp=first_source_timestamp,
                server_timestamp=None,
                received_at=received_at,
            ),
            OpcUaNodeObservation(
                channel_id="temperature",
                node_id="ns=2;s=Machine/Temperature",
                value=None,
                status_code=0x80030000,
                status_good=False,
                status_text="BadSensorFailure",
                variant_type="Double",
                source_timestamp=second_source_timestamp,
                server_timestamp=None,
                received_at=received_at,
            ),
        ),
    )


def test_receive_registered_opcua_source_preserves_snapshot_and_latest_source_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot(
        second_source_timestamp=datetime.fromisoformat("2026-09-23T01:00:01+00:00")
    )

    async def _read(_config: object) -> OpcUaReadSnapshot:
        return snapshot

    monkeypatch.setattr(source_receipt_module, "read_opcua_snapshot", _read)

    received = asyncio.run(
        receive_registered_opcua_source_observation(
            _source(),
            received_at=datetime.fromisoformat("2026-09-23T01:00:03+00:00"),
        )
    )

    assert received.observation.asset_id == "pump-01"
    assert received.observation.measurement_point_id == "drive-end"
    assert received.observation.channels == ("vibration_x", "temperature")
    assert received.observation.snapshot == snapshot
    assert received.observation.observed_at == datetime.fromisoformat("2026-09-23T01:00:01+00:00")
    assert received.receipt.observed_at == received.observation.observed_at
    assert received.receipt.lag_seconds == 2.0


def test_receive_registered_opcua_source_keeps_observation_time_unavailable_when_any_node_lacks_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot(second_source_timestamp=None)

    async def _read(_config: object) -> OpcUaReadSnapshot:
        return snapshot

    monkeypatch.setattr(source_receipt_module, "read_opcua_snapshot", _read)

    received = asyncio.run(
        receive_registered_opcua_source_observation(
            _source(),
            received_at=datetime.fromisoformat("2026-09-23T01:00:03+00:00"),
        )
    )

    assert received.observation.observed_at is None
    assert received.receipt.observed_at is None
    assert received.receipt.lag_seconds is None
    assert received.receipt.lag_unavailable_reason == "source observation time is unavailable"


def test_receive_registered_opcua_source_rejects_receipt_before_snapshot_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot(
        second_source_timestamp=datetime.fromisoformat("2026-09-23T01:00:01+00:00")
    )

    async def _read(_config: object) -> OpcUaReadSnapshot:
        return snapshot

    monkeypatch.setattr(source_receipt_module, "read_opcua_snapshot", _read)

    with pytest.raises(ValueError, match="snapshot completion"):
        asyncio.run(
            receive_registered_opcua_source_observation(
                _source(),
                received_at=datetime.fromisoformat("2026-09-23T01:00:01+00:00"),
            )
        )
