"""Long-lived OPC UA connector boundary backed by the optional asyncua runtime."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from importlib import import_module
from math import isfinite
from numbers import Real
from typing import Any

from industrial_phm.connectors.opcua import (
    OpcUaNodeMapping,
    OpcUaReadConfig,
    OpcUaRuntimeUnavailableError,
    OpcUaSourceError,
    OpcUaSubscriptionNotification,
    _opcua_node_id_string,
    _project_data_value,
)


class OpcUaConnectorConnectionState(StrEnum):
    """Connection states relevant to the application persistent-session contract."""

    RECONNECTING = "RECONNECTING"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"


@dataclass(frozen=True, slots=True)
class OpcUaConnectorStateEvent:
    state: OpcUaConnectorConnectionState
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.state, OpcUaConnectorConnectionState):
            raise ValueError("state must be an OpcUaConnectorConnectionState")
        _validate_aware_datetime(self.occurred_at, "occurred_at")


@dataclass(frozen=True, slots=True)
class OpcUaConnectorQueueOverflow:
    occurred_at: datetime

    def __post_init__(self) -> None:
        _validate_aware_datetime(self.occurred_at, "occurred_at")


@dataclass(frozen=True, slots=True)
class OpcUaPersistentConnectorConfig:
    """Concrete long-lived anonymous OPC UA subscription configuration."""

    endpoint_url: str
    node_mappings: Sequence[OpcUaNodeMapping]
    publishing_interval_ms: float = 500.0
    queue_maxsize: int = 128
    timeout_seconds: float = 4.0
    reconnect_max_delay_seconds: float = 30.0

    def __post_init__(self) -> None:
        read_config = OpcUaReadConfig(
            endpoint_url=self.endpoint_url,
            node_mappings=self.node_mappings,
            timeout_seconds=self.timeout_seconds,
        )
        object.__setattr__(self, "node_mappings", tuple(read_config.node_mappings))
        _validate_positive_finite(self.publishing_interval_ms, "publishing_interval_ms")
        _validate_positive_int(self.queue_maxsize, "queue_maxsize")
        _validate_positive_finite(
            self.reconnect_max_delay_seconds,
            "reconnect_max_delay_seconds",
        )


class OpcUaPersistentSubscription:
    """One connected asyncua subscription that survives transport reconnects."""

    def __init__(self, config: OpcUaPersistentConnectorConfig) -> None:
        if not isinstance(config, OpcUaPersistentConnectorConfig):
            raise ValueError("config must be OpcUaPersistentConnectorConfig")
        self._config = config
        self._client: Any | None = None
        self._subscription: Any | None = None
        self._state_context: Any | None = None
        self._state_subscription: Any | None = None
        self._data_change_type: type[Any] | None = None
        self._mapping_by_node_id = {
            mapping.node_id: mapping for mapping in self._config.node_mappings
        }
        self._overflow_queue: asyncio.Queue[OpcUaConnectorQueueOverflow] = asyncio.Queue()
        # Arrival (monotonic, wall clock) of each event queued by asyncua, FIFO with
        # its subscription queue, so received_at is arrival rather than dequeue time.
        self._arrivals: deque[tuple[float, datetime]] = deque()
        self._arrival_queue: Any | None = None
        self._metrics: Any | None = None
        self._overflow_signalled = False
        self._overflow_rejected = 0

    def attach_pipeline_metrics(self, metrics: Any) -> None:
        """Opt-in diagnostics sink (``industrial_phm.runtime.pipeline_metrics``)."""
        self._metrics = metrics

    @property
    def config(self) -> OpcUaPersistentConnectorConfig:
        return self._config

    async def start(self) -> None:
        """Connect once and create one subscription; asyncua owns later reconnect recovery."""
        if self._client is not None:
            raise ValueError("persistent OPC UA subscription has already been started")

        module = _load_asyncua_module()
        client_type = getattr(module, "Client", None)
        if client_type is None:
            raise OpcUaRuntimeUnavailableError("asyncua runtime does not expose Client")
        subscription_module = _load_asyncua_subscription_module()
        data_change_type = getattr(subscription_module, "DataChangeEvent", None)
        overflow_policy = getattr(subscription_module, "OverflowPolicy", None)
        if not isinstance(data_change_type, type):
            raise OpcUaRuntimeUnavailableError(
                "asyncua subscription runtime does not expose DataChangeEvent"
            )
        if overflow_policy is None or getattr(overflow_policy, "DISCONNECT", None) is None:
            raise OpcUaRuntimeUnavailableError(
                "asyncua subscription runtime does not expose OverflowPolicy.DISCONNECT"
            )

        client = client_type(
            url=self._config.endpoint_url,
            timeout=float(self._config.timeout_seconds),
            auto_reconnect=True,
            reconnect_max_delay=float(self._config.reconnect_max_delay_seconds),
        )
        self._client = client
        self._data_change_type = data_change_type
        try:
            await client.connect()
            state_context = client.subscribe_state()
            state_subscription = await state_context.__aenter__()
            self._state_context = state_context
            self._state_subscription = state_subscription

            nodes = [client.get_node(mapping.node_id) for mapping in self._config.node_mappings]
            subscription = await client.create_subscription(
                float(self._config.publishing_interval_ms),
                queue_maxsize=self._config.queue_maxsize,
                overflow=overflow_policy.DISCONNECT,
            )
            self._subscription = subscription

            def _on_queue_overflow() -> None:
                # asyncua calls this once per rejected notification. Signal the worker
                # once and leave the client state alone: notify_transport_lost() during
                # or just after a reconnect left asyncua 2.0.1 permanently disconnected
                # (Phase 10 burst reproduction). The worker restarts the session instead.
                self._overflow_rejected += 1
                if self._metrics is not None:
                    self._metrics.count("overflow_rejected")
                if not self._overflow_signalled:
                    self._overflow_signalled = True
                    self._overflow_queue.put_nowait(
                        OpcUaConnectorQueueOverflow(occurred_at=datetime.now(UTC))
                    )

            subscription.set_overflow_disconnect_handler(_on_queue_overflow)
            self._install_arrival_probe(subscription)
            await subscription.subscribe_data_change(nodes)
        except Exception:
            await self.close()
            raise

    async def next_state(self, timeout: float | None = None) -> OpcUaConnectorStateEvent:
        """Return the next application-relevant asyncua connection transition."""
        state_subscription = self._require_state_subscription()
        loop = asyncio.get_running_loop()
        deadline = None if timeout is None else loop.time() + timeout

        while True:
            if deadline is None:
                raw_state = await state_subscription.next_change()
            else:
                remaining = max(0.0, deadline - loop.time())
                if remaining <= 0.0:
                    raise TimeoutError
                raw_state = await state_subscription.next_change(remaining)
            state_name = getattr(raw_state, "name", None)
            if state_name == "RECONNECTING":
                state = OpcUaConnectorConnectionState.RECONNECTING
            elif state_name == "CONNECTING":
                state = OpcUaConnectorConnectionState.CONNECTING
            elif state_name == "CONNECTED":
                state = OpcUaConnectorConnectionState.CONNECTED
            else:
                continue
            return OpcUaConnectorStateEvent(
                state=state,
                occurred_at=datetime.now(UTC),
            )

    def _install_arrival_probe(self, subscription: Any) -> None:
        """Stamp arrival as asyncua enqueues each event (asyncua 2.0.1 ``_deliver``)."""
        deliver = getattr(subscription, "_deliver", None)
        if not callable(deliver):
            return

        def probed(event: Any) -> None:
            queue = getattr(subscription, "_event_queue", None)
            if queue is not self._arrival_queue:
                # asyncua replaces the queue on reconnect; old arrivals are gone with it.
                self._arrivals.clear()
                self._arrival_queue = queue
            before = 0 if queue is None else queue.qsize()
            deliver(event)
            after = 0 if queue is None else queue.qsize()
            if after > before:
                self._arrivals.append((time.monotonic(), datetime.now(UTC)))
            metrics = self._metrics
            if metrics is not None:
                metrics.count("arrived")
                if after <= before:
                    metrics.count("not_enqueued_queue_full")
                if queue is not None:
                    metrics.queue_depth(after, queue.maxsize)

        subscription._deliver = probed

    async def next_notification(
        self,
        timeout: float | None = None,
    ) -> OpcUaSubscriptionNotification | None:
        """Return the next DataChange notification while preserving replay evidence."""
        subscription = self._require_subscription()
        event = (
            await subscription.next_event()
            if timeout is None
            else await subscription.next_event(timeout=timeout)
        )
        if event is None:
            return None
        arrived_monotonic: float | None = None
        received_at = datetime.now(UTC)
        if self._arrivals:
            arrived_monotonic, received_at = self._arrivals.popleft()
        metrics = self._metrics
        if metrics is not None:
            metrics.count("dequeued")
            if arrived_monotonic is not None:
                metrics.observe("arrival_to_dequeue", time.monotonic() - arrived_monotonic)
            queue = getattr(subscription, "_event_queue", None)
            if queue is not None:
                metrics.queue_depth(queue.qsize())
        data_change_type = self._data_change_type
        if data_change_type is None:
            raise RuntimeError("persistent OPC UA DataChange runtime is not initialized")
        if not isinstance(event, data_change_type):
            return None

        node = getattr(event, "node", None)
        node_id = _opcua_node_id_string(node)
        mapping = self._mapping_by_node_id.get(node_id)
        if mapping is None:
            raise OpcUaSourceError(
                f"persistent subscription event references unmapped node: {node_id}"
            )
        event_data = getattr(event, "data", None)
        monitored_item = None if event_data is None else getattr(event_data, "monitored_item", None)
        data_value = None if monitored_item is None else getattr(monitored_item, "Value", None)
        if data_value is None:
            raise OpcUaSourceError(
                f"persistent subscription DataChange has no DataValue: {node_id}"
            )
        replayed = getattr(event, "replayed", False)
        if not isinstance(replayed, bool):
            raise OpcUaSourceError(f"persistent subscription replayed flag is invalid: {node_id}")
        return OpcUaSubscriptionNotification(
            observation=_project_data_value(
                mapping,
                data_value,
                received_at=received_at,
            ),
            replayed=replayed,
        )

    async def next_queue_overflow(self) -> OpcUaConnectorQueueOverflow:
        """Return the next explicit iterator-queue overflow signal."""
        return await self._overflow_queue.get()

    async def close(self) -> None:
        """Best-effort deterministic teardown suitable for graceful worker shutdown."""
        subscription = self._subscription
        self._subscription = None
        if subscription is not None:
            with suppress(Exception):
                await subscription.delete()

        state_context = self._state_context
        self._state_context = None
        self._state_subscription = None
        if state_context is not None:
            with suppress(Exception):
                await state_context.__aexit__(None, None, None)

        client = self._client
        self._client = None
        if client is not None:
            with suppress(Exception):
                await client.disconnect()
        self._data_change_type = None

    def _require_subscription(self) -> Any:
        if self._subscription is None:
            raise RuntimeError("persistent OPC UA subscription is not started")
        return self._subscription

    def _require_state_subscription(self) -> Any:
        if self._state_subscription is None:
            raise RuntimeError("persistent OPC UA state subscription is not started")
        return self._state_subscription


def _load_asyncua_module() -> Any:
    try:
        return import_module("asyncua")
    except ModuleNotFoundError as error:
        if error.name != "asyncua":
            raise
        raise OpcUaRuntimeUnavailableError(
            "OPC UA runtime is not installed; install the 'opcua' extra"
        ) from error


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
            "asyncua persistent subscription runtime is unavailable; install the 'opcua' extra"
        ) from error


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")


def _validate_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be at least 1")


def _validate_positive_finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ValueError(f"{field_name} must be a finite number")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
