"""Workspace-scoped FILE source registration and first-run web projection.

Only prepared CSV files already located inside the configured workspace can
be registered from this browser surface. Existing application services own the
validation, durable source registry and accepted receipt evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from industrial_phm.application import (
    CollectionDesiredState,
    FileSourceConfig,
    FileSourceMode,
    JsonSourceRepository,
    JsonSourceRuntimeRepository,
    RegisteredSource,
    SourceLifecycleState,
    SourceRuntimeCycleResult,
    SourceRuntimeCycleState,
    backfill_registered_file_source,
)
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime.operations_app_actions import (
    OperationsAppActions,
    OperationsDiagnosticKind,
)
from industrial_phm.runtime.operations_app_composition import OperationsAppSnapshot
from industrial_phm.runtime.operations_app_wiring import (
    OperationsAppPaths,
    resolve_operations_app_paths,
)
from industrial_phm.runtime.operations_web_read import _utc

_MAX_SOURCES = 100
# Reuse the Operations monitor's existing heartbeat and receive-silence budgets.
_COLLECTION_HEARTBEAT_TIMEOUT = timedelta(seconds=20)
_LIVE_RECEIVE_TIMEOUT = timedelta(seconds=30)
_MAX_INPUT_BYTES = 20 * 1024 * 1024
# Conservative bound for synchronous browser history writes; registration may accept larger files.
_MAX_WEB_HISTORY_BYTES = 1024 * 1024
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


def _age_seconds(at: datetime | None, assessed_at: datetime) -> int | None:
    """Negative durations are invalid observations, not proof of freshness."""
    if at is None:
        return None
    age = (assessed_at - at).total_seconds()
    if age < 0:
        return None
    return int(age)


def _recent(at: datetime | None, assessed_at: datetime, budget: timedelta) -> bool:
    """Use full precision at the freshness boundary; do not round age up to fresh."""
    if at is None:
        return False
    age = assessed_at - at
    return timedelta(0) <= age <= budget


def project_web_source_setup(snapshot: OperationsAppSnapshot) -> dict[str, object]:
    """Keep desired state, one-shot receipts, live telemetry and stored batches apart."""
    lifecycle = {record.source_id: record for record in snapshot.lifecycle_records}
    receipts = {receipt.source_id: receipt for receipt in snapshot.receipts}
    requests = {record.source_id: record for record in snapshot.collection_records}
    live = {item.source.source_id: item.source for item in snapshot.acquisition_surfaces}
    service = snapshot.collection_service
    service_fresh = (
        service is not None
        and service.state.value == "running"
        and _recent(service.heartbeat_at, snapshot.assessed_at, _COLLECTION_HEARTBEAT_TIMEOUT)
    )
    sources: list[dict[str, object]] = []
    for source in snapshot.registered_sources:
        record = lifecycle.get(source.source_id)
        receipt = receipts.get(source.source_id)
        request = requests.get(source.source_id)
        live_source = live.get(source.source_id) if source.source_type.value == "opcua" else None
        session = None if live_source is None else live_source.session
        history = None if live_source is None else live_source.history
        received_at = None if live_source is None else live_source.last_received_at
        receive_age = _age_seconds(received_at, snapshot.assessed_at)
        # A persisted CONNECTED session can outlive its worker or service. Only
        # report recent connection *evidence* from this service generation.
        connected_evidence = (
            service_fresh
            and request is not None
            and request.desired_state.value == "running"
            and session is not None
            and session.state.value == "CONNECTED"
            and session.state_changed_at >= service.started_at
        )
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
                # Process-level heartbeat is NOT a per-source collector ready flag.
                "collection_service_state": None if service is None else service.state.value,
                "collection_service_heartbeat_at": (
                    None if service is None else _utc(service.heartbeat_at)
                ),
                "collection_service_heartbeat_fresh": service_fresh,
                "opcua_session_last_state": None if session is None else session.state.value,
                "opcua_session_state_changed_at": (
                    None if session is None else _utc(session.state_changed_at)
                ),
                "recent_connected_evidence": connected_evidence,
                # Live callback/receipt evidence is distinct from a one-shot diagnostic.
                "last_live_received_at": _utc(received_at),
                "last_live_receive_age_seconds": receive_age,
                "last_live_receive_fresh": _recent(
                    received_at, snapshot.assessed_at, _LIVE_RECEIVE_TIMEOUT
                ),
                # Only committed OPC UA spool history is projected here. FILE
                # backfill is verified separately with history channels/trend.
                "last_live_history_committed_at": (
                    None if history is None else _utc(history.committed_at)
                ),
                "last_live_history_snapshot_id": (None if history is None else history.snapshot_id),
                "last_live_history_batch_event_count": (
                    None if history is None else history.source_event_count
                ),
                "live_telemetry_read_error": (
                    any(
                        error.scope in {"live-data", f"live-data:{source.source_id}"}
                        for error in snapshot.system_errors
                    )
                ),
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
        "live_evidence_error_scopes": sorted(
            {
                item.scope
                for item in snapshot.system_errors
                if item.scope in {"live-data", "asset-history"}
                or item.scope.startswith("live-data:")
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
    paths, _, _ = _checked_workspace_file(root, source_id)

    outcome, _ = OperationsAppActions(paths).run_diagnostic(
        source_id, kind=OperationsDiagnosticKind.CYCLE
    )
    assert isinstance(outcome, SourceRuntimeCycleResult)
    receipt = None
    if outcome.state == SourceRuntimeCycleState.SUCCEEDED:
        assert outcome.received is not None
        receipt = outcome.received.receipt
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


def _checked_workspace_file(
    root: Path, source_id: str
) -> tuple[OperationsAppPaths, JsonSourceRepository, RegisteredSource]:
    """Recheck single-writer Web scope before each explicit FILE mutation."""
    paths = resolve_operations_app_paths({"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(root)})
    registry = JsonSourceRepository(paths.registry)
    source = registry.get(source_id)
    if not isinstance(source.config, FileSourceConfig):
        raise SourceControlConflict("Web FILE action requires a FILE source")
    if source.config.mode != FileSourceMode.SNAPSHOT:
        raise SourceControlConflict("Web FILE action only supports snapshot CSV")
    if registry.get_lifecycle(source_id).state != SourceLifecycleState.ACTIVE:
        raise SourceControlConflict("Web FILE action requires ACTIVE source")

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
            or len(source.config.channel_columns) > 12
        ):
            raise SourceControlConflict("FILE source outside bounded Web scope")
    except (OSError, RuntimeError) as error:
        raise SourceControlConflict("FILE source file unavailable") from error
    return paths, registry, source


def backfill_workspace_file_history(root: Path, payload: dict[str, object]) -> dict[str, object]:
    """Append or recover one existing FILE batch; never claim live receipt/analysis.

    The only supported Web path is an ACTIVE, small prepared snapshot CSV with
    timezone-aware source timestamps and an independently persisted receipt.
    """
    if set(payload) != {"source_id"}:
        raise ValueError("unexpected FILE history fields")
    source_id = _text(payload, "source_id")
    assert isinstance(source_id, str)
    paths, registry, source = _checked_workspace_file(root, source_id)
    assert isinstance(source.config, FileSourceConfig)
    if source.config.timestamp_column is None:
        raise SourceControlConflict("historical FILE backfill needs explicit timestamps")
    if Path(source.config.source_path).stat().st_size > _MAX_WEB_HISTORY_BYTES:
        raise SourceControlConflict("FILE too large for synchronous Web backfill")
    if JsonSourceRuntimeRepository(paths.source_runtime).get_latest_receipt(source_id) is None:
        raise SourceControlConflict("validate FILE receipt before history backfill")

    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(
            catalog_path=paths.history_catalog,
            data_path=paths.history_data,
        )
    )
    result = backfill_registered_file_source(registry, history, source_id)
    return {
        "schema_version": 1,
        "source_id": result.source_id,
        "asset_id": result.asset_id,
        "event_count": result.event_count,
        "segment_count": len(result.segments),
        "recovered_segment_count": result.recovered_segment_count,
        "history_snapshot_id": result.history_snapshot_id,
        "meaning": "persisted-file-history-not-live-collection-or-analysis",
    }
