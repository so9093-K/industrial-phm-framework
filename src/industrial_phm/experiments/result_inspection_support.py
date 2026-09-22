"""Shared read-model contracts and validation helpers for result inspection."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from industrial_phm.experiments.config import ExperimentConfig

_FULL_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")


class ExperimentResultInspectionError(ValueError):
    """Raised when a result cannot be inspected as a supported evidence schema."""


InspectionFactValue = str | int | float


@dataclass(frozen=True, slots=True)
class InspectionFact:
    """One display-independent fact resolved from evidence and packaged contracts."""

    label: str
    value: InspectionFactValue


@dataclass(frozen=True, slots=True)
class InspectionStage:
    """One ordered pipeline stage in an experiment inspection read model."""

    name: str
    status: str
    facts: tuple[InspectionFact, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExperimentInspection:
    """Presentation-neutral read model for one validated experiment result."""

    schema_id: str
    status: str
    stages: tuple[InspectionStage, ...]


def _capability_stage(
    available: Sequence[str],
    unsupported: Sequence[str],
) -> InspectionStage:
    return InspectionStage(
        "Capability",
        "completed",
        (
            InspectionFact("Available", ", ".join(available)),
            InspectionFact("Unsupported", ", ".join(unsupported)),
        ),
    )


def _provenance_stage(
    config: ExperimentConfig,
    declared_revision: str,
    path: Path,
    *,
    evidence_facts: tuple[InspectionFact, ...] = (),
) -> InspectionStage:
    return InspectionStage(
        "Provenance",
        "completed",
        (
            InspectionFact("Experiment", config.experiment_id),
            InspectionFact("Split", f"{config.split_id} / {config.fold_id}"),
            *evidence_facts,
            InspectionFact("Declared code revision", declared_revision),
            InspectionFact("Checkout attestation", "unavailable"),
            InspectionFact("Artifact", str(path)),
        ),
    )


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ExperimentResultInspectionError(f"{context} must be a JSON object")
    for key in value:
        if not isinstance(key, str):
            raise ExperimentResultInspectionError(f"{context} keys must be strings")
    return cast(Mapping[str, object], value)


def _mapping_field(values: Mapping[str, object], key: str, context: str) -> Mapping[str, object]:
    if key not in values:
        raise ExperimentResultInspectionError(f"{context}.{key} is required")
    return _mapping(values[key], f"{context}.{key}")


def _sequence(values: Mapping[str, object], key: str, context: str) -> Sequence[object]:
    value = values.get(key)
    if not isinstance(value, list):
        raise ExperimentResultInspectionError(f"{context}.{key} must be a JSON array")
    return cast(Sequence[object], value)


def _text(values: Mapping[str, object], key: str, context: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise ExperimentResultInspectionError(f"{context}.{key} must be a non-empty string")
    return value


def _text_sequence(values: Mapping[str, object], key: str, context: str) -> tuple[str, ...]:
    raw = _sequence(values, key, context)
    result: list[str] = []
    for index, value in enumerate(raw):
        if not isinstance(value, str) or not value:
            raise ExperimentResultInspectionError(
                f"{context}.{key}[{index}] must be a non-empty string"
            )
        result.append(value)
    return tuple(result)


def _integer(values: Mapping[str, object], key: str, context: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExperimentResultInspectionError(f"{context}.{key} must be an integer")
    return value


def _positive_int(values: Mapping[str, object], key: str, context: str) -> int:
    value = _integer(values, key, context)
    if value <= 0:
        raise ExperimentResultInspectionError(f"{context}.{key} must be positive")
    return value


def _boolean(values: Mapping[str, object], key: str, context: str) -> bool:
    value = values.get(key)
    if not isinstance(value, bool):
        raise ExperimentResultInspectionError(f"{context}.{key} must be a boolean")
    return value


def _number_sequence(
    values: Mapping[str, object],
    key: str,
    context: str,
) -> tuple[float, ...]:
    raw = _sequence(values, key, context)
    result: list[float] = []
    for index, value in enumerate(raw):
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ExperimentResultInspectionError(f"{context}.{key}[{index}] must be a number")
        number = float(value)
        if not math.isfinite(number):
            raise ExperimentResultInspectionError(f"{context}.{key}[{index}] must be finite")
        result.append(number)
    return tuple(result)


def _number(values: Mapping[str, object], key: str, context: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ExperimentResultInspectionError(f"{context}.{key} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ExperimentResultInspectionError(f"{context}.{key} must be finite")
    return result


def _revision(values: Mapping[str, object], key: str, context: str) -> str:
    value = _text(values, key, context)
    if _FULL_GIT_REVISION.fullmatch(value) is None:
        raise ExperimentResultInspectionError(
            f"{context}.{key} must be a full lowercase 40-character Git SHA"
        )
    return value


def _expect_close(actual: float, expected: float, field_name: str) -> None:
    if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-15):
        raise ExperimentResultInspectionError(
            f"{field_name} does not match the artifact aggregation; "
            f"expected {expected!r}, got {actual!r}"
        )


def _expect_equal(actual: object, expected: object, field_name: str) -> None:
    if actual != expected:
        raise ExperimentResultInspectionError(
            f"{field_name} does not match the packaged protocol; "
            f"expected {expected!r}, got {actual!r}"
        )
