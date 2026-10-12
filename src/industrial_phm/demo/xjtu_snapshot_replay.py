"""Recorded XJTU-SY acquisition replay into the snapshot step store (ADR-0025).

Each acquisition CSV is delivered in lifecycle order as an acquisition snapshot whose evidence is
the original file and its SHA-256. Replay is always marked as replay; the delivery time is the
local wall clock, and no absolute acquisition time is invented for the recorded data.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from industrial_phm.adapters import XJTU_SY_CHANNELS, list_xjtu_acquisition_files
from industrial_phm.application.acquisition_snapshot import (
    AcquisitionSnapshot,
    SqliteAcquisitionSnapshotRepository,
    file_sha256,
)


@dataclass(frozen=True, slots=True)
class XjtuReplayProgress:
    asset_id: str
    delivered: int
    already_present: int
    last_ordinal: int | None


def replay_xjtu_bearing(
    snapshots: SqliteAcquisitionSnapshotRepository,
    source: Path,
    *,
    asset_id: str,
    source_id: str,
    interval_seconds: float,
    start: int = 1,
    count: int | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    on_delivered: Callable[[AcquisitionSnapshot], None] | None = None,
) -> XjtuReplayProgress:
    """Deliver acquisitions ``start..start+count-1`` in order, pausing between deliveries."""
    if interval_seconds < 0:
        raise ValueError("interval_seconds must not be negative")
    if start < 1 or (count is not None and count < 1):
        raise ValueError("start and count must be positive")
    files = [
        f
        for f in list_xjtu_acquisition_files(source.resolve(), asset_id)
        if f.acquisition_index >= start
    ]
    if count is not None:
        files = files[:count]
    delivered = present = 0
    last: int | None = None
    for position, item in enumerate(files):
        if position and interval_seconds:
            sleep(interval_seconds)
        snapshot = AcquisitionSnapshot(
            source_id=source_id,
            asset_id=asset_id,
            ordinal=item.acquisition_index,
            file_path=item.path.resolve(),
            sha256=file_sha256(item.path),
            channels=XJTU_SY_CHANNELS,
            sampling_rate_hz=item.sampling_rate_hz,
            sample_count=item.sample_count,
            delivered_at=now(),
            replay=True,
            acquisition_period_seconds=item.acquisition_period_seconds,
            metadata={
                "dataset_id": "xjtu-sy",
                "operating_condition": item.operating_condition,
                "rotational_speed_hz": item.rotational_speed_hz,
                "radial_load_kn": item.radial_load_kn,
            },
        )
        if snapshots.record(snapshot):
            delivered += 1
            if on_delivered is not None:
                on_delivered(snapshot)
        else:
            present += 1
        last = item.acquisition_index
    return XjtuReplayProgress(asset_id, delivered, present, last)
