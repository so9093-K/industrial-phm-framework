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


def test_copies_mutable_sequences_into_immutable_storage() -> None:
    timestamps = _timestamps(2)
    channels = ["sensor-a"]
    values = [[1.0], [2.0]]
    labels = [False, True]
    rul = [20.0, 19.0]

    series = CanonicalTimeSeries(
        asset_id="asset-001",
        timestamps=timestamps,
        channels=channels,
        values=values,
        labels=labels,
        rul=rul,
    )

    timestamps.clear()
    channels.append("sensor-b")
    values[0][0] = 99.0
    labels.clear()
    rul.clear()

    assert len(series.timestamps) == 2
    assert series.channels == ("sensor-a",)
    assert series.values == ((1.0,), (2.0,))
    assert series.labels == (False, True)
    assert series.rul == (20.0, 19.0)


def test_metadata_is_copied_and_read_only() -> None:
    metadata = {"site": "lab"}
    series = CanonicalTimeSeries(
        asset_id="asset-001",
        timestamps=_timestamps(1),
        channels=["sensor-a"],
        values=[[1.0]],
        metadata=metadata,
    )

    metadata["site"] = "field"

    assert series.metadata["site"] == "lab"
    with pytest.raises(TypeError):
        series.metadata["site"] = "field"  # type: ignore[index]


def test_rejects_blank_asset_id() -> None:
    with pytest.raises(ValueError, match="asset_id must not be empty"):
        CanonicalTimeSeries(
            asset_id="   ",
            timestamps=_timestamps(1),
            channels=["sensor-a"],
            values=[[1.0]],
        )


def test_rejects_empty_channels() -> None:
    with pytest.raises(ValueError, match="at least one channel"):
        CanonicalTimeSeries(
            asset_id="asset-001",
            timestamps=_timestamps(1),
            channels=[],
            values=[[]],
        )


def test_rejects_duplicate_channels() -> None:
    with pytest.raises(ValueError, match="channels must be unique"):
        CanonicalTimeSeries(
            asset_id="asset-001",
            timestamps=_timestamps(1),
            channels=["sensor-a", "sensor-a"],
            values=[[1.0, 2.0]],
        )


def test_rejects_sample_count_mismatch() -> None:
    with pytest.raises(ValueError, match="same number of samples"):
        CanonicalTimeSeries(
            asset_id="asset-001",
            timestamps=_timestamps(2),
            channels=["sensor-a"],
            values=[[1.0]],
        )


def test_rejects_channel_width_mismatch() -> None:
    with pytest.raises(ValueError, match="number of channels"):
        CanonicalTimeSeries(
            asset_id="asset-001",
            timestamps=_timestamps(1),
            channels=["sensor-a", "sensor-b"],
            values=[[1.0]],
        )


@pytest.mark.parametrize("sampling_rate_hz", [0.0, -1.0])
def test_rejects_non_positive_sampling_rate(sampling_rate_hz: float) -> None:
    with pytest.raises(ValueError, match="sampling_rate_hz must be positive"):
        CanonicalTimeSeries(
            asset_id="asset-001",
            timestamps=_timestamps(1),
            channels=["sensor-a"],
            values=[[1.0]],
            sampling_rate_hz=sampling_rate_hz,
        )


def test_rejects_label_length_mismatch() -> None:
    with pytest.raises(ValueError, match="labels must align"):
        CanonicalTimeSeries(
            asset_id="asset-001",
            timestamps=_timestamps(2),
            channels=["sensor-a"],
            values=[[1.0], [2.0]],
            labels=[True],
        )


def test_rejects_rul_length_mismatch() -> None:
    with pytest.raises(ValueError, match="rul must align"):
        CanonicalTimeSeries(
            asset_id="asset-001",
            timestamps=_timestamps(2),
            channels=["sensor-a"],
            values=[[1.0], [2.0]],
            rul=[1.0],
        )


@pytest.mark.parametrize("invalid_value", [float("nan"), float("inf"), float("-inf"), True, "1.0"])
def test_rejects_non_finite_or_non_numeric_values(invalid_value: object) -> None:
    with pytest.raises(ValueError, match="values must contain only finite numbers"):
        CanonicalTimeSeries(
            asset_id="asset-001",
            timestamps=_timestamps(1),
            channels=["sensor-a"],
            values=[[invalid_value]],  # type: ignore[list-item]
        )


@pytest.mark.parametrize("sampling_rate_hz", [float("nan"), float("inf"), float("-inf")])
def test_rejects_non_finite_sampling_rate(sampling_rate_hz: float) -> None:
    with pytest.raises(ValueError, match="sampling_rate_hz must be finite"):
        CanonicalTimeSeries(
            asset_id="asset-001",
            timestamps=None,
            channels=["sensor-a"],
            values=[[1.0]],
            sampling_rate_hz=sampling_rate_hz,
        )


@pytest.mark.parametrize("invalid_rul", [float("nan"), float("inf"), float("-inf"), True, "1.0"])
def test_rejects_non_finite_or_non_numeric_rul(invalid_rul: object) -> None:
    with pytest.raises(ValueError, match="rul must contain only finite numbers or None"):
        CanonicalTimeSeries(
            asset_id="asset-001",
            timestamps=_timestamps(1),
            channels=["sensor-a"],
            values=[[1.0]],
            rul=[invalid_rul],  # type: ignore[list-item]
        )
