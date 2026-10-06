"""Bounded, factual Monitor presentation payload for the packaged UI."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from industrial_phm.application.measurement_history import MultiSignalMeasurementHistoryAggregation
from industrial_phm.application.source_registration import RegisteredSource


def chart_payload(
    result: MultiSignalMeasurementHistoryAggregation | None,
    channel_order: Sequence[str] = (),
) -> dict[str, Any] | None:
    if result is None:
        return None
    actual = tuple(dict.fromkeys(bucket.channel_id for bucket in result.buckets))
    channels = tuple(
        dict.fromkeys((*[channel for channel in channel_order if channel in actual], *actual))
    )
    groups: dict[tuple[object, ...], dict[str, Any]] = {}
    palette = ("#82b6ff", "#66d2b0", "#edbd74", "#b6a4f2", "#e68da5", "#78cddd")
    for color_index, channel in enumerate(channels):
        identities: dict[tuple[str, str | None, str], list[Any]] = {}
        for bucket in result.buckets:
            if bucket.channel_id == channel:
                identities.setdefault(
                    (bucket.source_id, bucket.measurement_point_id, bucket.interpretation_json), []
                ).append(bucket)
        for identity_index, (identity, buckets) in enumerate(identities.items()):
            source, point, interpretation = identity
            definition = (json.loads(interpretation).get("semantics") or {}).get("definition") or {}
            prop, unit = definition.get("observed_property"), definition.get("unit")
            known = prop not in {None, "", "unresolved"} and unit not in {None, "", "unknown"}
            # A channel with multiple origins or interpretation snapshots is isolated;
            # it must never join a common unit axis by silently dropping provenance.
            key = (
                (prop, unit, source, point)
                if known and len(identities) == 1
                else ("isolated", channel, source, point, interpretation)
            )
            group = groups.setdefault(
                key,
                {
                    "title": str(prop) if known else channel,
                    "unit": str(unit) if unit not in {None, "", "unknown"} else "unit unknown",
                    "origin": source + (f" / {point}" if point else ""),
                    "interpretation": (json.loads(interpretation).get("semantics") or {}).get(
                        "version"
                    )
                    or "unversioned",
                    "series": [],
                },
            )
            group["series"].append(
                {
                    "channel": channel,
                    "source": source,
                    "point": point,
                    "color": palette[color_index % len(palette)],
                    "dash": "" if identity_index == 0 else "5 3",
                    "buckets": [
                        {
                            "start": bucket.bucket_start.timestamp() * 1000,
                            "end": bucket.bucket_end.timestamp() * 1000,
                            "first": bucket.first_event_at.timestamp() * 1000,
                            "last": bucket.last_event_at.timestamp() * 1000,
                            "mean": bucket.mean,
                            "min": bucket.minimum,
                            "max": bucket.maximum,
                            "usable": bucket.usable_count,
                            "null": bucket.null_count,
                            "non_good": bucket.non_good_count,
                            "conflict": bucket.conflict_count,
                        }
                        for bucket in buckets
                    ],
                }
            )
    return {
        "start": result.start_at.timestamp() * 1000,
        "end": result.end_at.timestamp() * 1000,
        "snapshot_id": result.snapshot_id,
        "groups": list(groups.values()),
    }


def signal_payload(
    rows: Sequence[Mapping[str, object]],
    sources: Sequence[RegisteredSource] = (),
    asset_id: str | None = None,
) -> list[dict[str, object]]:
    """Preserve stored meaning; registration fills only never-observed identities."""
    result = [
        {
            key: row.get(key)
            for key in (
                "channel",
                "observed_property",
                "scope",
                "unit",
                "value",
                "quality",
                "source_quality",
                "time",
                "event_time_state",
                "source",
                "measurement_point",
                "semantic_version",
            )
        }
        for row in rows
    ]
    existing = {(row["source"], row["measurement_point"], row["channel"]) for row in result}
    for source in sources:
        if source.asset_id != asset_id:
            continue
        bindings = {
            binding.channel_id: binding.definition
            for binding in getattr(source.config, "semantic_bindings", ())
        }
        for identity in source.channel_identities:
            if (source.source_id, source.measurement_point_id, identity.channel_id) in existing:
                continue
            definition = bindings.get(identity.channel_id)
            result.append(
                {
                    "channel": identity.channel_id,
                    "observed_property": None
                    if definition is None
                    else definition.observed_property,
                    "scope": None if definition is None else definition.scope,
                    "unit": "unknown" if definition is None else definition.unit or "unknown",
                    "value": None,
                    "quality": "not yet observed",
                    "source_quality": "unknown",
                    "time": None,
                    "event_time_state": "unavailable",
                    "source": source.source_id,
                    "measurement_point": source.measurement_point_id,
                }
            )
    return result


def utc_millis(value: datetime | None) -> float | None:
    return None if value is None else value.timestamp() * 1000


def comparison_channels(
    rows: Sequence[Mapping[str, object]],
    focus: str | None,
    saved: Sequence[str] | None,
) -> tuple[str, ...]:
    allowed = {row.get("channel") for row in rows}
    if saved is not None:
        return tuple(
            dict.fromkeys(channel for channel in saved if channel in allowed and channel != focus)
        )[:5]
    primary = next((row for row in rows if row.get("channel") == focus), {})
    if primary.get("observed_property") in {None, "unresolved"} or primary.get("unit") in {
        None,
        "unknown",
    }:
        return ()
    return tuple(
        dict.fromkeys(
            str(row["channel"])
            for row in rows
            if row.get("channel") != focus
            and all(
                row.get(key) == primary.get(key)
                for key in ("observed_property", "unit", "source", "measurement_point")
            )
        )
    )[:2]
