"""Prepared single-asset CSV sensor export adapter."""

from __future__ import annotations

import csv
import hashlib
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from io import StringIO
from itertools import pairwise
from pathlib import Path
from types import MappingProxyType

from industrial_phm.contracts import CanonicalTimeSeries, DataQualityIssue, DataQualitySeverity

# These historical IDs are persisted in feature metadata and must remain stable.
_DOMAIN_ID = "field-csv"
_ADAPTER_ID = "field-csv-v1"
_METADATA_VALUE = str | int | float | bool | None


class CsvSensorSourceError(ValueError):
    """Raised when a prepared CSV sensor export violates its declared layout."""


@dataclass(frozen=True, slots=True)
class CsvSensorLayout:
    """Explicit mapping from one CSV export into one canonical sensor segment."""

    asset_id: str
    channel_columns: Sequence[str]
    timestamp_column: str | None = None
    sampling_rate_hz: float | None = None
    sampling_rate_tolerance_ratio: float | None = None
    minimum_sample_count: int = 1
    delimiter: str = ","
    metadata: Mapping[str, _METADATA_VALUE] = field(default_factory=dict)

    def __post_init__(self) -> None:
        channels = tuple(self.channel_columns)
        metadata = MappingProxyType(dict(self.metadata))

        if not self.asset_id.strip():
            raise ValueError("asset_id must not be empty")
        if not channels:
            raise ValueError("channel_columns must contain at least one column")
        if any(not channel.strip() for channel in channels):
            raise ValueError("channel_columns must contain non-empty names")
        if len(set(channels)) != len(channels):
            raise ValueError("channel_columns must contain unique names")
        if self.timestamp_column is not None:
            if not self.timestamp_column.strip():
                raise ValueError("timestamp_column must be non-empty when provided")
            if self.timestamp_column in channels:
                raise ValueError("timestamp_column must not also be a channel column")
        if self.sampling_rate_hz is not None and (
            not math.isfinite(self.sampling_rate_hz) or self.sampling_rate_hz <= 0
        ):
            raise ValueError("sampling_rate_hz must be a positive finite number")
        if self.sampling_rate_tolerance_ratio is not None:
            if self.timestamp_column is None or self.sampling_rate_hz is None:
                raise ValueError(
                    "sampling_rate_tolerance_ratio requires timestamp_column and sampling_rate_hz"
                )
            if (
                not math.isfinite(self.sampling_rate_tolerance_ratio)
                or self.sampling_rate_tolerance_ratio < 0
            ):
                raise ValueError(
                    "sampling_rate_tolerance_ratio must be a finite non-negative number"
                )
        if self.timestamp_column is None and self.sampling_rate_hz is None:
            raise ValueError("timestamp_column or sampling_rate_hz must be provided")
        if (
            isinstance(self.minimum_sample_count, bool)
            or not isinstance(self.minimum_sample_count, int)
            or self.minimum_sample_count <= 0
        ):
            raise ValueError("minimum_sample_count must be a positive integer")
        if len(self.delimiter) != 1:
            raise ValueError("delimiter must contain exactly one character")

        object.__setattr__(self, "channel_columns", channels)
        object.__setattr__(self, "metadata", metadata)


@dataclass(frozen=True, slots=True)
class CsvSensorValidationReport:
    """Validated structure, quality observations and byte identity for one CSV source."""

    source: Path
    asset_id: str
    sample_count: int
    channels: tuple[str, ...]
    timestamp_column: str | None
    sampling_rate_hz: float | None
    sampling_rate_tolerance_ratio: float | None
    minimum_sample_count: int
    delimiter: str
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    minimum_interval_seconds: float | None
    maximum_interval_seconds: float | None
    maximum_sampling_interval_deviation_ratio: float | None
    source_sha256: str
    source_size_bytes: int
    quality_issues: tuple[DataQualityIssue, ...]

    @property
    def has_warnings(self) -> bool:
        """Return whether non-blocking source-quality issues were observed."""
        return any(issue.severity == DataQualitySeverity.WARNING for issue in self.quality_issues)


@dataclass(frozen=True, slots=True)
class _CsvSourceSnapshot:
    text: str
    sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class _ParsedCsvSensor:
    timestamps: tuple[datetime, ...] | None
    values: tuple[tuple[float, ...], ...]
    report: CsvSensorValidationReport


