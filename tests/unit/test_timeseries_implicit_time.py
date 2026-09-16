import pytest

from industrial_phm.contracts import CanonicalTimeSeries


def test_accepts_regular_series_without_explicit_timestamps() -> None:
    series = CanonicalTimeSeries(
        asset_id="bearing-001",
        timestamps=None,
        channels=["horizontal", "vertical"],
        values=[[0.1, 0.2], [0.3, 0.4]],
        sampling_rate_hz=25_600.0,
    )

    assert series.timestamps is None
    assert series.sampling_rate_hz == 25_600.0
    assert series.values == ((0.1, 0.2), (0.3, 0.4))


def test_rejects_series_without_explicit_or_implicit_time_basis() -> None:
    with pytest.raises(ValueError, match="timestamps may be omitted"):
        CanonicalTimeSeries(
            asset_id="bearing-001",
            timestamps=None,
            channels=["horizontal"],
            values=[[0.1]],
        )
