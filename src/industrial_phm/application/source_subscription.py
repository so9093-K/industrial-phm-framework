"""Bounded OPC UA subscription collection for registered operational sources."""

from __future__ import annotations

from dataclasses import dataclass

from industrial_phm.application.source_lifecycle import (
    SourceLifecycleRepository,
    SourceLifecycleState,
)
from industrial_phm.application.source_registration import (
    OpcUaSourceConfig,
    SourceRepository,
)
from industrial_phm.connectors import (
    OpcUaNodeMapping,
    OpcUaSubscriptionConfig,
    OpcUaSubscriptionResult,
    collect_opcua_subscription_notifications,
)


@dataclass(frozen=True, slots=True)
class RegisteredOpcUaSubscription:
    """One bounded subscription result tied to registered source identity and mapping.

    The notification sequence is event-level evidence. Its length does not imply that
    every configured channel produced a notification or that a complete observation
    snapshot/window exists.
    """

    source_id: str
    asset_id: str
    endpoint_url: str
    node_mappings: tuple[OpcUaNodeMapping, ...]
    subscription: OpcUaSubscriptionResult
    measurement_point_id: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        _validate_identifier(self.asset_id, "asset_id")
        _validate_identifier(self.endpoint_url, "endpoint_url")
        if self.measurement_point_id is not None:
            _validate_identifier(self.measurement_point_id, "measurement_point_id")
        if not self.node_mappings:
            raise ValueError("node_mappings must not be empty")
        if not all(isinstance(mapping, OpcUaNodeMapping) for mapping in self.node_mappings):
            raise ValueError("node_mappings must contain OpcUaNodeMapping values")
        if not isinstance(self.subscription, OpcUaSubscriptionResult):
            raise ValueError("subscription must be an OpcUaSubscriptionResult")
        if self.subscription.endpoint_url != self.endpoint_url:
            raise ValueError("subscription endpoint_url must match the registered OPC UA endpoint")

        mapping_pairs = {
            (mapping.channel_id, mapping.node_id) for mapping in self.node_mappings
        }
        for notification in self.subscription.notifications:
            observation = notification.observation
            if (observation.channel_id, observation.node_id) not in mapping_pairs:
                raise ValueError(
                    "subscription notification must match the registered OPC UA mapping"
                )


async def collect_registered_opcua_source_subscription(
    source_repository: SourceRepository,
    lifecycle_repository: SourceLifecycleRepository,
    source_id: str,
    *,
    publishing_interval_ms: float = 500.0,
    collection_timeout_seconds: float = 5.0,
    max_events: int = 1,
    queue_maxsize: int = 128,
) -> RegisteredOpcUaSubscription:
    """Collect one bounded subscription session for an ACTIVE registered OPC UA source.

    Endpoint, explicit NodeId mapping and request timeout always come from the registered
    source. Runtime collection bounds are supplied by this explicit call. The function
    does not persist notifications, mutate lifecycle, infer complete-channel observations,
    retry, reconnect, or create background execution.
    """
    source = source_repository.get(source_id)
    lifecycle = lifecycle_repository.get_lifecycle(source_id)
    if lifecycle.state != SourceLifecycleState.ACTIVE:
        raise ValueError(
            "registered OPC UA subscription collection requires an active source lifecycle"
        )

    config = source.config
    if not isinstance(config, OpcUaSourceConfig):
        raise ValueError("registered OPC UA subscription requires OpcUaSourceConfig")

    subscription_config = OpcUaSubscriptionConfig(
        endpoint_url=config.endpoint_url,
        node_mappings=tuple(config.node_mappings),
        publishing_interval_ms=publishing_interval_ms,
        collection_timeout_seconds=collection_timeout_seconds,
        max_events=max_events,
        queue_maxsize=queue_maxsize,
        timeout_seconds=config.timeout_seconds,
    )
    result = await collect_opcua_subscription_notifications(subscription_config)
    return RegisteredOpcUaSubscription(
        source_id=source.source_id,
        asset_id=config.asset_id,
        endpoint_url=config.endpoint_url,
        measurement_point_id=config.measurement_point_id,
        node_mappings=tuple(config.node_mappings),
        subscription=result,
    )


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
