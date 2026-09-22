"""Application projection from field CSV validation to operational observation status."""

from __future__ import annotations

from industrial_phm.adapters import CsvSensorValidationReport
from industrial_phm.application.observation import AssetObservationSummary
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
        data_quality=DataQualityAssessment(report.quality_issues),
    )
