"""Build an anomaly model from a person's chosen reference period and bind it (ADR-0032)."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from industrial_phm.application.history_window import (
    MAX_CHANNELS,
    HistoryModelRequest,
    build_history_model,
)
from industrial_phm.history import DuckLakeAssetHistory
from industrial_phm.history.ducklake import DuckLakeAssetHistoryConfig
from industrial_phm.runtime.operations_web_phm_models import create_phm_binding
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

HISTORY_MODEL_BUILD_ROUTE = "/api/v1/phm/models/build"
_REQUIRED = {
    "asset_id",
    "source_id",
    "channels",
    "reference_start",
    "reference_end",
    "window_seconds",
}


def _text(payload: dict[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 512:
        raise ValueError(f"invalid {name}")
    return value


def _instant(payload: dict[str, object], name: str) -> datetime:
    at = datetime.fromisoformat(_text(payload, name))
    if at.utcoffset() is None:
        raise ValueError(f"{name} must carry a time zone")
    return at.astimezone(UTC)


def _revision() -> str:
    try:
        return "industrial-phm-framework " + version("industrial-phm-framework")
    except PackageNotFoundError:
        return "industrial-phm (source)"


def build_web_history_model(root: Path, payload: dict[str, object]) -> dict[str, object]:
    """Exactly the fields the 모델 점수 screen sends; the period is read at one snapshot."""
    keys = set(payload)
    if not keys >= _REQUIRED or keys - _REQUIRED - {"measurement_point_id"}:
        raise ValueError("unexpected model build fields")
    channels = payload["channels"]
    if not isinstance(channels, list) or not 1 <= len(channels) <= MAX_CHANNELS:
        raise ValueError(f"choose 1 to {MAX_CHANNELS} signals")
    if any(not isinstance(c, str) or not c or len(c) > 512 for c in channels):
        raise ValueError("invalid signal")
    seconds = payload["window_seconds"]
    if isinstance(seconds, bool) or not isinstance(seconds, int):
        raise ValueError("invalid window length")
    point = payload.get("measurement_point_id")
    if point is not None:
        point = _text(payload, "measurement_point_id")
    request = HistoryModelRequest(
        asset_id=_text(payload, "asset_id"),
        source_id=_text(payload, "source_id"),
        channels=tuple(channels),
        reference_start=_instant(payload, "reference_start"),
        reference_end=_instant(payload, "reference_end"),
        window_seconds=seconds,
        measurement_point_id=point,
    )
    workspace = OperationsWorkspace(root)
    if not workspace.history_catalog_path.is_file():
        raise ValueError("no stored measurement history")
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    built = build_history_model(
        workspace.models_path,
        history,
        request,
        created_at=datetime.now(UTC),
        code_revision=_revision(),
    )
    body: dict[str, object] = {
        "schema_version": 1,
        "built": built.package_id is not None,
        "reference_windows": built.reference_windows,
        "skipped_windows": built.skipped_windows,
        "reused": built.reused,
    }
    if built.package_id is None:
        return {**body, "reason": built.reason}
    binding, _, _ = create_phm_binding(
        workspace,
        package_id=built.package_id,
        source_id=request.source_id,
        asset_id=request.asset_id,
        measurement_point_id=request.measurement_point_id,
    )
    return {
        **body,
        "package_id": built.package_id,
        "binding_id": binding.binding_id,
        "threshold": built.threshold,
    }
