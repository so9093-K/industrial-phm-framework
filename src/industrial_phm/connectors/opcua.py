"""Minimal one-shot OPC UA read boundary.

The first live connector intentionally supports only anonymous / SecurityPolicy None
reads of explicitly configured variable NodeIds. It preserves OPC UA quality and
source/server timestamps separately from the platform acceptance timestamp.

Subscription, reconnect, credentials, certificates, discovery/browse workflows and
continuous ingestion are later boundaries.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
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
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, Real)
            or not isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a positive finite number")
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
            "good OPC UA value must be finite for "
            f"{mapping.channel_id} ({mapping.node_id})"
        )
    return numeric


def _load_asyncua_client() -> Any:
    try:
        module = import_module("asyncua")
    except ModuleNotFoundError as error:
        if error.name != "asyncua":
            raise
        raise OpcUaRuntimeUnavailableError(
            "OPC UA runtime is not installed; install the 'opcua' extra"
        ) from error
    client_type = getattr(module, "Client", None)
    if client_type is None:
        raise OpcUaRuntimeUnavailableError("asyncua runtime does not expose Client")
    return client_type


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
