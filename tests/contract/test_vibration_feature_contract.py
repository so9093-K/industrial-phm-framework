import math

import pytest

from industrial_phm.contracts import CanonicalTimeSeries
from industrial_phm.features import (
    VIBRATION_STATISTICAL_FEATURE_SET_ID,
    extract_vibration_features,
    vibration_feature_names,
)


def test_statistical_v1_feature_contract_is_stable_and_table_friendly() -> None:
    series = CanonicalTimeSeries(
        asset_id="Bearing1_1",
        timestamps=None,
        channels=("horizontal", "vertical"),
        values=[(-1.0, -2.0), (0.0, -1.0), (1.0, 1.0), (0.0, 2.0)],
        sampling_rate_hz=25_600.0,
        metadata={
            "dataset_id": "xjtu-sy",
            "operating_condition": "35Hz12kN",
            "acquisition_index": 1,
        },
    )

    vector = extract_vibration_features(series)

    assert vector.feature_set_id == VIBRATION_STATISTICAL_FEATURE_SET_ID
    assert vector.feature_names == vibration_feature_names(series.channels)
    assert vector.feature_names == (
        "feature.horizontal.mean",
        "feature.horizontal.rms",
        "feature.horizontal.standard_deviation",
        "feature.horizontal.absolute_peak",
        "feature.horizontal.peak_to_peak",
        "feature.horizontal.crest_factor",
        "feature.horizontal.skewness",
        "feature.horizontal.excess_kurtosis",
        "feature.vertical.mean",
        "feature.vertical.rms",
        "feature.vertical.standard_deviation",
        "feature.vertical.absolute_peak",
        "feature.vertical.peak_to_peak",
        "feature.vertical.crest_factor",
        "feature.vertical.skewness",
        "feature.vertical.excess_kurtosis",
    )
    assert vector.values[:8] == pytest.approx(
        (
            0.0,
            math.sqrt(0.5),
            math.sqrt(0.5),
            1.0,
            2.0,
            math.sqrt(2.0),
            0.0,
            -1.0,
        )
    )
    assert vector.values[8:] == pytest.approx(
        (
            0.0,
            math.sqrt(2.5),
            math.sqrt(2.5),
            2.0,
            4.0,
            2.0 / math.sqrt(2.5),
            0.0,
            -1.64,
        )
    )

    record = vector.to_flat_record()
    assert record["asset_id"] == "Bearing1_1"
    assert record["meta.acquisition_index"] == 1
    assert record["feature.horizontal.rms"] == pytest.approx(math.sqrt(0.5))


def _series(
    asset_id: str,
    dataset_id: str,
    channels: tuple[str, ...],
    metadata: dict[str, object],
) -> CanonicalTimeSeries:
    width = len(channels)
    return CanonicalTimeSeries(
        asset_id=asset_id,
        timestamps=None,
        channels=channels,
        values=[tuple(float(row + column) for column in range(width)) for row in range(4)],
        sampling_rate_hz=20_000.0,
        metadata={"dataset_id": dataset_id, "acquisition_index": 1, **metadata},
    )


def test_feature_layer_stays_dataset_neutral_across_two_domains() -> None:
    """The feature set must not depend on one dataset's channel vocabulary."""
    xjtu = _series(
        "Bearing1_1",
        "xjtu-sy",
        ("Horizontal_vibration_signals", "Vertical_vibration_signals"),
        {"operating_condition": "35Hz12kN"},
    )
    ims_two_channel = _series(
        "set-1-bearing-1",
        "ims-bearings",
        ("x_axis_vibration", "y_axis_vibration"),
        {"test_id": "set-1", "bearing_number": 1},
    )
    ims_single_channel = _series(
        "set-2-bearing-1",
        "ims-bearings",
        ("vibration",),
        {"test_id": "set-2", "bearing_number": 1},
    )

    vectors = [
        extract_vibration_features(series) for series in (xjtu, ims_two_channel, ims_single_channel)
    ]

    assert {vector.feature_set_id for vector in vectors} == {VIBRATION_STATISTICAL_FEATURE_SET_ID}
    for series, vector in zip((xjtu, ims_two_channel, ims_single_channel), vectors, strict=True):
        assert vector.feature_names == vibration_feature_names(series.channels)
        assert len(vector.feature_names) == 8 * len(series.channels)
    assert vectors[0].feature_names != vectors[1].feature_names
    assert len(vectors[2].feature_names) == 8


def test_feature_layer_does_not_require_xjtu_only_metadata() -> None:
    """IMS canonical series carry no operating_condition; extraction must still succeed."""
    ims = _series(
        "set-2-bearing-1",
        "ims-bearings",
        ("vibration",),
        {"rotational_speed_rpm": 2000, "radial_load_lb": 6000},
    )

    vector = extract_vibration_features(ims)

    assert "operating_condition" not in vector.metadata
    assert vector.metadata["dataset_id"] == "ims-bearings"
    assert vector.feature_set_id == VIBRATION_STATISTICAL_FEATURE_SET_ID
