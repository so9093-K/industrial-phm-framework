from pathlib import Path

from industrial_phm.adapters import (
    CsvSensorAdapter,
    CsvSensorLayout,
    validate_csv_sensor_source,
)
from industrial_phm.features import (
    VIBRATION_STATISTICAL_FEATURE_SET_ID,
    extract_vibration_features,
    vibration_feature_names,
)


def test_field_csv_export_flows_into_vibration_feature_contract(tmp_path: Path) -> None:
    source = tmp_path / "pump.csv"
    source.write_text(
        "vibration_x,vibration_y\n"
        "-1.0,-2.0\n"
        "0.0,-1.0\n"
        "1.0,1.0\n"
        "0.0,2.0\n",
        encoding="utf-8",
    )
    layout = CsvSensorLayout(
        asset_id="pump-01",
        channel_columns=("vibration_x", "vibration_y"),
        sampling_rate_hz=12_800.0,
        metadata={
            "site": "pilot-a",
            "measurement_point": "drive-end-bearing",
        },
    )

    report = validate_csv_sensor_source(source, layout)
    series = next(iter(CsvSensorAdapter(layout).iter_series(source)))
    vector = extract_vibration_features(series)

    assert report.sample_count == 4
    assert report.quality_issues == ()
    assert len(report.source_sha256) == 64

    assert vector.feature_set_id == VIBRATION_STATISTICAL_FEATURE_SET_ID
    assert vector.asset_id == "pump-01"
    assert vector.feature_names == vibration_feature_names(("vibration_x", "vibration_y"))
    assert len(vector.values) == 16

    assert vector.metadata["source_adapter"] == "field-csv-v1"
    assert vector.metadata["source_sha256"] == report.source_sha256
    assert vector.metadata["source_size_bytes"] == report.source_size_bytes
    assert vector.metadata["site"] == "pilot-a"
    assert vector.metadata["measurement_point"] == "drive-end-bearing"

    record = vector.to_flat_record()
    assert record["meta.source_sha256"] == report.source_sha256
    assert record["meta.source_adapter"] == "field-csv-v1"
