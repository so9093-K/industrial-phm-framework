"""Bounded Asset History projections for the first real Operations signal trends.

Reads only the existing DuckLake history facade. In particular the result does not
label an individual observation as asset health, align unlike signals, interpolate
gaps, or claim that a stored event is fresh live telemetry.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

from industrial_phm.application.asset_history import MeasurementSourceQuality
from industrial_phm.application.measurement_history import MultiSignalMeasurementHistoryBucket
from industrial_phm.history import DuckLakeAssetHistory
from industrial_phm.runtime.operations_app_composition import OperationsAppSnapshot
from industrial_phm.runtime.operations_live import (
    OperationsReadError,
    list_operations_history_channels,
    query_operations_latest_measurements,
    query_operations_multi_signal_measurement_aggregation,
)

MAX_CHANNELS = 6
MAX_BUCKETS = 120
MAX_GROUPED_BUCKETS = 1000
MAX_LATEST_POINTS = 100
RANGE_DURATIONS = {
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}


def _time(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.utcoffset() is None:
        raise ValueError("history timestamps must have an offset")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _history(snapshot: OperationsAppSnapshot) -> DuckLakeAssetHistory:
    if snapshot.history_reader is None:
        raise OperationsReadError("Asset History not initialized or unavailable")
    return snapshot.history_reader


def _semantic(raw: str) -> dict[str, str | None]:
    """Only allow stable measurement semantics, not arbitrary provider metadata."""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("invalid history interpretation")
    binding = data.get("binding")
    semantics = data.get("semantics")
    definition = binding.get("definition") if isinstance(binding, dict) else None
    if not isinstance(definition, dict):
        definition = semantics if isinstance(semantics, dict) else {}
    return {
        name: value if isinstance(value := definition.get(name), str) else None
        for name in ("observed_property", "scope", "unit")
    }


def _bucket(item: MultiSignalMeasurementHistoryBucket) -> dict[str, object]:
    # Same digest implies the same exact interpretation within a selected
    # source/point/channel. Never merge unlike units or meanings for charting.
    return {
        "channel_id": item.channel_id,
        "source_id": item.source_id,
        "source_type": item.source_type,
        "measurement_point_id": item.measurement_point_id,
        "interpretation_id": hashlib.sha256(item.interpretation_json.encode("utf-8")).hexdigest(),
        "semantics": _semantic(item.interpretation_json),
        "bucket_start": _time(item.bucket_start),
        "bucket_end": _time(item.bucket_end),
        "first_event_at": _time(item.first_event_at),
        "last_event_at": _time(item.last_event_at),
        "observation_count": item.observation_count,
        "usable_count": item.usable_count,
        "null_count": item.null_count,
        "non_good_count": item.non_good_count,
        "conflict_count": item.conflict_count,
        "minimum": item.minimum,
        "maximum": item.maximum,
        "mean": item.mean,
    }


def project_history_channels(
    snapshot: OperationsAppSnapshot, *, asset_id: str
) -> dict[str, object]:
    """List stored channels for a selected asset, not a live connection roster."""
    channels = list_operations_history_channels(_history(snapshot), asset_id)
    return {
        "schema_version": 1,
        "assessed_at": _time(snapshot.assessed_at),
        "asset_id": asset_id,
        "meaning": "stored-history-channels-not-live-source-status",
        "channels": {
            "items": list(channels[:100]),
            "total": len(channels),
            "truncated": len(channels) > 100,
        },
    }


def project_signal_history(
    snapshot: OperationsAppSnapshot,
    *,
    asset_id: str,
    channel_ids: tuple[str, ...],
    range_preset: str = "1h",
    bucket_count: int = 60,
) -> dict[str, object]:
    """Read one bounded multi-signal time window plus stored per-source last points."""
    if not channel_ids or len(channel_ids) > MAX_CHANNELS or len(set(channel_ids)) != len(
        channel_ids
    ):
        raise ValueError("channel_ids must be 1 to 6 distinct identifiers")
    if range_preset not in RANGE_DURATIONS:
        raise ValueError("unsupported range")
    if isinstance(bucket_count, bool) or not 1 <= bucket_count <= MAX_BUCKETS:
        raise ValueError("bucket_count must be between 1 and 120")
    reader = _history(snapshot)
    end = snapshot.assessed_at
    start = end - RANGE_DURATIONS[range_preset]
    agg = query_operations_multi_signal_measurement_aggregation(
        reader,
        asset_id,
        channel_ids=channel_ids,
        start_at=start,
        end_at=end,
        bucket_count=bucket_count,
    )
    if len(agg.buckets) > MAX_GROUPED_BUCKETS:
        raise OperationsReadError("too many historical groups; narrow the query")

    latest: list[dict[str, object]] = []
    for channel in channel_ids:
        for point in query_operations_latest_measurements(reader, asset_id, channel_id=channel):
            if len(latest) >= MAX_LATEST_POINTS:
                raise OperationsReadError("too many stored last points; narrow the query")
            value = point.measurement
            latest.append(
                {
                    "raw_evidence_id": value.raw_evidence_id,
                    "asset_id": value.asset_id,
                    "channel_id": value.channel_id,
                    "source_id": value.source_id,
                    "source_type": value.source_type.value,
                    "measurement_point_id": value.measurement_point_id,
                    "event_at": _time(value.event_at),
                    "event_time_basis": value.event_time_basis.value,
                    "value": value.value,
                    "usable_for_display": (
                        value.value is not None
                        and not point.conflicting_duplicate
                        and value.source_quality != MeasurementSourceQuality.NON_GOOD
                    ),
                    "source_quality": value.source_quality.value,
                    "conflicting_duplicate": point.conflicting_duplicate,
                    "ingestion_mode": value.ingestion_mode.value,
                }
            )
    return {
        "schema_version": 1,
        "assessed_at": _time(snapshot.assessed_at),
        "meaning": "stored-history-not-live-reading-or-asset-health",
        "asset_id": asset_id,
        "channel_ids": list(channel_ids),
        "range": range_preset,
        "start_at": _time(start),
        "end_at": _time(end),
        "snapshot_id": agg.snapshot_id,
        "bucket_seconds": agg.bucket_seconds,
        "buckets": [_bucket(bucket) for bucket in agg.buckets],
        "latest_stored": latest,
    }
