"""Read-only signal exploration routes: what can be explored, and two-period profiles."""

from __future__ import annotations

import hashlib
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
from industrial_phm.application.exploratory_anomaly import (
    declared_running_total,
    find_departures,
    interval_comparison,
    latest_departure,
    record_changes,
)
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
    interpretation_property,
    interpretation_unit,
    is_current_in_amperes,
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
        "/api/v1/explore/findings",
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
# What a record held: all stored signals, read in the same buckets as the departure screen.
# Show distinct sustained, end-of-record and large changes, with simultaneous comparisons.
_FINDINGS_SHOWN = 3
_findings_cache: dict[tuple[str, str], tuple[datetime, int, float, dict[str, Any]]] = {}
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
        if path == "/api/v1/explore/findings":
            return HTTPStatus.OK, record_findings(workspace, asset_id)
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
    """One selected source/point/meaning record, from at most 1,000 buckets."""
    history = _history(workspace)
    if history is None:
        raise LookupError("no stored measurement history")
    summary = next((a for a in history.list_history_assets() if a.asset_id == asset_id), None)
    if summary is None:
        raise LookupError("no stored measurement history")
    channels = list(history.list_history_channels(asset_id))
    series = [value for value in query.get("series", []) if value] or channels[:1]
    if len(series) != 1:
        raise ValueError("choose one signal and its source record")
    baseline = (query.get("baseline") or ["first-30"])[0]
    records = signal_records(history, asset_id, series)
    selected_key = next(iter(query.get("record_key", [])), None)
    record = next((r for r in records if selected_key is None or r["key"] == selected_key), None)
    if record is None:
        raise LookupError("no matching source/point/meaning record")
    channel = record["channel"]
    found = find_departures({channel: record["points"]}, baseline=baseline)

    def span(value: dict[str, Any]) -> dict[str, Any]:
        return {**value, "from": iso(value["from"]), "to": iso(value["to"])}

    return {
        "schema_version": 1,
        "asset_id": asset_id,
        "available": channels[:200],
        "series": [channel],
        "units": {channel: record["unit"]},
        "record": record_context(record),
        "records": [record_context(r) for r in records],
        "bucket_seconds": record["bucket_seconds"],
        "threshold": found["threshold"],
        "baseline": span(found["baseline"]),
        "channels": [{**row, "baseline": span(row["baseline"])} for row in found["channels"]],
        "score": [[iso(at), value, name] for at, value, name in found["score"]],
        "intervals": [
            {
                **item,
                "start": iso(item["start"]),
                "end": iso(item["end"]),
                "baseline": span(item["baseline"]),
            }
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
        label, unit = resolve_channel_labels(
            tuple(s for s in sources if s.source_id == found["source_id"]), summary.asset_id
        ).get(found["channel"], (None, found["unit"]))
        body["items"].append(
            {
                "asset_id": summary.asset_id,
                **{
                    k: found[k]
                    for k in (
                        "key",
                        "channel",
                        "source_id",
                        "measurement_point_id",
                        "interpretation_id",
                        "record",
                    )
                },
                "kind": found.get("kind", "departure"),
                "label": label,
                "unit": found["unit"] or unit,
                "distance": found["distance"],
                "direction": found["direction"],
                "usual": found.get("usual"),
                "since": found["since"].astimezone(UTC).isoformat(),
                # The record end this check judged; a reused check never borrows a newer time.
                "last_at": iso(
                    (
                        datetime.fromisoformat(found["record"]["to"]) - timedelta(seconds=1)
                    ).astimezone(UTC)
                ),
            }
        )
    return body


def signal_records(
    history: DuckLakeAssetHistory, asset_id: str, channels: list[str]
) -> list[dict[str, Any]]:
    """Each source/point/meaning keeps its own time grid and observation bounds."""
    records = []
    for stream in history.list_history_streams(asset_id):
        selected = [channel for channel in channels if channel in stream.channels]
        for offset in range(0, len(selected), 4):
            aggregation = history.query_multi_signal_measurement_aggregation(
                asset_id,
                channel_ids=selected[offset : offset + 4],
                start_at=stream.start_at,
                end_at=stream.end_at + timedelta(seconds=1),
                bucket_count=_DEPARTURE_BUCKETS,
                source_id=stream.source_id,
                measurement_point_id=stream.measurement_point_id,
            )
            groups: dict[tuple[str, str], list[Any]] = {}
            for bucket in aggregation.buckets:
                groups.setdefault((bucket.channel_id, bucket.interpretation_json), []).append(
                    bucket
                )
            for (channel, meaning), buckets in groups.items():
                first = min(bucket.first_event_at for bucket in buckets)
                last = max(bucket.last_event_at for bucket in buckets) + timedelta(seconds=1)
                width = aggregation.bucket_seconds
                if first != aggregation.start_at or last != aggregation.end_at:
                    narrowed = history.query_multi_signal_measurement_aggregation(
                        asset_id,
                        channel_ids=[channel],
                        start_at=first,
                        end_at=last,
                        bucket_count=_DEPARTURE_BUCKETS,
                        source_id=stream.source_id,
                        measurement_point_id=stream.measurement_point_id,
                        interpretation_json=meaning,
                    )
                    buckets = list(narrowed.buckets)
                    width = narrowed.bucket_seconds
                identity = [channel, stream.source_id, stream.measurement_point_id, meaning]
                records.append(
                    {
                        "key": hashlib.sha256(
                            json.dumps(identity, ensure_ascii=False).encode()
                        ).hexdigest(),
                        "channel": channel,
                        "source_id": stream.source_id,
                        "point_id": stream.measurement_point_id,
                        "interpretation": meaning,
                        "interpretation_id": hashlib.sha256(meaning.encode()).hexdigest(),
                        "unit": interpretation_unit(meaning),
                        "bucket_seconds": width,
                        "record": {"from": iso(first), "to": iso(last)},
                        "points": [
                            (bucket.bucket_start, bucket.bucket_end, float(bucket.mean))
                            for bucket in buckets
                            if bucket.mean is not None
                        ],
                    }
                )
    return records


def record_context(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": record["key"],
        "channel": record["channel"],
        "source_id": record["source_id"],
        "measurement_point_id": record["point_id"],
        "interpretation_id": record["interpretation_id"],
        "observed_property": interpretation_property(record["interpretation"]),
        "record": record["record"],
    }


def record_findings(workspace: OperationsWorkspace, asset_id: str) -> dict[str, Any]:
    """Representative changes from each source/point/meaning record's own first 30%.

    A change that came back still counts. Each record owns its aggregation grid, baseline,
    units and links; adding another source cannot alter the facts already found in it.
    """
    body: dict[str, Any] = {
        "schema_version": 1,
        "asset_id": asset_id,
        "baseline": None,
        "record": None,
        "signals": [],
        "judged": 0,
        "unchecked": 0,
        "intervals": [],
        "interval_count": 0,
        "bucket_seconds": None,
        "meaning": "departures-from-the-first-30-percent-not-fault-diagnosis",
    }
    history = _history(workspace)
    if history is None:
        return body
    summary = next((a for a in history.list_history_assets() if a.asset_id == asset_id), None)
    if summary is None:
        return body
    key = (str(workspace.root), asset_id)
    held = _findings_cache.get(key)
    if held is not None and (held[0], held[1]) == (summary.end_at, summary.measurement_count):
        return held[3]
    channels = list(history.list_history_channels(asset_id))
    checked = channels
    records = signal_records(history, asset_id, checked)
    points = {record["key"]: record["points"] for record in records}
    by_key = {record["key"]: record for record in records}
    registry = workspace.source_registry_path
    sources = JsonSourceRepository(registry).list_sources() if registry.is_file() else ()
    labels = {source.source_id: resolve_channel_labels((source,), asset_id) for source in sources}

    def named(key: str) -> tuple[str, str | None]:
        record = by_key[key]
        label, unit = labels.get(record["source_id"], {}).get(record["channel"], (None, None))
        return label or record["channel"], record["unit"] or unit

    def running_total(channel: str) -> bool:
        label, unit = named(channel)
        record = by_key[channel]
        return declared_running_total(
            name=f"{record['channel']} {label}",
            unit=unit,
            meaning=interpretation_property(record["interpretation"]),
        )

    # A declared running total always leaves its early range; it is stated, not judged.
    cumulative = {channel: values for channel, values in points.items() if running_total(channel)}
    try:
        found = record_changes(
            {channel: values for channel, values in points.items() if channel not in cumulative},
            limit=_FINDINGS_SHOWN,
            streams={
                r["key"]: (r["source_id"], r["point_id"], r["interpretation"]) for r in records
            },
        )
    except LookupError, ValueError:
        found = None
    # Every signal says whether it was judged, and if not why: a signal that could not be judged
    # is never counted as one that showed no change.
    states = {item["key"]: item for item in found["channels"]} if found else {}
    signals = []
    for record in records:
        channel = record["key"]
        label, unit = named(channel)
        state = states.get(channel)
        row: dict[str, Any] = {
            **record_context(record),
            "label": label,
            "unit": unit,
            "state": (
                "cumulative" if channel in cumulative else state["state"] if state else "no-values"
            ),
        }
        if channel in cumulative:
            row["first"] = cumulative[channel][0][2]
            row["last"] = cumulative[channel][-1][2]
        if state and state["state"] in {"constant", "level-change"}:
            # Held one value through the baseline: no spread to judge a distance by, but what
            # the record did afterwards is still a fact worth stating.
            later = [
                value for start, _, value in points[channel] if start >= state["baseline"]["to"]
            ]
            row["held"] = state["median"]
            row["later"] = {"low": min(later), "high": max(later)} if later else None
        signals.append(row)
    body["signals"] = signals
    body["judged"] = sum(row["state"] in {"scored", "level-change", "constant"} for row in signals)
    body["signal_count"] = len(checked)
    body["record_count"] = len(records)
    if found is None:
        return body
    usual = {
        item["key"]: (item["median"], item["spread"])
        for item in found["channels"]
        if item["state"] in {"scored", "level-change"}
    }

    shown = []
    for item in found["intervals"]:
        median, spread = usual[item["channel"]]
        label, unit = named(item["channel"])
        record = by_key[item["channel"]]
        reference = (item["baseline"]["from"], item["baseline"]["to"])
        period = (item["start"], item["end"])
        comparisons = []
        for channel, values in points.items():
            # Compare simultaneous signals from the same source and measurement point.
            other_record = by_key[channel]
            if (other_record["source_id"], other_record["point_id"]) != (
                record["source_id"],
                record["point_id"],
            ):
                continue
            if other_record["channel"] == record["channel"] and channel != item["channel"]:
                continue
            comparison = interval_comparison(values, reference, period)
            if comparison is not None:
                other_label, other_unit = named(channel)
                comparisons.append(
                    {
                        **comparison,
                        "channel": channel,
                        "label": other_label,
                        "unit": other_unit,
                        "current_signal": is_current_in_amperes(other_record["interpretation"]),
                    }
                )
        own = next((row for row in comparisons if row["channel"] == item["channel"]), None)
        changed = sorted(
            [
                row
                for row in comparisons
                if row["channel"] != item["channel"] and row["state"] != "within"
            ],
            key=lambda row: (-row["distance"], row["channel"]),
        )
        similar = sorted(
            [
                row
                for row in comparisons
                if row["channel"] != item["channel"] and row["state"] == "within"
            ],
            key=lambda row: (not row["current_signal"], row["distance"], row["channel"]),
        )
        shown.append(
            {
                "start": iso(item["start"]),
                "end": iso(item["end"]),
                **record_context(record),
                "label": label,
                "unit": unit,
                "direction": item["direction"],
                "value": item["value"],
                "reason": item["reason"],
                "kind": item["kind"],
                "bucket_seconds": record["bucket_seconds"],
                "baseline": {"from": iso(reference[0]), "to": iso(reference[1])},
                "reference_value": own["reference"] if own else None,
                "typical_value": own["current"] if own else None,
                "related": [
                    {
                        **{
                            key: value
                            for key, value in row.items()
                            if key not in {"distance", "current_signal", "channel"}
                        },
                        **record_context(by_key[row["channel"]]),
                    }
                    for row in related(changed, similar)
                ],
                # The usual range is the one the departure was judged by.
                "usual": {
                    "low": median - found["threshold"] * spread,
                    "high": median + found["threshold"] * spread,
                },
                # Other signals whose representative value shifted in this interval.
                "within": [row["label"] for row in changed],
            }
        )
    for item in shown:
        owned = {
            key: item[key]
            for key in (
                "key",
                "start",
                "end",
                "baseline",
                "record",
                "usual",
                "value",
                "reference_value",
                "typical_value",
                "kind",
            )
        }
        item["review_key"] = hashlib.sha256(json.dumps(owned, sort_keys=True).encode()).hexdigest()
    body.update(
        {
            "baseline": {
                "from": iso(found["baseline"]["from"]),
                "to": iso(found["baseline"]["to"]),
            }
            if found["baseline"] is not None
            else None,
            "record": {"from": iso(summary.start_at), "to": iso(summary.end_at)},
            # Each value is a bucket mean over this many seconds, not a single measurement.
            "bucket_seconds": records[0]["bucket_seconds"]
            if records and len({r["bucket_seconds"] for r in records}) == 1
            else None,
            "intervals": shown,
            "interval_count": found["interval_count"],
        }
    )
    if len(_findings_cache) > 4 * MAX_ATTENTION_ASSETS:
        _findings_cache.clear()
    _findings_cache[key] = (summary.end_at, summary.measurement_count, time.monotonic(), body)
    return body


def related(changed: list[dict[str, Any]], similar: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The other signals shown with one change: the two that moved most and one that held.

    A current in amperes says whether the equipment ran, so one is always included: a stop
    first reads as a power factor falling to 0 and needs its current beside it.
    """
    rows = [*changed[:2], *similar[:1]]
    if not any(row["current_signal"] for row in rows):
        current = next((row for row in [*changed, *similar] if row["current_signal"]), None)
        if current is not None:
            rows.append(current)
    return rows


def _ends_departed(history: DuckLakeAssetHistory, summary: Any) -> dict[str, Any] | None:
    """The signal whose record ends farthest outside its own baseline, judged one signal at a
    time exactly as the 기준 구간 이탈 screen judges the signal it shows."""
    farthest: dict[str, Any] | None = None
    for record in signal_records(
        history,
        summary.asset_id,
        list(history.list_history_channels(summary.asset_id))[:_ATTENTION_CHANNELS],
    ):
        channel = record["channel"]
        if declared_running_total(
            name=channel,
            unit=record["unit"],
            meaning=interpretation_property(record["interpretation"]),
        ):
            continue
        try:
            judged = find_departures({channel: record["points"]}, baseline="first-30")
            found = latest_departure(judged)
        except LookupError, ValueError:
            continue
        if found is not None and (
            farthest is None or (found["distance"] or 0) > (farthest["distance"] or 0)
        ):
            scored = next(
                (row for row in judged["channels"] if row["state"] in {"scored", "level-change"}),
                None,
            )
            usual = (
                {
                    "low": scored["median"] - judged["threshold"] * scored["spread"],
                    "high": scored["median"] + judged["threshold"] * scored["spread"],
                }
                if scored
                else None
            )
            farthest = {**found, **record_context(record), "unit": record["unit"], "usual": usual}
    return farthest


def iso(value: datetime) -> str:
    return value.isoformat()
