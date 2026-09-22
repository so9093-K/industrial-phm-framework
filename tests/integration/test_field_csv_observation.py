import hashlib

import pytest
from datetime import datetime
from pathlib import Path

from industrial_phm.adapters import CsvSensorLayout
from industrial_phm.application import (
    load_field_csv_observation_summary,
    load_field_csv_observation_timeline,
)
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

    assert summary.source_snapshot is not None
    assert summary.source_snapshot.name == "pump.csv"
    assert summary.source_snapshot.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()
    assert summary.source_snapshot.size_bytes == source.stat().st_size

    assert summary.validation_policy is not None
    assert summary.validation_policy.source_timestamp_field == "timestamp"
    assert summary.validation_policy.minimum_sample_count == 1
    assert summary.validation_policy.sampling_rate_tolerance_ratio == 0.05



def test_field_csv_timeline_orders_segments_by_recorded_timestamp(
    tmp_path: Path,
) -> None:
    early = tmp_path / "segment-z.csv"
    early.write_text(
        "timestamp,vibration_x\n"
        "2026-09-22T10:00:00+09:00,-1.0\n"
        "2026-09-22T10:00:01+09:00,1.0\n",
        encoding="utf-8",
    )
    late = tmp_path / "segment-a.csv"
    late.write_text(
        "timestamp,vibration_x\n"
        "2026-09-22T11:00:00+09:00,-2.0\n"
        "2026-09-22T11:00:01+09:00,2.0\n",
        encoding="utf-8",
    )
    layout = CsvSensorLayout(
        asset_id="pump-01",
        timestamp_column="timestamp",
        channel_columns=("vibration_x",),
    )

    timeline = load_field_csv_observation_timeline(
        (late, early),
        layout,
        source_id="field-export:pump-01",
        measurement_point_id="drive-end-bearing",
    )

    assert timeline.segment_count == 2
    assert timeline.segments[0].source_snapshot is not None
    assert timeline.segments[0].source_snapshot.name == "segment-z.csv"
    assert timeline.segments[1].source_snapshot is not None
    assert timeline.segments[1].source_snapshot.name == "segment-a.csv"
    assert timeline.observed_start_at == datetime.fromisoformat(
        "2026-09-22T10:00:00+09:00"
    )
    assert timeline.observed_end_at == datetime.fromisoformat(
        "2026-09-22T11:00:01+09:00"
    )


def test_field_csv_timeline_requires_explicit_timestamp_column(
    tmp_path: Path,
) -> None:
    source = tmp_path / "segment.csv"
    source.write_text("vibration_x\n-1.0\n1.0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="explicit timestamp_column"):
        load_field_csv_observation_timeline(
            (source,),
            CsvSensorLayout(
                asset_id="pump-01",
                channel_columns=("vibration_x",),
                sampling_rate_hz=1_000.0,
            ),
            source_id="field-export:pump-01",
        )
