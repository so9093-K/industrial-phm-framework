"""Application projection from field CSV validation to operational observation status."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from industrial_phm.adapters import (
    CsvSensorLayout,
    CsvSensorValidationReport,
    validate_csv_sensor_source,
)
from industrial_phm.application.observation import (
    AssetObservationSummary,
    AssetObservationTimeline,
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



def load_field_csv_observation_timeline(
    sources: Sequence[Path],
    layout: CsvSensorLayout,
    *,
    source_id: str,
    measurement_point_id: str | None = None,
) -> AssetObservationTimeline:
    """Validate timestamped field CSV segments and order them by recorded observation time."""
    source_paths = tuple(sources)
    if not source_paths:
        raise ValueError("field observation timeline requires at least one source")
    if len(set(source_paths)) != len(source_paths):
        raise ValueError("field observation timeline sources must be unique")
    if layout.timestamp_column is None:
        raise ValueError(
            "field observation timeline requires an explicit timestamp_column"
        )

    dated_segments: list[tuple[datetime, AssetObservationSummary]] = []
    for source in source_paths:
        summary = load_field_csv_observation_summary(
            source,
            layout,
            source_id=source_id,
            measurement_point_id=measurement_point_id,
        )
        if summary.observed_start_at is None:
            raise AssertionError(
                "timestamped field CSV summary unexpectedly lacks observed_start_at"
            )
        dated_segments.append((summary.observed_start_at, summary))

    try:
        dated_segments.sort(key=lambda item: item[0])
    except TypeError as error:
        raise ValueError(
            "field observation timeline timestamps must use consistent timezone awareness"
        ) from error

    return AssetObservationTimeline(
        tuple(summary for _, summary in dated_segments)
    )



def load_field_csv_observation_timeline_directory(
    source_directory: Path,
    layout: CsvSensorLayout,
    *,
    source_id: str,
    measurement_point_id: str | None = None,
) -> AssetObservationTimeline:
    """Load immediate CSV files as one timestamp-ordered field observation timeline."""
    if not source_directory.is_dir():
        raise ValueError(
            f"field observation timeline directory does not exist: {source_directory}"
        )

    sources = tuple(
        path
        for path in source_directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".csv"
    )
    if not sources:
        raise ValueError(
            f"field observation timeline directory contains no CSV files: {source_directory}"
        )

    return load_field_csv_observation_timeline(
        sources,
        layout,
        source_id=source_id,
        measurement_point_id=measurement_point_id,
    )
