"""Application projection from field CSV validation to operational observation status."""

from __future__ import annotations

from pathlib import Path

from industrial_phm.adapters import (
    CsvSensorLayout,
    CsvSensorValidationReport,
    validate_csv_sensor_source,
)
from industrial_phm.application.observation import (
    AssetObservationSummary,
    ObservationValidationPolicy,
    SourceSnapshotEvidence,
)
from industrial_phm.contracts import DataQualityAssessment


def build_field_csv_observation_summary(
    report: CsvSensorValidationReport,
    *,
    source_id: str,
    measurement_point_id: str | None = None,
) -> AssetObservationSummary:
    """Project validated source facts without inventing PHM state or freshness policy."""
    return AssetObservationSummary(
        asset_id=report.asset_id,
        source_id=source_id,
        measurement_point_id=measurement_point_id,
        channels=report.channels,
        sample_count=report.sample_count,
        observed_start_at=report.first_timestamp,
        observed_end_at=report.last_timestamp,
        sampling_rate_hz=report.sampling_rate_hz,
        source_snapshot=SourceSnapshotEvidence(
            name=report.source.name,
            sha256=report.source_sha256,
            size_bytes=report.source_size_bytes,
        ),
        validation_policy=ObservationValidationPolicy(
            source_timestamp_field=report.timestamp_column,
            minimum_sample_count=report.minimum_sample_count,
            sampling_rate_tolerance_ratio=report.sampling_rate_tolerance_ratio,
        ),
        data_quality=DataQualityAssessment(report.quality_issues),
    )


def load_field_csv_observation_summary(
    source: Path,
    layout: CsvSensorLayout,
    *,
    source_id: str,
    measurement_point_id: str | None = None,
) -> AssetObservationSummary:
    """Validate one prepared field CSV and return its operational observation summary."""
    report = validate_csv_sensor_source(source, layout)
    return build_field_csv_observation_summary(
        report,
        source_id=source_id,
        measurement_point_id=measurement_point_id,
    )
