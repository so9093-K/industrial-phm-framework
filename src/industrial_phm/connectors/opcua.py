"""Minimal OPC UA probe, read, browse, and bounded subscription boundaries.

The first live connector intentionally supports only anonymous / SecurityPolicy None
connections and reads of explicitly configured variable NodeIds. The endpoint probe
records one successful connect/disconnect interval without inferring ongoing health.
The read boundary preserves OPC UA quality and source/server timestamps separately from
the platform acceptance timestamp.

A bounded subscription boundary can collect a finite number of DataChange notifications
without creating a background daemon. Reconnect, credentials, certificates and continuous
ingestion remain later boundaries. Browse is intentionally bounded and returns candidate
variable identity only.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from importlib import import_module
from math import isfinite
from numbers import Real
from typing import Any
from urllib.parse import urlsplit


class OpcUaRuntimeUnavailableError(RuntimeError):
    """Raised when the optional OPC UA SDK is not installed."""


class OpcUaSourceError(ValueError):
    """Raised when declared OPC UA source data violates the numeric read contract."""


@dataclass(frozen=True, slots=True)
class OpcUaBrowseConfig:
    """Configuration for one bounded anonymous OPC UA address-space browse."""

    endpoint_url: str
    start_node_id: str = "i=85"
    max_depth: int = 4
    max_nodes: int = 256
    timeout_seconds: float = 4.0

    def __post_init__(self) -> None:
        _validate_endpoint_url(self.endpoint_url)
        _validate_identifier(self.start_node_id, "start_node_id")
        if isinstance(self.max_depth, bool) or not isinstance(self.max_depth, int):
            raise ValueError("max_depth must be an integer")
        if self.max_depth < 1:
            raise ValueError("max_depth must be at least 1")
        if isinstance(self.max_nodes, bool) or not isinstance(self.max_nodes, int):
            raise ValueError("max_nodes must be an integer")
        if self.max_nodes < 1:
            raise ValueError("max_nodes must be at least 1")
        _validate_timeout_seconds(self.timeout_seconds)


@dataclass(frozen=True, slots=True)
class OpcUaBrowseVariable:
    """One discovered OPC UA Variable identity without reading its value."""

    node_id: str
    browse_name: str
    display_name: str
    browse_path: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_identifier(self.node_id, "node_id")
        _validate_identifier(self.browse_name, "browse_name")
        _validate_identifier(self.display_name, "display_name")
        if not self.browse_path:
            raise ValueError("browse_path must not be empty")
        if not all(
            isinstance(item, str) and item.strip() == item and item for item in self.browse_path
        ):
            raise ValueError("browse_path must contain non-empty trimmed strings")


@dataclass(frozen=True, slots=True)
class OpcUaBrowseResult:
    """Result of one bounded browse session.

    completed_at is recorded only after the client context has exited successfully.
    """

    endpoint_url: str
    connected_at: datetime
    completed_at: datetime
    start_node_id: str
    visited_node_count: int
    truncated: bool
    variables: tuple[OpcUaBrowseVariable, ...]

    def __post_init__(self) -> None:
        _validate_endpoint_url(self.endpoint_url)
        _validate_identifier(self.start_node_id, "start_node_id")
        if not isinstance(self.connected_at, datetime) or self.connected_at.utcoffset() is None:
            raise ValueError("connected_at must be a timezone-aware datetime")
        if not isinstance(self.completed_at, datetime) or self.completed_at.utcoffset() is None:
            raise ValueError("completed_at must be a timezone-aware datetime")
        if self.completed_at < self.connected_at:
            raise ValueError("completed_at must not be before connected_at")
        if isinstance(self.visited_node_count, bool) or not isinstance(
            self.visited_node_count, int
        ):
            raise ValueError("visited_node_count must be an integer")
        if self.visited_node_count < 0:
            raise ValueError("visited_node_count must not be negative")
        if not isinstance(self.truncated, bool):
            raise ValueError("truncated must be boolean")
        if not all(isinstance(item, OpcUaBrowseVariable) for item in self.variables):
            raise ValueError("variables must contain OpcUaBrowseVariable values")


@dataclass(frozen=True, slots=True)
class OpcUaNodeMapping:
    """Map one OPC UA variable NodeId to one framework channel identifier."""

    channel_id: str
    node_id: str

    def __post_init__(self) -> None:
        _validate_identifier(self.channel_id, "channel_id")
        _validate_identifier(self.node_id, "node_id")


@dataclass(frozen=True, slots=True)
class OpcUaReadConfig:
    """Configuration for the first anonymous one-shot OPC UA read slice."""

    endpoint_url: str
    node_mappings: Sequence[OpcUaNodeMapping]
    timeout_seconds: float = 4.0

    def __post_init__(self) -> None:
        _validate_endpoint_url(self.endpoint_url)
        mappings = tuple(self.node_mappings)
        if not mappings:
            raise ValueError("node_mappings must not be empty")
        if not all(isinstance(mapping, OpcUaNodeMapping) for mapping in mappings):
            raise ValueError("node_mappings must contain OpcUaNodeMapping values")
        channel_ids = tuple(mapping.channel_id for mapping in mappings)
        node_ids = tuple(mapping.node_id for mapping in mappings)
        if len(set(channel_ids)) != len(channel_ids):
            raise ValueError("node_mappings must use unique channel_id values")
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("node_mappings must use unique node_id values")
        _validate_timeout_seconds(self.timeout_seconds)
        object.__setattr__(self, "node_mappings", mappings)


@dataclass(frozen=True, slots=True)
class OpcUaNodeObservation:
    """One OPC UA DataValue projected without losing protocol timing/quality facts."""

    channel_id: str
    node_id: str
    value: float | None
    status_code: int
    status_good: bool
    status_text: str
    variant_type: str | None
    source_timestamp: datetime | None
    server_timestamp: datetime | None
    received_at: datetime

    def __post_init__(self) -> None:
        _validate_identifier(self.channel_id, "channel_id")
        _validate_identifier(self.node_id, "node_id")
        if self.value is not None and not isfinite(self.value):
            raise ValueError("value must be finite when provided")
        if isinstance(self.status_code, bool) or not isinstance(self.status_code, int):
            raise ValueError("status_code must be an integer")
        if not isinstance(self.status_good, bool):
            raise ValueError("status_good must be boolean")
        _validate_identifier(self.status_text, "status_text")
        if self.variant_type is not None:
            _validate_identifier(self.variant_type, "variant_type")
        if self.source_timestamp is not None:
            if not isinstance(self.source_timestamp, datetime):
                raise ValueError("source_timestamp must be a datetime when provided")
            if self.source_timestamp.utcoffset() is None:
                raise ValueError("source_timestamp must be timezone-aware when provided")
        if self.server_timestamp is not None:
            if not isinstance(self.server_timestamp, datetime):
                raise ValueError("server_timestamp must be a datetime when provided")
            if self.server_timestamp.utcoffset() is None:
                raise ValueError("server_timestamp must be timezone-aware when provided")
        if not isinstance(self.received_at, datetime) or self.received_at.utcoffset() is None:
            raise ValueError("received_at must be a timezone-aware datetime")
        if self.status_good and self.value is None:
            raise ValueError("good OPC UA status requires a numeric value")
        if not self.status_good and self.value is not None:
            raise ValueError("non-good OPC UA status must not be promoted to a numeric value")


@dataclass(frozen=True, slots=True)
class OpcUaReadSnapshot:
    """One completed OPC UA connect/read/disconnect iteration."""

    endpoint_url: str
    connected_at: datetime
    completed_at: datetime
    observations: tuple[OpcUaNodeObservation, ...]

    def __post_init__(self) -> None:
        _validate_endpoint_url(self.endpoint_url)
        if not isinstance(self.connected_at, datetime) or self.connected_at.utcoffset() is None:
            raise ValueError("connected_at must be a timezone-aware datetime")
        if not isinstance(self.completed_at, datetime) or self.completed_at.utcoffset() is None:
            raise ValueError("completed_at must be a timezone-aware datetime")
        if self.completed_at < self.connected_at:
            raise ValueError("completed_at must not be before connected_at")
        if not self.observations:
            raise ValueError("observations must not be empty")
        if not all(isinstance(item, OpcUaNodeObservation) for item in self.observations):
            raise ValueError("observations must contain OpcUaNodeObservation values")


class OpcUaSubscriptionCompletionReason(StrEnum):
    """Why one bounded subscription collection stopped."""

    MAX_EVENTS = "max-events"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class OpcUaSubscriptionConfig:
    """Configuration for one bounded anonymous OPC UA DataChange subscription."""

    endpoint_url: str
    node_mappings: Sequence[OpcUaNodeMapping]
    publishing_interval_ms: float = 500.0
    collection_timeout_seconds: float = 5.0
    max_events: int = 1
    queue_maxsize: int = 128
    timeout_seconds: float = 4.0

    def __post_init__(self) -> None:
        read_config = OpcUaReadConfig(
            endpoint_url=self.endpoint_url,
            node_mappings=self.node_mappings,
            timeout_seconds=self.timeout_seconds,
        )
        object.__setattr__(self, "node_mappings", tuple(read_config.node_mappings))
        _validate_positive_finite(self.publishing_interval_ms, "publishing_interval_ms")
        _validate_positive_finite(self.collection_timeout_seconds, "collection_timeout_seconds")
        if isinstance(self.max_events, bool) or not isinstance(self.max_events, int):
            raise ValueError("max_events must be an integer")
        if self.max_events < 1:
            raise ValueError("max_events must be at least 1")
        if isinstance(self.queue_maxsize, bool) or not isinstance(self.queue_maxsize, int):
            raise ValueError("queue_maxsize must be an integer")
        if self.queue_maxsize < 1:
            raise ValueError("queue_maxsize must be at least 1")


@dataclass(frozen=True, slots=True)
class OpcUaSubscriptionNotification:
    """One DataChange notification projected with protocol timing/quality facts."""

    observation: OpcUaNodeObservation
    replayed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.observation, OpcUaNodeObservation):
            raise ValueError("observation must be an OpcUaNodeObservation")
        if not isinstance(self.replayed, bool):
            raise ValueError("replayed must be boolean")


@dataclass(frozen=True, slots=True)
class OpcUaSubscriptionResult:
    """Result of one bounded subscription session.

    completed_at is recorded only after subscription and client contexts exit successfully.
    """

    endpoint_url: str
    connected_at: datetime
    completed_at: datetime
    completion_reason: OpcUaSubscriptionCompletionReason
    notifications: tuple[OpcUaSubscriptionNotification, ...]

    def __post_init__(self) -> None:
        _validate_endpoint_url(self.endpoint_url)
        if not isinstance(self.connected_at, datetime) or self.connected_at.utcoffset() is None:
            raise ValueError("connected_at must be a timezone-aware datetime")
        if not isinstance(self.completed_at, datetime) or self.completed_at.utcoffset() is None:
            raise ValueError("completed_at must be a timezone-aware datetime")
        if self.completed_at < self.connected_at:
            raise ValueError("completed_at must not be before connected_at")
        if not isinstance(self.completion_reason, OpcUaSubscriptionCompletionReason):
            raise ValueError("completion_reason must be an OpcUaSubscriptionCompletionReason")
        if not all(isinstance(item, OpcUaSubscriptionNotification) for item in self.notifications):
            raise ValueError("notifications must contain OpcUaSubscriptionNotification values")
        if (
            self.completion_reason == OpcUaSubscriptionCompletionReason.MAX_EVENTS
            and not self.notifications
        ):
            raise ValueError("max-events completion requires at least one notification")


async def collect_opcua_subscription_notifications(
    config: OpcUaSubscriptionConfig,
) -> OpcUaSubscriptionResult:
    """Collect bounded DataChange notifications without reconnect or background execution."""
    if not isinstance(config, OpcUaSubscriptionConfig):
        raise ValueError("config must be an OpcUaSubscriptionConfig")

    module = _load_asyncua_module()
    client_type = _require_asyncua_client(module)
    subscription_module = _load_asyncua_subscription_module()
    data_change_type = getattr(subscription_module, "DataChangeEvent", None)
    if not isinstance(data_change_type, type):
        raise OpcUaRuntimeUnavailableError(
            "asyncua subscription runtime does not expose DataChangeEvent"
        )

    client = client_type(
        url=config.endpoint_url,
        timeout=float(config.timeout_seconds),
        auto_reconnect=False,
    )
    mapping_by_node_id = {mapping.node_id: mapping for mapping in config.node_mappings}
    notifications: list[OpcUaSubscriptionNotification] = []
    completion_reason = OpcUaSubscriptionCompletionReason.TIMEOUT

    async with client:
        connected_at = datetime.now(UTC)
        nodes = [client.get_node(mapping.node_id) for mapping in config.node_mappings]
        subscription = await client.create_subscription(
            float(config.publishing_interval_ms),
            queue_maxsize=config.queue_maxsize,
        )
        async with subscription:
            await subscription.subscribe_data_change(nodes)
            loop = asyncio.get_running_loop()
            deadline = loop.time() + float(config.collection_timeout_seconds)

            while len(notifications) < config.max_events:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                event = await subscription.next_event(timeout=remaining)
                if event is None:
                    break
                if not isinstance(event, data_change_type):
                    continue

                node = getattr(event, "node", None)
                node_id = _opcua_node_id_string(node)
                mapping = mapping_by_node_id.get(node_id)
                if mapping is None:
                    raise OpcUaSourceError(
                        f"subscription event references unmapped node: {node_id}"
                    )

                event_data = getattr(event, "data", None)
                monitored_item = getattr(event_data, "monitored_item", None)
                data_value = (
                    None if monitored_item is None else getattr(monitored_item, "Value", None)
                )
                if data_value is None:
                    raise OpcUaSourceError(f"subscription DataChange has no DataValue: {node_id}")

                replayed = getattr(event, "replayed", False)
                if not isinstance(replayed, bool):
                    raise OpcUaSourceError(f"subscription replayed flag is invalid: {node_id}")
                notifications.append(
                    OpcUaSubscriptionNotification(
                        observation=_project_data_value(
                            mapping,
                            data_value,
                            received_at=datetime.now(UTC),
                        ),
                        replayed=replayed,
                    )
                )

            if len(notifications) >= config.max_events:
                completion_reason = OpcUaSubscriptionCompletionReason.MAX_EVENTS

    completed_at = datetime.now(UTC)
    return OpcUaSubscriptionResult(
        endpoint_url=config.endpoint_url,
        connected_at=connected_at,
        completed_at=completed_at,
        completion_reason=completion_reason,
        notifications=tuple(notifications),
    )


async def browse_opcua_variables(config: OpcUaBrowseConfig) -> OpcUaBrowseResult:
    """Browse bounded hierarchical Object/Variable candidates without reading values."""
    if not isinstance(config, OpcUaBrowseConfig):
        raise ValueError("config must be an OpcUaBrowseConfig")

    module = _load_asyncua_module()
    client_type = _require_asyncua_client(module)
    ua = getattr(module, "ua", None)
    if ua is None or getattr(ua, "NodeClass", None) is None:
        raise OpcUaRuntimeUnavailableError("asyncua runtime does not expose ua.NodeClass")

    client = client_type(
        url=config.endpoint_url,
        timeout=float(config.timeout_seconds),
        auto_reconnect=False,
    )

    variables: list[OpcUaBrowseVariable] = []
    visited_node_ids: set[str] = set()
    visited_node_count = 0
    truncated = False

    async with client:
        connected_at = datetime.now(UTC)
        start_node = client.get_node(config.start_node_id)
        stack: list[tuple[Any, tuple[str, ...], int]] = [(start_node, (), 0)]

        while stack and not truncated:
            parent, parent_path, parent_depth = stack.pop()
            children = await parent.get_children()
            for child in children:
                node_id = _opcua_node_id_string(child)
                if node_id in visited_node_ids:
                    continue
                if visited_node_count >= config.max_nodes:
                    truncated = True
                    break
                visited_node_ids.add(node_id)
                visited_node_count += 1

                node_class = await child.read_node_class()
                browse_name = _opcua_browse_name(await child.read_browse_name())
                child_path = (*parent_path, browse_name)
                child_depth = parent_depth + 1

                if node_class == ua.NodeClass.Variable:
                    display_name = _opcua_display_name(await child.read_display_name())
                    variables.append(
                        OpcUaBrowseVariable(
                            node_id=node_id,
                            browse_name=browse_name,
                            display_name=display_name,
                            browse_path=child_path,
                        )
                    )
                elif node_class == ua.NodeClass.Object and child_depth < config.max_depth:
                    stack.append((child, child_path, child_depth))

    completed_at = datetime.now(UTC)
    return OpcUaBrowseResult(
        endpoint_url=config.endpoint_url,
        connected_at=connected_at,
        completed_at=completed_at,
        start_node_id=config.start_node_id,
        visited_node_count=visited_node_count,
        truncated=truncated,
        variables=tuple(sorted(variables, key=lambda item: (item.browse_path, item.node_id))),
    )


async def read_opcua_snapshot(config: OpcUaReadConfig) -> OpcUaReadSnapshot:
    """Connect once, read configured variables once, and disconnect.

    The optional asyncua runtime is imported only when this function is called.
    Auto-reconnect is deliberately disabled: reconnect/subscription semantics belong to
    a later continuous-runtime boundary.
    """
    if not isinstance(config, OpcUaReadConfig):
        raise ValueError("config must be an OpcUaReadConfig")

    client_type = _load_asyncua_client()
    client = client_type(
        url=config.endpoint_url,
        timeout=float(config.timeout_seconds),
        auto_reconnect=False,
    )

    observations: list[OpcUaNodeObservation] = []
    async with client:
        connected_at = datetime.now(UTC)
        for mapping in config.node_mappings:
            node = client.get_node(mapping.node_id)
            data_value = await node.read_data_value(raise_on_bad_status=False)
            received_at = datetime.now(UTC)
            observations.append(
                _project_data_value(
                    mapping,
                    data_value,
                    received_at=received_at,
                )
            )

    completed_at = datetime.now(UTC)
    return OpcUaReadSnapshot(
        endpoint_url=config.endpoint_url,
        connected_at=connected_at,
        completed_at=completed_at,
        observations=tuple(observations),
    )


def _project_data_value(
    mapping: OpcUaNodeMapping,
    data_value: Any,
    *,
    received_at: datetime,
) -> OpcUaNodeObservation:
    status = getattr(data_value, "StatusCode", None)
    if status is None:
        raise OpcUaSourceError(f"OPC UA DataValue has no StatusCode: {mapping.node_id}")

    status_value = getattr(status, "value", None)
    if isinstance(status_value, bool) or not isinstance(status_value, int):
        raise OpcUaSourceError(f"OPC UA StatusCode is invalid: {mapping.node_id}")
    is_good = getattr(status, "is_good", None)
    if not callable(is_good):
        raise OpcUaSourceError(f"OPC UA StatusCode cannot be classified: {mapping.node_id}")
    status_good = bool(is_good())

    variant = getattr(data_value, "Value", None)
    raw_value = None if variant is None else getattr(variant, "Value", None)
    variant_type_raw = None if variant is None else getattr(variant, "VariantType", None)
    variant_type = None if variant_type_raw is None else str(variant_type_raw)

    numeric_value: float | None = None
    if status_good:
        numeric_value = _coerce_numeric_value(raw_value, mapping)

    source_timestamp = getattr(data_value, "SourceTimestamp", None)
    server_timestamp = getattr(data_value, "ServerTimestamp", None)
    if source_timestamp is not None and not isinstance(source_timestamp, datetime):
        raise OpcUaSourceError(f"OPC UA SourceTimestamp is invalid: {mapping.node_id}")
    if server_timestamp is not None and not isinstance(server_timestamp, datetime):
        raise OpcUaSourceError(f"OPC UA ServerTimestamp is invalid: {mapping.node_id}")

    return OpcUaNodeObservation(
        channel_id=mapping.channel_id,
        node_id=mapping.node_id,
        value=numeric_value,
        status_code=status_value,
        status_good=status_good,
        status_text=str(status),
        variant_type=variant_type,
        source_timestamp=source_timestamp,
        server_timestamp=server_timestamp,
        received_at=received_at,
    )


def _coerce_numeric_value(value: object, mapping: OpcUaNodeMapping) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise OpcUaSourceError(
            "good OPC UA value must be a finite numeric scalar for "
            f"{mapping.channel_id} ({mapping.node_id})"
        )
    numeric = float(value)
    if not isfinite(numeric):
        raise OpcUaSourceError(
            f"good OPC UA value must be finite for {mapping.channel_id} ({mapping.node_id})"
        )
    return numeric


def _load_asyncua_module() -> Any:
    try:
        return import_module("asyncua")
    except ModuleNotFoundError as error:
        if error.name != "asyncua":
            raise
        raise OpcUaRuntimeUnavailableError(
            "OPC UA runtime is not installed; install the 'opcua' extra"
        ) from error


def _require_asyncua_client(module: Any) -> Any:
    client_type = getattr(module, "Client", None)
    if client_type is None:
        raise OpcUaRuntimeUnavailableError("asyncua runtime does not expose Client")
    return client_type


def _load_asyncua_client() -> Any:
    return _require_asyncua_client(_load_asyncua_module())


def _load_asyncua_subscription_module() -> Any:
    try:
        return import_module("asyncua.common.subscription")
    except ModuleNotFoundError as error:
        if error.name not in {
            "asyncua",
            "asyncua.common",
            "asyncua.common.subscription",
        }:
            raise
        raise OpcUaRuntimeUnavailableError(
            "OPC UA subscription runtime is unavailable; install the 'opcua' extra"
        ) from error


def _opcua_node_id_string(node: Any) -> str:
    node_id = getattr(node, "nodeid", None)
    to_string = None if node_id is None else getattr(node_id, "to_string", None)
    if not callable(to_string):
        raise OpcUaSourceError("browsed OPC UA node does not expose a NodeId")
    value = to_string()
    if not isinstance(value, str):
        raise OpcUaSourceError("browsed OPC UA NodeId string is unavailable")
    _validate_identifier(value, "node_id")
    return value


def _opcua_browse_name(value: Any) -> str:
    name = getattr(value, "Name", None)
    if not isinstance(name, str):
        raise OpcUaSourceError("OPC UA BrowseName is unavailable")
    _validate_identifier(name, "browse_name")
    return name


def _opcua_display_name(value: Any) -> str:
    text = getattr(value, "Text", None)
    if not isinstance(text, str):
        raise OpcUaSourceError("OPC UA DisplayName is unavailable")
    _validate_identifier(text, "display_name")
    return text


def _validate_timeout_seconds(value: float) -> None:
    _validate_positive_finite(value, "timeout_seconds")


def _validate_positive_finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value) or value <= 0:
        raise ValueError(f"{field_name} must be a positive finite number")


def _validate_endpoint_url(value: str) -> None:
    _validate_identifier(value, "endpoint_url")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError(f"endpoint_url is invalid: {error}") from error
    if parsed.scheme != "opc.tcp":
        raise ValueError("endpoint_url must use opc.tcp")
    if parsed.hostname is None:
        raise ValueError("endpoint_url must include a host")
    if port is None:
        raise ValueError("endpoint_url must include an explicit port")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(
            "first OPC UA vertical slice is anonymous only; "
            "credentials in endpoint_url are unsupported"
        )
    if parsed.query or parsed.fragment:
        raise ValueError("endpoint_url must not contain query or fragment components")


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
