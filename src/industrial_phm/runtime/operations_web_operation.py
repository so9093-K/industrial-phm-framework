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

from industrial_phm.application.measurement_history import (
    HistoryStream,
    LevelAggregationBucket,
    ProfileLevel,
    ValueOccupancy,
)
from industrial_phm.application.operating_state import (
    OperatingLevels,
    find_levels,
    histogram_edges,
    main_current,
    running_bins,
)
from industrial_phm.application.signal_exploration import display_unit
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


def stream_levels(
    history: DuckLakeAssetHistory,
    asset_id: str,
    current: dict[str, Any],
    start: datetime,
    end: datetime,
) -> OperatingLevels:
    """Operating levels of a source from its chosen current over a range.

    Args:
        history: The asset history.
        asset_id: The asset.
        current: ``channel``, ``source_id``, ``point_id`` and ``interpretation`` of the current.
        start: Start of the range, inclusive.
        end: End of the range, exclusive.

    Returns:
        The stop floor and the running levels.

    Raises:
        LookupError: The current holds no usable value in the range.
    """
    return _levels(_reader(history, asset_id, current, start, end))


def stream_operation(
    history: DuckLakeAssetHistory,
    asset_id: str,
    record: dict[str, Any],
    levels: OperatingLevels,
) -> StreamOperation:
    """How long the source spent in each level over its current's record."""
    start = min(point[0] for point in record["points"])
    end = max(point[1] for point in record["points"]) + timedelta(seconds=1)
    timeline = _reader(history, asset_id, record, start, end)(levels.edges, _TIMELINE_BUCKETS)
    return StreamOperation(
        record["key"], levels, timeline, tuple(bucket.bucket_start for bucket in timeline.buckets)
    )


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
        # Observations taken while stopped, which no change is judged from.
        "excluded": sum(bucket.counts[0] for bucket in occupancy.buckets),
        "timeline": [
            [bucket.bucket_start.isoformat(), list(bucket.counts)] for bucket in occupancy.buckets
        ],
    }


# A level held for less than this part of a usual bucket gives too few values for its mean.
_LEVEL_SHARE_OF_BUCKET = 0.25


@dataclass(frozen=True, slots=True)
class LevelSeries:
    """One record's bucket means while its source ran at one level."""

    key: str
    band: int
    points: list[tuple[datetime, datetime, float]]


