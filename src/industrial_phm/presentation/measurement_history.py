"""Raw observation trend presentation; no numerical PHM interpretation."""

from __future__ import annotations

import importlib
import io
import json
from dataclasses import asdict
from datetime import UTC, datetime

from industrial_phm.application.asset_history import (
    HistoryIngestionMode,
    MeasurementSourceQuality,
)
from industrial_phm.application.measurement_history import (
    MeasurementHistoryAggregation,
    MeasurementHistoryBucket,
    MeasurementHistoryPage,
    MeasurementHistoryPoint,
    MultiSignalMeasurementHistoryAggregation,
    MultiSignalMeasurementHistoryBucket,
    assess_latest_measurement,
)


def measurement_history_rows(page: MeasurementHistoryPage) -> list[dict[str, object]]:
    return [_measurement_history_row(point) for point in page.points]


def _utc_iso(value: datetime | None) -> str | None:
    # Storage may return event time in the reader's local zone. Displayed event
    # times share the chart's UTC axis; source-local raw time stays in provenance.
    return value.astimezone(UTC).isoformat() if value is not None else None


def latest_measurement_rows(
    points: tuple[MeasurementHistoryPoint, ...],
    *,
    as_of: datetime,
) -> list[dict[str, object]]:
    """Keep interpretation evidence visible even outside the selected trend range."""
    rows = []
    for point in points:
        row = _measurement_history_row(point)
        status = assess_latest_measurement(point, as_of=as_of)
        row.update(
            value=None if point.conflicting_duplicate else point.measurement.value,
            event_time_state=status.event_time_state.value,
            history_age_seconds=status.age_seconds,
            expected_live_freshness=(
                "assessed in Sources"
                if point.measurement.ingestion_mode == HistoryIngestionMode.LIVE
                else "not-applicable"
            ),
        )
        rows.append(row)
    return rows


def _measurement_history_row(point: MeasurementHistoryPoint) -> dict[str, object]:
    m = point.measurement
    metadata = json.loads(point.source_metadata_json) if point.source_metadata_json else {}
    binding = metadata.get("binding", {})
    semantics = metadata.get("semantics", {})
    definition = semantics.get("definition", {})
    quality = []
    if m.value is None:
        quality.append("null")
    if m.source_quality == MeasurementSourceQuality.NON_GOOD:
        quality.append("source status non-good")
    if point.conflicting_duplicate:
        quality.append("conflicting duplicate")
    return {
        "time": _utc_iso(m.event_at),
        "value": m.value,
        "channel": m.channel_id,
        "observed_property": definition.get("observed_property") or "unresolved",
        "scope": definition.get("scope"),
        "legacy_property_label": definition.get("property_name"),
        "source_quality": m.source_quality.value,
        "value_availability": "null" if m.value is None else "present",
        "unit": definition.get("unit") or "unknown",
        "unit_evidence": definition.get("unit_evidence"),
        "semantic_version": semantics.get("version"),
        "interpretation_evidence": semantics.get("interpretation_evidence"),
        "event_time_basis": m.event_time_basis.value,
        "quality": ", ".join(quality) or "no recorded issue",
        "conflict": point.conflicting_duplicate,
        "source": m.source_id,
        "source_type": m.source_type.value,
        "measurement_point": m.measurement_point_id,
        "ingestion": m.ingestion_mode.value,
        "raw_evidence_id": m.raw_evidence_id,
        "source_file": point.source_file,
        "source_sha256": point.source_sha256,
        "archive": metadata.get("archive_name"),
        "member": metadata.get("member"),
        "record_index": metadata.get("record_index"),
        "raw_timestamp": metadata.get("raw_timestamp"),
        "source_timezone": binding.get("timezone"),
        "timezone_evidence": binding.get("timezone_evidence"),
        "identity_evidence": binding.get("identity_evidence"),
        "binding_version": binding.get("version"),
    }


