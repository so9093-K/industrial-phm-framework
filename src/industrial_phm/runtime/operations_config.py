"""Versioned non-secret configuration for one local Operations workspace."""

from __future__ import annotations

import os
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, cast

OPERATIONS_CONFIG_SCHEMA = "industrial-phm-operations-runtime-v1"
_CONFIG_KEYS = frozenset({"schema"})


class OperationsConfigFormatError(ValueError):
    """Raised when an Operations workspace configuration is unsupported or invalid."""


@dataclass(frozen=True, slots=True)
class OperationsRuntimeConfig:
    """Minimal versioned marker for an initialized local Operations workspace."""

    schema: str = OPERATIONS_CONFIG_SCHEMA

    def __post_init__(self) -> None:
        if self.schema != OPERATIONS_CONFIG_SCHEMA:
            raise ValueError(f"unsupported Operations config schema: {self.schema!r}")


def load_operations_runtime_config(path: Path) -> OperationsRuntimeConfig:
    """Load and validate a workspace config without inferring missing settings."""
    if not path.is_file():
        raise OSError(f"Operations config does not exist: {path}")

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise OperationsConfigFormatError("Operations config must contain valid TOML") from error

    root = _require_mapping(raw)
    actual_keys = frozenset(root)
    if actual_keys != _CONFIG_KEYS:
        missing = sorted(_CONFIG_KEYS - actual_keys)
        extra = sorted(actual_keys - _CONFIG_KEYS)
        raise OperationsConfigFormatError(
            f"Operations config keys must be exactly {sorted(_CONFIG_KEYS)!r}; "
            f"missing={missing!r} extra={extra!r}"
        )

    schema = root["schema"]
    if not isinstance(schema, str):
        raise OperationsConfigFormatError("Operations config schema must be a string")
    if schema != OPERATIONS_CONFIG_SCHEMA:
        raise OperationsConfigFormatError(f"unsupported Operations config schema: {schema!r}")
    return OperationsRuntimeConfig(schema=schema)


def write_operations_runtime_config(
    path: Path,
    config: OperationsRuntimeConfig = OperationsRuntimeConfig(),
) -> None:
    """Atomically persist the current Operations workspace config."""
    if not isinstance(config, OperationsRuntimeConfig):
        raise ValueError("config must be OperationsRuntimeConfig")

    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = f'schema = "{config.schema}"\n'
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _require_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise OperationsConfigFormatError("Operations config root must be a TOML table")
    return cast(Mapping[str, object], value)