class CsvSensorAdapter:
    """Read one prepared CSV export as one canonical asset segment."""

    def __init__(self, layout: CsvSensorLayout) -> None:
        self._layout = layout

    @property
    def domain(self) -> str:
        """Return the stable field-export domain identifier."""
        return _DOMAIN_ID

    def iter_series(self, source: Path) -> Iterable[CanonicalTimeSeries]:
        """Yield the validated CSV export as one canonical segment."""
        parsed = _parse_csv_sensor_source(source, self._layout)
        metadata = dict(self._layout.metadata)
        metadata.update(
            {
                "source_adapter": _ADAPTER_ID,
                "source_file": source.name,
                "source_sha256": parsed.report.source_sha256,
                "source_size_bytes": parsed.report.source_size_bytes,
                "source_csv_delimiter": parsed.report.delimiter,
                "source_minimum_sample_count": parsed.report.minimum_sample_count,
                "source_sampling_rate_tolerance_ratio": (
                    parsed.report.sampling_rate_tolerance_ratio
                ),
                **_quality_metadata(parsed.report),
            }
        )
        if self._layout.timestamp_column is not None:
            metadata["timestamp_column"] = self._layout.timestamp_column

        yield CanonicalTimeSeries(
            asset_id=self._layout.asset_id,
            timestamps=parsed.timestamps,
            channels=self._layout.channel_columns,
            values=parsed.values,
            sampling_rate_hz=self._layout.sampling_rate_hz,
            metadata=metadata,
        )


def validate_csv_sensor_source(
    source: Path,
    layout: CsvSensorLayout,
) -> CsvSensorValidationReport:
    """Validate one prepared CSV export without invoking any PHM model."""
    return _parse_csv_sensor_source(source, layout).report


def _parse_csv_sensor_source(source: Path, layout: CsvSensorLayout) -> _ParsedCsvSensor:
    if not source.is_file():
        raise CsvSensorSourceError(f"CSV sensor source file does not exist: {source}")

    snapshot = _read_csv_source_snapshot(source)
    reader = csv.reader(StringIO(snapshot.text, newline=""), delimiter=layout.delimiter)
    try:
        try:
            header = tuple(next(reader))
        except StopIteration as error:
            raise CsvSensorSourceError("CSV sensor source is empty") from error

        _validate_header(header, layout)
        index_by_name = {name: index for index, name in enumerate(header)}
        channel_indexes = tuple(index_by_name[name] for name in layout.channel_columns)
        timestamp_index = (
            None if layout.timestamp_column is None else index_by_name[layout.timestamp_column]
        )

        values: list[tuple[float, ...]] = []
        timestamps: list[datetime] | None = [] if timestamp_index is not None else None

        for row_number, row in enumerate(reader, start=2):
            if len(row) != len(header):
                raise CsvSensorSourceError(
                    f"CSV row {row_number} has {len(row)} fields; expected {len(header)}"
                )
            values.append(
                tuple(
                    _parse_numeric_cell(
                        row[index],
                        layout.channel_columns[position],
                        row_number,
                    )
                    for position, index in enumerate(channel_indexes)
                )
            )
            if timestamps is not None and timestamp_index is not None:
                timestamps.append(
                    _parse_timestamp_cell(
                        row[timestamp_index],
                        layout.timestamp_column or "timestamp",
                        row_number,
                    )
                )
    except csv.Error as error:
        raise CsvSensorSourceError(f"cannot parse CSV sensor source: {source}") from error

    if len(values) < layout.minimum_sample_count:
        raise CsvSensorSourceError(
            "CSV sensor source does not meet minimum_sample_count; "
            f"expected at least {layout.minimum_sample_count}, found {len(values)}"
        )

    timestamp_values = None if timestamps is None else tuple(timestamps)
    intervals = _validate_timestamp_order(timestamp_values)
    maximum_deviation_ratio = _maximum_sampling_interval_deviation_ratio(
        intervals,
        layout.sampling_rate_hz,
    )
    issues = _quality_issues(
        intervals,
        maximum_deviation_ratio,
        layout.sampling_rate_tolerance_ratio,
    )

    report = CsvSensorValidationReport(
        source=source,
        asset_id=layout.asset_id,
        sample_count=len(values),
        channels=tuple(layout.channel_columns),
        timestamp_column=layout.timestamp_column,
        sampling_rate_hz=layout.sampling_rate_hz,
        sampling_rate_tolerance_ratio=layout.sampling_rate_tolerance_ratio,
        minimum_sample_count=layout.minimum_sample_count,
        delimiter=layout.delimiter,
        first_timestamp=None if timestamp_values is None else timestamp_values[0],
        last_timestamp=None if timestamp_values is None else timestamp_values[-1],
        minimum_interval_seconds=None if not intervals else min(intervals),
        maximum_interval_seconds=None if not intervals else max(intervals),
        maximum_sampling_interval_deviation_ratio=maximum_deviation_ratio,
        source_sha256=snapshot.sha256,
        source_size_bytes=snapshot.size_bytes,
        quality_issues=issues,
    )
    return _ParsedCsvSensor(
        timestamps=timestamp_values,
        values=tuple(values),
        report=report,
    )


