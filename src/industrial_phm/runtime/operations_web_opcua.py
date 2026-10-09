"""Bounded, anonymous loopback OPC UA onboarding for opt-in Operations Web.

Do not accept arbitrary OPC UA hostnames or credentials in this preview:
one explicit local read is not authorization for remote network discovery.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from industrial_phm.application import (
    JsonSourceRepository,
    OpcUaSourceConfig,
    RegisteredSource,
    SourceLifecycleState,
    SourceRuntimeCycleResult,
    SourceRuntimeCycleState,
)
from industrial_phm.connectors import OpcUaNodeMapping
from industrial_phm.runtime.operations_app_actions import (
    OperationsAppActions,
    OperationsDiagnosticKind,
)
from industrial_phm.runtime.operations_app_wiring import resolve_operations_app_paths
from industrial_phm.runtime.operations_web_read import _utc
from industrial_phm.runtime.operations_web_setup import SourceControlConflict, _text

_REGISTRATION_FIELDS = frozenset(
    {"source_id", "name", "asset_id", "measurement_point_id", "endpoint_url", "node_mappings"}
)


def _loopback_endpoint(value: object) -> str:
    """Limit Web network actions to a literal local, anonymous OPC UA endpoint."""
    endpoint = _text({"value": value}, "value")
    assert isinstance(endpoint, str)
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError as error:
        raise ValueError("invalid OPC UA endpoint") from error
    if (
        parsed.scheme != "opc.tcp"
        or parsed.hostname != "127.0.0.1"
        or port is None
        or not 1 <= port <= 65535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.netloc != f"127.0.0.1:{port}"
    ):
        raise ValueError("Web OPC UA preview supports anonymous 127.0.0.1 endpoints only")
    return endpoint


def browse_local_opcua(root: Path, payload: dict[str, object]) -> dict[str, object]:
    """Discover bounded NodeIds, without registration or receipt persistence."""
    if set(payload) != {"endpoint_url"}:
        raise ValueError("unexpected OPC UA browse fields")
    endpoint = _loopback_endpoint(payload["endpoint_url"])
    paths = resolve_operations_app_paths({"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(root)})
    result = OperationsAppActions(paths).browse_opcua(
        endpoint_url=endpoint, timeout_seconds=2.0
    )
    variables = [
        {
            "node_id": row.node_id[:128],
            "browse_name": row.browse_name[:128],
            "display_name": row.display_name[:128],
        }
        for row in result.variables[:24]
    ]
    return {
        "schema_version": 1,
        "meaning": "address-space-candidates-not-received-or-registered",
        "connected_at": _utc(result.connected_at),
        "completed_at": _utc(result.completed_at),
        "visited_node_count": result.visited_node_count,
        "variables": variables,
        "truncated": result.truncated or len(result.variables) > len(variables),
    }


def register_local_opcua(root: Path, payload: dict[str, object]) -> dict[str, object]:
    """Register explicit channel/NodeId mappings without connecting or receiving."""
    if set(payload) != _REGISTRATION_FIELDS:
        raise ValueError("unexpected OPC UA registration fields")
    source_id = _text(payload, "source_id")
    name = _text(payload, "name")
    asset_id = _text(payload, "asset_id")
    point = _text(payload, "measurement_point_id", optional=True)
    endpoint = _loopback_endpoint(payload["endpoint_url"])
    raw = payload["node_mappings"]
    if not isinstance(raw, list) or not 1 <= len(raw) <= 12:
        raise ValueError("OPC UA requires 1 to 12 channel mappings")
    mappings: list[OpcUaNodeMapping] = []
    for item in raw:
        if not isinstance(item, dict) or set(item) != {"channel_id", "node_id"}:
            raise ValueError("invalid OPC UA mapping")
        channel_id = _text(item, "channel_id")
        node_id = _text(item, "node_id")
        assert isinstance(channel_id, str)
        assert isinstance(node_id, str)
        mappings.append(OpcUaNodeMapping(channel_id=channel_id, node_id=node_id))

    assert isinstance(source_id, str)
    assert isinstance(name, str)
    assert isinstance(asset_id, str)
    source = RegisteredSource(
        source_id=source_id,
        name=name,
        config=OpcUaSourceConfig(
            endpoint_url=endpoint,
            asset_id=asset_id,
            measurement_point_id=point,
            node_mappings=tuple(mappings),
            timeout_seconds=2.0,
        ),
        registered_at=datetime.now(UTC),
    )
    paths = resolve_operations_app_paths({"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(root)})
    OperationsAppActions(paths).register_source(source)
    return {
        "schema_version": 1,
        "source_id": source.source_id,
        "asset_id": source.asset_id,
        "registration_state": "registered",
        "receipt_confirmed": False,
        "meaning": "opcua-mapping-registered-not-connected-or-received",
    }


def diagnose_local_opcua(root: Path, payload: dict[str, object]) -> dict[str, object]:
    """Attempt one local read and persist the connector's actual receipt evidence."""
    if set(payload) != {"source_id"}:
        raise ValueError("unexpected OPC UA diagnostic fields")
    source_id = _text(payload, "source_id")
    assert isinstance(source_id, str)
    paths = resolve_operations_app_paths({"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(root)})
    repository = JsonSourceRepository(paths.registry)
    source = repository.get(source_id)
    if not isinstance(source.config, OpcUaSourceConfig):
        raise SourceControlConflict("OPC UA diagnostic requires an OPC UA source")
    _loopback_endpoint(source.config.endpoint_url)
    if len(source.config.node_mappings) > 12:
        raise SourceControlConflict("OPC UA source exceeds Web mapping limit")
    if repository.get_lifecycle(source_id).state != SourceLifecycleState.ACTIVE:
        raise SourceControlConflict("OPC UA diagnostic requires ACTIVE source")

    result, _ = OperationsAppActions(paths).run_diagnostic(
        source_id, kind=OperationsDiagnosticKind.CYCLE
    )
    assert isinstance(result, SourceRuntimeCycleResult)
    receipt = None
    if result.state == SourceRuntimeCycleState.SUCCEEDED:
        assert result.received is not None
        receipt = result.received.receipt
    return {
        "schema_version": 1,
        "source_id": source_id,
        "cycle_state": result.state.value,
        "accepted_new_receipt": receipt is not None,
        "accepted_received_at": None if receipt is None else _utc(receipt.received_at),
        "accepted_observed_at": None if receipt is None else _utc(receipt.observed_at),
        "failure_scope": None if result.failure_scope is None else result.failure_scope.value,
        "lifecycle_state": result.lifecycle_after.state.value,
        "meaning": "one-shot-opcua-read-not-continuous-collection-or-history",
    }
