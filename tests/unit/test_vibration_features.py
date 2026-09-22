import pytest

from industrial_phm.contracts import CanonicalTimeSeries
from industrial_phm.features import (
    VibrationFeatureError,
    extract_vibration_features,
    iter_vibration_features,
)


def _series(
    values: list[tuple[float, float]],
    *,
    acquisition_index: int = 1,
) -> CanonicalTimeSeries:
    return CanonicalTimeSeries(
        asset_id="Bearing1_1",
        timestamps=None,
        channels=("horizontal", "vertical"),
        values=values,
        sampling_rate_hz=25_600.0,
        metadata={"acquisition_index": acquisition_index},
    )


def test_vibration_features_reject_degenerate_channels() -> None:
    with pytest.raises(VibrationFeatureError, match="non-zero variance"):
        extract_vibration_features(_series([(1.0, 0.0), (1.0, 1.0), (1.0, 2.0)]))


def test_iter_vibration_features_is_lazy_and_preserves_acquisition_order() -> None:
    consumed: list[int] = []

    def series_source():
        for acquisition_index in (1, 2):
            consumed.append(acquisition_index)
            yield _series(
                [(-1.0, -2.0), (0.0, -1.0), (1.0, 1.0), (0.0, 2.0)],
                acquisition_index=acquisition_index,
            )

    features = iter_vibration_features(series_source())
    first = next(features)

    assert consumed == [1]
    assert first.metadata["acquisition_index"] == 1

    second = next(features)
    assert consumed == [1, 2]
    assert second.metadata["acquisition_index"] == 2
