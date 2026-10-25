"""A model built from a chosen reference period scores stored history by window (ADR-0032)."""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from importlib.util import find_spec
from pathlib import Path

import pytest

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.application.history_window import (
    project_history_window,
    run_history_window_bindings,
)
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore, StepState
from industrial_phm.application.phm_read import project_phm_monitor
from industrial_phm.application.phm_runner import PackageCache
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime import OperationsWorkspace, initialize_operations_workspace
from industrial_phm.runtime.operations_web_history_model import build_web_history_model

BASE = datetime(2026, 10, 15, tzinfo=UTC)
DAY = 1440


def _pump(minutes: int) -> tuple[FileBackfillEvent, ...]:
    """One-minute vibration and temperature; wear begins 1.6 days into the record."""
    rng = random.Random(7)
    events = []
    for minute in range(minutes):
        wear = max(0.0, minute / DAY - 1.6)
        for offset, channel, unit, value in (
            (0, "vibration", "mm/s", 2.1 + rng.gauss(0, 0.08) + 1.8 * wear**2),
            (1, "temperature", "°C", 48 + rng.gauss(0, 0.3) + 6.5 * wear**1.5),
        ):
            events.append(
                FileBackfillEvent(
                    raw_evidence_id=f"file:pump:{'c' * 64}:{2 * minute + offset}",
                    source_id="pump-file",
                    asset_id="pump-01",
                    channel_id=channel,
                    source_file="pump.csv",
                    source_sha256="c" * 64,
                    source_size_bytes=10,
                    sample_index=2 * minute + offset,
                    event_at=BASE + timedelta(minutes=minute),
                    value=value,
                    source_metadata_json=json.dumps({"binding": {"definition": {"unit": unit}}}),
                )
            )
    return tuple(events)


def _backfill() -> tuple[FileBackfillEvent, ...]:
    """A late file with extra vibration readings between the first hour's minutes."""
    return tuple(
        FileBackfillEvent(
            raw_evidence_id=f"file:late:{'d' * 64}:{index}",
            source_id="pump-file",
            asset_id="pump-01",
            channel_id="vibration",
            source_file="late.csv",
            source_sha256="d" * 64,
            source_size_bytes=10,
            sample_index=index,
            event_at=BASE + timedelta(minutes=index, seconds=30),
            value=2.6,
            source_metadata_json=json.dumps({"binding": {"definition": {"unit": "mm/s"}}}),
        )
        for index in range(60)
    )


def _request(end: datetime) -> dict[str, object]:
    return {
        "asset_id": "pump-01",
        "source_id": "pump-file",
        "channels": ["vibration", "temperature"],
        "reference_start": BASE.isoformat(),
        "reference_end": end.isoformat(),
        "window_seconds": 600,
    }


def test_reference_model_scores_each_later_window_and_shows_its_exact_input(
    tmp_path: Path,
) -> None:
    if find_spec("duckdb") is None:
        pytest.skip("DuckLake history runtime is not installed")
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    history.append_file_batch(_pump(3 * DAY), batch_id="pump")

    thin = build_web_history_model(workspace.root, _request(BASE + timedelta(hours=2)))
    assert thin["built"] is False and thin["reference_windows"] == 12
    assert "최소 24개" in str(thin["reason"])
    assert not list(workspace.models_path.glob("*/package.json"))

    built = build_web_history_model(workspace.root, _request(BASE + timedelta(days=1)))
    assert built["built"] is True and built["reference_windows"] == 144 and not built["reused"]
    # Pressing again with the same choices reuses that model and binding.
    again = build_web_history_model(workspace.root, _request(BASE + timedelta(days=1)))
    assert again["reused"] is True
    assert (again["package_id"], again["binding_id"]) == (built["package_id"], built["binding_id"])
    assert (again["reference_windows"], again["threshold"]) == (144, built["threshold"])
    assert len(list(workspace.models_path.glob("*/package.json"))) == 1
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    packages = PackageCache(workspace.models_path)
    results = []
    for _ in range(10):
        found = [
            r
            for cycle in run_history_window_bindings(store, history, packages)
            for r in cycle.results
        ]
        if not found:
            break
        results += found
    # Every ten-minute window is scored once; the one holding the latest value waits for more.
    assert len(results) == 3 * 144 - 1
    assert all(r.state is StepState.ANALYZED for r in results)
    assert [r.position for r in results] == sorted({r.position for r in results})

    def share(start: float, end: float) -> float:
        part = [
            r
            for r in results
            if BASE + timedelta(days=start) <= r.event_start < BASE + timedelta(days=end)
        ]
        return sum(bool(r.output["exceeds_threshold"]) for r in part) / len(part)

    assert share(1.0, 1.5) <= 0.05
    assert share(2.6, 3.0) >= 0.9

    # The monitor names the period the model learned, so two such models read apart.
    (item,) = project_phm_monitor(
        store,
        workspace.models_path,
        SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
    )["items"]
    assert item["training_reference"] == {
        "start": BASE.isoformat(),
        "end": (BASE + timedelta(days=1)).isoformat(),
        "channels": 2,
    }

    last = results[-1]
    preview = project_history_window(
        store, history, binding_id=str(built["binding_id"]), position=last.position
    )
    assert preview["available"] is True
    assert [c["channel_id"] for c in preview["channels"]] == ["vibration", "temperature"]
    assert all(len(c["points"]) == 10 for c in preview["channels"])

    # A file backfilled into the reference period changes what the model would learn: same
    # choices then build a new model instead of reusing the old one.
    history.append_file_batch(_backfill(), batch_id="late")
    rebuilt = build_web_history_model(workspace.root, _request(BASE + timedelta(days=1)))
    assert rebuilt["built"] is True and rebuilt["reused"] is False
    assert rebuilt["package_id"] != built["package_id"]
    assert len(list(workspace.models_path.glob("*/package.json"))) == 2


