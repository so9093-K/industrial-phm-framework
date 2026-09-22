"""Local durable repository for registered operational sources."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import cast

from industrial_phm.application.source_registration import (
    FileSourceConfig,
    FileSourceMode,
    RegisteredSource,
    SourceAlreadyRegisteredError,
    SourceType,
    UnknownRegisteredSourceError,
)

_REGISTRY_SCHEMA = "industrial-phm-source-registry-v1"
_ROOT_KEYS = frozenset({"schema", "sources"})
_SOURCE_KEYS = frozenset({"source_id", "name", "source_type", "registered_at", "config"})
_FILE_CONFIG_KEYS = frozenset(
    {
        "source_path",
        "asset_id",
        "channel_columns",
        "mode",
        "measurement_point_id",
        "timestamp_column",
        "sampling_rate_hz",
        "sampling_rate_tolerance_ratio",
        "minimum_sample_count",
        "delimiter",
    }
)


class SourceRegistryFormatError(ValueError):
    """Raised when persisted source-registry content is unsupported or invalid."""


class JsonSourceRepository:
    """Single-writer local JSON implementation of the SourceRepository boundary.

    Writes use a same-directory temporary file plus ``os.replace`` so readers never
    observe a partially written registry. Cross-process write coordination is not yet
    provided; the current pre-alpha Operations runtime is expected to have one writer.
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        """Return the configured registry file path."""
        return self._path

    def register(self, source: RegisteredSource) -> None:
        if not isinstance(source, RegisteredSource):
            raise ValueError("source must be RegisteredSource")

        sources = list(self._read_sources())
        if any(existing.source_id == source.source_id for existing in sources):
            raise SourceAlreadyRegisteredError(f"source is already registered: {source.source_id}")

        sources.append(source)
        self._write_sources(sources)

    def get(self, source_id: str) -> RegisteredSource:
        _validate_lookup_source_id(source_id)
        for source in self._read_sources():
            if source.source_id == source_id:
                return source
        raise UnknownRegisteredSourceError(f"registered source does not exist: {source_id}")

    def list_sources(self) -> tuple[RegisteredSource, ...]:
        return self._read_sources()

    def _read_sources(self) -> tuple[RegisteredSource, ...]:
        if not self._path.exists():
            return ()
        if not self._path.is_file():
            raise OSError(f"source registry path is not a file: {self._path}")

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise SourceRegistryFormatError("source registry must contain valid JSON") from error

        root = _require_mapping(raw, "source registry root")
        _require_exact_keys(root, _ROOT_KEYS, "source registry root")
        if _require_string(root["schema"], "source registry schema") != _REGISTRY_SCHEMA:
            raise SourceRegistryFormatError(
                f"unsupported source registry schema: {root['schema']!r}"
            )

        sources_raw = root["sources"]
        if not isinstance(sources_raw, list):
            raise SourceRegistryFormatError("source registry sources must be a JSON array")

        sources = tuple(
            _parse_registered_source(item, index=index)
            for index, item in enumerate(sources_raw)
        )
        source_ids = tuple(source.source_id for source in sources)
        if len(set(source_ids)) != len(source_ids):
            raise SourceRegistryFormatError("source registry contains duplicate source_id values")
        return tuple(sorted(sources, key=lambda source: source.source_id))

    def _write_sources(self, sources: Sequence[RegisteredSource]) -> None:
        ordered = tuple(sorted(sources, key=lambda source: source.source_id))
        payload = {
            "schema": _REGISTRY_SCHEMA,
            "sources": [_serialize_registered_source(source) for source in ordered],
        }
        rendered = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"

        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def _serialize_registered_source(source: RegisteredSource) -> dict[str, object]:
    config = source.config
    return {
        "source_id": source.source_id,
        "name": source.name,
        "source_type": source.source_type.value,
        "registered_at": source.registered_at.isoformat(),
        "config": {
            "source_path": config.source_path,
            "asset_id": config.asset_id,
            "channel_columns": list(config.channel_columns),
            "mode": config.mode.value,
            "measurement_point_id": config.measurement_point_id,
            "timestamp_column": config.timestamp_column,
            "sampling_rate_hz": config.sampling_rate_hz,
            "sampling_rate_tolerance_ratio": config.sampling_rate_tolerance_ratio,
            "minimum_sample_count": config.minimum_sample_count,
            "delimiter": config.delimiter,
        },
    }


