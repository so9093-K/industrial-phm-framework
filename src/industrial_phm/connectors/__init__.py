"""Operational source connector boundaries.

Connector modules keep protocol SDK dependencies optional and outside the core PHM runtime.
"""

from industrial_phm.connectors.opcua import (
    OpcUaBrowseConfig,
    OpcUaBrowseResult,
    OpcUaBrowseVariable,
    OpcUaNodeMapping,
    OpcUaNodeObservation,
    OpcUaReadConfig,
    OpcUaReadSnapshot,
    OpcUaRuntimeUnavailableError,
    OpcUaSourceError,
    OpcUaSubscriptionCompletionReason,
    OpcUaSubscriptionConfig,
    OpcUaSubscriptionNotification,
    OpcUaSubscriptionResult,
    browse_opcua_variables,
    collect_opcua_subscription_notifications,
    read_opcua_snapshot,
)

__all__ = [
    "OpcUaConnectorConnectionState",
    "OpcUaConnectorQueueOverflow",
    "OpcUaConnectorStateEvent",
    "OpcUaPersistentConnectorConfig",
    "OpcUaPersistentSubscription",
    "OpcUaBrowseConfig",
    "OpcUaBrowseResult",
    "OpcUaBrowseVariable",
    "OpcUaNodeMapping",
    "OpcUaNodeObservation",
    "OpcUaReadConfig",
    "OpcUaReadSnapshot",
    "OpcUaRuntimeUnavailableError",
    "OpcUaSourceError",
    "OpcUaSubscriptionCompletionReason",
    "OpcUaSubscriptionConfig",
    "OpcUaSubscriptionNotification",
    "OpcUaSubscriptionResult",
    "browse_opcua_variables",
    "collect_opcua_subscription_notifications",
    "read_opcua_snapshot",
]

from industrial_phm.connectors.opcua_persistent import (
    OpcUaConnectorConnectionState,
    OpcUaConnectorQueueOverflow,
    OpcUaConnectorStateEvent,
    OpcUaPersistentConnectorConfig,
    OpcUaPersistentSubscription,
)