def measurement_history_range_summary(
    page: MeasurementHistoryPage, *, start_at: datetime, end_at: datetime
) -> dict[str, object]:
    """Describe returned raw points, never claim they represent the full interval."""
    times = [p.measurement.event_at for p in page.points if p.measurement.event_at is not None]
    return {
        "requested_start_inclusive": _utc_iso(start_at),
        "requested_end_exclusive": _utc_iso(end_at),
        "returned_start": _utc_iso(min(times, default=None)),
        "returned_end": _utc_iso(max(times, default=None)),
        "returned_points": len(page.points),
        "point_budget": page.point_budget,
        "truncated": page.truncated,
        "representation": "raw points; no downsampling or interpolation",
    }


def render_measurement_history_svg(
    page: MeasurementHistoryPage,
    *,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
) -> str:
    """Show separate source/point series as points, never interpolate across gaps."""
    figure_module = importlib.import_module("matplotlib.figure")
    figure = figure_module.Figure(figsize=(11, 3.6), layout="constrained")
    axes = figure.subplots()
    groups: dict[tuple[str, str | None], list[int]] = {}
    for index, point in enumerate(page.points):
        m = point.measurement
        groups.setdefault((m.source_id, m.measurement_point_id), []).append(index)
    for (source, measurement_point), indices in groups.items():
        good = [
            page.points[i]
            for i in indices
            if page.points[i].measurement.value is not None
            and page.points[i].measurement.event_at is not None
            and page.points[i].measurement.source_quality != MeasurementSourceQuality.NON_GOOD
            and not page.points[i].conflicting_duplicate
        ]
        axes.scatter(
            [p.measurement.event_at.astimezone(UTC) for p in good if p.measurement.event_at],
            [p.measurement.value for p in good],
            s=12,
            label=source + (f" / {measurement_point}" if measurement_point else ""),
        )
    suspect = [
        p
        for p in page.points
        if p.measurement.value is not None
        and p.measurement.event_at is not None
        and (
            p.conflicting_duplicate
            or p.measurement.source_quality == MeasurementSourceQuality.NON_GOOD
        )
    ]
    if suspect:
        axes.scatter(
            [p.measurement.event_at.astimezone(UTC) for p in suspect if p.measurement.event_at],
            [p.measurement.value for p in suspect],
            marker="x",
            color="red",
            label="quality/conflict",
        )
    nulls = [
        p for p in page.points if p.measurement.value is None and p.measurement.event_at is not None
    ]
    if nulls:
        axes.plot(
            [p.measurement.event_at.astimezone(UTC) for p in nulls if p.measurement.event_at],
            [0.03] * len(nulls),
            transform=axes.get_xaxis_transform(),
            linestyle="none",
            marker="|",
            color="red",
            label="null (time marker, not zero)",
        )
    if start_at is not None and end_at is not None:
        axes.set_xlim(start_at.astimezone(UTC), end_at.astimezone(UTC))
    axes.set_xlabel("Requested event-time range (UTC)")
    # No common unit is invented when raw/source metadata has none.
    units = {row["unit"] for row in measurement_history_rows(page)}
    axes.set_ylabel(f"Value ({next(iter(units)) if len(units) == 1 else 'mixed/unknown units'})")
    axes.grid(alpha=0.2)
    if page.points:
        axes.legend(fontsize="small")
    figure.autofmt_xdate()
    output = io.StringIO()
    figure.savefig(output, format="svg")
    return output.getvalue()


def measurement_aggregation_summary(result: MeasurementHistoryAggregation) -> dict[str, object]:
    return {
        "requested_start_inclusive": _utc_iso(result.start_at),
        "requested_end_exclusive": _utc_iso(result.end_at),
        "returned_start": _utc_iso(min((b.first_event_at for b in result.buckets), default=None)),
        "returned_end": _utc_iso(max((b.last_event_at for b in result.buckets), default=None)),
        "bucket_seconds": result.bucket_seconds,
        "returned_buckets": len(result.buckets),
        "observation_count": sum(b.observation_count for b in result.buckets),
        "usable_count": sum(b.usable_count for b in result.buckets),
        "snapshot_id": result.snapshot_id,
    }


