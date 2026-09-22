"""Source-registration control-plane contracts for operational data sources."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from industrial_phm.adapters import CsvSensorLayout


class SourceType(StrEnum):
    """Supported registered-source families."""

    FILE = "file"


class FileSourceMode(StrEnum):
    """Supported prepared-file source shapes."""

    SNAPSHOT = "snapshot"
    HISTORY_DIRECTORY = "history-directory"


@dataclass(frozen=True, slots=True)
class FileSourceConfig:
    """Registration-time configuration for the existing prepared CSV boundary.

    The config records how a user-declared file or directory should be interpreted.
    It does not assert that the path is currently reachable and it does not add
    streaming, freshness, sensor identity, unit, or connector-health semantics.
    """

    source_path: str
    asset_id: str
    channel_columns: Sequence[str]
    mode: FileSourceMode = FileSourceMode.SNAPSHOT
    measurement_point_id: str | None = None
    timestamp_column: str | None = None
    sampling_rate_hz: float | None = None
    sampling_rate_tolerance_ratio: float | None = None
    minimum_sample_count: int = 1
    delimiter: str = ","

    def __post_init__(self) -> None:
        _validate_identifier(self.source_path, "source_path")
        _validate_identifier(self.asset_id, "asset_id")
        if self.measurement_point_id is not None:
            _validate_identifier(self.measurement_point_id, "measurement_point_id")
        if not isinstance(self.mode, FileSourceMode):
            raise ValueError("mode must be a FileSourceMode")
        if self.mode == FileSourceMode.HISTORY_DIRECTORY and self.timestamp_column is None:
            raise ValueError("history-directory source requires an explicit timestamp_column")

        layout = self.to_csv_sensor_layout()
        object.__setattr__(self, "channel_columns", tuple(layout.channel_columns))

    def to_csv_sensor_layout(self) -> CsvSensorLayout:
        """Build the existing CSV adapter layout without changing its semantics."""
        return CsvSensorLayout(
            asset_id=self.asset_id,
            channel_columns=tuple(self.channel_columns),
            timestamp_column=self.timestamp_column,
            sampling_rate_hz=self.sampling_rate_hz,
            sampling_rate_tolerance_ratio=self.sampling_rate_tolerance_ratio,
            minimum_sample_count=self.minimum_sample_count,
            delimiter=self.delimiter,
        )


@dataclass(frozen=True, slots=True)
class RegisteredSource:
    """Authoritative registration record for one operational source.

    Registration is control-plane state only. The existence of this record does not
    imply that the source is connected, healthy, actively ingested, or producing PHM
    evidence.
    """

    source_id: str
    name: str
    config: FileSourceConfig
    registered_at: datetime

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        _validate_identifier(self.name, "name")
        if not isinstance(self.config, FileSourceConfig):
            raise ValueError("config must be FileSourceConfig")
        if not isinstance(self.registered_at, datetime):
            raise ValueError("registered_at must be a datetime")
        if self.registered_at.utcoffset() is None:
            raise ValueError("registered_at must be timezone-aware")

    @property
    def source_type(self) -> SourceType:
        """Return the source family implied by the registered config."""
        return SourceType.FILE

    @property
    def asset_id(self) -> str:
        """Return the asset identity declared by the source mapping."""
        return self.config.asset_id

    @property
    def measurement_point_id(self) -> str | None:
        """Return the optional measurement-point identity declared by the mapping."""
        return self.config.measurement_point_id


class SourceAlreadyRegisteredError(ValueError):
    """Raised when a repository already owns a source ID."""


class UnknownRegisteredSourceError(LookupError):
    """Raised when a registered source cannot be resolved by ID."""


@runtime_checkable
class SourceRepository(Protocol):
    """Persistence boundary for registered-source control-plane state."""

    def register(self, source: RegisteredSource) -> None:
        """Store a newly registered source and reject duplicate source IDs."""
        ...

    def get(self, source_id: str) -> RegisteredSource:
        """Resolve one source by its stable ID or raise UnknownRegisteredSourceError."""
        ...

    def list_sources(self) -> tuple[RegisteredSource, ...]:
        """Return registered sources in deterministic source-ID order."""
        ...


class InMemorySourceRepository:
    """Non-persistent reference repository for application workflows and tests."""

    def __init__(self) -> None:
        self._sources: dict[str, RegisteredSource] = {}

    def register(self, source: RegisteredSource) -> None:
        if not isinstance(source, RegisteredSource):
            raise ValueError("source must be RegisteredSource")
        if source.source_id in self._sources:
            raise SourceAlreadyRegisteredError(f"source is already registered: {source.source_id}")
        self._sources[source.source_id] = source

    def get(self, source_id: str) -> RegisteredSource:
        _validate_identifier(source_id, "source_id")
        try:
            return self._sources[source_id]
        except KeyError as error:
            raise UnknownRegisteredSourceError(
                f"registered source does not exist: {source_id}"
            ) from error

    def list_sources(self) -> tuple[RegisteredSource, ...]:
        return tuple(sorted(self._sources.values(), key=lambda source: source.source_id))


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
