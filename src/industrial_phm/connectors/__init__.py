"""Operational source connector boundaries.

Connector modules keep protocol SDK dependencies optional and outside the core PHM runtime.
"""

from industrial_phm.connectors.opcua import (
    OpcUaEndpointProbeConfig,
    OpcUaEndpointProbeResult,
    OpcUaNodeMapping,
    OpcUaNodeObservation,
    OpcUaReadConfig,
    OpcUaReadSnapshot,
    OpcUaRuntimeUnavailableError,
    OpcUaSourceError,
    probe_opcua_endpoint,
    read_opcua_snapshot,
)

__all__ = [
    "OpcUaEndpointProbeConfig",
    "OpcUaEndpointProbeResult",
    "OpcUaNodeMapping",
    "OpcUaNodeObservation",
    "OpcUaReadConfig",
    "OpcUaReadSnapshot",
    "OpcUaRuntimeUnavailableError",
    "OpcUaSourceError",
    "probe_opcua_endpoint",
    "read_opcua_snapshot",
]
