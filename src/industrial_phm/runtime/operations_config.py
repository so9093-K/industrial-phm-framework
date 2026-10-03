"""Versioned non-secret configuration for one local Operations workspace."""

from __future__ import annotations

import json
import os
import tempfile
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite
from numbers import Real
from pathlib import Path
from typing import cast

OPERATIONS_CONFIG_SCHEMA = "industrial-phm-operations-runtime-v2"
_ROOT_KEYS = frozenset({"schema", "collection", "analysis", "ui"})
_COLLECTION_KEYS = frozenset(
    {
        "reconcile_interval_seconds",
        "window_duration_seconds",
        "allowed_lateness_seconds",
    }
)
_ANALYSIS_KEYS = frozenset(
    {
        "poll_interval_seconds",
        "alignment",
        "max_carry_age_seconds",
        "alignment_basis",
    }
)
_UI_KEYS = frozenset({"port"})
_ALIGNMENT_MODES = frozenset({"strict", "bounded-previous"})


class OperationsConfigFormatError(ValueError):
    """Raised when an Operations workspace configuration is unsupported or invalid."""


@dataclass(frozen=True, slots=True)
class OperationsCollectionConfig:
    """User-facing collection/window policy owned by the workspace runtime."""

    reconcile_interval_seconds: float = 0.5
    window_duration_seconds: float = 60.0
    allowed_lateness_seconds: float = 5.0

    def __post_init__(self) -> None:
        _validate_positive_finite(
            self.reconcile_interval_seconds,
            "collection.reconcile_interval_seconds",
        )
        _validate_positive_finite(
            self.window_duration_seconds,
            "collection.window_duration_seconds",
        )
        _validate_non_negative_finite(
            self.allowed_lateness_seconds,
            "collection.allowed_lateness_seconds",
        )


@dataclass(frozen=True, slots=True)
class OperationsAnalysisConfig:
    """User-facing live-analysis policy owned by the workspace runtime."""

    poll_interval_seconds: float = 5.0
    alignment: str = "strict"
    max_carry_age_seconds: float | None = None
    alignment_basis: str | None = None

    def __post_init__(self) -> None:
        _validate_positive_finite(self.poll_interval_seconds, "analysis.poll_interval_seconds")
        if self.alignment not in _ALIGNMENT_MODES:
            raise ValueError(f"analysis.alignment must be one of {sorted(_ALIGNMENT_MODES)!r}")
        if self.alignment == "strict":
            if self.max_carry_age_seconds is not None or self.alignment_basis is not None:
                raise ValueError(
                    "strict analysis alignment takes no max_carry_age_seconds or alignment_basis"
                )
            return
        if self.max_carry_age_seconds is None:
            raise ValueError("bounded-previous analysis alignment requires max_carry_age_seconds")
        _validate_positive_finite(
            self.max_carry_age_seconds,
            "analysis.max_carry_age_seconds",
        )
        if not isinstance(self.alignment_basis, str) or not self.alignment_basis.strip():
            raise ValueError(
                "bounded-previous analysis alignment requires a non-empty alignment_basis"
            )
        object.__setattr__(self, "alignment_basis", self.alignment_basis.strip())


@dataclass(frozen=True, slots=True)
class OperationsUiConfig:
    """Local-only Operations web application transport policy."""

    port: int = 2718

    def __post_init__(self) -> None:
        if isinstance(self.port, bool) or not isinstance(self.port, int):
            raise ValueError("ui.port must be an integer")
        if not 1 <= self.port <= 65535:
            raise ValueError("ui.port must be between 1 and 65535")


@dataclass(frozen=True, slots=True)
class OperationsRuntimeConfig:
    """Versioned non-secret policy for one local Operations workspace."""

    schema: str = OPERATIONS_CONFIG_SCHEMA
    collection: OperationsCollectionConfig = field(default_factory=OperationsCollectionConfig)
    analysis: OperationsAnalysisConfig = field(default_factory=OperationsAnalysisConfig)
    ui: OperationsUiConfig = field(default_factory=OperationsUiConfig)

    def __post_init__(self) -> None:
        if self.schema != OPERATIONS_CONFIG_SCHEMA:
            raise ValueError(f"unsupported Operations config schema: {self.schema!r}")
        if not isinstance(self.collection, OperationsCollectionConfig):
            raise ValueError("collection must be OperationsCollectionConfig")
        if not isinstance(self.analysis, OperationsAnalysisConfig):
            raise ValueError("analysis must be OperationsAnalysisConfig")
        if not isinstance(self.ui, OperationsUiConfig):
            raise ValueError("ui must be OperationsUiConfig")


def load_operations_runtime_config(path: Path) -> OperationsRuntimeConfig:
    """Load one current Operations workspace configuration."""
    if not path.is_file():
        raise OSError(f"Operations config does not exist: {path}")

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise OperationsConfigFormatError("Operations config must contain valid TOML") from error

    root = _require_mapping(raw, "Operations config root")
    if "schema" not in root:
        raise OperationsConfigFormatError("Operations config requires schema")

    schema = root["schema"]
    if not isinstance(schema, str):
        raise OperationsConfigFormatError("Operations config schema must be a string")
    if schema != OPERATIONS_CONFIG_SCHEMA:
        raise OperationsConfigFormatError(f"unsupported Operations config schema: {schema!r}")
    _reject_unknown_keys(root, _ROOT_KEYS, "Operations config")

    collection = _load_collection_config(root.get("collection"))
    analysis = _load_analysis_config(root.get("analysis"))
    ui = _load_ui_config(root.get("ui"))
    return OperationsRuntimeConfig(
        collection=collection,
        analysis=analysis,
        ui=ui,
    )