def measurement_aggregation_rows(
    result: MeasurementHistoryAggregation,
) -> list[dict[str, object]]:
    rows = []
    for bucket in result.buckets:
        metadata = json.loads(bucket.interpretation_json)
        semantics = metadata.get("semantics") or {}
        definition = semantics.get("definition") or {}
        row: dict[str, object] = asdict(bucket)
        for key in ("bucket_start", "bucket_end", "first_event_at", "last_event_at"):
            row[key] = _utc_iso(getattr(bucket, key))
        row["unit"] = definition.get("unit") or "unknown"
        row["observed_property"] = definition.get("observed_property") or "unresolved"
        row["source_quality"] = "unknown" if bucket.source_type == "file" else "see non_good_count"
        row["snapshot_id"] = result.snapshot_id
        rows.append(row)
    return rows


def render_multi_signal_measurement_aggregation_svg(
    result: MultiSignalMeasurementHistoryAggregation,
    *,
    selected_channel: str | None = None,
) -> str:
    """Render channel-separated small multiples on one event-time axis."""

    if not isinstance(result, MultiSignalMeasurementHistoryAggregation):
        raise ValueError("result must be a MultiSignalMeasurementHistoryAggregation")
    channels = tuple(dict.fromkeys(bucket.channel_id for bucket in result.buckets))
    if selected_channel in channels:
        channels = (selected_channel, *(channel for channel in channels if channel != selected_channel))
    figure_module = importlib.import_module("matplotlib.figure")
    row_count = max(1, len(channels))
    figure = figure_module.Figure(
        figsize=(11, max(3.2, 2.15 * row_count)),
        layout="constrained",
    )
    axes_grid = figure.subplots(nrows=row_count, ncols=1, sharex=True, squeeze=False)
    axes = [axes_grid[index][0] for index in range(row_count)]

    if not channels:
        axis = axes[0]
        axis.set_xlim(result.start_at.astimezone(UTC), result.end_at.astimezone(UTC))
        axis.set_title("No observations in requested event-time window", loc="left")
        axis.set_xlabel("Event time (UTC)")
    else:
        for axis, channel in zip(axes, channels, strict=True):
            channel_buckets = tuple(bucket for bucket in result.buckets if bucket.channel_id == channel)
            _render_multi_signal_channel_axis(axis, channel, channel_buckets)
            axis.set_xlim(result.start_at.astimezone(UTC), result.end_at.astimezone(UTC))
            axis.grid(alpha=0.16)
        axes[-1].set_xlabel("Event time (UTC)")
        for axis in axes[:-1]:
            axis.tick_params(labelbottom=False)
        figure.autofmt_xdate()

    output = io.StringIO()
    figure.savefig(output, format="svg")
    return output.getvalue()


