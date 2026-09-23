import asyncio
from datetime import datetime
from types import SimpleNamespace
from typing import ClassVar

import pytest

import industrial_phm.connectors.opcua as opcua_module
from industrial_phm.connectors import (
    OpcUaEndpointProbeConfig,
    OpcUaEndpointProbeResult,
    OpcUaNodeMapping,
    OpcUaReadConfig,
    OpcUaRuntimeUnavailableError,
    OpcUaSourceError,
    probe_opcua_endpoint,
    read_opcua_snapshot,
)


class _FakeStatus:
    def __init__(self, value: int, *, good: bool) -> None:
        self.value = value
        self._good = good

    def is_good(self) -> bool:
        return self._good

    def __str__(self) -> str:
        return "Good" if self._good else "BadSensorFailure"


class _FakeNode:
    def __init__(self, data_value: object) -> None:
        self._data_value = data_value

    async def read_data_value(self, *, raise_on_bad_status: bool) -> object:
        assert raise_on_bad_status is False
        return self._data_value


class _FakeClient:
    values: ClassVar[dict[str, object]] = {}
    init_kwargs: ClassVar[dict[str, object]] = {}
    enter_count: ClassVar[int] = 0
    exit_count: ClassVar[int] = 0

    def __init__(self, **kwargs: object) -> None:
        type(self).init_kwargs = dict(kwargs)

    async def __aenter__(self) -> _FakeClient:
        type(self).enter_count += 1
        return self

    async def __aexit__(self, *args: object) -> None:
        type(self).exit_count += 1
        return None

    def get_node(self, node_id: str) -> _FakeNode:
        return _FakeNode(type(self).values[node_id])


def _data_value(
    value: object,
    *,
    status: _FakeStatus,
    source_timestamp: datetime | None = None,
    server_timestamp: datetime | None = None,
) -> object:
    return SimpleNamespace(
        Value=SimpleNamespace(Value=value, VariantType="Double"),
        StatusCode=status,
        SourceTimestamp=source_timestamp,
        ServerTimestamp=server_timestamp,
    )


def test_opcua_endpoint_probe_config_reuses_anonymous_endpoint_and_timeout_contract() -> None:
    with pytest.raises(ValueError, match="anonymous only"):
        OpcUaEndpointProbeConfig(
            endpoint_url="opc.tcp://user:secret@localhost:4840",
        )

    with pytest.raises(ValueError, match="positive finite"):
        OpcUaEndpointProbeConfig(
            endpoint_url="opc.tcp://localhost:4840",
            timeout_seconds=0.0,
        )


def test_opcua_endpoint_probe_records_connect_disconnect_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeClient.enter_count = 0
    _FakeClient.exit_count = 0
    monkeypatch.setattr(
        opcua_module,
        "import_module",
        lambda name: SimpleNamespace(Client=_FakeClient),
    )

    result = asyncio.run(
        probe_opcua_endpoint(
            OpcUaEndpointProbeConfig(
                endpoint_url="opc.tcp://localhost:4840/test/",
                timeout_seconds=1.5,
            )
        )
    )

    assert _FakeClient.init_kwargs == {
        "url": "opc.tcp://localhost:4840/test/",
        "timeout": 1.5,
        "auto_reconnect": False,
    }
    assert _FakeClient.enter_count == 1
    assert _FakeClient.exit_count == 1
    assert result.endpoint_url == "opc.tcp://localhost:4840/test/"
    assert result.connected_at.utcoffset() is not None
    assert result.disconnected_at >= result.connected_at


def test_opcua_endpoint_probe_result_rejects_time_regression() -> None:
    with pytest.raises(ValueError, match="must not be before"):
        OpcUaEndpointProbeResult(
            endpoint_url="opc.tcp://localhost:4840",
            connected_at=datetime.fromisoformat("2026-09-23T10:00:01+00:00"),
            disconnected_at=datetime.fromisoformat("2026-09-23T10:00:00+00:00"),
        )


def test_opcua_read_config_requires_anonymous_explicit_endpoint_and_unique_mapping() -> None:
    with pytest.raises(ValueError, match=r"opc\.tcp"):
        OpcUaReadConfig(
            endpoint_url="https://localhost:4840",
            node_mappings=(OpcUaNodeMapping("vibration_x", "ns=2;s=VibrationX"),),
        )

    with pytest.raises(ValueError, match="explicit port"):
        OpcUaReadConfig(
            endpoint_url="opc.tcp://localhost",
            node_mappings=(OpcUaNodeMapping("vibration_x", "ns=2;s=VibrationX"),),
        )

    with pytest.raises(ValueError, match="anonymous only"):
        OpcUaReadConfig(
            endpoint_url="opc.tcp://user:secret@localhost:4840",
            node_mappings=(OpcUaNodeMapping("vibration_x", "ns=2;s=VibrationX"),),
        )

    with pytest.raises(ValueError, match="unique channel_id"):
        OpcUaReadConfig(
            endpoint_url="opc.tcp://localhost:4840",
            node_mappings=(
                OpcUaNodeMapping("vibration_x", "ns=2;s=VibrationX"),
                OpcUaNodeMapping("vibration_x", "ns=2;s=VibrationY"),
            ),
        )


