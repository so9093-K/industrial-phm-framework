"""Workspace-scoped FILE source registration and first-run web projection.

Only prepared CSV files already located inside the configured workspace can
be registered from this browser surface. Existing application services own the
validation, durable source registry and accepted receipt evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from industrial_phm.application import (
    CollectionDesiredState,
    FileSourceConfig,
    FileSourceMode,
    JsonSourceRepository,
    RegisteredSource,
    SourceLifecycleState,
    SourceRuntimeCycleState,
)
from industrial_phm.runtime.operations_app_actions import (
    OperationsAppActions,
    OperationsDiagnosticKind,
)
from industrial_phm.runtime.operations_app_composition import OperationsAppSnapshot
from industrial_phm.runtime.operations_app_wiring import resolve_operations_app_paths
from industrial_phm.runtime.operations_web_read import _utc

_MAX_SOURCES = 100
_MAX_INPUT_BYTES = 20 * 1024 * 1024
_FIELDS = frozenset(
    {
        "source_id",
        "name",
        "asset_id",
        "file_path",
        "channel_columns",
        "timestamp_column",
        "measurement_point_id",
    }
)


def project_web_source_setup(snapshot: OperationsAppSnapshot) -> dict[str, object]:
    """Represent registration and durable accepted receipt as separate facts."""
    lifecycle = {record.source_id: record for record in snapshot.lifecycle_records}
    receipts = {receipt.source_id: receipt for receipt in snapshot.receipts}
    requests = {record.source_id: record for record in snapshot.collection_records}
    sources: list[dict[str, object]] = []
    for source in snapshot.registered_sources:
        record = lifecycle.get(source.source_id)
        receipt = receipts.get(source.source_id)
        request = requests.get(source.source_id)
        sources.append(
            {
                "source_id": source.source_id,
                "name": source.name,
                "source_type": source.source_type.value,
                "asset_id": source.asset_id,
                "measurement_point_id": source.measurement_point_id,
                "channel_ids": [identity.channel_id for identity in source.channel_identities][:24],
                "lifecycle_state": None if record is None else record.state.value,
                "last_accepted_received_at": None if receipt is None else _utc(receipt.received_at),
                "last_accepted_observed_at": None if receipt is None else _utc(receipt.observed_at),
                "receipt_confirmed": receipt is not None,
                "continuous_collection_supported": source.source_type.value == "opcua",
                "collection_desired_state": (
                    None if request is None else request.desired_state.value
                ),
                "collection_request_generation": None if request is None else request.generation,
                "collection_requested_at": None if request is None else _utc(request.requested_at),
            }
        )
    return {
        "schema_version": 1,
        "assessed_at": _utc(snapshot.assessed_at),
        "meaning": "registration-does-not-imply-accepted-receipt-or-live-connection",
        "sources": {
            "items": sources[:_MAX_SOURCES],
            "total": len(sources),
            "truncated": len(sources) > _MAX_SOURCES,
        },
        "read_error_scopes": sorted(
            {
                item.scope
                for item in snapshot.system_errors
                if item.scope in {"source-settings", "source-runtime", "collection-control"}
            }
        ),
    }


def _text(payload: dict[str, object], key: str, *, optional: bool = False) -> str | None:
    value = payload.get(key)
    if optional and value in (None, ""):
        return None
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise ValueError("invalid field")
    if value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("invalid identifier")
    return value


def register_workspace_csv_source(root: Path, payload: dict[str, object]) -> dict[str, object]:
    """Validate one bounded, workspace-owned CSV, then call the existing write facade."""
    if set(payload) != _FIELDS:
        raise ValueError("unexpected registration fields")
    source_id = _text(payload, "source_id")
    name = _text(payload, "name")
    asset_id = _text(payload, "asset_id")
    timestamp = _text(payload, "timestamp_column", optional=True)
    point = _text(payload, "measurement_point_id", optional=True)
    file_path = _text(payload, "file_path")
    channels = payload["channel_columns"]
    if not isinstance(channels, list) or not 1 <= len(channels) <= 12:
        raise ValueError("invalid channel count")
    channel_ids: list[str] = []
    for value in channels:
        channel = _text({"channel": value}, "channel")
        if channel is None:
            raise ValueError("invalid channel")
        channel_ids.append(channel)
    if len(set(channel_ids)) != len(channel_ids):
        raise ValueError("duplicate channels")
    assert isinstance(source_id, str)
    assert isinstance(name, str)
    assert isinstance(asset_id, str)
    assert isinstance(file_path, str)
    if Path(file_path).is_absolute() or "\\" in file_path or ":" in file_path:
        raise ValueError("CSV path must be relative to workspace")
    target = (root / file_path).resolve(strict=True)
    if not target.is_relative_to(root) or target.suffix.lower() != ".csv":
        raise ValueError("CSV must be located inside workspace")
    if not target.is_file() or not 0 < target.stat().st_size <= _MAX_INPUT_BYTES:
        raise ValueError("CSV size outside registration limits")
    paths = resolve_operations_app_paths({"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(root)})
    source = RegisteredSource(
        source_id=source_id,
        name=name,
        config=FileSourceConfig(
            source_path=str(target),
            asset_id=asset_id,
            measurement_point_id=point,
            channel_columns=tuple(channel_ids),
            timestamp_column=timestamp,
        ),
        registered_at=datetime.now(UTC),
    )
    OperationsAppActions(paths).register_source(source)
    return {
        "schema_version": 1,
        "source_id": source.source_id,
        "asset_id": source.asset_id,
        "registration_state": "registered",
        "receipt_confirmed": False,
        "meaning": "validated-registration-only-not-collected",
    }


class SourceControlConflict(ValueError):
    """Existing source state forbids this transition or collection request."""


def change_web_source_control(
    root: Path, action: str, payload: dict[str, object]
) -> dict[str, object]:
    """Request one durable control-plane change, never a confirmed live connection.

    The existing application facade validates lifecycle transitions, source type
    and collection start prerequisites. Web transport owns only bounded input.
    """
    if set(payload) != {"source_id", "target_state"}:
        raise ValueError("unexpected source action fields")
    source_id = _text(payload, "source_id")
    target = _text(payload, "target_state")
    if source_id is None or target is None:
        raise ValueError("source action needs identity and target state")
    paths = resolve_operations_app_paths({"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(root)})
    facade = OperationsAppActions(paths)
    at = datetime.now(UTC)
    if action == "lifecycle":
        if target not in {"active", "paused"}:
            raise ValueError("unsupported source lifecycle target")
        try:
            record, _ = facade.transition_source(
                source_id, SourceLifecycleState(target), changed_at=at
            )
        except ValueError as error:
            raise SourceControlConflict("lifecycle transition rejected") from error
        return {
            "schema_version": 1,
            "source_id": record.source_id,
            "lifecycle_state": record.state.value,
            "changed_at": _utc(record.changed_at),
            "meaning": "administrative-state-not-connected-or-received",
        }
    if action == "collection":
        if target not in {"running", "stopped"}:
            raise ValueError("unsupported collection target")
        try:
            control_record, _ = facade.request_collection(
                source_id, CollectionDesiredState(target), requested_at=at
            )
        except ValueError as error:
            raise SourceControlConflict("collection request rejected") from error
        return {
            "schema_version": 1,
            "source_id": control_record.source_id,
            "desired_state": control_record.desired_state.value,
            "request_generation": control_record.generation,
            "requested_at": _utc(control_record.requested_at),
            "meaning": "desired-state-only-not-running-or-received",
        }
    raise ValueError("unknown source action")


def receive_workspace_file_source(root: Path, payload: dict[str, object]) -> dict[str, object]:
    """Run one existing FILE diagnostic; accepted receipt is not historical backfill.

    Only an ACTIVE, workspace-owned prepared snapshot CSV can be read by this
    preview. Re-check the registered path before every explicit invocation,
    rather than trusting a file registration made earlier.
    """
    if set(payload) != {"source_id"}:
        raise ValueError("unexpected FILE receipt fields")
    source_id = _text(payload, "source_id")
    assert isinstance(source_id, str)
    paths = resolve_operations_app_paths({"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(root)})
    registry = JsonSourceRepository(paths.registry)
    source = registry.get(source_id)
    if not isinstance(source.config, FileSourceConfig):
        raise SourceControlConflict("FILE receipt only supports FILE sources")
    if source.config.mode != FileSourceMode.SNAPSHOT:
        raise SourceControlConflict("FILE receipt only supports snapshot CSV")
    if registry.get_lifecycle(source_id).state != SourceLifecycleState.ACTIVE:
        raise SourceControlConflict("FILE receipt requires ACTIVE source")

    registered_path = Path(source.config.source_path)
    try:
        resolved = registered_path.resolve(strict=True)
        if (
            not registered_path.is_absolute()
            or resolved != registered_path
            or not resolved.is_relative_to(root)
            or resolved.suffix.lower() != ".csv"
            or not resolved.is_file()
            or not 0 < resolved.stat().st_size <= _MAX_INPUT_BYTES
        ):
            raise SourceControlConflict("FILE source path is outside Web receipt scope")
    except (OSError, RuntimeError) as error:
        raise SourceControlConflict("FILE source path is unavailable") from error

    outcome, _ = OperationsAppActions(paths).run_diagnostic(
        source_id, kind=OperationsDiagnosticKind.CYCLE
    )
    receipt = outcome.received.receipt if outcome.state == SourceRuntimeCycleState.SUCCEEDED else None
    return {
        "schema_version": 1,
        "source_id": source_id,
        "cycle_state": outcome.state.value,
        "accepted_new_receipt": receipt is not None,
        "accepted_received_at": None if receipt is None else _utc(receipt.received_at),
        "accepted_observed_at": None if receipt is None else _utc(receipt.observed_at),
        "failure_scope": None if outcome.failure_scope is None else outcome.failure_scope.value,
        "meaning": "file-receipt-only-not-history-backfill",
    }