def level_series(
    buckets: Sequence[LevelAggregationBucket], keys: dict[tuple[str, str], str]
) -> dict[str, LevelSeries]:
    """Each record split into one series per running level.

    A bucket gives a level its mean only when the level held for a fair part of it; stopped
    values are left out.

    Args:
        buckets: Band buckets of one source and point.
        keys: Record key per ``(channel_id, interpretation_json)``.

    Returns:
        Series keyed ``"<record key>@<band>"``.
    """
    totals: dict[tuple[str, datetime], int] = {}
    grouped: dict[tuple[str, int], list[LevelAggregationBucket]] = {}
    for row in buckets:
        key = keys.get((row.channel_id, row.interpretation_json))
        if key is None:
            continue
        totals[key, row.bucket_start] = totals.get((key, row.bucket_start), 0) + row.usable_count
        grouped.setdefault((key, row.band), []).append(row)
    usual: dict[str, list[int]] = {}
    for (key, _), total in totals.items():
        usual.setdefault(key, []).append(total)
    found: dict[str, LevelSeries] = {}
    for (key, band), rows in grouped.items():
        if band == 0:
            continue
        counts = sorted(usual[key])
        least = max(1.0, _LEVEL_SHARE_OF_BUCKET * counts[len(counts) // 2])
        kept = [(b.bucket_start, b.bucket_end, b.mean) for b in rows if b.usable_count >= least]
        if kept:
            found[f"{key}@{band}"] = LevelSeries(key, band, kept)
    return found


# Levels per source, so the summary and the comparison split by the same levels without reading
# the whole record again. A record that grows changes its extent and so its entry.
_SOURCE_LEVELS: dict[tuple[str, ...], tuple[tuple[str, str], OperatingLevels] | None] = {}


def source_levels(
    history: DuckLakeAssetHistory, asset_id: str, stream: HistoryStream
) -> tuple[tuple[str, str], OperatingLevels] | None:
    """The current a source's operating levels are read from, and the levels.

    Args:
        history: The asset history.
        asset_id: The asset.
        stream: The source and point, with its stored extent.

    Returns:
        ``((channel_id, interpretation_json), levels)``, or None when the source records no
        current in A with a usable value.
    """
    key = (
        str(history.config.catalog_path),
        asset_id,
        stream.source_id,
        stream.measurement_point_id or "",
        stream.start_at.isoformat(),
        stream.end_at.isoformat(),
    )
    if key in _SOURCE_LEVELS:
        return _SOURCE_LEVELS[key]
    start, end = stream.start_at, stream.end_at + timedelta(seconds=1)
    meanings = history.list_stream_meanings(
        asset_id,
        source_id=stream.source_id,
        measurement_point_id=stream.measurement_point_id,
        start_at=start,
        end_at=end,
    )
    labels = {f"{channel}\0{meaning}": (channel, meaning) for channel, meaning in meanings}
    main = main_current([(name, display_unit(*pair), pair[1]) for name, pair in labels.items()])
    found = None
    if main is not None:
        channel, meaning = labels[main]
        current = {
            "channel": channel,
            "source_id": stream.source_id,
            "point_id": stream.measurement_point_id,
            "interpretation": meaning,
        }
        try:
            found = (labels[main], stream_levels(history, asset_id, current, start, end))
        except LookupError:
            found = None
    if len(_SOURCE_LEVELS) > 256:
        _SOURCE_LEVELS.clear()
    _SOURCE_LEVELS[key] = found
    return found


def comparison_operation(
    history: DuckLakeAssetHistory,
    asset_id: str,
    periods: Sequence[tuple[str, datetime, datetime]],
    *,
    source_id: str | None = None,
    point_id: str | None = None,
) -> tuple[dict[str, Any], ProfileLevelSource] | None:
    """How the source ran in each compared period, and what a level filter reads from.

    Args:
        history: The asset history.
        asset_id: The asset.
        periods: The named periods being compared.
        source_id: The source to read, required when several sources record a current.
        point_id: Its measurement point.

    Returns:
        The levels with each period's share per band, and the level signal; None when no single
        source with a current in A can be chosen.
    """
    streams = [
        stream
        for stream in history.list_history_streams(asset_id)
        if source_id is None
        or (stream.source_id, stream.measurement_point_id) == (source_id, point_id)
    ]
    found = [
        (stream, read) for stream in streams if (read := source_levels(history, asset_id, stream))
    ]
    if len(found) != 1:
        return None
    stream, ((channel, meaning), levels) = found[0]
    shares: dict[str, list[float] | None] = {}
    for name, start, end in periods:
        occupancy = history.query_value_occupancy(
            asset_id,
            channel_id=channel,
            source_id=stream.source_id,
            measurement_point_id=stream.measurement_point_id,
            interpretation_json=meaning,
            start_at=start,
            end_at=end,
            edges=levels.edges,
        )
        counts = occupancy.buckets[0].counts if occupancy.buckets else ()
        shares[name] = [count / sum(counts) for count in counts] if sum(counts) else None
    body = {
        "source_id": stream.source_id,
        "point_id": stream.measurement_point_id,
        "label": channel,
        "unit": display_unit(channel, meaning),
        **levels_body(levels),
        "shares": shares,
    }
    return body, ProfileLevelSource(
        stream.source_id, stream.measurement_point_id, channel, meaning, levels
    )


@dataclass(frozen=True, slots=True)
class ProfileLevelSource:
    """The level signal of one source, from which a band's bounds are taken."""

    source_id: str
    point_id: str | None
    channel_id: str
    interpretation_json: str
    levels: OperatingLevels

    def bounds(self, band: int) -> ProfileLevel:
        """The level restriction of one band: stopped is 0, running levels count from 1."""
        edges = self.levels.edges
        if not 0 <= band <= len(edges):
            raise ValueError("unknown operating level")
        return ProfileLevel(
            self.source_id,
            self.point_id,
            self.channel_id,
            self.interpretation_json,
            edges[band - 1] if band > 0 else None,
            edges[band] if band < len(edges) else None,
        )
