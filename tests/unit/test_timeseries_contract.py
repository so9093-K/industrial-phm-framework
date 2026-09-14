from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.contracts import CanonicalTimeSeries


def _timestamps(count: int) -> list[datetime]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return [start + timedelta(seconds=index) for index in range(count)]


def test_accepts_valid_multivariate_series() -> None:
    series = CanonicalTimeSeries(
        asset_id="asset-001",
        timestamps=_timestamps(2),
        channels=["sensor-a", "sensor-b"],
        values=[[1.0, 2.0], [1.5, 2.5]],
        sampling_rate_hz=1.0,
        labels=[False, True],
        rul=[20.0, 19.0],
        metadata={"site": "lab"},
    )

    assert series.asset_id == "asset-001"
    assert series.metadata["site"] == "lab"


def test_rejects_channel_width_mismatch() -> None:
    with pytest.raises(ValueError, match="number of channels"):
        CanonicalTimeSeries(
            asset_id="asset-001",
            timestamps=_timestamps(1),
            channels=["sensor-a", "sensor-b"],
            values=[[1.0]],
        )


def test_rejects_optional_target_length_mismatch() -> None:
    with pytest.raises(ValueError, match="labels must align"):
        CanonicalTimeSeries(
            asset_id="asset-001",
            timestamps=_timestamps(2),
            channels=["sensor-a"],
            values=[[1.0], [2.0]],
            labels=[True],
        )
