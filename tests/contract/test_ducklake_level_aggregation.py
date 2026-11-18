"""One read of a source gives each signal on its own grid, also split by a level signal."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from importlib.util import find_spec
from pathlib import Path

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig

BASE = datetime(2026, 10, 14, 0, 0, tzinfo=UTC)


def _event(
    channel: str, index: int, seconds: int, value: float | None, unit: str
) -> FileBackfillEvent:
    return FileBackfillEvent(
        raw_evidence_id=f"file:device-a:{'a' * 64}:{channel}:{index}",
        source_id="device-a",
        asset_id="pump-01",
        channel_id=channel,
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
    # The current moves between 10 A and 60 A; the voltage is lower at 60 A.
    current = [(0, 10.0), (5, 10.0), (10, 60.0), (20, 10.0), (30, 60.0), (40, None), (50, 60.0)]
    current += [(60, 60.0), (70, 60.0)]
    voltage = [(0, 230.0), (10, 220.0), (20, 232.0), (30, 222.0), (40, 231.0), (50, 218.0)]
    # One voltage timestamp conflicts.
    voltage += [(60, 221.0), (70, 219.0), (70, 225.0)]
    events = [_event("current", i, s, v, "A") for i, (s, v) in enumerate(current)]
    events += [_event("voltage", 100 + i, s, v, "V") for i, (s, v) in enumerate(voltage)]
    # The same channel under another meaning stays apart, on its own grid.
    events.append(_event("voltage", 200, 5, 0.23, "kV"))
    store.append_file_batch(tuple(events), batch_id="levels")
    return store


def _meanings(history: DuckLakeAssetHistory) -> dict[tuple[str, str], str]:
    found = history.list_stream_meanings(
        "pump-01",
        source_id="device-a",
        measurement_point_id=None,
        start_at=BASE,
        end_at=BASE + timedelta(minutes=2),
    )
    return {
        (channel, unit): meaning
        for channel, meaning in found
        for unit in ("A", "V", "kV")
        if f'"unit":"{unit}"' in meaning.replace(" ", "")
    }


def test_each_meaning_is_listed_once_per_channel(history: DuckLakeAssetHistory) -> None:
    assert sorted(_meanings(history)) == [("current", "A"), ("voltage", "V"), ("voltage", "kV")]


def test_each_value_takes_the_level_measured_at_its_own_time(
    history: DuckLakeAssetHistory,
) -> None:
    meanings = _meanings(history)
    found = history.query_stream_aggregation(
        "pump-01",
        source_id="device-a",
        measurement_point_id=None,
        channel_ids=["voltage"],
        start_at=BASE,
        end_at=BASE + timedelta(minutes=2),
        bucket_count=2,
        level=("current", meanings["current", "A"], (1.0, 30.0)),
    )
    volts = meanings["voltage", "V"]
    # The volts run from 0 s to one second past 70 s, in two buckets of 35.5 s.
    plain = [row for row in found.buckets if row.interpretation_json == volts]
    assert [(row.bucket_start, row.bucket_end) for row in plain] == [
        (BASE, BASE + timedelta(seconds=35.5)),
        (BASE + timedelta(seconds=35.5), BASE + timedelta(seconds=71)),
    ]
    assert [(row.usable_count, row.conflict_count) for row in plain] == [(4, 0), (3, 2)]
    split = {
        (row.bucket_start, row.band): row
        for row in found.level_buckets
        if row.interpretation_json == volts
    }
    low, high = split[(BASE, 1)], split[(BASE, 2)]
    assert (low.usable_count, low.mean) == (2, pytest.approx(231.0))
    assert (high.usable_count, high.mean) == (2, pytest.approx(221.0))
    # 40 s has no current reading and the conflicting 70 s is unusable.
    later = split[(BASE + timedelta(seconds=35.5), 2)]
    assert (later.usable_count, later.mean, later.minimum) == (2, pytest.approx(219.5), 218.0)
    assert len(split) == 3
    # The kV meaning has its own grid and level.
    (kilo,) = [row for row in found.level_buckets if row.interpretation_json != volts]
    assert (kilo.band, kilo.mean, kilo.bucket_start) == (1, 0.23, BASE + timedelta(seconds=5))


def test_without_a_level_only_the_plain_buckets_are_read(history: DuckLakeAssetHistory) -> None:
    found = history.query_stream_aggregation(
        "pump-01",
        source_id="device-a",
        measurement_point_id=None,
        channel_ids=["current"],
        start_at=BASE,
        end_at=BASE + timedelta(minutes=2),
        bucket_count=1,
    )
    (row,) = found.buckets
    assert (row.observation_count, row.usable_count, row.null_count) == (9, 8, 1)
    assert found.level_buckets == () and found.edges == ()


@pytest.mark.parametrize("edges", [(), (2.0, 1.0), tuple(float(i) for i in range(33))])
def test_level_edges_must_be_few_and_increasing(
    history: DuckLakeAssetHistory, edges: tuple[float, ...]
) -> None:
    with pytest.raises(ValueError, match="edges"):
        history.query_stream_aggregation(
            "pump-01",
            source_id="device-a",
            measurement_point_id=None,
            channel_ids=["voltage"],
            start_at=BASE,
            end_at=BASE + timedelta(minutes=2),
            bucket_count=2,
            level=("current", "{}", edges),
        )


@pytest.mark.parametrize("with_level", [False, True])
def test_wide_stream_batching_preserves_every_bucket_and_meaning(
    history: DuckLakeAssetHistory, monkeypatch: pytest.MonkeyPatch, with_level: bool
) -> None:
    import industrial_phm.history.ducklake as adapter

    extra = [
        _event(f"signal-{channel}", 1000 + channel * 10 + i, i * 10, float(i), "V")
        for channel in range(7)
        for i in range(8)
    ]
    # One unresolved item and another source/point must not borrow a declared meaning.
    extra.append(replace(_event("unresolved", 2000, 10, 2.0, "V"), source_metadata_json=None))
    extra.extend(
        replace(event, source_id="other-source", raw_evidence_id="other:" + event.raw_evidence_id)
        for event in extra[:8]
    )
    history.append_file_batch(tuple(extra), batch_id="wide-stream")
    meanings = _meanings(history)
    arguments = dict(
        source_id="device-a",
        measurement_point_id=None,
        # Unsorted with a repeated channel; the level is outside several batches.
        channel_ids=[
            "voltage",
            "signal-5",
            "unresolved",
            "signal-0",
            "current",
            "signal-1",
            "signal-2",
            "signal-3",
            "signal-4",
            "signal-6",
            "voltage",
        ],
        start_at=BASE,
        end_at=BASE + timedelta(minutes=2),
        bucket_count=3,
        level=("current", meanings["current", "A"], (1.0, 30.0)) if with_level else None,
    )
    monkeypatch.setattr(adapter, "_STREAM_CHANNEL_BATCH", 100)
    whole = history.query_stream_aggregation("pump-01", **arguments)
    whole_meanings = history.list_stream_meanings(
        "pump-01",
        source_id="device-a",
        measurement_point_id=None,
        start_at=BASE,
        end_at=BASE + timedelta(minutes=2),
    )
    monkeypatch.setattr(adapter, "_STREAM_CHANNEL_BATCH", 2)
    assert history.query_stream_aggregation("pump-01", **arguments) == whole
    assert (
        history.list_stream_meanings(
            "pump-01",
            source_id="device-a",
            measurement_point_id=None,
            start_at=BASE,
            end_at=BASE + timedelta(minutes=2),
        )
        == whole_meanings
    )
    assert ("unresolved", '{"binding":null,"semantics":null}') in whole_meanings
    assert len(whole_meanings) == 11
    assert {row.source_id for row in whole.buckets} == {"device-a"}


def test_wide_live_stream_keeps_semantics_and_protocol_quality(
    history: DuckLakeAssetHistory,
) -> None:
    from tests.contract.test_ducklake_runtime import _event as live_event
    from tests.contract.test_ducklake_runtime import _phase_binding

    events = [
        live_event(
            channel_id=f"live-{channel}",
            event_at=BASE + timedelta(seconds=10 * i),
            event_index=channel * 10 + i,
            value=float(i),
            semantic_binding=_phase_binding(f"live-{channel}", "R", "phase current", "A"),
        )
        for channel in range(6)
        for i in range(3)
    ]
    bad = events[-1]
    events[-1] = replace(
        bad,
        event=replace(
            bad.event,
            notification=replace(
                bad.event.notification,
                observation=replace(
                    bad.event.notification.observation,
                    status_good=False,
                    value=None,
                    status_code=0x80000000,
                    status_text="Bad",
                ),
            ),
        ),
    )
    history.append_opcua_batch(tuple(events), batch_id="live-wide")
    meanings = history.list_stream_meanings(
        "pump-01",
        source_id="source-a",
        measurement_point_id="drive-end",
        start_at=BASE,
        end_at=BASE + timedelta(minutes=2),
    )
    assert len(meanings) == 6 and all('"unit":"A"' in meaning for _, meaning in meanings)
    found = history.query_stream_aggregation(
        "pump-01",
        source_id="source-a",
        measurement_point_id="drive-end",
        channel_ids=[f"live-{channel}" for channel in range(6)],
        start_at=BASE,
        end_at=BASE + timedelta(minutes=2),
        bucket_count=1,
    )
    assert len(found.buckets) == 6
    for row in found.buckets:
        assert row.source_type == "opcua" and row.observation_count == 3
        assert (row.non_good_count, row.usable_count, row.mean) == (
            (1, 2, 0.5) if row.channel_id == "live-5" else (0, 3, 1.0)
        )