def _parse_registered_source(value: object, *, index: int) -> RegisteredSource:
    label = f"source registry sources[{index}]"
    source = _require_mapping(value, label)
    _require_exact_keys(source, _SOURCE_KEYS, label)

    source_type = _require_string(source["source_type"], f"{label}.source_type")
    if source_type != SourceType.FILE.value:
        raise SourceRegistryFormatError(f"{label}.source_type is unsupported: {source_type!r}")

    config_label = f"{label}.config"
    config = _require_mapping(source["config"], config_label)
    _require_exact_keys(config, _FILE_CONFIG_KEYS, config_label)

    channels_raw = config["channel_columns"]
    if not isinstance(channels_raw, list) or not all(
        isinstance(channel, str) for channel in channels_raw
    ):
        raise SourceRegistryFormatError(f"{config_label}.channel_columns must be a string array")

    registered_at_raw = _require_string(source["registered_at"], f"{label}.registered_at")
    try:
        registered_at = datetime.fromisoformat(registered_at_raw)
        parsed = RegisteredSource(
            source_id=_require_string(source["source_id"], f"{label}.source_id"),
            name=_require_string(source["name"], f"{label}.name"),
            config=FileSourceConfig(
                source_path=_require_string(config["source_path"], f"{config_label}.source_path"),
                asset_id=_require_string(config["asset_id"], f"{config_label}.asset_id"),
                channel_columns=tuple(cast(list[str], channels_raw)),
                mode=FileSourceMode(
                    _require_string(config["mode"], f"{config_label}.mode")
                ),
                measurement_point_id=_optional_string(
                    config["measurement_point_id"],
                    f"{config_label}.measurement_point_id",
                ),
                timestamp_column=_optional_string(
                    config["timestamp_column"],
                    f"{config_label}.timestamp_column",
                ),
                sampling_rate_hz=_optional_number(
                    config["sampling_rate_hz"],
                    f"{config_label}.sampling_rate_hz",
                ),
                sampling_rate_tolerance_ratio=_optional_number(
                    config["sampling_rate_tolerance_ratio"],
                    f"{config_label}.sampling_rate_tolerance_ratio",
                ),
                minimum_sample_count=_require_integer(
                    config["minimum_sample_count"],
                    f"{config_label}.minimum_sample_count",
                ),
                delimiter=_require_string(config["delimiter"], f"{config_label}.delimiter"),
            ),
            registered_at=registered_at,
        )
    except ValueError as error:
        if isinstance(error, SourceRegistryFormatError):
            raise
        raise SourceRegistryFormatError(f"{label} is invalid: {error}") from error
    return parsed


def _require_mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise SourceRegistryFormatError(f"{label} must be a JSON object")
    return cast(dict[str, object], value)


def _require_exact_keys(
    value: Mapping[str, object],
    expected: frozenset[str],
    label: str,
) -> None:
    actual = frozenset(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise SourceRegistryFormatError(
            f"{label} keys do not match schema; missing={missing}, unexpected={unexpected}"
        )


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise SourceRegistryFormatError(f"{label} must be a string")
    return value


def _optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _require_string(value, label)


def _optional_number(value: object, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SourceRegistryFormatError(f"{label} must be a number or null")
    return float(value)


def _require_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SourceRegistryFormatError(f"{label} must be an integer")
    return value


def _validate_lookup_source_id(source_id: str) -> None:
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError("source_id must not be empty")
    if source_id != source_id.strip():
        raise ValueError("source_id must not contain surrounding whitespace")
