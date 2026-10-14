"""Two-period measurement profiles are exact statistics of raw observations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from importlib.util import find_spec
from pathlib import Path

import pytest

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig

BASE = datetime(2026, 10, 14, 0, 0, tzinfo=UTC)


def _event(
    index: int, seconds: int, value: float | None, *, channel: str = "current", unit: str = "A"
):
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
    # Period A (0-600 s): 10 s steps of 1..5, a 60 s gap, three equal values in a row,
    # one missing value and one conflicting pair at 500 s.
    a = [(0, 1.0), (10, 2.0), (20, 3.0), (30, 4.0), (40, 5.0), (100, 2.0), (110, 2.0)]
    a += [(120, 2.0), (130, 3.0), (140, None), (500, 7.0), (500, 8.0)]
    # Period B (600-1200 s): higher values, regular 10 s steps.
    b = [(600 + 10 * i, 6.0 + i) for i in range(6)]
    events = [_event(i, s, v) for i, (s, v) in enumerate(a + b)]
    store.append_file_batch(tuple(events), batch_id="profiles")
    return store


def test_each_period_is_described_from_its_raw_values(history: DuckLakeAssetHistory) -> None:
    profiles = history.query_measurement_profiles(
        "pump-01",
        channel_ids=["current"],
        periods=[
            ("a", BASE, BASE + timedelta(seconds=600)),
            ("b", BASE + timedelta(seconds=600), BASE + timedelta(seconds=1200)),
        ],
        bins=4,
    )
    a, b = sorted(profiles, key=lambda item: item.period)
    assert (a.observation_count, a.usable_count, a.null_count, a.conflict_count) == (12, 9, 1, 2)
    assert a.minimum == 1.0 and a.maximum == 5.0
    assert a.quantiles is not None and a.quantiles[2] == pytest.approx(2.0)
    # Gaps are between usable timestamps: 40 -> 100 is the largest, 130 -> (nothing usable).
    assert a.median_interval_seconds == pytest.approx(10.0)
    assert a.largest_gap_seconds == pytest.approx(60.0)
    assert a.largest_gap_start == BASE + timedelta(seconds=40)
    assert a.long_gap_count == 1
    assert a.longest_constant_count == 3
    assert a.longest_constant_start == BASE + timedelta(seconds=100)
    # Both periods share edges 1..11, so the histograms can be overlaid.
    assert (a.histogram_low, a.histogram_high) == (b.histogram_low, b.histogram_high) == (1, 11)
    assert sum(a.histogram) == 9 and sum(b.histogram) == 6
    # Every B value is above A's 95th percentile; no A value lies inside B's 5-95 % band.
    assert b.outside_other_band == 6
    assert '"unit":"A"' in a.interpretation_json.replace(" ", "")


def test_profile_inputs_are_bounded(history: DuckLakeAssetHistory) -> None:
    with pytest.raises(ValueError, match="31 days"):
        history.query_measurement_profiles(
            "pump-01",
            channel_ids=["current"],
            periods=[("a", BASE, BASE + timedelta(days=40))],
        )
    with pytest.raises(ValueError, match="1 to 8 channels"):
        history.query_measurement_profiles(
            "pump-01", channel_ids=[], periods=[("a", BASE, BASE + timedelta(hours=1))]
        )


def test_two_channels_pair_only_at_identical_timestamps(history: DuckLakeAssetHistory) -> None:
    voltage = [
        _event(100 + i, seconds, value, channel="voltage")
        for i, (seconds, value) in enumerate([(0, 10.0), (10, 20.0), (20, 30.0), (25, 99.0)])
    ]
    history.append_file_batch(tuple(voltage), batch_id="voltage")
    (group,) = history.query_measurement_pairs(
        "pump-01",
        x_channel="current",
        y_channel="voltage",
        periods=[("a", BASE, BASE + timedelta(seconds=600))],
    )
    # current exists at 0/10/20 s with 1, 2, 3; voltage's 25 s value has no partner.
    assert (group.pair_count, group.x_usable_count, group.y_usable_count) == (3, 9, 4)
    assert group.pearson == pytest.approx(1.0) and group.spearman == pytest.approx(1.0)
    assert [point[1:] for point in group.points] == [(1.0, 10.0), (2.0, 20.0), (3.0, 30.0)]
    with pytest.raises(ValueError, match="two different channels"):
        history.query_measurement_pairs(
            "pump-01", x_channel="current", y_channel="current", periods=[("a", BASE, BASE)]
        )


def test_pairs_never_mix_two_meanings_of_one_channel(history: DuckLakeAssetHistory) -> None:
    # The voltage mapping changed from V to mV at 20 s: one correlation across both would
    # compare numbers that do not mean the same thing.
    voltage = [
        _event(200 + i, seconds, value, channel="voltage", unit=unit)
        for i, (seconds, value, unit) in enumerate(
            [(0, 10.0, "V"), (10, 20.0, "V"), (20, 3000.0, "mV"), (30, 4000.0, "mV")]
        )
    ]
    history.append_file_batch(tuple(voltage), batch_id="voltage-units")
    groups = history.query_measurement_pairs(
        "pump-01",
        x_channel="current",
        y_channel="voltage",
        periods=[("a", BASE, BASE + timedelta(seconds=600))],
    )
    by_unit = {'"mV"' in g.y_interpretation_json: g for g in groups}
    assert len(groups) == 2 and set(by_unit) == {True, False}
    assert [(p[1], p[2]) for p in by_unit[False].points] == [(1.0, 10.0), (2.0, 20.0)]
    assert [(p[1], p[2]) for p in by_unit[True].points] == [(3.0, 3000.0), (4.0, 4000.0)]
    assert by_unit[True].pair_count == by_unit[True].y_usable_count == 2
