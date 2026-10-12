from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from industrial_phm.adapters import XJTU_SY_CHANNELS
from industrial_phm.application.acquisition_snapshot import SqliteAcquisitionSnapshotRepository
from industrial_phm.demo.xjtu_snapshot_replay import replay_xjtu_bearing


def _source(root: Path, count: int) -> Path:
    bearing = root / "35Hz12kN" / "Bearing1_1"
    bearing.mkdir(parents=True)
    for index in range(1, count + 1):
        rows = "\n".join(f"{0.1 * index},{-0.1 * index}" for _ in range(4))
        bearing.joinpath(f"{index}.csv").write_text(",".join(XJTU_SY_CHANNELS) + "\n" + rows + "\n")
    return root


def test_replay_delivers_in_lifecycle_order_once_and_marks_replay(tmp_path: Path) -> None:
    source = _source(tmp_path / "xjtu", 4)
    repo = SqliteAcquisitionSnapshotRepository(tmp_path / "snapshots.sqlite")
    pauses: list[float] = []
    progress = replay_xjtu_bearing(
        repo,
        source,
        asset_id="Bearing1_1",
        source_id="xjtu-replay",
        interval_seconds=0.25,
        now=lambda: datetime(2026, 10, 12, tzinfo=UTC),
        sleep=pauses.append,
    )
    assert (progress.delivered, progress.already_present, progress.last_ordinal) == (4, 0, 4)
    assert pauses == [0.25, 0.25, 0.25]
    snapshots = repo.list_after("xjtu-replay", "Bearing1_1", after_ordinal=None)
    assert [s.ordinal for s in snapshots] == [1, 2, 3, 4]
    first = snapshots[0]
    assert first.replay and first.event_at is None
    assert first.metadata["operating_condition"] == "35Hz12kN"
    assert first.acquisition_period_seconds == 60.0 and first.sampling_rate_hz == 25_600.0

    again = replay_xjtu_bearing(
        repo, source, asset_id="Bearing1_1", source_id="xjtu-replay", interval_seconds=0, start=3
    )
    assert (again.delivered, again.already_present) == (0, 2)


def test_replay_rejects_unknown_bearing_and_bad_range(tmp_path: Path) -> None:
    source = _source(tmp_path / "xjtu", 2)
    repo = SqliteAcquisitionSnapshotRepository(tmp_path / "snapshots.sqlite")
    with pytest.raises(ValueError, match="unknown"):
        replay_xjtu_bearing(repo, source, asset_id="Bearing9_9", source_id="s", interval_seconds=0)
    with pytest.raises(ValueError, match="positive"):
        replay_xjtu_bearing(
            repo, source, asset_id="Bearing1_1", source_id="s", interval_seconds=0, start=0
        )
