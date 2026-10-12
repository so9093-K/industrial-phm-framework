"""Read projections for the anomaly and RUL monitoring screens (ADR-0025).

Projections read the PHM store, package manifests and the snapshot repository directly; they
never load or run a model. Every response carries the latest delivered step and the latest
analyzed step separately so the screen can show analysis lag, plus the change sequence used for
incremental refresh.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from industrial_phm.application.acquisition_snapshot import (
    AcquisitionSnapshotError,
    SqliteAcquisitionSnapshotRepository,
    read_snapshot_waveform,
)
from industrial_phm.application.observation_window_sqlite import SqliteObservationWindowRepository
from industrial_phm.application.phm_analysis import (
    PhmBinding,
    ReviewInterval,
    SqlitePhmAnalysisStore,
    StepResult,
)
from industrial_phm.models.package import StepKind

PHM_READ_SCHEMA_VERSION = 1
_MAX_PREVIEW_BINS = 2000
_SERIES_PAGE_SIZE = 5000


class PhmReadError(ValueError):
    """Raised for a request the PHM read model cannot answer (unknown binding, bad position)."""


def project_phm_bindings(
    store: SqlitePhmAnalysisStore,
    models_root: Path,
    snapshots: SqliteAcquisitionSnapshotRepository,
    *,
    windows: SqliteObservationWindowRepository | None = None,
) -> dict[str, Any]:
    if not store.path.exists():
        return {"schema_version": PHM_READ_SCHEMA_VERSION, "change_seq": 0, "bindings": []}
    items = []
    for binding in store.list_bindings():
        progress = store.progress(binding.binding_id)
        latest = store.latest_result(binding.binding_id)
        items.append(
            {
                **_binding_json(binding),
                "health": progress.health,
                "health_reason": progress.health_reason,
                "package": _package_summary(models_root, binding.package_id),
                "latest_analyzed": None if latest is None else _step_brief(latest),
                "latest_delivered": _latest_delivered(binding, snapshots, windows),
                "open_intervals": sum(
                    1 for i in store.list_intervals(binding.binding_id) if i.open
                ),
            }
        )
    return {
        "schema_version": PHM_READ_SCHEMA_VERSION,
        "change_seq": store.latest_change_seq(),
        "bindings": items,
    }


def project_phm_series(
    store: SqlitePhmAnalysisStore,
    models_root: Path,
    snapshots: SqliteAcquisitionSnapshotRepository,
    *,
    binding_id: str,
    since_change_seq: int = 0,
    windows: SqliteObservationWindowRepository | None = None,
) -> dict[str, Any]:
    """Return step results newer than ``since_change_seq`` and the current interval set."""
    binding = _binding(store, binding_id)
    progress = store.progress(binding_id)
    # Capture before reading: a result committed after an empty read must remain visible
    # next time. A full page advances only through returned rows, never past unseen rows.
    watermark = store.latest_change_seq()
    page = store.list_results(
        binding_id, after_change_seq=since_change_seq, limit=_SERIES_PAGE_SIZE + 1
    )
    results = page[:_SERIES_PAGE_SIZE]
    cursor = results[-1].change_seq if results else watermark
    latest = store.latest_result(binding_id)
    return {
        "schema_version": PHM_READ_SCHEMA_VERSION,
        "change_seq": cursor,
        "has_more": len(page) > _SERIES_PAGE_SIZE,
        "since_change_seq": since_change_seq,
        "binding": {
            **_binding_json(binding),
            "health": progress.health,
            "health_reason": progress.health_reason,
        },
        "package": _package_summary(models_root, binding.package_id),
        "latest_analyzed": None if latest is None else _step_brief(latest),
        "latest_delivered": _latest_delivered(binding, snapshots, windows),
        "steps": [_step_json(result) for result in results],
        "intervals": [_interval_json(item) for item in store.list_intervals(binding_id)],
    }


def project_snapshot_preview(
    store: SqlitePhmAnalysisStore,
    snapshots: SqliteAcquisitionSnapshotRepository,
    *,
    binding_id: str,
    position: int,
    bins: int = 400,
) -> dict[str, Any]:
    """Min/max envelope of one delivered waveform, verified against its recorded SHA-256."""
    binding = _binding(store, binding_id)
    if binding.step_kind is not StepKind.ACQUISITION_SNAPSHOT:
        raise PhmReadError("binding does not consume acquisition snapshots")
    if not 1 <= bins <= _MAX_PREVIEW_BINS:
        raise PhmReadError("bins out of range")
    snapshot = snapshots.get(binding.source_id, binding.asset_id, position)
    if snapshot is None:
        raise PhmReadError("snapshot not delivered")
    try:
        series = read_snapshot_waveform(snapshot)
    except AcquisitionSnapshotError as error:
        return {
            "schema_version": PHM_READ_SCHEMA_VERSION,
            "position": position,
            "available": False,
            "reason": str(error),
        }
    count = len(series.values)
    width = max(1, -(-count // bins))
    channels = []
    for index, name in enumerate(series.channels):
        column = [row[index] for row in series.values]
        envelope = [
            [min(column[start : start + width]), max(column[start : start + width])]
            for start in range(0, count, width)
        ]
        channels.append({"channel": name, "envelope": envelope})
    return {
        "schema_version": PHM_READ_SCHEMA_VERSION,
        "position": position,
        "available": True,
        "sha256": snapshot.sha256,
        "file_name": snapshot.file_path.name,
        "sampling_rate_hz": snapshot.sampling_rate_hz,
        "sample_count": count,
        "samples_per_bin": width,
        "replay": snapshot.replay,
        "delivered_at": snapshot.delivered_at.isoformat(),
        "channels": channels,
    }


def _binding(store: SqlitePhmAnalysisStore, binding_id: str) -> PhmBinding:
    if not store.path.exists():
        raise PhmReadError("unknown binding")
    for binding in store.list_bindings():
        if binding.binding_id == binding_id:
            return binding
    raise PhmReadError("unknown binding")


def _binding_json(binding: PhmBinding) -> dict[str, Any]:
    return {
        "binding_id": binding.binding_id,
        "package_id": binding.package_id,
        "source_id": binding.source_id,
        "asset_id": binding.asset_id,
        "step_kind": binding.step_kind.value,
        "created_at": binding.created_at.isoformat(),
        "recorded_replay": binding.recorded_replay,
        "measurement_point_id": binding.measurement_point_id,
    }


def _latest_delivered(
    binding: PhmBinding,
    snapshots: SqliteAcquisitionSnapshotRepository,
    windows: SqliteObservationWindowRepository | None = None,
) -> dict[str, Any] | None:
    if binding.step_kind is StepKind.OBSERVATION_WINDOW:
        if windows is None or not windows.path.exists():
            return None
        window = windows.latest_for_stream(
            binding.source_id, binding.asset_id, binding.measurement_point_id
        )
        if window is None:
            return None
        return {
            "position": int(window.window_end.timestamp() * 1_000_000),
            "delivered_at": max(e.event_time.ingested_at for e in window.events).isoformat(),
            "event_at": window.window_end.isoformat(),
            "finalized_at": window.finalized_at.isoformat(),
            "replay": binding.recorded_replay,
        }
    if binding.step_kind is not StepKind.ACQUISITION_SNAPSHOT or not snapshots.path.exists():
        return None
    snapshot = snapshots.latest(binding.source_id, binding.asset_id)
    if snapshot is None:
        return None
    return {
        "position": snapshot.ordinal,
        "delivered_at": snapshot.delivered_at.isoformat(),
        "event_at": _iso(snapshot.event_at),
        "replay": snapshot.replay,
    }


def _package_summary(models_root: Path, package_id: str) -> dict[str, Any] | None:
    """Descriptive manifest fields; verification belongs to the runner, not the read model."""
    if "/" in package_id or package_id.startswith("."):
        return None
    try:
        body = json.loads((models_root / package_id / "package.json").read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return None
    if not isinstance(body, dict):
        return None
    keys = (
        "package_id",
        "recipe_id",
        "estimator_kind",
        "input",
        "output",
        "training_scope",
        "validation",
        "applicability",
        "runtime",
        "created_at",
        "code_revision",
    )
    return {key: body.get(key) for key in keys}


def _step_brief(result: StepResult) -> dict[str, Any]:
    return {
        "position": result.position,
        "state": result.state.value,
        "event_start": _iso(result.event_start),
        "processed_at": result.processed_at.isoformat(),
        "replay": result.replay,
    }


def _step_json(result: StepResult) -> dict[str, Any]:
    return {
        "position": result.position,
        "step_key": result.step_key,
        "state": result.state.value,
        "reason": result.reason,
        "analysis_run_id": result.analysis_run_id,
        "event_start": _iso(result.event_start),
        "event_end": _iso(result.event_end),
        "processed_at": result.processed_at.isoformat(),
        "replay": result.replay,
        "output": dict(result.output),
        "features": None if result.features is None else dict(result.features),
        "input_reference": dict(result.input_reference),
        "change_seq": result.change_seq,
    }


def _interval_json(interval: ReviewInterval) -> dict[str, Any]:
    return {
        "interval_id": interval.interval_id,
        "start_position": interval.start_position,
        "end_position": interval.end_position,
        "start_event_at": _iso(interval.start_event_at),
        "end_event_at": _iso(interval.end_event_at),
        "step_count": interval.step_count,
        "peak_score": interval.peak_score,
        "peak_step_key": interval.peak_step_key,
        "open": interval.open,
        "change_seq": interval.change_seq,
    }


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()
