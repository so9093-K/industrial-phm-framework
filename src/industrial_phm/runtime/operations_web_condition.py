"""Bounded operating-condition analysis of one asset/source/point at one history snapshot."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from industrial_phm.application.electrical_condition import (
    analyze_electrical_condition,
    electrical_samples,
)
from industrial_phm.application.phase_unbalance import UnbalanceQuantity, resolve_phase_channels
from industrial_phm.runtime.operations_app_composition import OperationsAppSnapshot
from industrial_phm.runtime.operations_live import query_operations_latest_asset_measurements


class ConditionSelectionError(ValueError):
    """Invalid user-selected source or comparison period."""


_PERIODS = {"1h": timedelta(hours=1), "6h": timedelta(hours=6), "24h": timedelta(days=1)}


def project_electrical_condition(
    snapshot: OperationsAppSnapshot,
    *,
    asset_id: str,
    period: str = "24h",
    source_id: str | None = None,
    point_id: str | None = None,
    end_at: datetime | None = None,
    reference_start: datetime | None = None,
    reference_end: datetime | None = None,
) -> dict[str, object]:
    """Analyze recorded values; no review writes, training artifacts or provider labels."""
    base: dict[str, object] = {
        "schema_version": 1,
        "asset_id": asset_id,
        "state": "unavailable",
        "meaning": "measured-operating-change-and-reference-pattern-not-fault-diagnosis",
    }
    reader = snapshot.history_reader
    if reader is None:
        return {**base, "state": "no-history"}
    latest = query_operations_latest_asset_measurements(reader, asset_id, limit=100)
    if not latest:
        return {**base, "state": "no-history"}
    if len(latest) >= 100:
        return {**base, "state": "too-many-sources"}
    choices = sorted(
        {(point.measurement.source_id, point.measurement.measurement_point_id) for point in latest},
        key=lambda pair: (pair[0], pair[1] or ""),
    )
    base["sources"] = [{"source_id": source, "point_id": point} for source, point in choices]
    if source_id is None:
        if len(choices) != 1:
            return {**base, "state": "select-source"}
        source_id, point_id = choices[0]
    if (source_id, point_id) not in choices:
        raise ConditionSelectionError("source/point does not belong to the selected asset")
    if period not in _PERIODS:
        raise ValueError("unsupported condition period")
    relevant = [
        point
        for point in latest
        if (point.measurement.source_id, point.measurement.measurement_point_id)
        == (source_id, point_id)
    ]
    stored_times = [at for point in relevant if (at := point.measurement.event_at) is not None]
    if not stored_times:
        return {**base, "state": "unknown-event-time"}
    end = end_at or max(stored_times) + timedelta(seconds=1)
    start = end - _PERIODS[period]
    reference_end = reference_end or start
    reference_start = reference_start or reference_end - _PERIODS[period]
    for at in (start, end, reference_start, reference_end):
        if at.utcoffset() is None:
            raise ValueError("condition times require explicit timezone")
    if not reference_start < reference_end <= start or reference_end - reference_start > timedelta(
        days=1
    ):
        raise ConditionSelectionError("reference must precede target and span at most 24 hours")
    snapshot_id = reader.current_snapshot_id()
    candidates = tuple(
        candidate
        for candidate in reader.list_channel_semantics(
            asset_id,
            source_id=source_id,
            start_at=reference_start,
            end_at=end,
            snapshot_id=snapshot_id,
        )
        if candidate.measurement_point_id == point_id
    )
    try:
        roles = resolve_phase_channels(candidates)
    except ValueError:
        return {**base, "state": "ambiguous-phase-roles"}
    voltage = roles[UnbalanceQuantity.VOLTAGE] or ()
    current = roles[UnbalanceQuantity.CURRENT] or ()
    if not voltage and not current:
        return {**base, "state": "unsupported-signals"}
    channels = (*voltage, *current)
    versions = {
        channel: {c.semantic_version for c in candidates if c.channel_id == channel}
        for channel in channels
    }
    if any(len(values) != 1 for values in versions.values()):
        return {**base, "state": "changed-measurement-meaning"}
    time_evidence: set[str] = set()
    for point in relevant:
        if not point.source_metadata_json:
            continue
        metadata = json.loads(point.source_metadata_json)
        binding = metadata.get("binding") if isinstance(metadata, dict) else None
        if isinstance(binding, dict) and isinstance(binding.get("timezone_evidence"), str):
            time_evidence.add(
                str(binding.get("timezone", "")) + ": " + binding["timezone_evidence"]
            )
    base.update(
        {
            "time_evidence": sorted(time_evidence),
            "source_id": source_id,
            "point_id": point_id,
            "snapshot_id": snapshot_id,
            "target_start": start.astimezone(UTC).isoformat(),
            "target_end": end.astimezone(UTC).isoformat(),
            "reference_start": reference_start.astimezone(UTC).isoformat(),
            "reference_end": reference_end.astimezone(UTC).isoformat(),
            "channels": list(channels),
            "semantic_versions": {name: sorted(v) for name, v in versions.items()},
            "last_observed_at": max(stored_times).isoformat(),
            "source_quality": "unknown"
            if any(point.measurement.source_type.value == "file" for point in relevant)
            else "per-observation-status",
        }
    )
    reference_rows = reader.query_channel_observations(
        asset_id,
        source_id=source_id,
        channel_ids=channels,
        start_at=reference_start,
        end_at=reference_end,
        snapshot_id=snapshot_id,
        max_rows=22_000,
    )
    target_rows = reader.query_channel_observations(
        asset_id,
        source_id=source_id,
        channel_ids=channels,
        start_at=start,
        end_at=end,
        snapshot_id=snapshot_id,
        max_rows=22_000,
    )
    reference, reference_excluded = electrical_samples(
        reference_rows,
        source_id=source_id,
        point_id=point_id,
        voltage_channels=voltage,
        current_channels=current,
    )
    target, target_excluded = electrical_samples(
        target_rows,
        source_id=source_id,
        point_id=point_id,
        voltage_channels=voltage,
        current_channels=current,
    )
    if not target:
        return {**base, "state": "no-target-observations"}
    if not any(sample.voltage is not None or sample.current is not None for sample in target):
        return {**base, "state": "no-usable-target", "excluded": target_excluded}
    result = analyze_electrical_condition(
        reference,
        target,
        channels=channels,
        include_voltage=bool(voltage),
        include_current=bool(current),
        reference_start=reference_start,
        reference_end=reference_end,
        target_start=start,
        target_end=end,
    )
    return {
        **base,
        "state": "analyzed",
        **result,
        "excluded": {"reference": reference_excluded, "target": target_excluded},
    }