def _render_multi_signal_channel_axis(
    axis: object,
    channel: str,
    buckets: tuple[MultiSignalMeasurementHistoryBucket, ...],
) -> None:
    groups: dict[
        tuple[str, str | None, str],
        list[MultiSignalMeasurementHistoryBucket],
    ] = {}
    for bucket in buckets:
        groups.setdefault(
            (bucket.source_id, bucket.measurement_point_id, bucket.interpretation_json),
            [],
        ).append(bucket)

    for index, ((source, point, _), grouped) in enumerate(groups.items()):
        usable = [bucket for bucket in grouped if bucket.usable_count and bucket.mean is not None]
        times = [
            bucket.bucket_start + (bucket.bucket_end - bucket.bucket_start) / 2
            for bucket in usable
        ]
        color = f"C{index % 10}"
        axis.vlines(
            times,
            [bucket.minimum for bucket in usable],
            [bucket.maximum for bucket in usable],
            color=color,
            alpha=0.35,
        )
        axis.scatter(
            times,
            [bucket.mean for bucket in usable],
            s=13,
            color=color,
            label=source + (f" / {point}" if point else ""),
        )

    suspect = [
        bucket
        for bucket in buckets
        if bucket.null_count or bucket.non_good_count or bucket.conflict_count
    ]
    if suspect:
        axis.plot(
            [
                bucket.bucket_start + (bucket.bucket_end - bucket.bucket_start) / 2
                for bucket in suspect
            ],
            [0.04] * len(suspect),
            transform=axis.get_xaxis_transform(),
            linestyle="none",
            marker="|",
            color="red",
            label="quality/conflict excluded",
        )

    title, unit = _multi_signal_channel_label(channel, buckets)
    axis.set_title(title, loc="left", fontsize="medium", fontweight="semibold")
    axis.set_ylabel(unit)
    if groups:
        axis.legend(fontsize="x-small", loc="upper left")


def _multi_signal_channel_label(
    channel: str,
    buckets: tuple[MultiSignalMeasurementHistoryBucket, ...],
) -> tuple[str, str]:
    definitions = []
    for bucket in buckets:
        metadata = json.loads(bucket.interpretation_json)
        semantics = metadata.get("semantics") or {}
        definition = semantics.get("definition") or {}
        definitions.append(
            (
                definition.get("observed_property"),
                definition.get("scope"),
                definition.get("unit"),
            )
        )
    confirmed = {definition for definition in definitions if definition[0]}
    if len(confirmed) != 1:
        return channel, "mixed / unknown"
    observed_property, scope, unit = next(iter(confirmed))
    label = str(observed_property)
    if scope:
        label += f" · {scope}"
    return f"{label}  ·  {channel}", str(unit or "unknown")


def render_measurement_aggregation_svg(result: MeasurementHistoryAggregation) -> str:
    figure_module = importlib.import_module("matplotlib.figure")
    figure = figure_module.Figure(figsize=(11, 3.6), layout="constrained")
    axes = figure.subplots()
    groups: dict[tuple[str, str | None, str], list[MeasurementHistoryBucket]] = {}
    for bucket in result.buckets:
        groups.setdefault(
            (bucket.source_id, bucket.measurement_point_id, bucket.interpretation_json), []
        ).append(bucket)
    for index, ((source, point, _), buckets) in enumerate(groups.items()):
        usable = [b for b in buckets if b.usable_count]
        times = [b.bucket_start + (b.bucket_end - b.bucket_start) / 2 for b in usable]
        color = f"C{index % 10}"
        axes.vlines(
            times, [b.minimum for b in usable], [b.maximum for b in usable], color=color, alpha=0.5
        )
        axes.scatter(
            times,
            [b.mean for b in usable],
            s=12,
            color=color,
            label=f"{source} / {point or '-'} / interpretation {index + 1}",
        )
    suspect = [b for b in result.buckets if b.null_count or b.non_good_count or b.conflict_count]
    if suspect:
        axes.plot(
            [b.bucket_start + (b.bucket_end - b.bucket_start) / 2 for b in suspect],
            [0.03] * len(suspect),
            transform=axes.get_xaxis_transform(),
            linestyle="none",
            marker="|",
            color="red",
            label="excluded quality/conflict records",
        )
    axes.set_xlim(result.start_at.astimezone(UTC), result.end_at.astimezone(UTC))
    axes.set_xlabel("Requested event-time range (UTC)")
    axes.set_ylabel("UI min/max/mean (raw units; see table)")
    if groups:
        axes.legend(fontsize="small")
    axes.grid(alpha=0.2)
    figure.autofmt_xdate()
    output = io.StringIO()
    figure.savefig(output, format="svg")
    return output.getvalue()
