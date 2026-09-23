"""Operational source connector boundaries.

Connector modules keep protocol SDK dependencies optional and outside the core PHM runtime.
"""

from industrial_phm.connectors.opcua import (
    OpcUaBrowseConfig,
    OpcUaBrowseResult,
    OpcUaBrowseVariable,
    OpcUaEndpointProbeConfig,
    OpcUaEndpointProbeResult,
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
    probe_opcua_endpoint,
    read_opcua_snapshot,
)

__all__ = [
    "OpcUaBrowseConfig",
    "OpcUaBrowseResult",
    "OpcUaBrowseVariable",
    "OpcUaEndpointProbeConfig",
    "OpcUaEndpointProbeResult",
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
    "probe_opcua_endpoint",
    "read_opcua_snapshot",
]
