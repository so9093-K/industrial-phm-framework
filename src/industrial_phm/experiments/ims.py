"""IMS single-channel cross-test split and fixed experiment configuration."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Literal

from industrial_phm.experiments.config import (
    ExperimentConfig,
    ExperimentContext,
    ModelFamily,
    ReferenceStrategy,
    ScalingStrategy,
    load_experiment_configs,
)
from industrial_phm.features import (
    VIBRATION_STATISTICAL_FEATURE_SET_ID,
    vibration_feature_names,
)

IMS_DATASET_ID = "ims-bearings"
IMS_CROSS_TEST_SPLIT_ID = "ims-single-channel-cross-test-v1"
IMS_CROSS_TEST_CONFIGURATION_ID = "ims-bearings-iforest-single-channel-cross-test-v1"
IMS_CROSS_TEST_FOLD_ID = "fold-1"
IMS_TRAIN_TEST_ID = "set-2"
IMS_EVALUATION_TEST_ID = "set-3"
IMS_EVALUATION_ARCHIVE_SCOPE: Literal["readme-documented"] = "readme-documented"
IMS_TRAIN_ACQUISITION_COUNT = 984
IMS_EVALUATION_ACQUISITION_COUNT = 4_448
IMS_BEARING_COUNT = 4
IMS_ROTATIONAL_SPEED_RPM = 2_000.0
IMS_RADIAL_LOAD_LB = 6_000.0

_SPLIT_MANIFEST = "ims-bearings-single-channel-cross-test-v1.toml"
_CONFIG_MANIFEST = "ims-bearings-iforest-single-channel-cross-test-v1.toml"
_SUPPORTED_SAMPLING_POLICY_IDS = ("acquisition-uniform-v1",)
_EXPECTED_MODEL_PARAMETERS = {
    "n_estimators": 256,
    "max_samples": "auto",
    "contamination": "auto",
    "max_features": 1.0,
    "bootstrap": False,
}


class ImsExperimentProtocolError(ValueError):
    """Raised when the packaged IMS cross-test protocol drifts."""


@dataclass(frozen=True, slots=True)
class ImsCrossTestSplit:
    """One fixed test-level train/evaluation assignment for IMS v1."""

    split_id: str
    dataset_id: str
    split_unit: str
    strategy: str
    fold_id: str
    train_test_id: str
    evaluation_test_id: str
    evaluation_archive_scope: str
    train_acquisition_count: int
    evaluation_acquisition_count: int

    @classmethod
    def from_toml(cls, content: str) -> ImsCrossTestSplit:
        raw = tomllib.loads(content)
        expected_fields = {
            "id",
            "dataset_id",
            "split_unit",
            "strategy",
            "fold_id",
            "train_test_id",
            "evaluation_test_id",
            "evaluation_archive_scope",
            "train_acquisition_count",
            "evaluation_acquisition_count",
        }
        if set(raw) != expected_fields:
            missing = sorted(expected_fields - set(raw))
            unknown = sorted(set(raw) - expected_fields)
            raise ImsExperimentProtocolError(
                f"IMS split fields do not match v1; missing={missing}, unknown={unknown}"
            )
        manifest = cls(
            split_id=_required_str(raw, "id"),
            dataset_id=_required_str(raw, "dataset_id"),
            split_unit=_required_str(raw, "split_unit"),
            strategy=_required_str(raw, "strategy"),
            fold_id=_required_str(raw, "fold_id"),
            train_test_id=_required_str(raw, "train_test_id"),
            evaluation_test_id=_required_str(raw, "evaluation_test_id"),
            evaluation_archive_scope=_required_str(raw, "evaluation_archive_scope"),
            train_acquisition_count=_required_int(raw, "train_acquisition_count"),
            evaluation_acquisition_count=_required_int(raw, "evaluation_acquisition_count"),
        )
        manifest.validate()
        return manifest

    def validate(self) -> None:
        expected = (
            ("split_id", self.split_id, IMS_CROSS_TEST_SPLIT_ID),
            ("dataset_id", self.dataset_id, IMS_DATASET_ID),
            ("split_unit", self.split_unit, "test"),
            ("strategy", self.strategy, "fixed-cross-test"),
            ("fold_id", self.fold_id, IMS_CROSS_TEST_FOLD_ID),
            ("train_test_id", self.train_test_id, IMS_TRAIN_TEST_ID),
            ("evaluation_test_id", self.evaluation_test_id, IMS_EVALUATION_TEST_ID),
            (
                "evaluation_archive_scope",
                self.evaluation_archive_scope,
                IMS_EVALUATION_ARCHIVE_SCOPE,
            ),
            (
                "train_acquisition_count",
                self.train_acquisition_count,
                IMS_TRAIN_ACQUISITION_COUNT,
            ),
            (
                "evaluation_acquisition_count",
                self.evaluation_acquisition_count,
                IMS_EVALUATION_ACQUISITION_COUNT,
            ),
        )
        for field_name, value, configured in expected:
            if value != configured:
                raise ImsExperimentProtocolError(
                    f"IMS cross-test {field_name} must be {configured!r}, got {value!r}"
                )


@lru_cache(maxsize=1)
def get_ims_cross_test_split() -> ImsCrossTestSplit:
    content = (
        resources.files("industrial_phm.experiments.manifests")
        .joinpath(_SPLIT_MANIFEST)
        .read_text(encoding="utf-8")
    )
    return ImsCrossTestSplit.from_toml(content)


def ims_experiment_context() -> ExperimentContext:
    """Return the dataset-owned context for the fixed single-channel IMS experiment."""
    return ExperimentContext(
        dataset_id=IMS_DATASET_ID,
        split_id=IMS_CROSS_TEST_SPLIT_ID,
        fold_ids=(IMS_CROSS_TEST_FOLD_ID,),
        feature_set_id=VIBRATION_STATISTICAL_FEATURE_SET_ID,
        feature_names=vibration_feature_names(("vibration",)),
        supported_sampling_policy_ids=_SUPPORTED_SAMPLING_POLICY_IDS,
    )


def load_packaged_ims_experiment_configs(filename: str) -> tuple[ExperimentConfig, ...]:
    content = (
        resources.files("industrial_phm.experiments.manifests")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )
    return load_experiment_configs(content, context=ims_experiment_context())


@lru_cache(maxsize=1)
def get_ims_cross_test_configuration() -> ExperimentConfig:
    """Return the one configuration frozen before IMS numerical evaluation."""
    configs = load_packaged_ims_experiment_configs(_CONFIG_MANIFEST)
    if len(configs) != 1:
        raise ImsExperimentProtocolError(
            f"IMS cross-test manifest must contain exactly one experiment, got {len(configs)}"
        )
    config = configs[0]
    expected_axes = (
        ("experiment_id", config.experiment_id, IMS_CROSS_TEST_CONFIGURATION_ID),
        ("dataset_id", config.dataset_id, IMS_DATASET_ID),
        ("split_id", config.split_id, IMS_CROSS_TEST_SPLIT_ID),
        ("fold_id", config.fold_id, IMS_CROSS_TEST_FOLD_ID),
        ("reference_strategy", config.reference_strategy, ReferenceStrategy.ALL_TRAIN_OBSERVATIONS),
        ("sampling_policy_id", config.sampling_policy_id, "acquisition-uniform-v1"),
        ("scaling_strategy", config.scaling_strategy, ScalingStrategy.IDENTITY),
        ("model_family", config.model_family, ModelFamily.ISOLATION_FOREST),
        ("random_seed", config.random_seed, 42),
    )
    for field_name, value, expected in expected_axes:
        if value != expected:
            raise ImsExperimentProtocolError(
                f"IMS cross-test {field_name} must be {expected!r}, got {value!r}"
            )
    expected_features = vibration_feature_names(("vibration",))
    if tuple(config.selected_features) != expected_features:
        raise ImsExperimentProtocolError(
            "IMS cross-test selected_features must be the full single-channel v1 schema"
        )
    if dict(config.model_parameters) != _EXPECTED_MODEL_PARAMETERS:
        raise ImsExperimentProtocolError(
            "IMS cross-test model parameters must match the protocol-fixed Isolation Forest"
        )
    get_ims_cross_test_split()
    return config


def _required_str(values: dict[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ImsExperimentProtocolError(f"IMS split field {key!r} must be a non-empty string")
    return value


def _required_int(values: dict[str, object], key: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ImsExperimentProtocolError(f"IMS split field {key!r} must be a positive integer")
    return value
