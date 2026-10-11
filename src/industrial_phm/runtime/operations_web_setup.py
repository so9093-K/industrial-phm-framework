"""Workspace-scoped FILE source registration and first-run web projection.

Only prepared CSV files already located inside the configured workspace can
be registered from this browser surface. Existing application services own the
validation, durable source registry and accepted receipt evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from industrial_phm.adapters.csv_sensor import (
    CsvSensorSourceError,
    validate_csv_sensor_source,
)
from industrial_phm.application import (
    ChannelSemanticBinding,
    CollectionDesiredState,
    FileSourceConfig,
    FileSourceMode,
    JsonSourceRepository,
    JsonSourceRuntimeRepository,
    MeasurementDefinition,
    RegisteredSource,
    SourceLifecycleState,
    SourceRuntimeCycleResult,
    SourceRuntimeCycleState,
    SqlitePhaseUnbalanceRepository,
    backfill_registered_file_source,
    run_phase_unbalance_analysis,
)
from industrial_phm.application.measurement_semantics import serialize_channel_semantic_binding
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
_PHASE_FILE_FIELD = "phase_channels"
_PHASE_CHANNEL_FIELDS = frozenset(
    {"channel_id", "quantity", "phase", "unit_evidence", "interpretation_evidence"}
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
            and service is not None
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
                "phase_binding_count": (
                    len(source.config.semantic_bindings)
                    if isinstance(source.config, FileSourceConfig)
                    else 0
                ),
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


def _file_phase_bindings(
    payload: dict[str, object], source_id: str, channels: tuple[str, ...]
) -> tuple[ChannelSemanticBinding, ...]:
    """Interpret only explicitly selected V/A three-phase roles with evidence."""
    raw = payload.get(_PHASE_FILE_FIELD, [])
    if not isinstance(raw, list) or len(raw) not in {0, 3, 6}:
        raise ValueError("phase channels require zero, three or six explicit roles")
    bindings: list[ChannelSemanticBinding] = []
    roles: set[tuple[str, str]] = set()
    assigned: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or set(item) != _PHASE_CHANNEL_FIELDS:
            raise ValueError("invalid phase channel fields")
        channel = _text(item, "channel_id")
        quantity = _text(item, "quantity")
        phase = _text(item, "phase")
        unit_evidence = _text(item, "unit_evidence")
        interpretation_evidence = _text(item, "interpretation_evidence")
        assert isinstance(channel, str)
        assert isinstance(quantity, str)
        assert isinstance(phase, str)
        assert isinstance(unit_evidence, str)
        assert isinstance(interpretation_evidence, str)
        if quantity not in {"voltage", "current"} or phase not in {"R", "S", "T"}:
            raise ValueError("only explicit R/S/T voltage V or current A roles are supported")
        if channel not in channels or channel in assigned or (quantity, phase) in roles:
            raise ValueError("phase roles must map distinct registered channels")
        assigned.add(channel)
        roles.add((quantity, phase))
        bindings.append(
            ChannelSemanticBinding(
                source_id=source_id,
                channel_id=channel,
                version="file-web-phase-v1",
                definition=MeasurementDefinition(
                    observed_property=f"phase {quantity}",
                    scope=f"phase {phase}",
                    unit="V" if quantity == "voltage" else "A",
                    unit_evidence=unit_evidence,
                ),
                interpretation_evidence=interpretation_evidence,
            )
        )
    for quantity in ("voltage", "current"):
        selected = {phase for selected_quantity, phase in roles if selected_quantity == quantity}
        if selected and selected != {"R", "S", "T"}:
            raise ValueError("each selected quantity requires R/S/T phase bindings")
    return tuple(bindings)


def _prepare_workspace_csv_source(root: Path, payload: dict[str, object]) -> RegisteredSource:
    """Build the exact registered FILE candidate without persisting it."""
    if set(payload) not in {_FIELDS, _FIELDS | {_PHASE_FILE_FIELD}}:
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
    source = RegisteredSource(
        source_id=source_id,
        name=name,
        config=FileSourceConfig(
            source_path=str(target),
            asset_id=asset_id,
            measurement_point_id=point,
            channel_columns=tuple(channel_ids),
            timestamp_column=timestamp,
            semantic_bindings=_file_phase_bindings(payload, source_id, tuple(channel_ids)),
        ),
        registered_at=datetime.now(UTC),
    )
    return source


def register_workspace_csv_source(root: Path, payload: dict[str, object]) -> dict[str, object]:
    """Register a validated workspace-owned CSV; registration is not ingestion."""
    source = _prepare_workspace_csv_source(root, payload)
    paths = resolve_operations_app_paths({"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(root)})
    OperationsAppActions(paths).register_source(source)
    return {
        "schema_version": 1,
        "source_id": source.source_id,
        "asset_id": source.asset_id,
        "registration_state": "registered",
        "receipt_confirmed": False,
        "meaning": "validated-registration-only-not-collected",
    }


_MAX_WEB_UPLOAD_BYTES = 1024 * 1024
_UPLOAD_FIELDS = (_FIELDS - {"file_path"}) | {"staged_name"}
_UPLOAD_OPTIONAL_FIELDS = _UPLOAD_FIELDS | {_PHASE_FILE_FIELD}
_STAGED_CSV_NAME = re.compile(r"[0-9a-f]{32}\.csv\Z")


def register_uploaded_csv_source(
    root: Path, payload: dict[str, object], *, upload_directory: Path
) -> dict[str, object]:
    """Register browser CSV via the supervisor's private staging area.

    The supervised UI child may stage a bounded file, but only this existing
    single-writer action may copy it into the persistent workspace and register
    its source. Never trust a browser-controlled absolute path.
    """
    if set(payload) not in {_UPLOAD_FIELDS, _UPLOAD_OPTIONAL_FIELDS}:
        raise ValueError("unexpected CSV upload fields")
    staged_name = payload["staged_name"]
    if not isinstance(staged_name, str) or _STAGED_CSV_NAME.fullmatch(staged_name) is None:
        raise ValueError("invalid staged CSV identity")
    stage_root = upload_directory.resolve(strict=True)
    staged = upload_directory / staged_name
    if (
        staged.is_symlink()
        or not staged.is_file()
        or staged.resolve(strict=True).parent != stage_root
    ):
        raise ValueError("CSV staging location invalid")
    if not 0 < staged.stat().st_size <= _MAX_WEB_UPLOAD_BYTES:
        raise ValueError("CSV upload too large")

    # The broker owns the staging directory and refuses arbitrary staged paths.
    # UTF-8 decoding here rejects binary payloads before durable files are created.
    descriptor = os.open(staged, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as stream:
        raw = stream.read(_MAX_WEB_UPLOAD_BYTES + 1)
    if not 0 < len(raw) <= _MAX_WEB_UPLOAD_BYTES:
        raise ValueError("CSV upload too large")
    text = raw.decode("utf-8-sig")
    if "\x00" in text:
        raise ValueError("CSV contains binary data")

    destination_dir = root / "web-uploads"
    if destination_dir.is_symlink():
        raise ValueError("workspace upload directory is not trusted")
    destination_dir.mkdir(mode=0o700, exist_ok=True)
    if destination_dir.resolve(strict=True).parent != root.resolve():
        raise ValueError("workspace upload directory escapes workspace")
    destination = destination_dir / staged_name
    # Exclusive creation protects existing source bytes; no rewrite or overwrite.
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
        registration = {key: value for key, value in payload.items() if key != "staged_name"}
        registration["file_path"] = f"web-uploads/{staged_name}"
        return register_workspace_csv_source(root, registration)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


_CSV_DIAGNOSTICS: tuple[tuple[str, str, str], ...] = (
    (
        "missing required columns",
        "missing-column",
        "선택한 시간·측정 컬럼이 없습니다. CSV 헤더를 확인하세요.",
    ),
    (
        "duplicate column names",
        "duplicate-header",
        "CSV 헤더의 중복 컬럼명을 수정하세요.",
    ),
    ("empty column name", "empty-header", "CSV 헤더의 빈 컬럼명을 수정하세요."),
    (
        "must be an ISO 8601 timestamp",
        "timestamp-format",
        "시간을 ISO 8601로 기록하세요. 예: 2026-10-11T09:00:00+09:00",
    ),
    (
        "contains a missing timestamp",
        "missing-timestamp",
        "표시된 행의 빈 시각을 확인하세요.",
    ),
    (
        "timestamps must use consistent timezone awareness",
        "mixed-timezone",
        "모든 시각에 시간대 포함 여부를 일치시키세요.",
    ),
    (
        "timestamps must be strictly increasing",
        "time-order",
        "시간이 중복·역순입니다. 행 순서를 확인하세요.",
    ),
    (
        "contains a missing value",
        "missing-value",
        "표시된 행·컬럼의 누락값을 확인하세요.",
    ),
    ("must be numeric", "non-numeric", "측정 컬럼에 숫자만 기록하세요."),
    ("must be finite", "non-finite", "NaN·무한대는 사용할 수 없습니다."),
    ("has", "row-width", "행의 컬럼 수와 CSV 쉼표·인용부호를 확인하세요."),
    ("not valid UTF-8", "encoding", "파일을 UTF-8 CSV로 다시 저장하세요."),
)


def _csv_preflight_problem(error: Exception) -> dict[str, object]:
    message = str(error)
    if "phase channels" in message or "phase role" in message or "phase binding" in message:
        diagnostic = (
            "phase-mapping",
            "V/A 단위와 서로 다른 R/S/T 채널 3개 또는 6개를 지정하고 근거를 확인하세요.",
        )
    elif "timestamp_column or sampling_rate_hz" in message:
        diagnostic = ("timestamp-required", "명시적 시간 컬럼을 선택하세요.")
    elif "CSV path" in message or "inside workspace" in message:
        diagnostic = ("invalid-path", "CSV의 작업공간 내부 상대 경로를 확인하세요.")
    else:
        diagnostic = next(
            (
                (code, guidance)
                for pattern, code, guidance in _CSV_DIAGNOSTICS
                if pattern in message
            ),
            (
                "csv-invalid",
                "CSV 헤더·측정값·시간 형식을 확인하세요. 등록이나 저장은 하지 않았습니다.",
            ),
        )
    match = re.search(r"CSV row (\d+) column '([^']{1,128})'", message)
    if match is None:
        match = re.search(r"CSV row (\d+)", message)
    return {
        "code": diagnostic[0],
        "guidance": diagnostic[1],
        "row_number": int(match.group(1)) if match else None,
        "column": match.group(2) if match and match.lastindex == 2 else None,
    }


def _csv_preflight_result(source: RegisteredSource) -> dict[str, object]:
    """Read only; never produce receipt, history, analysis, or registration."""
    assert isinstance(source.config, FileSourceConfig)
    try:
        report = validate_csv_sensor_source(
            Path(source.config.source_path), source.config.to_csv_sensor_layout()
        )
    except (CsvSensorSourceError, ValueError) as error:
        return {
            "schema_version": 1,
            "status": "blocked",
            "sample_count": None,
            "history_ready": False,
            "phase_mapping_ready": False,
            "issue": _csv_preflight_problem(error),
            "meaning": "csv-preflight-only-not-registered-or-ingested",
        }
    start, end = report.first_timestamp, report.last_timestamp
    timezone_aware = (
        start is not None
        and end is not None
        and all(value.utcoffset() is not None for value in (start, end))
    )
    history_ready = timezone_aware
    status = "ready" if history_ready else "needs_input"
    if not history_ready:
        issue: dict[str, object] | None = {
            "code": "timestamp-required" if start is None else "timezone-required",
            "guidance": (
                "이력 적재에는 시간 컬럼을 지정해야 합니다."
                if start is None
                else (
                    "이력 적재에는 시간대가 있는 ISO 8601 값이 필요합니다. "
                    "예: 2026-10-11T09:00:00+09:00"
                )
            ),
            "row_number": None,
            "column": source.config.timestamp_column,
        }
    else:
        issue = None
    return {
        "schema_version": 1,
        "status": status,
        "sample_count": report.sample_count,
        "channel_columns": list(report.channels),
        "first_timestamp": start.isoformat() if start else None,
        "last_timestamp": end.isoformat() if end else None,
        "source_sha256": report.source_sha256,
        "source_size_bytes": report.source_size_bytes,
        "history_ready": history_ready,
        "phase_mapping_ready": history_ready and len(source.config.semantic_bindings) >= 3,
        "semantic_binding_count": len(source.config.semantic_bindings),
        "quality_warnings": [issue.code for issue in report.quality_issues],
        "issue": issue,
        "meaning": "csv-preflight-only-not-registered-or-ingested",
    }


def preflight_workspace_csv_source(root: Path, payload: dict[str, object]) -> dict[str, object]:
    """Check a bounded workspace file using the registration contract, without writing."""
    try:
        source = _prepare_workspace_csv_source(root, payload)
    except (ValueError, FileNotFoundError, NotADirectoryError, OSError) as error:
        return {
            "schema_version": 1,
            "status": "blocked",
            "sample_count": None,
            "history_ready": False,
            "phase_mapping_ready": False,
            "issue": _csv_preflight_problem(error),
            "meaning": "csv-preflight-only-not-registered-or-ingested",
        }
    return _csv_preflight_result(source)


def preflight_uploaded_csv_source(
    root: Path, payload: dict[str, object], *, upload_directory: Path
) -> dict[str, object]:
    """Validate an ephemeral upload, without copying into the workspace."""
    if set(payload) not in {_UPLOAD_FIELDS, _UPLOAD_OPTIONAL_FIELDS}:
        raise ValueError("unexpected CSV preflight fields")
    staged_name = payload["staged_name"]
    if not isinstance(staged_name, str) or _STAGED_CSV_NAME.fullmatch(staged_name) is None:
        raise ValueError("invalid staged CSV identity")
    if upload_directory.is_symlink():
        raise ValueError("untrusted staging directory")
    stage_root = upload_directory.resolve(strict=True)
    staged = upload_directory / staged_name
    if (
        staged.is_symlink()
        or not staged.is_file()
        or staged.resolve(strict=True).parent != stage_root
        or not 0 < staged.stat().st_size <= _MAX_WEB_UPLOAD_BYTES
    ):
        raise ValueError("CSV staging location invalid")
    try:
        source_id = _text(payload, "source_id")
        name = _text(payload, "name")
        asset_id = _text(payload, "asset_id")
        point = _text(payload, "measurement_point_id", optional=True)
        timestamp = _text(payload, "timestamp_column", optional=True)
        channels = payload["channel_columns"]
        if not isinstance(channels, list) or not 1 <= len(channels) <= 12:
            raise ValueError("invalid channel count")
        channel_ids: list[str] = []
        for item in channels:
            channel = _text({"channel": item}, "channel")
            if channel is None:
                raise ValueError("invalid channel")
            channel_ids.append(channel)
        if len(set(channel_ids)) != len(channel_ids):
            raise ValueError("duplicate or invalid channel")
        assert isinstance(source_id, str)
        assert isinstance(name, str)
        assert isinstance(asset_id, str)
        config = FileSourceConfig(
            source_path=str(staged),
            asset_id=asset_id,
            measurement_point_id=point,
            channel_columns=tuple(channel_ids),
            timestamp_column=timestamp,
            semantic_bindings=_file_phase_bindings(payload, source_id, tuple(channel_ids)),
        )
        source = RegisteredSource(
            source_id=source_id, name=name, config=config, registered_at=datetime.now(UTC)
        )
    except (ValueError, TypeError) as error:
        return {
            "schema_version": 1,
            "status": "blocked",
            "sample_count": None,
            "history_ready": False,
            "phase_mapping_ready": False,
            "issue": _csv_preflight_problem(error),
            "meaning": "csv-preflight-only-not-registered-or-ingested",
        }
    return _csv_preflight_result(source)


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


def analyze_workspace_file_source(root: Path, payload: dict[str, object]) -> dict[str, object]:
    """Produce a new persisted FILE feature Run/Evidence from the registered CSV.

    This uses the existing snapshot feature producer, not DuckLake backfill or a
    synthetic analysis fixture. It never infers equipment health or fault status.
    """
    if set(payload) != {"source_id"}:
        raise ValueError("unexpected FILE analysis fields")
    source_id = _text(payload, "source_id")
    assert isinstance(source_id, str)
    paths, _, source = _checked_workspace_file(root, source_id)
    assert isinstance(source.config, FileSourceConfig)
    if Path(source.config.source_path).stat().st_size > _MAX_WEB_HISTORY_BYTES:
        raise SourceControlConflict("FILE too large for synchronous Web analysis")
    if JsonSourceRuntimeRepository(paths.source_runtime).get_latest_receipt(source_id) is None:
        raise SourceControlConflict("validate FILE receipt before analysis")

    result, _ = OperationsAppActions(paths).record_file_analysis(source)
    return {
        "schema_version": 1,
        "source_id": source_id,
        "asset_id": result.run.asset_id,
        "analysis_run_id": result.run.analysis_run_id,
        "evidence_id": result.evidence.evidence_id,
        "capability_id": result.evidence.capability_id,
        "source_snapshot_sha256": result.evidence.source_snapshot_sha256,
        "meaning": "persisted-file-statistical-features-not-diagnosis-or-history",
    }


def analyze_workspace_file_phase(root: Path, payload: dict[str, object]) -> dict[str, object]:
    """Analyze only exact, already committed, meaning-bound FILE history."""
    if set(payload) != {"source_id"}:
        raise ValueError("unexpected phase analysis fields")
    source_id = _text(payload, "source_id")
    assert isinstance(source_id, str)
    paths, _, source = _checked_workspace_file(root, source_id)
    assert isinstance(source.config, FileSourceConfig)
    if not source.config.semantic_bindings:
        raise SourceControlConflict("FILE requires explicit three-phase semantic bindings")
    file_path = Path(source.config.source_path)
    if file_path.stat().st_size > _MAX_WEB_HISTORY_BYTES:
        raise SourceControlConflict("FILE too large for synchronous phase analysis")
    if JsonSourceRuntimeRepository(paths.source_runtime).get_latest_receipt(source_id) is None:
        raise SourceControlConflict("validate FILE receipt before phase analysis")
    if not paths.history_catalog.is_file():
        raise SourceControlConflict("persist FILE history before phase analysis")

    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(paths.history_catalog, paths.history_data)
    )
    events = history.query_file_events(source_id)
    if not events or len(events) > 100_000:
        raise SourceControlConflict("bounded FILE history evidence unavailable")
    source_bytes = file_path.read_bytes()
    digest = hashlib.sha256(source_bytes).hexdigest()
    known_channels = set(source.config.channel_columns)
    semantic_snapshots = {
        binding.channel_id: serialize_channel_semantic_binding(binding)
        for binding in source.config.semantic_bindings
    }
    if any(
        event.source_sha256 != digest
        or event.source_size_bytes != len(source_bytes)
        or event.source_file != file_path.name
        or event.asset_id != source.asset_id
        or event.measurement_point_id != source.measurement_point_id
        or event.channel_id not in known_channels
        or (
            event.channel_id in semantic_snapshots
            and (
                event.source_metadata_json is None
                or json.loads(event.source_metadata_json).get("semantics")
                != semantic_snapshots[event.channel_id]
            )
        )
        for event in events
    ):
        raise SourceControlConflict("stored FILE history does not match source or binding")
    start_at = min(event.event_at for event in events)
    end_at = max(event.event_at for event in events) + timedelta(microseconds=1)
    snapshot = history.current_snapshot_id()
    result = run_phase_unbalance_analysis(
        history,
        asset_id=source.asset_id,
        source_id=source_id,
        start_at=start_at,
        end_at=end_at,
        measurement_point_id=source.measurement_point_id,
        snapshot_id=snapshot,
    )
    SqlitePhaseUnbalanceRepository(paths.phase_analysis).record(result)
    return {
        "schema_version": 1,
        "source_id": source_id,
        "asset_id": source.asset_id,
        "analysis_run_id": result.run.analysis_run_id,
        "evidence_id": result.evidence.evidence_id,
        "capability_id": result.evidence.capability_id,
        "history_snapshot_id": snapshot,
        "source_sha256": digest,
        "meaning": "persisted-phase-unbalance-from-bound-file-history-not-fault-diagnosis",
    }


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
