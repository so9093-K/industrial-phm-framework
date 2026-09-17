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
