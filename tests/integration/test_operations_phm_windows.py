from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.application.observation_window_sqlite import SqliteObservationWindowRepository
from industrial_phm.application.phm_analysis import SqlitePhmAnalysisStore
from industrial_phm.application.phm_read import project_phm_series
from industrial_phm.application.phm_runner import PackageCache, run_window_bindings
from industrial_phm.application.phm_window_read import project_phm_window
from tests.support.electrical_phm import electrical_window, electrical_workspace
from tests.support.window_analysis import START


def test_real_finalized_windows_are_point_isolated_scored_and_read_as_raw_signals(
    tmp_path: Path,
) -> None:
    workspace = electrical_workspace(tmp_path / "ws")
    windows = SqliteObservationWindowRepository(workspace.window_state_path)
    for i, current in enumerate((10.0, 20.0, 20.0)):
        windows.record_window(
            electrical_window(
                f"other-{i}", START + timedelta(minutes=i * 5), 999.0, point="other-board"
            )
        )
        windows.record_window(
            electrical_window(f"own-{i}", START + timedelta(minutes=i * 5), current)
        )
    store = SqlitePhmAnalysisStore(workspace.phm_analysis_path)
    (cycle,) = run_window_bindings(
        store, windows, PackageCache(workspace.models_path), max_scanned=1
    )
    assert [r.input_reference["window_id"] for r in cycle.results] == ["own-0", "own-1", "own-2"]
    assert all(r.output["applicability"] == "inside" for r in cycle.results)
    for r in cycle.results:
        assert sum(r.output["feature_contributions"].values()) == r.output["score"]
    assert len(store.list_intervals("electrical-a")) == 1
    assert run_window_bindings(store, windows, PackageCache(workspace.models_path))[0].results == ()
    preview = project_phm_window(
        store, windows, binding_id="electrical-a", position=cycle.results[-1].position
    )
    assert preview["available"] and len(preview["channels"]) == 7
    assert all(len(c["points"]) == 5 for c in preview["channels"])
    assert str(tmp_path) not in json.dumps(preview)
    series = project_phm_series(
        store,
        workspace.models_path,
        SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
        binding_id="electrical-a",
        windows=windows,
    )
    assert series["latest_delivered"]["event_at"] == cycle.results[-1].event_end.isoformat()
    assert series["latest_delivered"]["replay"]
    previous_position = cycle.results[-1].position
    windows.record_window(
        electrical_window("too-short", START + timedelta(minutes=15), duration_minutes=1)
    )
    run_window_bindings(store, windows, PackageCache(workspace.models_path))
    series = project_phm_series(
        store,
        workspace.models_path,
        SqliteAcquisitionSnapshotRepository(workspace.acquisition_snapshot_path),
        binding_id="electrical-a",
        windows=windows,
    )
    assert series["latest_analyzed"]["position"] == previous_position
    assert series["latest_processed"]["state"] == "skipped"
    assert (
        series["steps"][-1]["reason"]
        == "electrical-window-v1 requires a 300-second finalized window"
    )


@pytest.mark.parametrize("had_replay", [False, True])
def test_m1_store_is_migrated_without_discarding_binding_or_state(
    tmp_path: Path, had_replay: bool
) -> None:
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE phm_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO phm_meta VALUES('schema_version','1');
            CREATE TABLE binding(binding_id TEXT PRIMARY KEY, package_id TEXT, source_id TEXT,
                asset_id TEXT, step_kind TEXT, created_at TEXT, cursor_position INTEGER,
                cursor_step_key TEXT, state TEXT, health TEXT, health_reason TEXT, health_at TEXT);
            INSERT INTO binding VALUES('old','package','source','asset','acquisition-snapshot',
                '2026-10-12T00:00:00+00:00',3,'s3','{"last_estimate":42}','ok',NULL,NULL);
        """)
        if had_replay:
            connection.execute("ALTER TABLE binding ADD COLUMN recorded_replay INTEGER DEFAULT 0")
            connection.execute("UPDATE binding SET recorded_replay = 1")
    store = SqlitePhmAnalysisStore(path)
    (binding,) = store.list_bindings()
    assert binding.binding_id == "old" and binding.recorded_replay == had_replay
    assert binding.measurement_point_id is None
    progress = store.progress("old")
    assert progress.cursor_position == 3 and progress.state["last_estimate"] == 42
