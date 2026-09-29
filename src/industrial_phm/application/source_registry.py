"""Local durable repository for registered operational sources."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import cast

from industrial_phm.application.measurement_semantics import (
    parse_channel_semantic_binding,
    serialize_channel_semantic_binding,
)
from industrial_phm.application.source_freshness import SourceFreshnessPolicy
from industrial_phm.application.source_lifecycle import (
    SourceLifecycleRecord,
    SourceLifecycleState,
)
from industrial_phm.application.source_registration import (
    FileSourceConfig,
    FileSourceMode,
    OpcUaSourceConfig,
    RegisteredSource,
    SourceAlreadyRegisteredError,
    SourceType,
    UnknownRegisteredSourceError,
)
from industrial_phm.connectors import OpcUaNodeMapping

_REGISTRY_SCHEMA = "industrial-phm-source-registry-v5"
_ROOT_KEYS = frozenset({"schema", "sources", "lifecycle", "freshness_policies"})
_SOURCE_KEYS = frozenset({"source_id", "name", "source_type", "registered_at", "config"})
_LIFECYCLE_KEYS = frozenset({"source_id", "state", "changed_at", "detail"})
_FRESHNESS_POLICY_KEYS = frozenset({"source_id", "max_observation_age_seconds", "changed_at"})
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
_OPCUA_CONFIG_KEYS = frozenset(
    {
        "endpoint_url",
        "asset_id",
        "measurement_point_id",
        "node_mappings",
        "timeout_seconds",
        "semantic_bindings",
    }
)
_OPCUA_NODE_MAPPING_KEYS = frozenset({"channel_id", "node_id"})


class SourceRegistryFormatError(ValueError):
    """Raised when persisted source-registry content is unsupported or invalid."""


class JsonSourceRepository:
    """Single-writer local JSON registration/lifecycle/freshness repository.

    The repository accepts only the current v5 schema. Older pre-alpha local registry
    formats are intentionally unsupported; sources must be registered again rather than
    carrying migration branches indefinitely.

    Writes use a same-directory temporary file plus os.replace so readers never observe
    a partially written registry. Cross-process write coordination is not yet provided.
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

        sources, lifecycle, freshness = self._read_registry()
        if any(existing.source_id == source.source_id for existing in sources):
            raise SourceAlreadyRegisteredError(f"source is already registered: {source.source_id}")

        next_sources = (*sources, source)
        next_lifecycle = dict(lifecycle)
        next_lifecycle[source.source_id] = SourceLifecycleRecord(
            source_id=source.source_id,
            state=SourceLifecycleState.REGISTERED,
            changed_at=source.registered_at,
        )
        self._write_registry(next_sources, next_lifecycle, freshness)

    def get(self, source_id: str) -> RegisteredSource:
        _validate_lookup_source_id(source_id)
        sources, _, _ = self._read_registry()
        for source in sources:
            if source.source_id == source_id:
                return source
        raise UnknownRegisteredSourceError(f"registered source does not exist: {source_id}")

    def list_sources(self) -> tuple[RegisteredSource, ...]:
        sources, _, _ = self._read_registry()
        return sources

    def get_lifecycle(self, source_id: str) -> SourceLifecycleRecord:
        _validate_lookup_source_id(source_id)
        sources, lifecycle, _ = self._read_registry()
        _require_registered_source_id(sources, source_id)
        return lifecycle[source_id]

    def set_lifecycle(self, record: SourceLifecycleRecord) -> None:
        if not isinstance(record, SourceLifecycleRecord):
            raise ValueError("record must be SourceLifecycleRecord")

        sources, lifecycle, freshness = self._read_registry()
        _require_registered_source_id(sources, record.source_id)

        current = lifecycle[record.source_id]
        expected = current.transition_to(
            record.state,
            changed_at=record.changed_at,
            detail=record.detail,
        )
        if expected != record:
            raise ValueError("lifecycle record does not match the validated transition")

        next_lifecycle = dict(lifecycle)
        next_lifecycle[record.source_id] = record
        self._write_registry(sources, next_lifecycle, freshness)

    def get_freshness_policy(self, source_id: str) -> SourceFreshnessPolicy | None:
        _validate_lookup_source_id(source_id)
        sources, _, freshness = self._read_registry()
        _require_registered_source_id(sources, source_id)
        return freshness.get(source_id)

    def set_freshness_policy(self, policy: SourceFreshnessPolicy) -> None:
        if not isinstance(policy, SourceFreshnessPolicy):
            raise ValueError("policy must be SourceFreshnessPolicy")

        sources, lifecycle, freshness = self._read_registry()
        _require_registered_source_id(sources, policy.source_id)
        current = freshness.get(policy.source_id)
        if current is not None and policy.changed_at < current.changed_at:
            raise ValueError("freshness policy changed_at must not move backwards")

        next_freshness = dict(freshness)
        next_freshness[policy.source_id] = policy
        self._write_registry(sources, lifecycle, next_freshness)

    def clear_freshness_policy(self, source_id: str) -> None:
        _validate_lookup_source_id(source_id)
        sources, lifecycle, freshness = self._read_registry()
        _require_registered_source_id(sources, source_id)
        if source_id not in freshness:
            return

        next_freshness = dict(freshness)
        del next_freshness[source_id]
        self._write_registry(sources, lifecycle, next_freshness)

    def _read_registry(
        self,
    ) -> tuple[
        tuple[RegisteredSource, ...],
        dict[str, SourceLifecycleRecord],
        dict[str, SourceFreshnessPolicy],
    ]:
        if not self._path.exists():
            return (), {}, {}
        if not self._path.is_file():
            raise OSError(f"source registry path is not a file: {self._path}")

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise SourceRegistryFormatError("source registry must contain valid JSON") from error

        root = _require_mapping(raw, "source registry root")
        schema = _require_string(root.get("schema"), "source registry schema")
        if schema != _REGISTRY_SCHEMA:
            raise SourceRegistryFormatError(f"unsupported source registry schema: {schema!r}")

        _require_exact_keys(root, _ROOT_KEYS, "source registry root")
        sources = _parse_sources(root["sources"])
        lifecycle = _parse_lifecycle(root["lifecycle"])
        freshness = _parse_freshness_policies(root["freshness_policies"])
        _validate_lifecycle_alignment(sources, lifecycle)
        _validate_freshness_alignment(sources, freshness)
        return sources, lifecycle, freshness

    def _write_registry(
        self,
        sources: Sequence[RegisteredSource],
        lifecycle: Mapping[str, SourceLifecycleRecord],
        freshness: Mapping[str, SourceFreshnessPolicy],
    ) -> None:
        ordered_sources = tuple(sorted(sources, key=lambda source: source.source_id))
        _validate_lifecycle_alignment(ordered_sources, lifecycle)
        _validate_freshness_alignment(ordered_sources, freshness)
        payload = {
            "schema": _REGISTRY_SCHEMA,
            "sources": [_serialize_registered_source(source) for source in ordered_sources],
            "lifecycle": [
                _serialize_lifecycle(lifecycle[source.source_id]) for source in ordered_sources
            ],
            "freshness_policies": [
                _serialize_freshness_policy(freshness[source_id]) for source_id in sorted(freshness)
            ],
        }
        rendered = (
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

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


def _parse_sources(value: object) -> tuple[RegisteredSource, ...]:
    if not isinstance(value, list):
        raise SourceRegistryFormatError("source registry sources must be a JSON array")
    sources = tuple(_parse_registered_source(item, index=index) for index, item in enumerate(value))
    source_ids = tuple(source.source_id for source in sources)
    if len(set(source_ids)) != len(source_ids):
        raise SourceRegistryFormatError("source registry contains duplicate source_id values")
    return tuple(sorted(sources, key=lambda source: source.source_id))


def _parse_lifecycle(value: object) -> dict[str, SourceLifecycleRecord]:
    if not isinstance(value, list):
        raise SourceRegistryFormatError("source registry lifecycle must be a JSON array")
    records = tuple(_parse_lifecycle_record(item, index=index) for index, item in enumerate(value))
    source_ids = tuple(record.source_id for record in records)
    if len(set(source_ids)) != len(source_ids):
        raise SourceRegistryFormatError(
            "source registry contains duplicate lifecycle source_id values"
        )
    return {record.source_id: record for record in records}


def _parse_freshness_policies(value: object) -> dict[str, SourceFreshnessPolicy]:
    if not isinstance(value, list):
        raise SourceRegistryFormatError("source registry freshness_policies must be a JSON array")
    policies = tuple(_parse_freshness_policy(item, index=index) for index, item in enumerate(value))
    source_ids = tuple(policy.source_id for policy in policies)
    if len(set(source_ids)) != len(source_ids):
        raise SourceRegistryFormatError(
            "source registry contains duplicate freshness-policy source_id values"
        )
    return {policy.source_id: policy for policy in policies}


def _validate_lifecycle_alignment(
    sources: Sequence[RegisteredSource],
    lifecycle: Mapping[str, SourceLifecycleRecord],
) -> None:
    source_ids = {source.source_id for source in sources}
    lifecycle_ids = set(lifecycle)
    if source_ids != lifecycle_ids:
        missing = sorted(source_ids - lifecycle_ids)
        unexpected = sorted(lifecycle_ids - source_ids)
        raise SourceRegistryFormatError(
            "source registry lifecycle IDs do not match registered sources; "
            f"missing={missing}, unexpected={unexpected}"
        )


def _validate_freshness_alignment(
    sources: Sequence[RegisteredSource],
    freshness: Mapping[str, SourceFreshnessPolicy],
) -> None:
    source_ids = {source.source_id for source in sources}
    unexpected = sorted(set(freshness) - source_ids)
    if unexpected:
        raise SourceRegistryFormatError(
            "source registry freshness-policy IDs include unregistered sources; "
            f"unexpected={unexpected}"
        )


def _require_registered_source_id(
    sources: Sequence[RegisteredSource],
    source_id: str,
) -> None:
    if not any(source.source_id == source_id for source in sources):
        raise UnknownRegisteredSourceError(f"registered source does not exist: {source_id}")


def _serialize_registered_source(source: RegisteredSource) -> dict[str, object]:
    config = source.config
    if isinstance(config, FileSourceConfig):
        config_payload: dict[str, object] = {
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
        }
    elif isinstance(config, OpcUaSourceConfig):
        config_payload = {
            "endpoint_url": config.endpoint_url,
            "asset_id": config.asset_id,
            "measurement_point_id": config.measurement_point_id,
            "node_mappings": [
                {"channel_id": mapping.channel_id, "node_id": mapping.node_id}
                for mapping in config.node_mappings
            ],
            "timeout_seconds": config.timeout_seconds,
            "semantic_bindings": [
                serialize_channel_semantic_binding(binding) for binding in config.semantic_bindings
            ],
        }
    else:
        raise ValueError("unsupported registered source config")

    return {
        "source_id": source.source_id,
        "name": source.name,
        "source_type": source.source_type.value,
        "registered_at": source.registered_at.isoformat(),
        "config": config_payload,
    }


def _serialize_lifecycle(record: SourceLifecycleRecord) -> dict[str, object]:
    return {
        "source_id": record.source_id,
        "state": record.state.value,
        "changed_at": record.changed_at.isoformat(),
        "detail": record.detail,
    }


def _serialize_freshness_policy(policy: SourceFreshnessPolicy) -> dict[str, object]:
    return {
        "source_id": policy.source_id,
        "max_observation_age_seconds": policy.max_observation_age_seconds,
        "changed_at": policy.changed_at.isoformat(),
    }


def _parse_registered_source(
    value: object,
    *,
    index: int,
) -> RegisteredSource:
    label = f"source registry sources[{index}]"
    source = _require_mapping(value, label)
    _require_exact_keys(source, _SOURCE_KEYS, label)

    source_type_raw = _require_string(source["source_type"], f"{label}.source_type")
    try:
        source_type = SourceType(source_type_raw)
    except ValueError as error:
        raise SourceRegistryFormatError(
            f"{label}.source_type is unsupported: {source_type_raw!r}"
        ) from error
    config_label = f"{label}.config"
    config_raw = _require_mapping(source["config"], config_label)
    registered_at_raw = _require_string(source["registered_at"], f"{label}.registered_at")

    try:
        config: FileSourceConfig | OpcUaSourceConfig
        if source_type == SourceType.FILE:
            config = _parse_file_source_config(config_raw, config_label)
        else:
            config = _parse_opcua_source_config(config_raw, config_label)

        return RegisteredSource(
            source_id=_require_string(source["source_id"], f"{label}.source_id"),
            name=_require_string(source["name"], f"{label}.name"),
            config=config,
            registered_at=datetime.fromisoformat(registered_at_raw),
        )
    except ValueError as error:
        if isinstance(error, SourceRegistryFormatError):
            raise
        raise SourceRegistryFormatError(f"{label} is invalid: {error}") from error


def _parse_file_source_config(
    config: Mapping[str, object],
    label: str,
) -> FileSourceConfig:
    _require_exact_keys(config, _FILE_CONFIG_KEYS, label)
    channels_raw = config["channel_columns"]
    if not isinstance(channels_raw, list) or not all(
        isinstance(channel, str) for channel in channels_raw
    ):
        raise SourceRegistryFormatError(f"{label}.channel_columns must be a string array")

    return FileSourceConfig(
        source_path=_require_string(config["source_path"], f"{label}.source_path"),
        asset_id=_require_string(config["asset_id"], f"{label}.asset_id"),
        channel_columns=tuple(cast(list[str], channels_raw)),
        mode=FileSourceMode(_require_string(config["mode"], f"{label}.mode")),
        measurement_point_id=_optional_string(
            config["measurement_point_id"],
            f"{label}.measurement_point_id",
        ),
        timestamp_column=_optional_string(
            config["timestamp_column"],
            f"{label}.timestamp_column",
        ),
        sampling_rate_hz=_optional_number(
            config["sampling_rate_hz"],
            f"{label}.sampling_rate_hz",
        ),
        sampling_rate_tolerance_ratio=_optional_number(
            config["sampling_rate_tolerance_ratio"],
            f"{label}.sampling_rate_tolerance_ratio",
        ),
        minimum_sample_count=_require_integer(
            config["minimum_sample_count"],
            f"{label}.minimum_sample_count",
        ),
        delimiter=_require_string(config["delimiter"], f"{label}.delimiter"),
    )


def _parse_opcua_source_config(
    config: Mapping[str, object],
    label: str,
) -> OpcUaSourceConfig:
    _require_exact_keys(config, _OPCUA_CONFIG_KEYS, label)
    mappings_raw = config["node_mappings"]
    if not isinstance(mappings_raw, list):
        raise SourceRegistryFormatError(f"{label}.node_mappings must be a JSON array")

    bindings_raw = config["semantic_bindings"]
    if not isinstance(bindings_raw, list):
        raise SourceRegistryFormatError(f"{label}.semantic_bindings must be a JSON array")

    node_mappings: list[OpcUaNodeMapping] = []
    for index, value in enumerate(mappings_raw):
        mapping_label = f"{label}.node_mappings[{index}]"
        mapping = _require_mapping(value, mapping_label)
        _require_exact_keys(mapping, _OPCUA_NODE_MAPPING_KEYS, mapping_label)
        node_mappings.append(
            OpcUaNodeMapping(
                channel_id=_require_string(mapping["channel_id"], f"{mapping_label}.channel_id"),
                node_id=_require_string(mapping["node_id"], f"{mapping_label}.node_id"),
            )
        )

    return OpcUaSourceConfig(
        endpoint_url=_require_string(config["endpoint_url"], f"{label}.endpoint_url"),
        asset_id=_require_string(config["asset_id"], f"{label}.asset_id"),
        measurement_point_id=_optional_string(
            config["measurement_point_id"],
            f"{label}.measurement_point_id",
        ),
        node_mappings=tuple(node_mappings),
        timeout_seconds=_require_number(config["timeout_seconds"], f"{label}.timeout_seconds"),
        semantic_bindings=tuple(parse_channel_semantic_binding(value) for value in bindings_raw),
    )


def _parse_lifecycle_record(value: object, *, index: int) -> SourceLifecycleRecord:
    label = f"source registry lifecycle[{index}]"
    record = _require_mapping(value, label)
    _require_exact_keys(record, _LIFECYCLE_KEYS, label)
    try:
        return SourceLifecycleRecord(
            source_id=_require_string(record["source_id"], f"{label}.source_id"),
            state=SourceLifecycleState(_require_string(record["state"], f"{label}.state")),
            changed_at=datetime.fromisoformat(
                _require_string(record["changed_at"], f"{label}.changed_at")
            ),
            detail=_optional_string(record["detail"], f"{label}.detail"),
        )
    except ValueError as error:
        if isinstance(error, SourceRegistryFormatError):
            raise
        raise SourceRegistryFormatError(f"{label} is invalid: {error}") from error


def _parse_freshness_policy(value: object, *, index: int) -> SourceFreshnessPolicy:
    label = f"source registry freshness_policies[{index}]"
    policy = _require_mapping(value, label)
    _require_exact_keys(policy, _FRESHNESS_POLICY_KEYS, label)
    try:
        return SourceFreshnessPolicy(
            source_id=_require_string(policy["source_id"], f"{label}.source_id"),
            max_observation_age_seconds=_require_number(
                policy["max_observation_age_seconds"],
                f"{label}.max_observation_age_seconds",
            ),
            changed_at=datetime.fromisoformat(
                _require_string(policy["changed_at"], f"{label}.changed_at")
            ),
        )
    except ValueError as error:
        if isinstance(error, SourceRegistryFormatError):
            raise
        raise SourceRegistryFormatError(f"{label} is invalid: {error}") from error


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
    return _require_number(value, label)


def _require_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SourceRegistryFormatError(f"{label} must be a number")
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