def _stream(
    source: str, start: datetime, minutes: int, *, point: str | None, first_index: int = 0
) -> tuple[FileBackfillEvent, ...]:
    """Steady one-minute vibration of one source and measurement point."""
    rng = random.Random(first_index)
    return tuple(
        FileBackfillEvent(
            raw_evidence_id=f"file:{source}:{'e' * 64}:{first_index + minute}",
            source_id=source,
            asset_id="pump-01",
            channel_id="vibration",
            source_file=f"{source}.csv",
            source_sha256="e" * 64,
            source_size_bytes=10,
            sample_index=first_index + minute,
            event_at=start + timedelta(minutes=minute),
            value=2.1 + rng.gauss(0, 0.08),
            measurement_point_id=point,
            source_metadata_json=json.dumps({"binding": {"definition": {"unit": "mm/s"}}}),
        )
        for minute in range(minutes)
    )


def test_progress_follows_the_bound_streams_own_observations_across_a_long_gap(
    tmp_path: Path,
) -> None:
    if find_spec("duckdb") is None:
        pytest.skip("DuckLake history runtime is not installed")
    workspace = OperationsWorkspace(tmp_path / "ws")
    initialize_operations_workspace(workspace)
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(workspace.history_catalog_path, workspace.history_data_path)
    )
    resumed = BASE + timedelta(days=20)
    history.append_file_batch(
        _stream("pump-opc", BASE, 360, point="drive-end")
        + _stream("pump-opc", resumed, 120, point="drive-end", first_index=360),
        batch_id="drive-end",
    )
    # Another source of the same asset and signal keeps recording long after.
    history.append_file_batch(
        _stream("other", resumed + timedelta(days=5), 60, point=None), batch_id="other"
    )
    request = {
        "asset_id": "pump-01",
        "source_id": "pump-opc",
        "channels": ["vibration"],
        "reference_start": BASE.isoformat(),
        "reference_end": (BASE + timedelta(hours=4)).isoformat(),
        "window_seconds": 300,
    }
    # Without its measurement point the stream holds no reference values at all.
    assert build_web_history_model(workspace.root, request)["reference_windows"] == 0
    built = build_web_history_model(
        workspace.root, {**request, "measurement_point_id": "drive-end"}
    )
    assert built["built"] is True and built["reference_windows"] == 48

    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    packages = PackageCache(workspace.models_path)
    results = []
    for _ in range(5):
        found = [
            r
            for cycle in run_history_window_bindings(store, history, packages)
            for r in cycle.results
        ]
        if not found:
            break
        results += found
    # 72 windows before the 20-day gap, then 24 after it; the one holding the stream's latest
    # value waits even though the other source has later observations.
    assert len(results) == 72 + 23
    assert results[-1].event_end == resumed + timedelta(minutes=115)
    preview = project_history_window(
        store, history, binding_id=str(built["binding_id"]), position=results[-1].position
    )
    assert preview["available"] is True
