"""Dataset-neutral experiment configuration contract."""

from __future__ import annotations

import math
import tomllib
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import cast

EXPERIMENT_CONFIG_SCHEMA_ID = "experiment-config-v1"
ExperimentParameter = str | int | float | bool


class ExperimentConfigError(ValueError):
    """Raised when an experiment configuration violates the v1 contract."""


class FitPartition(StrEnum):
    TRAIN = "train"


class ReferenceStrategy(StrEnum):
    ALL_TRAIN_OBSERVATIONS = "all-train-observations"
    TRAIN_BEARING_EARLY_THIRD = "train-bearing-early-third-v1"


class ScalingStrategy(StrEnum):
    IDENTITY = "identity"
    ROBUST = "robust"


class ModelFamily(StrEnum):
    ISOLATION_FOREST = "isolation-forest"


@dataclass(frozen=True, slots=True)
class ExperimentContext:
    """Dataset-owned split and feature inputs available to a candidate."""

    dataset_id: str
    split_id: str
    fold_ids: Collection[str]
    feature_set_id: str
    feature_names: Collection[str]
    supported_sampling_policy_ids: Collection[str]

    def __post_init__(self) -> None:
        _validate_text(self.dataset_id, "dataset_id")
        _validate_text(self.split_id, "split_id")
        _validate_text(self.feature_set_id, "feature_set_id")
        object.__setattr__(self, "fold_ids", _validated_names(self.fold_ids, "fold_ids"))
        object.__setattr__(
            self,
            "feature_names",
            frozenset(_validated_names(self.feature_names, "feature_names")),
        )
        object.__setattr__(
            self,
            "supported_sampling_policy_ids",
            frozenset(
                _validated_names(
                    self.supported_sampling_policy_ids,
                    "supported_sampling_policy_ids",
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    """One fully resolved, reproducible model-development candidate."""

    experiment_id: str
    dataset_id: str
    split_id: str
    fold_id: str
    fit_partition: FitPartition
    feature_set_id: str
    selected_features: Sequence[str]
    reference_strategy: ReferenceStrategy
    sampling_policy_id: str
    scaling_strategy: ScalingStrategy
    model_family: ModelFamily
    model_parameters: Mapping[str, ExperimentParameter]
    random_seed: int

    def __post_init__(self) -> None:
        for field_name in (
            "experiment_id",
            "dataset_id",
            "split_id",
            "fold_id",
            "feature_set_id",
            "sampling_policy_id",
        ):
            _validate_text(getattr(self, field_name), field_name)

        selected_features = _validated_names(self.selected_features, "selected_features")
        object.__setattr__(self, "selected_features", selected_features)

        enum_fields: tuple[tuple[str, object, type[StrEnum]], ...] = (
            ("fit_partition", self.fit_partition, FitPartition),
            ("reference_strategy", self.reference_strategy, ReferenceStrategy),
            ("scaling_strategy", self.scaling_strategy, ScalingStrategy),
            ("model_family", self.model_family, ModelFamily),
        )
        for field_name, value, enum_type in enum_fields:
            if not isinstance(value, enum_type):
                raise ExperimentConfigError(
                    f"{field_name} must be a supported {enum_type.__name__}"
                )

        if isinstance(self.random_seed, bool) or not isinstance(self.random_seed, int):
            raise ExperimentConfigError("random_seed must be an integer")
        if self.random_seed < 0:
            raise ExperimentConfigError("random_seed must be non-negative")

        parameters = dict(self.model_parameters)
        if not parameters:
            raise ExperimentConfigError("model_parameters must contain at least one parameter")
        for name, value in parameters.items():
            _validate_text(name, "model parameter name")
            if not isinstance(value, str | int | float | bool):
                raise ExperimentConfigError(f"model parameter {name!r} must be a TOML scalar")
            if isinstance(value, float) and not math.isfinite(value):
                raise ExperimentConfigError(f"model parameter {name!r} must be finite")
        object.__setattr__(self, "model_parameters", MappingProxyType(parameters))

    def validate_against(self, context: ExperimentContext) -> None:
        """Resolve identifiers against dataset-owned split and feature contracts."""
        expected_ids = (
            ("dataset_id", self.dataset_id, context.dataset_id),
            ("split_id", self.split_id, context.split_id),
            ("feature_set_id", self.feature_set_id, context.feature_set_id),
        )
        for field_name, value, expected in expected_ids:
            if value != expected:
                raise ExperimentConfigError(
                    f"unknown {field_name} {value!r}; expected {expected!r}"
                )
        if self.fold_id not in context.fold_ids:
            raise ExperimentConfigError(f"unknown fold_id {self.fold_id!r}")
        if self.sampling_policy_id not in context.supported_sampling_policy_ids:
            raise ExperimentConfigError(f"unknown sampling_policy_id {self.sampling_policy_id!r}")
        unknown_features = sorted(set(self.selected_features) - set(context.feature_names))
        if unknown_features:
            raise ExperimentConfigError(f"unknown selected feature(s): {unknown_features}")


_EXPERIMENT_FIELDS = {
    "experiment_id",
    "dataset_id",
    "split_id",
    "fold_id",
    "fit_partition",
    "feature_set_id",
    "selected_features",
    "reference_strategy",
    "sampling_policy_id",
    "scaling_strategy",
    "model_family",
    "model_parameters",
    "random_seed",
}


def load_experiment_configs(
    content: str,
    *,
    context: ExperimentContext | None = None,
) -> tuple[ExperimentConfig, ...]:
    """Parse and validate one versioned TOML collection of resolved candidates."""
    try:
        raw = tomllib.loads(content)
    except tomllib.TOMLDecodeError as error:
        raise ExperimentConfigError(f"invalid experiment config TOML: {error}") from error

    _require_exact_fields(raw, {"schema_id", "experiment"}, "experiment config root")
    schema_id = _required(raw, "schema_id", str)
    if schema_id != EXPERIMENT_CONFIG_SCHEMA_ID:
        raise ExperimentConfigError(
            f"unsupported experiment config schema_id {schema_id!r}; "
            f"expected {EXPERIMENT_CONFIG_SCHEMA_ID!r}"
        )

    raw_experiments = _required(raw, "experiment", list)
    if not raw_experiments:
        raise ExperimentConfigError("experiment config must contain at least one candidate")

    configs: list[ExperimentConfig] = []
    for raw_experiment in raw_experiments:
        if not isinstance(raw_experiment, dict):
            raise ExperimentConfigError("experiment entries must be TOML tables")
        configs.append(_parse_experiment(cast(Mapping[str, object], raw_experiment)))

    experiment_ids = tuple(config.experiment_id for config in configs)
    if len(experiment_ids) != len(set(experiment_ids)):
        raise ExperimentConfigError("experiment_id values must be unique within a config file")
    if context is not None:
        for config in configs:
            config.validate_against(context)
    return tuple(configs)


def _parse_experiment(values: Mapping[str, object]) -> ExperimentConfig:
    _require_exact_fields(values, _EXPERIMENT_FIELDS, "experiment")
    selected_features = _required(values, "selected_features", list)
    parameters = _required(values, "model_parameters", dict)
    random_seed = _required(values, "random_seed", int)
    if isinstance(random_seed, bool):
        raise ExperimentConfigError("experiment field 'random_seed' must be an integer")
    return ExperimentConfig(
        experiment_id=_required(values, "experiment_id", str),
        dataset_id=_required(values, "dataset_id", str),
        split_id=_required(values, "split_id", str),
        fold_id=_required(values, "fold_id", str),
        fit_partition=_required_enum(values, "fit_partition", FitPartition),
        feature_set_id=_required(values, "feature_set_id", str),
        selected_features=cast(Sequence[str], selected_features),
        reference_strategy=_required_enum(values, "reference_strategy", ReferenceStrategy),
        sampling_policy_id=_required(values, "sampling_policy_id", str),
        scaling_strategy=_required_enum(values, "scaling_strategy", ScalingStrategy),
        model_family=_required_enum(values, "model_family", ModelFamily),
        model_parameters=cast(Mapping[str, ExperimentParameter], parameters),
        random_seed=random_seed,
    )


def _validated_names(values: Collection[str], field_name: str) -> tuple[str, ...]:
    result = tuple(values)
    if not result:
        raise ExperimentConfigError(f"{field_name} must contain at least one value")
    for value in result:
        _validate_text(value, field_name)
    if len(result) != len(set(result)):
        raise ExperimentConfigError(f"{field_name} must contain unique values")
    return result


def _validate_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ExperimentConfigError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise ExperimentConfigError(f"{field_name} must not contain surrounding whitespace")


def _required[ValueType](
    values: Mapping[str, object],
    key: str,
    value_type: type[ValueType],
) -> ValueType:
    value = values.get(key)
    if not isinstance(value, value_type):
        raise ExperimentConfigError(f"experiment field {key!r} must be {value_type.__name__}")
    return value


def _required_enum[EnumType: StrEnum](
    values: Mapping[str, object],
    key: str,
    enum_type: type[EnumType],
) -> EnumType:
    value = _required(values, key, str)
    try:
        return enum_type(value)
    except ValueError as error:
        supported = tuple(item.value for item in enum_type)
        raise ExperimentConfigError(
            f"unsupported {key} {value!r}; expected one of {supported}"
        ) from error


def _require_exact_fields(
    values: Mapping[str, object],
    expected: set[str],
    scope: str,
) -> None:
    observed = set(values)
    if observed != expected:
        missing = sorted(expected - observed)
        unknown = sorted(observed - expected)
        raise ExperimentConfigError(
            f"{scope} fields do not match the v1 contract; missing={missing}, unknown={unknown}"
        )
