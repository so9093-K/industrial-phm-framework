"""Value occupancy counts raw observations per value band and time bucket."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from importlib.util import find_spec
from pathlib import Path

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig

BASE = datetime(2026, 10, 14, 0, 0, tzinfo=UTC)


def _event(index: int, seconds: int, value: float | None, *, unit: str = "A") -> FileBackfillEvent:
    return FileBackfillEvent(
        raw_evidence_id=f"file:device-a:{'a' * 64}:current:{index}",
        source_id="device-a",
        asset_id="pump-01",
        channel_id="current",
        source_file="pump.csv",
        source_sha256="a" * 64,
        source_size_bytes=10,
        sample_index=index,
        event_at=BASE + timedelta(seconds=seconds),
        value=value,
        source_metadata_json=f'{{"binding":{{"definition":{{"unit":"{unit}"}}}}}}',
    )


@pytest.fixture
def history(tmp_path: Path) -> DuckLakeAssetHistory:
    if find_spec("duckdb") is None:
        pytest.skip("DuckLake history runtime is not installed")
    store = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog.sqlite", tmp_path / "data")
    )
    # First minute stopped, then 10 A and 60 A; a missing value and a conflicting pair at 90 s.
    values = [(0, 0.0), (10, 0.2), (20, 0.0), (30, 10.0), (40, 11.0), (50, 60.0), (60, 61.0)]
    values += [(70, 9.0), (80, None), (90, 30.0), (90, 31.0), (100, 62.0)]
    events = [_event(i, s, v) for i, (s, v) in enumerate(values)]
    # Another meaning of the same channel is never counted with the first.
    events.append(_event(len(events), 110, 500.0, unit="mA"))
    store.append_file_batch(tuple(events), batch_id="occupancy")
    return store


def _meaning(history: DuckLakeAssetHistory, unit: str) -> str:
    aggregation = history.query_multi_signal_measurement_aggregation(
        "pump-01", channel_ids=["current"], start_at=BASE, end_at=BASE + timedelta(minutes=2)
    )
    return next(
        bucket.interpretation_json
        for bucket in aggregation.buckets
        if f'"unit":"{unit}"' in bucket.interpretation_json.replace(" ", "")
    )


def test_time_in_each_band_is_counted_from_raw_values(history: DuckLakeAssetHistory) -> None:
    occupancy = history.query_value_occupancy(
        "pump-01",
        channel_id="current",
        source_id="device-a",
        measurement_point_id=None,
        interpretation_json=_meaning(history, "A"),
        start_at=BASE,
        end_at=BASE + timedelta(seconds=120),
        edges=(1.0, 30.0),
        bucket_count=2,
    )
    assert occupancy.edges == (1.0, 30.0)
    assert (occupancy.minimum, occupancy.maximum) == (0.0, 62.0)
    first, second = occupancy.buckets
    # 0-60 s: three stopped, two near 10 A, one near 60 A. 60-120 s: 61, 9 and 62 A; the
    # missing value, the conflicting pair and the other meaning are left out.
    assert first.counts == (3, 2, 1)
    assert second.counts == (0, 1, 2)
    assert (second.bucket_start, second.bucket_end) == (
        BASE + timedelta(seconds=60),
        BASE + timedelta(seconds=120),
    )


def test_without_edges_one_band_holds_every_usable_value(history: DuckLakeAssetHistory) -> None:
    occupancy = history.query_value_occupancy(
        "pump-01",
        channel_id="current",
        source_id="device-a",
        measurement_point_id=None,
        interpretation_json=_meaning(history, "mA"),
        start_at=BASE,
        end_at=BASE + timedelta(seconds=120),
    )
    assert [bucket.counts for bucket in occupancy.buckets] == [(1,)]
    assert (occupancy.minimum, occupancy.maximum) == (500.0, 500.0)


@pytest.mark.parametrize("edges", [(2.0, 1.0), (1.0, 1.0), (float("nan"),), tuple(range(257))])
def test_edges_must_be_finite_and_increasing(
    history: DuckLakeAssetHistory, edges: tuple[float, ...]
) -> None:
    with pytest.raises(ValueError, match="edges"):
        history.query_value_occupancy(
            "pump-01",
            channel_id="current",
            source_id="device-a",
            measurement_point_id=None,
            interpretation_json="{}",
            start_at=BASE,
            end_at=BASE + timedelta(seconds=120),
            edges=edges,
        )
