from datetime import datetime
from pathlib import Path

from industrial_phm.adapters import CsvSensorLayout
from industrial_phm.application import load_field_csv_observation_summary
from industrial_phm.contracts import DataQualityState


def test_field_csv_validation_projects_into_operational_observation_summary(
    tmp_path: Path,
) -> None:
    source = tmp_path / "pump.csv"
    source.write_text(
        "timestamp,vibration_x\n"
        "2026-09-22T10:00:00+09:00,-1.0\n"
        "2026-09-22T10:00:01+09:00,0.0\n"
        "2026-09-22T10:00:02+09:00,1.0\n",
        encoding="utf-8",
    )

    summary = load_field_csv_observation_summary(
        source,
        CsvSensorLayout(
            asset_id="pump-01",
            timestamp_column="timestamp",
            channel_columns=("vibration_x",),
            sampling_rate_hz=2.0,
            sampling_rate_tolerance_ratio=0.05,
        ),
        source_id="field-export:pump-01",
        measurement_point_id="drive-end-bearing",
    )

    assert summary.asset_id == "pump-01"
    assert summary.source_id == "field-export:pump-01"
    assert summary.measurement_point_id == "drive-end-bearing"
    assert summary.channels == ("vibration_x",)
    assert summary.sample_count == 3
    assert summary.observed_start_at == datetime.fromisoformat("2026-09-22T10:00:00+09:00")
    assert summary.observed_end_at == datetime.fromisoformat("2026-09-22T10:00:02+09:00")
    assert summary.sampling_rate_hz == 2.0
    assert summary.data_quality.state == DataQualityState.WARNING
    assert summary.data_quality.issue_codes == ("sampling-rate-mismatch",)