def _validate_header(header: tuple[str, ...], layout: CsvSensorLayout) -> None:
    if not header:
        raise CsvSensorSourceError("CSV sensor source header is empty")
    if any(not name.strip() for name in header):
        raise CsvSensorSourceError("CSV sensor source header contains an empty column name")
    if len(set(header)) != len(header):
        raise CsvSensorSourceError("CSV sensor source header contains duplicate column names")

    required = set(layout.channel_columns)
    if layout.timestamp_column is not None:
        required.add(layout.timestamp_column)
    missing = sorted(required - set(header))
    if missing:
        raise CsvSensorSourceError(f"CSV sensor source is missing required columns: {missing}")


def _parse_numeric_cell(value: str, column: str, row_number: int) -> float:
    if not value.strip():
        raise CsvSensorSourceError(
            f"CSV row {row_number} column {column!r} contains a missing value"
        )
    try:
        result = float(value)
    except ValueError as error:
        raise CsvSensorSourceError(
            f"CSV row {row_number} column {column!r} must be numeric"
        ) from error
    if not math.isfinite(result):
        raise CsvSensorSourceError(f"CSV row {row_number} column {column!r} must be finite")
    return result


def _parse_timestamp_cell(value: str, column: str, row_number: int) -> datetime:
    if not value.strip():
        raise CsvSensorSourceError(
            f"CSV row {row_number} column {column!r} contains a missing timestamp"
        )
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError as error:
        raise CsvSensorSourceError(
            f"CSV row {row_number} column {column!r} must be an ISO 8601 timestamp"
        ) from error


def _validate_timestamp_order(
    timestamps: tuple[datetime, ...] | None,
) -> tuple[float, ...]:
    if timestamps is None or len(timestamps) < 2:
        return ()

    intervals: list[float] = []
    for previous, current in pairwise(timestamps):
        try:
            interval = (current - previous).total_seconds()
        except TypeError as error:
            raise CsvSensorSourceError(
                "CSV timestamps must use consistent timezone awareness"
            ) from error
        if interval <= 0:
            raise CsvSensorSourceError("CSV timestamps must be strictly increasing")
        intervals.append(interval)
    return tuple(intervals)


def _maximum_sampling_interval_deviation_ratio(
    intervals: tuple[float, ...],
    sampling_rate_hz: float | None,
) -> float | None:
    if not intervals or sampling_rate_hz is None:
        return None

    expected_interval = 1.0 / sampling_rate_hz
    return max(abs(interval - expected_interval) / expected_interval for interval in intervals)


def _quality_issues(
    intervals: tuple[float, ...],
    maximum_deviation_ratio: float | None,
    sampling_rate_tolerance_ratio: float | None,
) -> tuple[DataQualityIssue, ...]:
    issues: list[DataQualityIssue] = []
    if len(intervals) >= 2 and min(intervals) != max(intervals):
        issues.append(
            DataQualityIssue(
                code="irregular-sampling",
                severity=DataQualitySeverity.WARNING,
                message=(
                    "timestamp intervals are not uniform; preserve explicit timestamps and "
                    "do not infer a regular sampling grid"
                ),
            )
        )

    if (
        maximum_deviation_ratio is not None
        and sampling_rate_tolerance_ratio is not None
        and maximum_deviation_ratio > sampling_rate_tolerance_ratio
    ):
        issues.append(
            DataQualityIssue(
                code="sampling-rate-mismatch",
                severity=DataQualitySeverity.WARNING,
                message=(
                    "explicit timestamp intervals exceed the declared sampling-rate tolerance; "
                    "preserve the recorded timestamps and review source metadata"
                ),
            )
        )
    return tuple(issues)


def _quality_metadata(report: CsvSensorValidationReport) -> dict[str, _METADATA_VALUE]:
    issue_codes = ",".join(issue.code for issue in report.quality_issues) or None
    return {
        "source_quality_state": "warning" if report.has_warnings else "pass",
        "source_quality_issue_count": len(report.quality_issues),
        "source_quality_issue_codes": issue_codes,
        "source_sampling_interval_max_deviation_ratio": (
            report.maximum_sampling_interval_deviation_ratio
        ),
    }


def _read_csv_source_snapshot(source: Path) -> _CsvSourceSnapshot:
    try:
        payload = source.read_bytes()
    except OSError as error:
        raise CsvSensorSourceError(f"cannot read CSV sensor source: {source}") from error

    try:
        text = payload.decode("utf-8-sig")
    except UnicodeError as error:
        raise CsvSensorSourceError(f"CSV sensor source is not valid UTF-8: {source}") from error

    return _CsvSourceSnapshot(
        text=text,
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )
