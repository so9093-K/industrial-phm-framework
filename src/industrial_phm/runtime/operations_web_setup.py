"""Workspace-scoped FILE source registration and first-run web projection.

Only prepared CSV files already located inside the configured workspace can
be registered from this browser surface. Existing application services own the
validation, durable source registry and accepted receipt evidence.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from industrial_phm.application import FileSourceConfig, RegisteredSource
from industrial_phm.runtime.operations_app_actions import OperationsAppActions
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
    sources: list[dict[str, object]] = []
    for source in snapshot.registered_sources:
        record = lifecycle.get(source.source_id)
        receipt = receipts.get(source.source_id)
        sources.append(
            {
                "source_id": source.source_id,
                "name": source.name,
                "source_type": source.source_type.value,
                "asset_id": source.asset_id,
                "measurement_point_id": source.measurement_point_id,
                "channel_ids": [identity.channel_id for identity in source.channel_identities][:24],
                "lifecycle_state": None if record is None else record.state.value,
                "last_accepted_received_at": None
                if receipt is None
                else _utc(receipt.received_at),
                "last_accepted_observed_at": None
                if receipt is None
                else _utc(receipt.observed_at),
                "receipt_confirmed": receipt is not None,
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
                if item.scope in {"source-settings", "source-runtime"}
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


def register_workspace_csv_source(
    root: Path, payload: dict[str, object]
) -> dict[str, object]:
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
    paths = resolve_operations_app_paths(
        {"INDUSTRIAL_PHM_OPERATIONS_WORKSPACE": str(root)}
    )
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
