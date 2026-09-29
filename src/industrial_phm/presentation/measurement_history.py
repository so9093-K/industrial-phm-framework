"""Raw observation trend presentation; no numerical PHM interpretation."""

from __future__ import annotations

import importlib
import io
import json
from datetime import UTC, datetime

from industrial_phm.application.measurement_history import (
    MeasurementHistoryPage,
    MeasurementHistoryPoint,
    assess_latest_measurement,
)


def measurement_history_rows(page: MeasurementHistoryPage) -> list[dict[str, object]]:
    return [_measurement_history_row(point) for point in page.points]


def latest_measurement_rows(
    points: tuple[MeasurementHistoryPoint, ...],
    *,
    as_of: datetime,
    stale_after_seconds: float,
) -> list[dict[str, object]]:
    """Keep interpretation evidence visible even outside the selected trend range."""
    rows = []
    for point in points:
        row = _measurement_history_row(point)
        status = assess_latest_measurement(
            point, as_of=as_of, stale_after_seconds=stale_after_seconds
        )
        row.update(
            value=None if point.conflicting_duplicate else point.measurement.value,
            status_good=point.measurement.status_good,
            currency=status.currency.value,
            age_seconds=status.age_seconds,
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
    if not m.status_good:
        quality.append("quality unavailable/bad")
    if point.conflicting_duplicate:
        quality.append("conflicting duplicate")
    return {
        "time": m.event_at.isoformat() if m.event_at else None,
        "value": m.value,
        "channel": m.channel_id,
        "property": definition.get("property_name", m.channel_id),
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


def render_measurement_history_svg(page: MeasurementHistoryPage) -> str:
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
            and page.points[i].measurement.status_good
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
        and (p.conflicting_duplicate or not p.measurement.status_good)
    ]
    if suspect:
        axes.scatter(
            [p.measurement.event_at.astimezone(UTC) for p in suspect if p.measurement.event_at],
            [p.measurement.value for p in suspect],
            marker="x",
            color="red",
            label="quality/conflict",
        )
    nulls = [p for p in page.points if p.measurement.value is None]
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
    axes.set_xlabel("Event time (UTC)")
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
