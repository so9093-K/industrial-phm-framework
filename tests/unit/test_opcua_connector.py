import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import ClassVar

import pytest

import industrial_phm.connectors.opcua as opcua_module
from industrial_phm.connectors import (
    OpcUaBrowseConfig,
    OpcUaNodeMapping,
    OpcUaReadConfig,
    OpcUaRuntimeUnavailableError,
    OpcUaSourceError,
    OpcUaSubscriptionCompletionReason,
    OpcUaSubscriptionConfig,
    browse_opcua_variables,
    collect_opcua_subscription_notifications,
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


class _FakeBrowseNodeId:
    def __init__(self, value: str) -> None:
        self._value = value

    def to_string(self) -> str:
        return self._value


class _FakeBrowseNode:
    def __init__(
        self,
        node_id: str,
        *,
        node_class: str,
        browse_name: str,
        display_name: str,
        children: tuple[_FakeBrowseNode, ...] = (),
    ) -> None:
        self.nodeid = _FakeBrowseNodeId(node_id)
        self._node_class = node_class
        self._browse_name = browse_name
        self._display_name = display_name
        self._children = children

    async def get_children(self) -> list[_FakeBrowseNode]:
        return list(self._children)

    async def read_node_class(self) -> str:
        return self._node_class

    async def read_browse_name(self) -> object:
        return SimpleNamespace(Name=self._browse_name)

    async def read_display_name(self) -> object:
        return SimpleNamespace(Text=self._display_name)

    async def read_data_value(self, **_: object) -> object:
        raise AssertionError("browse must not read DataValue")


class _FakeBrowseClient:
    root: ClassVar[_FakeBrowseNode]
    init_kwargs: ClassVar[dict[str, object]] = {}
    exit_completed_at: ClassVar[datetime | None] = None

    def __init__(self, **kwargs: object) -> None:
        type(self).init_kwargs = dict(kwargs)

    async def __aenter__(self) -> _FakeBrowseClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        await asyncio.sleep(0.001)
        type(self).exit_completed_at = datetime.now(UTC)
        return None

    def get_node(self, node_id: str) -> _FakeBrowseNode:
        assert node_id == "i=85"
        return type(self).root


class _FakeSubscriptionNode:
    def __init__(self, node_id: str) -> None:
        self.nodeid = _FakeBrowseNodeId(node_id)


class _FakeDataChangeEvent:
    def __init__(
        self,
        node_id: str,
        data_value: object,
        *,
        replayed: bool = False,
    ) -> None:
        self.node = _FakeSubscriptionNode(node_id)
        self.value = None
        self.data = SimpleNamespace(monitored_item=SimpleNamespace(Value=data_value))
        self.replayed = replayed


class _FakeSubscription:
    events: ClassVar[list[object]] = []
    publishing_interval_ms: ClassVar[float | None] = None
    queue_maxsize: ClassVar[int | None] = None
    subscribed_node_ids: ClassVar[tuple[str, ...]] = ()
    next_timeouts: ClassVar[list[float | None]] = []
    enter_count: ClassVar[int] = 0
    exit_count: ClassVar[int] = 0
    exit_completed_at: ClassVar[datetime | None] = None

    async def __aenter__(self) -> _FakeSubscription:
        type(self).enter_count += 1
        return self

    async def __aexit__(self, *args: object) -> None:
        await asyncio.sleep(0.001)
        type(self).exit_count += 1
        type(self).exit_completed_at = datetime.now(UTC)
        return None

    async def subscribe_data_change(
        self,
        nodes: list[_FakeSubscriptionNode],
    ) -> None:
        type(self).subscribed_node_ids = tuple(node.nodeid.to_string() for node in nodes)

    async def next_event(self, timeout: float | None = None) -> object | None:
        type(self).next_timeouts.append(timeout)
        if not type(self).events:
            return None
        return type(self).events.pop(0)


class _FakeSubscriptionClient:
    init_kwargs: ClassVar[dict[str, object]] = {}
    enter_count: ClassVar[int] = 0
    exit_count: ClassVar[int] = 0
    exit_completed_at: ClassVar[datetime | None] = None

    def __init__(self, **kwargs: object) -> None:
        type(self).init_kwargs = dict(kwargs)

    async def __aenter__(self) -> _FakeSubscriptionClient:
        type(self).enter_count += 1
        return self

    async def __aexit__(self, *args: object) -> None:
        await asyncio.sleep(0.001)
        type(self).exit_count += 1
        type(self).exit_completed_at = datetime.now(UTC)
        return None

    def get_node(self, node_id: str) -> _FakeSubscriptionNode:
        return _FakeSubscriptionNode(node_id)

    async def create_subscription(
        self,
        publishing_interval_ms: float,
        *,
        queue_maxsize: int,
    ) -> _FakeSubscription:
        _FakeSubscription.publishing_interval_ms = publishing_interval_ms
        _FakeSubscription.queue_maxsize = queue_maxsize
        return _FakeSubscription()


class _FakeClient:
    values: ClassVar[dict[str, object]] = {}
    init_kwargs: ClassVar[dict[str, object]] = {}
    enter_count: ClassVar[int] = 0
    exit_count: ClassVar[int] = 0
    exit_completed_at: ClassVar[datetime | None] = None

    def __init__(self, **kwargs: object) -> None:
        type(self).init_kwargs = dict(kwargs)

    async def __aenter__(self) -> _FakeClient:
        type(self).enter_count += 1
        return self

    async def __aexit__(self, *args: object) -> None:
        await asyncio.sleep(0.001)
        type(self).exit_count += 1
        type(self).exit_completed_at = datetime.now(UTC)
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


def test_opcua_browse_config_bounds_depth_node_budget_and_timeout() -> None:
    with pytest.raises(ValueError, match="max_depth"):
        OpcUaBrowseConfig(
            endpoint_url="opc.tcp://localhost:4840",
            max_depth=0,
        )

    with pytest.raises(ValueError, match="max_nodes"):
        OpcUaBrowseConfig(
            endpoint_url="opc.tcp://localhost:4840",
            max_nodes=0,
        )

    with pytest.raises(ValueError, match="positive finite"):
        OpcUaBrowseConfig(
            endpoint_url="opc.tcp://localhost:4840",
            timeout_seconds=0.0,
        )


def test_opcua_browse_discovers_variables_without_reading_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variable = "variable"
    object_node = "object"
    temperature = _FakeBrowseNode(
        "ns=2;s=Machine/Bearing/Temperature",
        node_class=variable,
        browse_name="Temperature",
        display_name="Bearing Temperature",
    )
    bearing = _FakeBrowseNode(
        "ns=2;s=Machine/Bearing",
        node_class=object_node,
        browse_name="Bearing",
        display_name="Bearing",
        children=(temperature,),
    )
    vibration = _FakeBrowseNode(
        "ns=2;s=Machine/VibrationX",
        node_class=variable,
        browse_name="VibrationX",
        display_name="Vibration X",
    )
    machine = _FakeBrowseNode(
        "ns=2;s=Machine",
        node_class=object_node,
        browse_name="Machine",
        display_name="Machine",
        children=(bearing, vibration),
    )
    _FakeBrowseClient.root = _FakeBrowseNode(
        "i=85",
        node_class=object_node,
        browse_name="Objects",
        display_name="Objects",
        children=(machine,),
    )
    _FakeBrowseClient.exit_completed_at = None
    monkeypatch.setattr(
        opcua_module,
        "import_module",
        lambda name: SimpleNamespace(
            Client=_FakeBrowseClient,
            ua=SimpleNamespace(
                NodeClass=SimpleNamespace(
                    Object=object_node,
                    Variable=variable,
                )
            ),
        ),
    )

    result = asyncio.run(
        browse_opcua_variables(
            OpcUaBrowseConfig(
                endpoint_url="opc.tcp://localhost:4840/test/",
                max_depth=3,
                max_nodes=16,
                timeout_seconds=1.5,
            )
        )
    )

    assert _FakeBrowseClient.init_kwargs == {
        "url": "opc.tcp://localhost:4840/test/",
        "timeout": 1.5,
        "auto_reconnect": False,
    }
    assert _FakeBrowseClient.exit_completed_at is not None
    assert result.completed_at >= _FakeBrowseClient.exit_completed_at
    assert result.truncated is False
    assert result.visited_node_count == 4
    assert tuple(item.node_id for item in result.variables) == (
        "ns=2;s=Machine/Bearing/Temperature",
        "ns=2;s=Machine/VibrationX",
    )
    assert result.variables[0].browse_path == ("Machine", "Bearing", "Temperature")
    assert result.variables[1].browse_path == ("Machine", "VibrationX")


def test_opcua_browse_respects_depth_and_node_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    variable = "variable"
    object_node = "object"
    nested_variable = _FakeBrowseNode(
        "ns=2;s=Machine/Bearing/Temperature",
        node_class=variable,
        browse_name="Temperature",
        display_name="Temperature",
    )
    bearing = _FakeBrowseNode(
        "ns=2;s=Machine/Bearing",
        node_class=object_node,
        browse_name="Bearing",
        display_name="Bearing",
        children=(nested_variable,),
    )
    machine = _FakeBrowseNode(
        "ns=2;s=Machine",
        node_class=object_node,
        browse_name="Machine",
        display_name="Machine",
        children=(bearing,),
    )
    _FakeBrowseClient.root = _FakeBrowseNode(
        "i=85",
        node_class=object_node,
        browse_name="Objects",
        display_name="Objects",
        children=(machine,),
    )
    monkeypatch.setattr(
        opcua_module,
        "import_module",
        lambda name: SimpleNamespace(
            Client=_FakeBrowseClient,
            ua=SimpleNamespace(
                NodeClass=SimpleNamespace(
                    Object=object_node,
                    Variable=variable,
                )
            ),
        ),
    )

    depth_limited = asyncio.run(
        browse_opcua_variables(
            OpcUaBrowseConfig(
                endpoint_url="opc.tcp://localhost:4840",
                max_depth=2,
                max_nodes=16,
            )
        )
    )
    budget_limited = asyncio.run(
        browse_opcua_variables(
            OpcUaBrowseConfig(
                endpoint_url="opc.tcp://localhost:4840",
                max_depth=3,
                max_nodes=1,
            )
        )
    )

    assert depth_limited.variables == ()
    assert depth_limited.truncated is False
    assert budget_limited.variables == ()
    assert budget_limited.truncated is True
    assert budget_limited.visited_node_count == 1


def test_opcua_subscription_config_bounds_session_and_queue() -> None:
    mapping = (OpcUaNodeMapping("vibration_x", "ns=2;s=VibrationX"),)

    with pytest.raises(ValueError, match="publishing_interval_ms"):
        OpcUaSubscriptionConfig(
            endpoint_url="opc.tcp://localhost:4840",
            node_mappings=mapping,
            publishing_interval_ms=0.0,
        )

    with pytest.raises(ValueError, match="collection_timeout_seconds"):
        OpcUaSubscriptionConfig(
            endpoint_url="opc.tcp://localhost:4840",
            node_mappings=mapping,
            collection_timeout_seconds=0.0,
        )

    with pytest.raises(ValueError, match="max_events"):
        OpcUaSubscriptionConfig(
            endpoint_url="opc.tcp://localhost:4840",
            node_mappings=mapping,
            max_events=0,
        )

    with pytest.raises(ValueError, match="queue_maxsize"):
        OpcUaSubscriptionConfig(
            endpoint_url="opc.tcp://localhost:4840",
            node_mappings=mapping,
            queue_maxsize=0,
        )


def test_opcua_subscription_collects_bounded_datachange_notifications(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_at = datetime.fromisoformat("2026-09-23T10:00:00+00:00")
    server_at = datetime.fromisoformat("2026-09-23T10:00:01+00:00")
    _FakeSubscription.events = [
        SimpleNamespace(kind="status-change"),
        _FakeDataChangeEvent(
            "ns=2;s=VibrationX",
            _data_value(
                12.5,
                status=_FakeStatus(0, good=True),
                source_timestamp=source_at,
                server_timestamp=server_at,
            ),
        ),
        _FakeDataChangeEvent(
            "ns=2;s=Temperature",
            _data_value(
                999.0,
                status=_FakeStatus(0x80030000, good=False),
                source_timestamp=source_at,
                server_timestamp=server_at,
            ),
            replayed=True,
        ),
    ]
    _FakeSubscription.next_timeouts = []
    _FakeSubscription.enter_count = 0
    _FakeSubscription.exit_count = 0
    _FakeSubscription.exit_completed_at = None
    _FakeSubscriptionClient.enter_count = 0
    _FakeSubscriptionClient.exit_count = 0
    _FakeSubscriptionClient.exit_completed_at = None

    def _import(name: str) -> object:
        if name == "asyncua":
            return SimpleNamespace(Client=_FakeSubscriptionClient)
        if name == "asyncua.common.subscription":
            return SimpleNamespace(DataChangeEvent=_FakeDataChangeEvent)
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(opcua_module, "import_module", _import)

    result = asyncio.run(
        collect_opcua_subscription_notifications(
            OpcUaSubscriptionConfig(
                endpoint_url="opc.tcp://localhost:4840/test/",
                node_mappings=(
                    OpcUaNodeMapping("vibration_x", "ns=2;s=VibrationX"),
                    OpcUaNodeMapping("temperature", "ns=2;s=Temperature"),
                ),
                publishing_interval_ms=250.0,
                collection_timeout_seconds=3.0,
                max_events=2,
                queue_maxsize=7,
                timeout_seconds=2.5,
            )
        )
    )

    assert _FakeSubscriptionClient.init_kwargs == {
        "url": "opc.tcp://localhost:4840/test/",
        "timeout": 2.5,
        "auto_reconnect": False,
    }
    assert _FakeSubscription.publishing_interval_ms == 250.0
    assert _FakeSubscription.queue_maxsize == 7
    assert _FakeSubscription.subscribed_node_ids == (
        "ns=2;s=VibrationX",
        "ns=2;s=Temperature",
    )
    assert _FakeSubscriptionClient.enter_count == 1
    assert _FakeSubscriptionClient.exit_count == 1
    assert _FakeSubscription.enter_count == 1
    assert _FakeSubscription.exit_count == 1
    assert _FakeSubscription.exit_completed_at is not None
    assert _FakeSubscriptionClient.exit_completed_at is not None
    assert result.completed_at >= _FakeSubscription.exit_completed_at
    assert result.completed_at >= _FakeSubscriptionClient.exit_completed_at
    assert result.completion_reason == OpcUaSubscriptionCompletionReason.MAX_EVENTS
    assert len(result.notifications) == 2

    good, bad = result.notifications
    assert good.observation.channel_id == "vibration_x"
    assert good.observation.value == 12.5
    assert good.observation.status_good is True
    assert good.observation.source_timestamp == source_at
    assert good.observation.server_timestamp == server_at
    assert good.replayed is False

    assert bad.observation.channel_id == "temperature"
    assert bad.observation.value is None
    assert bad.observation.status_good is False
    assert bad.observation.status_code == 0x80030000
    assert bad.replayed is True


def test_opcua_subscription_timeout_returns_partial_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeSubscription.events = []
    _FakeSubscription.next_timeouts = []

    def _import(name: str) -> object:
        if name == "asyncua":
            return SimpleNamespace(Client=_FakeSubscriptionClient)
        if name == "asyncua.common.subscription":
            return SimpleNamespace(DataChangeEvent=_FakeDataChangeEvent)
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr(opcua_module, "import_module", _import)

    result = asyncio.run(
        collect_opcua_subscription_notifications(
            OpcUaSubscriptionConfig(
                endpoint_url="opc.tcp://localhost:4840",
                node_mappings=(OpcUaNodeMapping("vibration_x", "ns=2;s=VibrationX"),),
                collection_timeout_seconds=1.0,
                max_events=2,
            )
        )
    )

    assert result.completion_reason == OpcUaSubscriptionCompletionReason.TIMEOUT
    assert result.notifications == ()
    assert _FakeSubscription.next_timeouts
    assert _FakeSubscription.next_timeouts[0] is not None
    assert _FakeSubscription.next_timeouts[0] <= 1.0


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
    _FakeClient.exit_completed_at = None
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
    assert _FakeClient.exit_completed_at is not None
    assert snapshot.completed_at >= _FakeClient.exit_completed_at

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
