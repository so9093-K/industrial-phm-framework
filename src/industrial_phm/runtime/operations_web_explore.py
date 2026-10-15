"""Read-only signal exploration routes: what can be explored, and two-period profiles."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs

from industrial_phm.application.acquisition_snapshot import (
    AcquisitionSnapshotError,
    SqliteAcquisitionSnapshotRepository,
)
from industrial_phm.application.phm_analysis import PhmAnalysisError, SqlitePhmAnalysisStore
from industrial_phm.application.signal_exploration import (
    MAX_SERIES,
    acquisition_binding,
    acquisition_relation,
    acquisition_series,
    acquisition_source,
    acquisition_spectrum,
    history_relation,
    history_series,
)
from industrial_phm.history import DuckLakeAssetHistory
from industrial_phm.history.ducklake import DuckLakeAssetHistoryConfig
from industrial_phm.models.package import RETIRED_TASKS
from industrial_phm.runtime.operations_live import OperationsReadError
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

EXPLORE_READ_ROUTES = frozenset(
    {
        "/api/v1/explore/sources",
        "/api/v1/explore/profile",
        "/api/v1/explore/relation",
        "/api/v1/explore/spectrum",
    }
)
_MAX_ID_LENGTH = 512


def _query(raw: str) -> dict[str, list[str]]:
    parsed = parse_qs(raw, keep_blank_values=True, strict_parsing=False)
    if any(len(values) != 1 for name, values in parsed.items() if name != "series"):
        raise ValueError("repeated query parameter")
    return parsed


def _one(query: dict[str, list[str]], name: str) -> str:
    value = (query.get(name) or [""])[0]
    if not value or len(value) > _MAX_ID_LENGTH or any(ord(c) < 32 for c in value):
        raise ValueError(f"invalid {name}")
    return value


def _instant(query: dict[str, list[str]], name: str) -> datetime:
    value = datetime.fromisoformat(_one(query, name).replace("Z", "+00:00"))
    if value.utcoffset() is None:
        raise ValueError(f"{name} must carry a time zone")
    return value


def _history(workspace: OperationsWorkspace) -> DuckLakeAssetHistory | None:
    if not workspace.history_catalog_path.is_file():
        return None
    return DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )


def handle_explore_read(
    workspace: OperationsWorkspace, path: str, raw_query: str
) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        query = _query(raw_query)
        asset_id = _one(query, "asset_id")
        store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
        if path == "/api/v1/explore/sources":
            return HTTPStatus.OK, explore_sources(workspace, store, asset_id)
        if path in {"/api/v1/explore/relation", "/api/v1/explore/spectrum"}:
            return HTTPStatus.OK, _relation_or_spectrum(workspace, store, asset_id, path, query)
        series = [value for value in query.get("series", []) if value]
        if not 1 <= len(series) <= MAX_SERIES or len(set(series)) != len(series):
            raise ValueError(f"choose 1 to {MAX_SERIES} distinct series")
        kind = _one(query, "kind")
        if kind == "history":
            history = _history(workspace)
            if history is None:
                raise LookupError("no stored measurement history")
            periods = [
                (name, _instant(query, f"{name}_from"), _instant(query, f"{name}_to"))
                for name in ("a", "b")
            ]
            profiles = history.query_measurement_profiles(
                asset_id, channel_ids=series, periods=periods
            )
            body = history_series(profiles, periods)
            ranges: dict[str, dict[str, Any]] = {
                name: {"from": start.isoformat(), "to": end.isoformat()}
                for name, start, end in periods
            }
        elif kind == "acquisition":
            binding = acquisition_binding(store, asset_id) if store.path.exists() else None
            if binding is None:
                raise LookupError("no stored acquisition features")
            spans = [
                (name, int(_one(query, f"{name}_from")), int(_one(query, f"{name}_to")))
                for name in ("a", "b")
            ]
            body = acquisition_series(
                store,
                SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
                binding,
                series,
                spans,
            )
            ranges = {name: {"from": first, "to": last} for name, first, last in spans}
        else:
            raise ValueError("unknown exploration kind")
        return HTTPStatus.OK, {
            "schema_version": 1,
            "asset_id": asset_id,
            "kind": kind,
            "periods": ranges,
            "series": body,
            "meaning": "stored-measurements-compared-not-asset-health",
        }
    except LookupError as error:
        return HTTPStatus.NOT_FOUND, {"error": "nothing_to_explore", "detail": str(error)}
    except ValueError:
        return HTTPStatus.BAD_REQUEST, {"error": "invalid_explore_query"}
    except AcquisitionSnapshotError:
        return HTTPStatus.CONFLICT, {"error": "original_waveform_unavailable"}
    except OperationsReadError, PhmAnalysisError, OSError, sqlite3.Error:
        return HTTPStatus.SERVICE_UNAVAILABLE, {"error": "explore_store_unavailable"}


def _time_periods(query: dict[str, list[str]]) -> list[tuple[str, datetime, datetime]]:
    return [
        (name, _instant(query, f"{name}_from"), _instant(query, f"{name}_to"))
        for name in ("a", "b")
    ]


def _acquisition_periods(query: dict[str, list[str]]) -> list[tuple[str, int, int]]:
    return [
        (name, int(_one(query, f"{name}_from")), int(_one(query, f"{name}_to")))
        for name in ("a", "b")
    ]


def _relation_or_spectrum(
    workspace: OperationsWorkspace,
    store: SqlitePhmAnalysisStore,
    asset_id: str,
    path: str,
    query: dict[str, list[str]],
) -> dict[str, Any]:
    kind = _one(query, "kind") if path.endswith("relation") else "acquisition"
    body: dict[str, Any] = {"schema_version": 1, "asset_id": asset_id, "kind": kind}
    if kind == "history":
        history = _history(workspace)
        if history is None:
            raise LookupError("no stored measurement history")
        x, y = _one(query, "x"), _one(query, "y")
        groups = history.query_measurement_pairs(
            asset_id, x_channel=x, y_channel=y, periods=_time_periods(query)
        )
        return body | {
            "x": x,
            "y": y,
            "groups": history_relation(groups),
            "pairing": "same-source-point-and-timestamp",
        }
    if kind != "acquisition":
        raise ValueError("unknown exploration kind")
    binding = acquisition_binding(store, asset_id) if store.path.exists() else None
    if binding is None:
        raise LookupError("no stored acquisition features")
    periods = _acquisition_periods(query)
    if path.endswith("spectrum"):
        snapshots = SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path)
        return body | acquisition_spectrum(snapshots, binding, periods)
    x, y = _one(query, "x"), _one(query, "y")
    return body | {
        "x": x,
        "y": y,
        "groups": acquisition_relation(store, binding, x, y, periods),
        "pairing": "same-acquisition",
    }


def explore_sources(
    workspace: OperationsWorkspace, store: SqlitePhmAnalysisStore, asset_id: str
) -> dict[str, Any]:
    """What this asset offers for exploration: stored history, acquisition features, or both."""
    history = None
    reader = _history(workspace)
    if reader is not None:
        summary = next((a for a in reader.list_history_assets() if a.asset_id == asset_id), None)
        if summary is not None:
            history = {
                "channels": list(reader.list_history_channels(asset_id))[:200],
                "start_at": summary.start_at.isoformat(),
                "end_at": summary.end_at.isoformat(),
                "measurement_count": summary.measurement_count,
            }
    binding = acquisition_binding(store, asset_id) if store.path.exists() else None
    acquisition = None
    if binding is not None:
        acquisition = acquisition_source(store, binding)
        # Which model results an acquisition range can open, per binding.
        acquisition["models"] = [
            {"binding_id": item.binding_id, "task": task}
            for item in store.list_bindings()
            if item.asset_id == asset_id
            and item.source_id == binding.source_id
            and (task := package_task(workspace, item.package_id)) not in RETIRED_TASKS
        ]
    return {
        "schema_version": 1,
        "asset_id": asset_id,
        "history": history,
        "acquisition": acquisition,
    }


def package_task(workspace: OperationsWorkspace, package_id: str) -> str | None:
    try:
        manifest = json.loads((workspace.models_path / package_id / "package.json").read_text())
    except OSError, ValueError:
        return None
    output = manifest.get("output") if isinstance(manifest, dict) else None
    task = output.get("task") if isinstance(output, dict) else None
    return task if isinstance(task, str) else None
