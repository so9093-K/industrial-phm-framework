"""Read-only signal exploration routes: what can be explored, and two-period profiles."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs

from industrial_phm.application.acquisition_snapshot import (
    AcquisitionSnapshotError,
    SqliteAcquisitionSnapshotRepository,
)
from industrial_phm.application.asset_display import resolve_channel_labels
from industrial_phm.application.exploratory_anomaly import find_departures, latest_departure
from industrial_phm.application.phm_analysis import PhmAnalysisError, SqlitePhmAnalysisStore
from industrial_phm.application.phm_signal_comparison import feature_unit, stream_amplitude_unit
from industrial_phm.application.signal_exploration import (
    MAX_SERIES,
    acquisition_binding,
    acquisition_relation,
    acquisition_series,
    acquisition_source,
    acquisition_spectrum,
    history_relation,
    history_series,
    interpretation_unit,
    strongest_identity,
)
from industrial_phm.application.source_registry import JsonSourceRepository
from industrial_phm.history import DuckLakeAssetHistory
from industrial_phm.history.ducklake import DuckLakeAssetHistoryConfig
from industrial_phm.models.package import SUPPORTED_TASKS
from industrial_phm.runtime.operations_live import OperationsReadError
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

EXPLORE_READ_ROUTES = frozenset(
    {
        "/api/v1/explore/sources",
        "/api/v1/explore/profile",
        "/api/v1/explore/relation",
        "/api/v1/explore/spectrum",
        "/api/v1/explore/anomaly",
        "/api/v1/explore/attention",
    }
)
# The buckets a stored record is read in for baseline departures. 관측 현황's check and the
# 기준 구간 이탈 screen use the same, so both name the same distance and the same start.
_DEPARTURE_BUCKETS = 1000
# Assets checked for a record that ends away from its baseline. A result is reused while the
# asset's record is unchanged, and for a short while when it keeps growing (a live source),
# so screens that ask often do not recompute it on every read.
MAX_ATTENTION_ASSETS = 50
_ATTENTION_CHANNELS = 6
_ATTENTION_REUSE_SECONDS = 30.0
# (root, asset) → (record end, record count, computed at, result)
# (record end judged, measurement count, monotonic time, result) per workspace and asset.
_attention_cache: dict[tuple[str, str], tuple[datetime, int, float, dict[str, Any] | None]] = {}
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
        if path == "/api/v1/explore/attention":
            only = _one(query, "asset_id") if "asset_id" in query else None
            return HTTPStatus.OK, departure_attention(workspace, only)
        asset_id = _one(query, "asset_id")
        store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
        if path == "/api/v1/explore/sources":
            return HTTPStatus.OK, explore_sources(workspace, store, asset_id)
        if path in {"/api/v1/explore/relation", "/api/v1/explore/spectrum"}:
            return HTTPStatus.OK, _relation_or_spectrum(workspace, store, asset_id, path, query)
        if path == "/api/v1/explore/anomaly":
            return HTTPStatus.OK, _departures(workspace, asset_id, query)
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
    amplitude_unit = stream_amplitude_unit(
        SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
        binding.source_id,
        binding.asset_id,
    )
    return body | {
        "x": x,
        "y": y,
        "x_unit": feature_unit(x, amplitude_unit),
        "y_unit": feature_unit(y, amplitude_unit),
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
                # Each source and measurement point with what it actually holds, so a model is
                # built from one stream's own signals and period.
                "streams": [
                    {
                        "source_id": stream.source_id,
                        "measurement_point_id": stream.measurement_point_id,
                        "channels": list(stream.channels),
                        "start_at": stream.start_at.isoformat(),
                        "end_at": stream.end_at.isoformat(),
                    }
                    for stream in reader.list_history_streams(asset_id)[:20]
                ],
                "start_at": summary.start_at.isoformat(),
                "end_at": summary.end_at.isoformat(),
                "measurement_count": summary.measurement_count,
            }
    binding = acquisition_binding(store, asset_id) if store.path.exists() else None
    acquisition = None
    if binding is not None:
        acquisition = acquisition_source(store, binding)
        acquisition["period_seconds"] = acquisition_period(workspace, asset_id, binding.source_id)
        # Which model results an acquisition range can open, per binding.
        acquisition["models"] = [
            {"binding_id": item.binding_id, "task": task}
            for item in store.list_bindings()
            if item.asset_id == asset_id
            and item.source_id == binding.source_id
            and (task := package_task(workspace, item.package_id)) in SUPPORTED_TASKS
        ]
    return {
        "schema_version": 1,
        "asset_id": asset_id,
        "history": history,
        "acquisition": acquisition,
    }


def acquisition_period(
    workspace: OperationsWorkspace, asset_id: str, source_id: str
) -> float | None:
    """The recorded acquisition interval, if declared by the stored stream."""
    if not workspace.acquisition_snapshot_path.is_file():
        return None
    for stream in SqliteAcquisitionSnapshotRepository(
        workspace.acquisition_snapshot_path
    ).list_streams():
        if stream.asset_id == asset_id and stream.source_id == source_id:
            return stream.acquisition_period_seconds
    return None


def package_task(workspace: OperationsWorkspace, package_id: str) -> str | None:
    try:
        manifest = json.loads((workspace.models_path / package_id / "package.json").read_text())
    except OSError, ValueError:
        return None
    output = manifest.get("output") if isinstance(manifest, dict) else None
    task = output.get("task") if isinstance(output, dict) else None
    return task if isinstance(task, str) else None


def _departures(
    workspace: OperationsWorkspace, asset_id: str, query: dict[str, list[str]]
) -> dict[str, Any]:
    """Where up to six stored signals leave their baseline range, from at most 1,000 buckets."""
    history = _history(workspace)
    if history is None:
        raise LookupError("no stored measurement history")
    summary = next((a for a in history.list_history_assets() if a.asset_id == asset_id), None)
    if summary is None:
        raise LookupError("no stored measurement history")
    channels = list(history.list_history_channels(asset_id))
    series = [value for value in query.get("series", []) if value] or channels[:3]
    if not 1 <= len(series) <= MAX_SERIES or len(set(series)) != len(series):
        raise ValueError(f"choose 1 to {MAX_SERIES} distinct series")
    baseline = (query.get("baseline") or ["first-30"])[0]
    points: dict[str, list[tuple[datetime, datetime, float]]] = {}
    units: dict[str, str | None] = {}
    width = 0.0
    for channel in series:
        aggregation = history.query_measurement_aggregation(
            asset_id,
            channel_id=channel,
            start_at=summary.start_at,
            end_at=summary.end_at + timedelta(seconds=1),
            bucket_count=_DEPARTURE_BUCKETS,
        )
        width = aggregation.bucket_seconds
        key, buckets = strongest_identity(aggregation.buckets)
        units[channel] = interpretation_unit(key[2])
        points[channel] = [
            (b.bucket_start, b.bucket_end, float(b.mean)) for b in buckets if b.mean is not None
        ]
    found = find_departures(points, baseline=baseline)
    return {
        "schema_version": 1,
        "asset_id": asset_id,
        "available": channels[:200],
        "series": series,
        "units": units,
        "bucket_seconds": width,
        "threshold": found["threshold"],
        "baseline": {
            "name": found["baseline"]["name"],
            "from": iso(found["baseline"]["from"]),
            "to": iso(found["baseline"]["to"]),
        },
        "channels": found["channels"],
        "score": [[iso(start), value, name] for start, value, name in found["score"]],
        "intervals": [
            {**item, "start": iso(item["start"]), "end": iso(item["end"])}
            for item in found["intervals"][:50]
        ],
        "interval_count": len(found["intervals"]),
        "meaning": "departures-from-a-chosen-baseline-not-fault-diagnosis",
    }


def departure_attention(
    workspace: OperationsWorkspace, asset_id: str | None = None
) -> dict[str, Any]:
    """Assets whose stored signals end far from the first 30% of their own record.

    A light check for assets no model watches: the same median ± MAD comparison as the
    baseline departure screen, kept while the record is unchanged. ``asset_id`` checks one
    asset, for a screen that only needs that asset's flagged signal.
    """
    body: dict[str, Any] = {
        "schema_version": 1,
        "baseline": "first-30",
        "items": [],
        "truncated": False,
        "meaning": "stored-signal-ends-outside-own-baseline-not-a-fault-verdict",
    }
    history = _history(workspace)
    if history is None:
        return body
    assets = [item for item in history.list_history_assets() if asset_id in {None, item.asset_id}]
    body["truncated"] = len(assets) > MAX_ATTENTION_ASSETS
    registry = workspace.source_registry_path
    sources = JsonSourceRepository(registry).list_sources() if registry.is_file() else ()
    if len(_attention_cache) > 4 * MAX_ATTENTION_ASSETS:
        _attention_cache.clear()
    for summary in assets[:MAX_ATTENTION_ASSETS]:
        key = (str(workspace.root), summary.asset_id)
        end, count, now = summary.end_at, summary.measurement_count, time.monotonic()
        held = _attention_cache.get(key)
        if held is None or (
            (held[0], held[1]) != (end, count) and now - held[2] >= _ATTENTION_REUSE_SECONDS
        ):
            held = (end, count, now, _ends_departed(history, summary))
            _attention_cache[key] = held
        found = held[3]
        if found is None:
            continue
        label, unit = resolve_channel_labels(sources, summary.asset_id).get(
            found["channel"], (None, found["unit"])
        )
        body["items"].append(
            {
                "asset_id": summary.asset_id,
                "channel": found["channel"],
                "label": label,
                "unit": unit or found["unit"],
                "distance": found["distance"],
                "direction": found["direction"],
                "since": found["since"].astimezone(UTC).isoformat(),
                # The record end this check judged; a reused check never borrows a newer time.
                "last_at": held[0].astimezone(UTC).isoformat(),
            }
        )
    return body


def _ends_departed(history: DuckLakeAssetHistory, summary: Any) -> dict[str, Any] | None:
    """The signal whose record ends farthest outside its own baseline, judged one signal at a
    time exactly as the 기준 구간 이탈 screen judges the signal it shows."""
    farthest: dict[str, Any] | None = None
    for channel in history.list_history_channels(summary.asset_id)[:_ATTENTION_CHANNELS]:
        aggregation = history.query_measurement_aggregation(
            summary.asset_id,
            channel_id=channel,
            start_at=summary.start_at,
            end_at=summary.end_at + timedelta(seconds=1),
            bucket_count=_DEPARTURE_BUCKETS,
        )
        if not aggregation.buckets:
            continue
        key, buckets = strongest_identity(aggregation.buckets)
        points = [
            (b.bucket_start, b.bucket_end, float(b.mean)) for b in buckets if b.mean is not None
        ]
        try:
            found = latest_departure(find_departures({channel: points}, baseline="first-30"))
        except LookupError, ValueError:
            continue
        if found is not None and (farthest is None or found["distance"] > farthest["distance"]):
            farthest = {**found, "unit": interpretation_unit(key[2])}
    return farthest


def iso(value: datetime) -> str:
    return value.isoformat()
