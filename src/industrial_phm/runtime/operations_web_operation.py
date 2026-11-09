"""How each source of an asset ran over its record: stopped, or at which current level.

The levels are found once per source and point from the whole record's current, so every
analysis that splits by them splits the same way.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from industrial_phm.application.measurement_history import ValueOccupancy
from industrial_phm.application.operating_state import (
    OperatingLevels,
    find_levels,
    histogram_edges,
    main_current,
    running_bins,
)
from industrial_phm.history import DuckLakeAssetHistory

_TIMELINE_BUCKETS = 1000
# A time bucket counts as stopped when the equipment was stopped for at least this share of it.
STOPPED_MAJORITY = 0.5


@dataclass(frozen=True, slots=True)
class StreamOperation:
    """Operating levels of one source and point, and how long it spent in each over time."""

    key: str
    levels: OperatingLevels
    occupancy: ValueOccupancy
    starts: tuple[datetime, ...]

    def counts(self, start: datetime, end: datetime) -> list[float]:
        """Observations per band between two times; a partly covered bucket counts in part."""
        buckets = self.occupancy.buckets
        totals = [0.0] * (len(self.levels.edges) + 1)
        index = max(0, bisect_right(self.starts, start) - 1)
        for bucket in buckets[index:]:
            if bucket.bucket_start >= end:
                break
            span = (bucket.bucket_end - bucket.bucket_start).total_seconds()
            covered = (
                min(end, bucket.bucket_end) - max(start, bucket.bucket_start)
            ).total_seconds()
            if span <= 0 or covered <= 0:
                continue
            for band, count in enumerate(bucket.counts):
                totals[band] += count * covered / span
        return totals

    def shares(self, start: datetime, end: datetime) -> list[float] | None:
        """Share of the observations in each band between two times, stopped first."""
        totals = self.counts(start, end)
        whole = sum(totals)
        return [count / whole for count in totals] if whole else None

    def stopped(self, start: datetime, end: datetime) -> bool:
        """Whether the equipment was stopped for most of a period."""
        shares = self.shares(start, end)
        return shares is not None and shares[0] >= STOPPED_MAJORITY


def stream_operations(
    history: DuckLakeAssetHistory, asset_id: str, records: Sequence[dict[str, Any]]
) -> dict[tuple[str, str | None], StreamOperation]:
    """Operating levels per source and point that records a current in A.

    Args:
        history: The asset history.
        asset_id: The asset.
        records: Signal records with ``key``, ``channel``, ``source_id``, ``point_id``,
            ``unit``, ``interpretation`` and ``points``.

    Returns:
        The operation of each source and point whose current could be read.
    """
    found: dict[tuple[str, str | None], StreamOperation] = {}
    for stream in {(record["source_id"], record["point_id"]) for record in records}:
        members = [r for r in records if (r["source_id"], r["point_id"]) == stream]
        key = main_current([(r["key"], r["unit"], r["interpretation"]) for r in members])
        record = next((r for r in members if r["key"] == key), None)
        if record is None or not record["points"]:
            continue
        try:
            found[stream] = _operation(history, asset_id, record)
        except LookupError, ValueError, RuntimeError:
            continue
    return found


def _operation(
    history: DuckLakeAssetHistory, asset_id: str, record: dict[str, Any]
) -> StreamOperation:
    start = min(point[0] for point in record["points"])
    end = max(point[1] for point in record["points"]) + timedelta(seconds=1)
    read = _reader(history, asset_id, record, start, end)
    levels = _levels(read)
    timeline = read(levels.edges, _TIMELINE_BUCKETS)
    return StreamOperation(
        record["key"], levels, timeline, tuple(bucket.bucket_start for bucket in timeline.buckets)
    )


def current_levels(
    history: DuckLakeAssetHistory,
    asset_id: str,
    *,
    source_id: str,
    point_id: str | None,
    channel_id: str,
) -> OperatingLevels | None:
    """Operating levels of one source and point, found from one current's whole record.

    The same record and rule as the summary give the same levels, so an analysis split by them
    names the levels the summary shows.

    Args:
        history: The asset history.
        asset_id: The asset.
        source_id: The source.
        point_id: The measurement point, or None.
        channel_id: The current to read the levels from.

    Returns:
        The levels, or None when the current holds no usable value.
    """
    stream = next(
        (
            item
            for item in history.list_history_streams(asset_id)
            if (item.source_id, item.measurement_point_id) == (source_id, point_id)
        ),
        None,
    )
    if stream is None or channel_id not in stream.channels:
        return None
    start, end = stream.start_at, stream.end_at + timedelta(seconds=1)
    whole = history.query_multi_signal_measurement_aggregation(
        asset_id,
        channel_ids=[channel_id],
        start_at=start,
        end_at=end,
        bucket_count=1,
        source_id=source_id,
        measurement_point_id=point_id,
    )
    if not whole.buckets:
        return None
    meaning = max(whole.buckets, key=lambda bucket: bucket.usable_count).interpretation_json
    record = {"channel": channel_id, "source_id": source_id, "point_id": point_id}
    try:
        return _levels(_reader(history, asset_id, record | {"interpretation": meaning}, start, end))
    except LookupError:
        return None


def _reader(
    history: DuckLakeAssetHistory,
    asset_id: str,
    record: dict[str, Any],
    start: datetime,
    end: datetime,
) -> Callable[..., ValueOccupancy]:
    def occupancy(edges: Sequence[float], buckets: int = 1) -> ValueOccupancy:
        return history.query_value_occupancy(
            asset_id,
            channel_id=record["channel"],
            source_id=record["source_id"],
            measurement_point_id=record["point_id"],
            interpretation_json=record["interpretation"],
            start_at=start,
            end_at=end,
            edges=edges,
            bucket_count=buckets,
        )

    return occupancy


def _levels(read: Callable[..., ValueOccupancy]) -> OperatingLevels:
    whole = read(histogram_edges(0.0, 0.0, 0))
    if not whole.buckets or whole.minimum is None or whole.maximum is None:
        raise LookupError("no usable current")
    low, width, bins = running_bins(whole.minimum, whole.maximum, whole.buckets[0].counts[1])
    histogram = read(histogram_edges(low, width, bins)) if bins else whole
    return find_levels(low, width, histogram.buckets[0].counts[1:])


def levels_body(levels: OperatingLevels) -> dict[str, Any]:
    """The stop floor and each running level, as the screens name them."""
    edges = levels.edges
    return {
        "stopped_below": edges[0],
        "levels": [
            {
                "low": edges[index],
                "high": edges[index + 1] if index + 1 < len(edges) else None,
                "typical": typical,
            }
            for index, typical in enumerate(levels.typical)
        ],
    }


def operation_body(
    operation: StreamOperation, baseline: tuple[datetime, datetime] | None
) -> dict[str, Any]:
    """What the summary shows of one source's operation.

    Args:
        operation: The source's operation.
        baseline: The period the changes were judged against, if one is shared.

    Returns:
        Levels, shares over the record, before and after the baseline, and a timeline.
    """
    occupancy = operation.occupancy
    record = (occupancy.start_at, occupancy.end_at)
    return {
        "key": operation.key,
        **levels_body(operation.levels),
        "baseline": {"from": baseline[0].isoformat(), "to": baseline[1].isoformat()}
        if baseline
        else None,
        "shares": {
            "record": operation.shares(*record),
            "baseline": operation.shares(*baseline) if baseline else None,
            "after": operation.shares(baseline[1], record[1]) if baseline else None,
        },
        "bucket_seconds": occupancy.bucket_seconds,
        "timeline": [
            [bucket.bucket_start.isoformat(), list(bucket.counts)] for bucket in occupancy.buckets
        ],
    }