def write_operations_runtime_config(
    path: Path,
    config: OperationsRuntimeConfig | None = None,
) -> None:
    """Atomically persist the current Operations workspace config."""
    effective_config = OperationsRuntimeConfig() if config is None else config
    if not isinstance(effective_config, OperationsRuntimeConfig):
        raise ValueError("config must be OperationsRuntimeConfig")

    collection = effective_config.collection
    analysis = effective_config.analysis
    ui = effective_config.ui
    lines = [
        f"schema = {_toml_string(effective_config.schema)}",
        "",
        "[collection]",
        f"reconcile_interval_seconds = {float(collection.reconcile_interval_seconds)!r}",
        f"window_duration_seconds = {float(collection.window_duration_seconds)!r}",
        f"allowed_lateness_seconds = {float(collection.allowed_lateness_seconds)!r}",
        "",
        "[analysis]",
        f"poll_interval_seconds = {float(analysis.poll_interval_seconds)!r}",
        f"alignment = {_toml_string(analysis.alignment)}",
    ]
    if analysis.max_carry_age_seconds is not None:
        lines.append(f"max_carry_age_seconds = {float(analysis.max_carry_age_seconds)!r}")
    if analysis.alignment_basis is not None:
        lines.append(f"alignment_basis = {_toml_string(analysis.alignment_basis)}")
    lines.extend(("", "[ui]", f"port = {ui.port}"))
    rendered = "\n".join((*lines, ""))

    path.parent.mkdir(parents=True, exist_ok=True)
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


def _load_collection_config(value: object) -> OperationsCollectionConfig:
    if value is None:
        return OperationsCollectionConfig()
    table = _require_mapping(value, "collection")
    _reject_unknown_keys(table, _COLLECTION_KEYS, "collection")
    return OperationsCollectionConfig(
        reconcile_interval_seconds=_optional_float(
            table,
            "reconcile_interval_seconds",
            0.5,
        ),
        window_duration_seconds=_optional_float(
            table,
            "window_duration_seconds",
            60.0,
        ),
        allowed_lateness_seconds=_optional_float(
            table,
            "allowed_lateness_seconds",
            5.0,
        ),
    )


def _load_analysis_config(value: object) -> OperationsAnalysisConfig:
    if value is None:
        return OperationsAnalysisConfig()
    table = _require_mapping(value, "analysis")
    _reject_unknown_keys(table, _ANALYSIS_KEYS, "analysis")

    alignment = table.get("alignment", "strict")
    if not isinstance(alignment, str):
        raise OperationsConfigFormatError("analysis.alignment must be a string")
    basis = table.get("alignment_basis")
    if basis is not None and not isinstance(basis, str):
        raise OperationsConfigFormatError("analysis.alignment_basis must be a string")

    return OperationsAnalysisConfig(
        poll_interval_seconds=_optional_float(table, "poll_interval_seconds", 5.0),
        alignment=alignment,
        max_carry_age_seconds=_optional_nullable_float(
            table,
            "max_carry_age_seconds",
        ),
        alignment_basis=basis,
    )


def _load_ui_config(value: object) -> OperationsUiConfig:
    if value is None:
        return OperationsUiConfig()
    table = _require_mapping(value, "ui")
    _reject_unknown_keys(table, _UI_KEYS, "ui")
    port = table.get("port", 2718)
    if isinstance(port, bool) or not isinstance(port, int):
        raise OperationsConfigFormatError("ui.port must be an integer")
    return OperationsUiConfig(port=port)


def _optional_float(
    table: Mapping[str, object],
    key: str,
    default: float,
) -> float:
    if key not in table:
        return default
    return _require_float(table[key], key)


def _optional_nullable_float(
    table: Mapping[str, object],
    key: str,
) -> float | None:
    if key not in table:
        return None
    return _require_float(table[key], key)


def _require_float(value: object, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise OperationsConfigFormatError(f"{key} must be a number")
    number = float(value)
    if not isfinite(number):
        raise OperationsConfigFormatError(f"{key} must be finite")
    return number


def _validate_positive_finite(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite positive number")
    number = float(value)
    if not isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a finite positive number")


def _validate_non_negative_finite(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite non-negative number")
    number = float(value)
    if not isfinite(number) or number < 0:
        raise ValueError(f"{name} must be a finite non-negative number")


def _require_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise OperationsConfigFormatError(f"{name} must be a TOML table")
    return cast(Mapping[str, object], value)


def _reject_unknown_keys(
    table: Mapping[str, object],
    allowed: frozenset[str],
    name: str,
) -> None:
    extra = sorted(frozenset(table) - allowed)
    if extra:
        raise OperationsConfigFormatError(f"{name} contains unknown keys: {extra!r}")


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)
