"""Discovery, validation and registration use cases for prepared file sources."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from industrial_phm.application.field_csv import (
    load_field_csv_observation_summary,
    load_field_csv_observation_timeline_directory,
)
from industrial_phm.application.observation import (
    AssetObservationSummary,
    AssetObservationTimeline,
    SourceSnapshotEvidence,
)
from industrial_phm.application.source_registration import (
    FileSourceConfig,
    FileSourceMode,
    RegisteredSource,
    SourceRepository,
)
from industrial_phm.contracts import DataQualityAssessment, DataQualityState


class FileSourceDiscoveryError(ValueError):
    """Raised when a prepared file source cannot be structurally discovered."""


@dataclass(frozen=True, slots=True)
class FileSourceDiscovery:
    """Read-only discovery result before asset/channel semantics are registered."""

    source_path: str
    mode: FileSourceMode
    file_count: int
    total_size_bytes: int
    common_columns: Sequence[str]
    representative_columns: Sequence[str]
    header_variant_count: int
    representative_file: str
    preview_rows: Sequence[Sequence[str]]

    def __post_init__(self) -> None:
        common_columns = tuple(self.common_columns)
        representative_columns = tuple(self.representative_columns)
        preview_rows = tuple(tuple(row) for row in self.preview_rows)

        if not self.source_path.strip():
            raise ValueError("source_path must not be empty")
        if not isinstance(self.mode, FileSourceMode):
            raise ValueError("mode must be a FileSourceMode")
        if self.file_count <= 0:
            raise ValueError("file_count must be positive")
        if self.total_size_bytes <= 0:
            raise ValueError("total_size_bytes must be positive")
        if not common_columns:
            raise ValueError("common_columns must contain at least one column")
        if not representative_columns:
            raise ValueError("representative_columns must contain at least one column")
        if self.header_variant_count <= 0:
            raise ValueError("header_variant_count must be positive")
        if not self.representative_file.strip():
            raise ValueError("representative_file must not be empty")
        if any(len(row) != len(representative_columns) for row in preview_rows):
            raise ValueError("preview_rows must align with representative_columns")

        object.__setattr__(self, "common_columns", common_columns)
        object.__setattr__(self, "representative_columns", representative_columns)
        object.__setattr__(self, "preview_rows", preview_rows)


@dataclass(frozen=True, slots=True)
class FileSourceRegistrationValidation:
    """Validated source facts shown before persistence."""

    source_id: str
    mode: FileSourceMode
    segment_count: int
    total_sample_count: int
    observed_start_at: datetime | None
    observed_end_at: datetime | None
    quality_state: DataQualityState
    quality_issue_codes: Sequence[str]
    source_snapshots: Sequence[SourceSnapshotEvidence]

    def __post_init__(self) -> None:
        issue_codes = tuple(self.quality_issue_codes)
        snapshots = tuple(self.source_snapshots)
        if not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        if not isinstance(self.mode, FileSourceMode):
            raise ValueError("mode must be a FileSourceMode")
        if self.segment_count <= 0:
            raise ValueError("segment_count must be positive")
        if self.total_sample_count <= 0:
            raise ValueError("total_sample_count must be positive")
        if not isinstance(self.quality_state, DataQualityState):
            raise ValueError("quality_state must be a DataQualityState")
        if any(not code.strip() for code in issue_codes):
            raise ValueError("quality_issue_codes must contain non-empty values")
        if any(not isinstance(snapshot, SourceSnapshotEvidence) for snapshot in snapshots):
            raise ValueError("source_snapshots must contain SourceSnapshotEvidence values")
        object.__setattr__(self, "quality_issue_codes", issue_codes)
        object.__setattr__(self, "source_snapshots", snapshots)


@dataclass(frozen=True, slots=True)
class RegisteredFileObservation:
    """Current validated observation loaded from one registered prepared-file source."""

    latest: AssetObservationSummary
    timeline: AssetObservationTimeline | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.latest, AssetObservationSummary):
            raise ValueError("latest must be an AssetObservationSummary")
        if self.timeline is not None:
            if not isinstance(self.timeline, AssetObservationTimeline):
                raise ValueError("timeline must be an AssetObservationTimeline when provided")
            if self.timeline.latest != self.latest:
                raise ValueError("timeline latest segment must match latest observation")

    @property
    def segment_count(self) -> int:
        """Return the validated segment population represented by this load."""
        return 1 if self.timeline is None else self.timeline.segment_count


def discover_file_source(
    source_path: Path,
    mode: FileSourceMode,
    *,
    delimiter: str = ",",
    preview_row_limit: int = 5,
) -> FileSourceDiscovery:
    """Discover file/header shape without assigning PHM or asset semantics."""
    if not isinstance(mode, FileSourceMode):
        raise ValueError("mode must be a FileSourceMode")
    if len(delimiter) != 1:
        raise ValueError("delimiter must contain exactly one character")
    if (
        isinstance(preview_row_limit, bool)
        or not isinstance(preview_row_limit, int)
        or preview_row_limit <= 0
    ):
        raise ValueError("preview_row_limit must be a positive integer")

    files = _source_files(source_path, mode)
    headers = tuple(_read_header(path, delimiter) for path in files)
    representative_columns = headers[0]
    common_columns = tuple(
        column
        for column in representative_columns
        if all(column in header for header in headers[1:])
    )
    if not common_columns:
        raise FileSourceDiscoveryError(
            "file source has no columns shared by every discovered CSV file"
        )

    preview_rows = _read_preview_rows(
        files[0],
        delimiter,
        expected_column_count=len(representative_columns),
        row_limit=preview_row_limit,
    )
    return FileSourceDiscovery(
        source_path=str(source_path),
        mode=mode,
        file_count=len(files),
        total_size_bytes=sum(path.stat().st_size for path in files),
        common_columns=common_columns,
        representative_columns=representative_columns,
        header_variant_count=len(set(headers)),
        representative_file=files[0].name,
        preview_rows=preview_rows,
    )


def load_registered_file_source_observation(
    source: RegisteredSource,
) -> RegisteredFileObservation:
    """Load the current prepared-file bytes declared by a registered source.

    Registration is not treated as a cached observation. Every load runs the existing
    CSV/timeline validation again so changed or unavailable source bytes fail closed.
    """
    if not isinstance(source, RegisteredSource):
        raise ValueError("source must be RegisteredSource")

    config = _require_file_source_config(source)
    layout = config.to_csv_sensor_layout()
    path = Path(config.source_path)

    if config.mode == FileSourceMode.SNAPSHOT:
        latest = load_field_csv_observation_summary(
            path,
            layout,
            source_id=source.source_id,
            measurement_point_id=config.measurement_point_id,
        )
        return RegisteredFileObservation(latest=latest)

    timeline = load_field_csv_observation_timeline_directory(
        path,
        layout,
        source_id=source.source_id,
        measurement_point_id=config.measurement_point_id,
    )
    return RegisteredFileObservation(latest=timeline.latest, timeline=timeline)


def validate_registered_file_source(
    source: RegisteredSource,
) -> FileSourceRegistrationValidation:
    """Run the registered-source observation loader for one registration candidate."""
    loaded = load_registered_file_source_observation(source)
    config = _require_file_source_config(source)
    segments: tuple[AssetObservationSummary, ...] = (
        (loaded.latest,) if loaded.timeline is None else tuple(loaded.timeline.segments)
    )

    quality = DataQualityAssessment(
        tuple(issue for segment in segments for issue in segment.data_quality.issues)
    )
    issue_codes = tuple(dict.fromkeys(quality.issue_codes))
    snapshots = tuple(
        snapshot for segment in segments if (snapshot := segment.source_snapshot) is not None
    )
    starts = tuple(
        value for segment in segments if (value := segment.observed_start_at) is not None
    )
    ends = tuple(value for segment in segments if (value := segment.observed_end_at) is not None)

    return FileSourceRegistrationValidation(
        source_id=source.source_id,
        mode=config.mode,
        segment_count=len(segments),
        total_sample_count=sum(segment.sample_count for segment in segments),
        observed_start_at=None if not starts else min(starts),
        observed_end_at=None if not ends else max(ends),
        quality_state=quality.state,
        quality_issue_codes=issue_codes,
        source_snapshots=snapshots,
    )


def register_file_source(
    source: RegisteredSource,
    repository: SourceRepository,
) -> FileSourceRegistrationValidation:
    """Validate a prepared source completely before persisting its registration."""
    validation = validate_registered_file_source(source)
    repository.register(source)
    return validation


def _source_files(source_path: Path, mode: FileSourceMode) -> tuple[Path, ...]:
    if mode == FileSourceMode.SNAPSHOT:
        if not source_path.is_file():
            raise FileSourceDiscoveryError(
                f"file source does not exist or is not a file: {source_path}"
            )
        return (source_path,)

    if not source_path.is_dir():
        raise FileSourceDiscoveryError(
            f"history-directory source does not exist or is not a directory: {source_path}"
        )
    files = tuple(
        sorted(
            (
                path
                for path in source_path.iterdir()
                if path.is_file() and path.suffix.lower() == ".csv"
            ),
            key=lambda path: path.name,
        )
    )
    if not files:
        raise FileSourceDiscoveryError(
            f"history-directory source contains no CSV files: {source_path}"
        )
    return files


def _read_header(source: Path, delimiter: str) -> tuple[str, ...]:
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            try:
                header = tuple(next(reader))
            except StopIteration as error:
                raise FileSourceDiscoveryError(f"CSV source is empty: {source}") from error
    except UnicodeDecodeError as error:
        raise FileSourceDiscoveryError(f"CSV source is not UTF-8 text: {source}") from error
    except csv.Error as error:
        raise FileSourceDiscoveryError(f"cannot discover CSV source: {source}") from error

    if any(not name.strip() for name in header):
        raise FileSourceDiscoveryError(f"CSV source header contains an empty column: {source}")
    if len(set(header)) != len(header):
        raise FileSourceDiscoveryError(
            f"CSV source header contains duplicate column names: {source}"
        )
    if not header:
        raise FileSourceDiscoveryError(f"CSV source header is empty: {source}")
    return header


def _read_preview_rows(
    source: Path,
    delimiter: str,
    *,
    expected_column_count: int,
    row_limit: int,
) -> tuple[tuple[str, ...], ...]:
    rows: list[tuple[str, ...]] = []
    try:
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            next(reader, None)
            for row_number, row in enumerate(reader, start=2):
                if len(row) != expected_column_count:
                    raise FileSourceDiscoveryError(
                        f"CSV row {row_number} has {len(row)} fields; "
                        f"expected {expected_column_count}: {source}"
                    )
                rows.append(tuple(row))
                if len(rows) >= row_limit:
                    break
    except UnicodeDecodeError as error:
        raise FileSourceDiscoveryError(f"CSV source is not UTF-8 text: {source}") from error
    except csv.Error as error:
        raise FileSourceDiscoveryError(f"cannot preview CSV source: {source}") from error
    return tuple(rows)



def _require_file_source_config(source: RegisteredSource) -> FileSourceConfig:
    config = source.config
    if not isinstance(config, FileSourceConfig):
        raise ValueError("registered file source must use FileSourceConfig")
    return config
