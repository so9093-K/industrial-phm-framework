"""Operational source connector boundaries.

Connector modules keep protocol SDK dependencies optional and outside the core PHM runtime.
"""

from industrial_phm.connectors.opcua import (
    OpcUaNodeMapping,
    OpcUaNodeObservation,
    OpcUaReadConfig,
    OpcUaReadSnapshot,
    OpcUaRuntimeUnavailableError,
    OpcUaSourceError,
    read_opcua_snapshot,
)

__all__ = [
    "OpcUaNodeMapping",
    "OpcUaNodeObservation",
    "OpcUaReadConfig",
    "OpcUaReadSnapshot",
    "OpcUaRuntimeUnavailableError",
    "OpcUaSourceError",
    "read_opcua_snapshot",
]