def test_opcua_snapshot_preserves_quality_and_protocol_timestamps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_at = datetime.fromisoformat("2026-09-23T10:00:00+00:00")
    server_at = datetime.fromisoformat("2026-09-23T10:00:01+00:00")
    _FakeClient.values = {
        "ns=2;s=VibrationX": _data_value(
            12.5,
            status=_FakeStatus(0, good=True),
            source_timestamp=source_at,
            server_timestamp=server_at,
        ),
        "ns=2;s=Temperature": _data_value(
            999.0,
            status=_FakeStatus(0x80030000, good=False),
            source_timestamp=source_at,
            server_timestamp=server_at,
        ),
    }
    monkeypatch.setattr(
        opcua_module,
        "import_module",
        lambda name: SimpleNamespace(Client=_FakeClient),
    )

    snapshot = asyncio.run(
        read_opcua_snapshot(
            OpcUaReadConfig(
                endpoint_url="opc.tcp://localhost:4840/test/",
                node_mappings=(
                    OpcUaNodeMapping("vibration_x", "ns=2;s=VibrationX"),
                    OpcUaNodeMapping("temperature", "ns=2;s=Temperature"),
                ),
                timeout_seconds=2.5,
            )
        )
    )

    assert _FakeClient.init_kwargs == {
        "url": "opc.tcp://localhost:4840/test/",
        "timeout": 2.5,
        "auto_reconnect": False,
    }
    assert snapshot.connected_at.utcoffset() is not None
    assert snapshot.completed_at >= snapshot.connected_at

    good, bad = snapshot.observations
    assert good.value == 12.5
    assert good.status_good is True
    assert good.status_code == 0
    assert good.source_timestamp == source_at
    assert good.server_timestamp == server_at
    assert good.received_at.utcoffset() is not None

    assert bad.status_good is False
    assert bad.status_code == 0x80030000
    assert bad.value is None
    assert bad.status_text == "BadSensorFailure"


def test_opcua_good_nonnumeric_value_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeClient.values = {
        "ns=2;s=State": _data_value(
            "running",
            status=_FakeStatus(0, good=True),
        )
    }
    monkeypatch.setattr(
        opcua_module,
        "import_module",
        lambda name: SimpleNamespace(Client=_FakeClient),
    )

    with pytest.raises(OpcUaSourceError, match="finite numeric scalar"):
        asyncio.run(
            read_opcua_snapshot(
                OpcUaReadConfig(
                    endpoint_url="opc.tcp://localhost:4840",
                    node_mappings=(OpcUaNodeMapping("state", "ns=2;s=State"),),
                )
            )
        )


def test_opcua_runtime_missing_extra_fails_with_install_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _missing(_: str) -> object:
        raise ModuleNotFoundError("No module named 'asyncua'", name="asyncua")

    monkeypatch.setattr(opcua_module, "import_module", _missing)

    with pytest.raises(OpcUaRuntimeUnavailableError, match="install the 'opcua' extra"):
        asyncio.run(
            read_opcua_snapshot(
                OpcUaReadConfig(
                    endpoint_url="opc.tcp://localhost:4840",
                    node_mappings=(OpcUaNodeMapping("vibration_x", "ns=2;s=VibrationX"),),
                )
            )
        )


def test_opcua_observation_rejects_naive_protocol_timestamps() -> None:
    from industrial_phm.connectors import OpcUaNodeObservation

    with pytest.raises(ValueError, match="source_timestamp must be timezone-aware"):
        OpcUaNodeObservation(
            channel_id="vibration_x",
            node_id="ns=2;s=VibrationX",
            value=1.0,
            status_code=0,
            status_good=True,
            status_text="Good",
            variant_type="Double",
            source_timestamp=datetime.fromisoformat("2026-09-23T10:00:00"),
            server_timestamp=None,
            received_at=datetime.fromisoformat("2026-09-23T10:00:01+00:00"),
        )


def test_opcua_runtime_does_not_mask_nested_dependency_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _broken(_: str) -> object:
        raise ModuleNotFoundError(
            "No module named 'some_nested_dependency'",
            name="some_nested_dependency",
        )

    monkeypatch.setattr(opcua_module, "import_module", _broken)

    with pytest.raises(ModuleNotFoundError, match="some_nested_dependency"):
        asyncio.run(
            read_opcua_snapshot(
                OpcUaReadConfig(
                    endpoint_url="opc.tcp://localhost:4840",
                    node_mappings=(OpcUaNodeMapping("vibration_x", "ns=2;s=VibrationX"),),
                )
            )
        )
