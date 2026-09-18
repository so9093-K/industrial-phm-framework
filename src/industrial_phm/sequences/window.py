"""Dataset-neutral construction and lineage contracts for feature-sequence windows."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise


class SequenceWindowError(ValueError):
    """Raised when observations cannot form valid sequence windows."""


class SequenceAlignment(StrEnum):
    """Supported mapping from one sequence window to its source observation identity."""

    RIGHT_EDGE = "right-edge"


@dataclass(frozen=True, slots=True)
class SequenceWindowSpec:
    """Mechanical construction settings shared by one collection of windows."""

    length: int
    stride: int
    alignment: SequenceAlignment = SequenceAlignment.RIGHT_EDGE

    def __post_init__(self) -> None:
        _validate_positive_integer(self.length, "length")
        _validate_positive_integer(self.stride, "stride")
        if not isinstance(self.alignment, SequenceAlignment):
            raise SequenceWindowError("alignment must be a supported SequenceAlignment")


@dataclass(frozen=True, slots=True)
class SequenceFeatureObservation:
    """One ordered feature observation supplied to sequence construction."""

    sequence_id: str
    asset_id: str
    partition_id: str
    source_observation_id: str
    sequence_position: int
    feature_values: Sequence[float]

    def __post_init__(self) -> None:
        for field_name in (
            "sequence_id",
            "asset_id",
            "partition_id",
            "source_observation_id",
        ):
            _validate_text(getattr(self, field_name), field_name)
        if (
            isinstance(self.sequence_position, bool)
            or not isinstance(self.sequence_position, int)
            or self.sequence_position < 0
        ):
            raise SequenceWindowError("sequence_position must be a non-negative integer")

        feature_values = _finite_values(self.feature_values, "feature_values")
        if not feature_values:
            raise SequenceWindowError("feature_values must contain at least one value")
        object.__setattr__(self, "feature_values", feature_values)


@dataclass(frozen=True, slots=True)
class SequenceWindow:
    """One immutable feature window with complete source-row lineage."""

    spec: SequenceWindowSpec
    sequence_id: str
    asset_id: str
    partition_id: str
    feature_set_id: str
    feature_names: Sequence[str]
    values: Sequence[Sequence[float]]
    source_observation_ids: Sequence[str]
    source_positions: Sequence[int]
    aligned_source_observation_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.spec, SequenceWindowSpec):
            raise SequenceWindowError("spec must be a SequenceWindowSpec")
        for field_name in (
            "sequence_id",
            "asset_id",
            "partition_id",
            "feature_set_id",
            "aligned_source_observation_id",
        ):
            _validate_text(getattr(self, field_name), field_name)

        feature_names = _validated_names(self.feature_names, "feature_names")
        values = _validated_rows(self.values, width=len(feature_names), context="sequence window")
        source_observation_ids = tuple(self.source_observation_ids)
        if len(source_observation_ids) != len(set(source_observation_ids)):
            raise SequenceWindowError("source_observation_ids must be unique within a window")
        for value in source_observation_ids:
            _validate_text(value, "source_observation_ids")
        source_positions = tuple(self.source_positions)
        for position in source_positions:
            if isinstance(position, bool) or not isinstance(position, int) or position < 0:
                raise SequenceWindowError("source_positions must contain non-negative integers")

        expected_length = self.spec.length
        if not (
            len(values) == len(source_observation_ids) == len(source_positions) == expected_length
        ):
            raise SequenceWindowError(
                "values, source_observation_ids, and source_positions must match "
                f"window length {expected_length}"
            )
        if any(current != previous + 1 for previous, current in pairwise(source_positions)):
            raise SequenceWindowError("source_positions must form a contiguous sequence")
        if (
            self.spec.alignment is SequenceAlignment.RIGHT_EDGE
            and self.aligned_source_observation_id != source_observation_ids[-1]
        ):
            raise SequenceWindowError(
                "right-edge alignment must use the final source observation identity"
            )

        object.__setattr__(self, "feature_names", feature_names)
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "source_observation_ids", source_observation_ids)
        object.__setattr__(self, "source_positions", source_positions)

    @property
    def window_id(self) -> str:
        """Return a stable identity derived from sequence and source positions."""
        return f"{self.sequence_id}:window-{self.source_positions[0]}-{self.source_positions[-1]}"

    @property
    def start_source_observation_id(self) -> str:
        """Return the first source observation identity in the window."""
        return self.source_observation_ids[0]

    @property
    def end_source_observation_id(self) -> str:
        """Return the final source observation identity in the window."""
        return self.source_observation_ids[-1]

    @property
    def feature_width(self) -> int:
        """Return the ordered feature width of every row."""
        return len(self.feature_names)


@dataclass(frozen=True, slots=True)
class SequenceConstruction:
    """Constructed windows and population-unit provenance for one input collection."""

    spec: SequenceWindowSpec
    feature_set_id: str
    feature_names: Sequence[str]
    source_observation_count: int
    sequence_count: int
    dropped_prefix_observation_count: int
    windows: Sequence[SequenceWindow]

    def __post_init__(self) -> None:
        if not isinstance(self.spec, SequenceWindowSpec):
            raise SequenceWindowError("spec must be a SequenceWindowSpec")
        _validate_text(self.feature_set_id, "feature_set_id")
        feature_names = _validated_names(self.feature_names, "feature_names")
        _validate_positive_integer(self.source_observation_count, "source_observation_count")
        _validate_positive_integer(self.sequence_count, "sequence_count")
        if self.sequence_count > self.source_observation_count:
            raise SequenceWindowError("sequence_count cannot exceed source_observation_count")
        minimum_source_count = self.sequence_count * self.spec.length
        if self.source_observation_count < minimum_source_count:
            raise SequenceWindowError(
                "every sequence must contain enough source observations for one complete window"
            )
        if (
            isinstance(self.dropped_prefix_observation_count, bool)
            or not isinstance(self.dropped_prefix_observation_count, int)
            or not 0 <= self.dropped_prefix_observation_count <= self.source_observation_count
        ):
            raise SequenceWindowError(
                "dropped_prefix_observation_count must fall inside the source population"
            )
        expected_dropped_prefix_count = self.sequence_count * (self.spec.length - 1)
        if self.dropped_prefix_observation_count != expected_dropped_prefix_count:
            raise SequenceWindowError(
                "dropped_prefix_observation_count must preserve the right-edge alignment "
                "prefix for every sequence"
            )

        windows = tuple(self.windows)
        if not windows:
            raise SequenceWindowError("sequence construction must generate at least one window")
        if len(windows) > self.source_observation_count:
            raise SequenceWindowError(
                "window count cannot exceed source_observation_count under unique alignment"
            )
        unaligned_count = self.source_observation_count - len(windows)
        if self.dropped_prefix_observation_count > unaligned_count:
            raise SequenceWindowError(
                "dropped_prefix_observation_count cannot exceed unaligned source observations"
            )
        for window in windows:
            if not isinstance(window, SequenceWindow):
                raise SequenceWindowError("windows must contain only SequenceWindow values")
            if window.spec != self.spec:
                raise SequenceWindowError("window spec does not match sequence construction")
            if window.feature_set_id != self.feature_set_id:
                raise SequenceWindowError(
                    "window feature_set_id does not match sequence construction"
                )
            if tuple(window.feature_names) != feature_names:
                raise SequenceWindowError(
                    "window feature schema does not match sequence construction"
                )
        window_identities = tuple(
            (window.sequence_id, window.source_positions[0], window.source_positions[-1])
            for window in windows
        )
        if len(window_identities) != len(set(window_identities)):
            raise SequenceWindowError("constructed window identities must be unique")
        aligned_ids = tuple(window.aligned_source_observation_id for window in windows)
        if len(aligned_ids) != len(set(aligned_ids)):
            raise SequenceWindowError(
                "each constructed window must align to a unique source observation"
            )

        object.__setattr__(self, "feature_names", feature_names)
        object.__setattr__(self, "windows", windows)

    @property
    def window_count(self) -> int:
        """Return the model-input population after sequence construction."""
        return len(self.windows)

    @property
    def unaligned_source_observation_count(self) -> int:
        """Return source observations without an aligned output under this spec."""
        return self.source_observation_count - self.window_count


def construct_sequence_windows(
    observations: Iterable[SequenceFeatureObservation],
    *,
    feature_set_id: str,
    feature_names: Sequence[str],
    spec: SequenceWindowSpec,
) -> SequenceConstruction:
    """Construct windows without crossing declared sequence or partition boundaries."""
    if not isinstance(spec, SequenceWindowSpec):
        raise SequenceWindowError("spec must be a SequenceWindowSpec")
    _validate_text(feature_set_id, "feature_set_id")
    validated_feature_names = _validated_names(feature_names, "feature_names")
    materialized = tuple(observations)
    if not materialized:
        raise SequenceWindowError("sequence construction requires source observations")
    if not all(isinstance(observation, SequenceFeatureObservation) for observation in materialized):
        raise SequenceWindowError(
            "observations must contain only SequenceFeatureObservation values"
        )

    observation_ids = tuple(observation.source_observation_id for observation in materialized)
    if len(observation_ids) != len(set(observation_ids)):
        raise SequenceWindowError("source observation identities must be unique")
    for index, observation in enumerate(materialized):
        if len(observation.feature_values) != len(validated_feature_names):
            raise SequenceWindowError(
                f"source observation {index} feature width must be "
                f"{len(validated_feature_names)}, got {len(observation.feature_values)}"
            )

    groups = _contiguous_sequence_groups(materialized)
    windows: list[SequenceWindow] = []
    dropped_prefix_count = 0
    for group in groups:
        if len(group) < spec.length:
            raise SequenceWindowError(
                f"sequence {group[0].sequence_id!r} requires at least {spec.length} "
                f"observations, got {len(group)}"
            )
        dropped_prefix_count += spec.length - 1
        for start in range(0, len(group) - spec.length + 1, spec.stride):
            source = group[start : start + spec.length]
            windows.append(
                SequenceWindow(
                    spec=spec,
                    sequence_id=source[0].sequence_id,
                    asset_id=source[0].asset_id,
                    partition_id=source[0].partition_id,
                    feature_set_id=feature_set_id,
                    feature_names=validated_feature_names,
                    values=tuple(observation.feature_values for observation in source),
                    source_observation_ids=tuple(
                        observation.source_observation_id for observation in source
                    ),
                    source_positions=tuple(observation.sequence_position for observation in source),
                    aligned_source_observation_id=source[-1].source_observation_id,
                )
            )

    return SequenceConstruction(
        spec=spec,
        feature_set_id=feature_set_id,
        feature_names=validated_feature_names,
        source_observation_count=len(materialized),
        sequence_count=len(groups),
        dropped_prefix_observation_count=dropped_prefix_count,
        windows=windows,
    )


def _contiguous_sequence_groups(
    observations: Sequence[SequenceFeatureObservation],
) -> tuple[tuple[SequenceFeatureObservation, ...], ...]:
    groups: list[tuple[SequenceFeatureObservation, ...]] = []
    current: list[SequenceFeatureObservation] = []
    seen_sequence_ids: set[str] = set()

    for observation in observations:
        if not current or observation.sequence_id == current[0].sequence_id:
            current.append(observation)
            continue
        groups.append(_validated_sequence_group(current))
        seen_sequence_ids.add(current[0].sequence_id)
        if observation.sequence_id in seen_sequence_ids:
            raise SequenceWindowError(
                f"sequence {observation.sequence_id!r} must occupy one contiguous input block"
            )
        current = [observation]

    if current:
        if current[0].sequence_id in seen_sequence_ids:
            raise SequenceWindowError(
                f"sequence {current[0].sequence_id!r} must occupy one contiguous input block"
            )
        groups.append(_validated_sequence_group(current))
    return tuple(groups)


def _validated_sequence_group(
    observations: Sequence[SequenceFeatureObservation],
) -> tuple[SequenceFeatureObservation, ...]:
    first = observations[0]
    for observation in observations[1:]:
        if observation.asset_id != first.asset_id:
            raise SequenceWindowError(
                f"sequence {first.sequence_id!r} cannot cross asset boundaries"
            )
        if observation.partition_id != first.partition_id:
            raise SequenceWindowError(
                f"sequence {first.sequence_id!r} cannot cross partition boundaries"
            )
    positions = tuple(observation.sequence_position for observation in observations)
    if any(current != previous + 1 for previous, current in pairwise(positions)):
        raise SequenceWindowError(
            f"sequence {first.sequence_id!r} positions must be contiguous and ordered"
        )
    return tuple(observations)


def _validated_names(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    result = tuple(values)
    if not result:
        raise SequenceWindowError(f"{field_name} must contain at least one value")
    for value in result:
        _validate_text(value, field_name)
    if len(result) != len(set(result)):
        raise SequenceWindowError(f"{field_name} must contain unique values")
    return result


def _validated_rows(
    rows: Sequence[Sequence[float]],
    *,
    width: int,
    context: str,
) -> tuple[tuple[float, ...], ...]:
    result = tuple(_finite_values(row, f"{context} row {index}") for index, row in enumerate(rows))
    for index, row in enumerate(result):
        if len(row) != width:
            raise SequenceWindowError(
                f"{context} row {index} width must be {width}, got {len(row)}"
            )
    return result


def _finite_values(values: Sequence[float], field_name: str) -> tuple[float, ...]:
    result: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise SequenceWindowError(f"{field_name} must contain only numerical values")
        number = float(value)
        if not math.isfinite(number):
            raise SequenceWindowError(f"{field_name} must contain only finite values")
        result.append(number)
    return tuple(result)


def _validate_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SequenceWindowError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise SequenceWindowError(f"{field_name} must not contain surrounding whitespace")


def _validate_positive_integer(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SequenceWindowError(f"{field_name} must be a positive integer")
