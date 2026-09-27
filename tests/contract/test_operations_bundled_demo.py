from datetime import UTC, datetime
from pathlib import Path

from industrial_phm.application import (
    FileSourceConfig,
    FileSourceMode,
    RegisteredSource,
    run_registered_file_feature_analysis,
    validate_registered_file_source,
)


def _bundled_demo_source() -> RegisteredSource:
    source_path = (
        Path(__file__).resolve().parents[2]
        / "examples"
        / "operations"
        / "demo-bearing-snapshot.csv"
    )
    return RegisteredSource(
        source_id="demo-bearing-snapshot",
        name="Bundled demo bearing snapshot",
        config=FileSourceConfig(
            source_path=str(source_path),
            asset_id="demo-bearing-01",
            measurement_point_id="drive-end",
            channel_columns=("vibration_x",),
            mode=FileSourceMode.SNAPSHOT,
            timestamp_column="timestamp",
            sampling_rate_hz=1.0,
            sampling_rate_tolerance_ratio=0.01,
            minimum_sample_count=16,
        ),
        registered_at=datetime(2026, 9, 27, 0, 1, tzinfo=UTC),
    )


def test_bundled_operations_demo_validates_and_runs_feature_analysis() -> None:
    source = _bundled_demo_source()

    validation = validate_registered_file_source(source)
    result = run_registered_file_feature_analysis(source)

    assert validation.segment_count == 1
    assert validation.total_sample_count == 32
    assert validation.quality_issue_codes == ()
    assert result.run.source_id == "demo-bearing-snapshot"
    assert result.run.asset_id == "demo-bearing-01"
    assert result.run.measurement_point_id == "drive-end"
    assert result.run.observed_start_at == datetime(2026, 9, 27, 0, 0, tzinfo=UTC)
    assert result.run.observed_end_at == datetime(2026, 9, 27, 0, 0, 31, tzinfo=UTC)
    assert result.evidence.feature_set_id == "vibration-statistical-v1"
    assert len(result.evidence.feature_names) == 8
    assert len(result.evidence.values) == 8
