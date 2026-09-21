"""XJTU-SY experiment protocol and bearing-run split contract."""

from __future__ import annotations

import tomllib
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import cast

from industrial_phm.adapters.xjtu import XJTU_SY_CHANNELS
from industrial_phm.experiments.config import (
    ExperimentConfig,
    ExperimentContext,
    load_experiment_configs,
)
from industrial_phm.features import (
    VIBRATION_STATISTICAL_FEATURE_SET_ID,
    vibration_feature_names,
)

_DATASET_ID = "xjtu-sy"
_SPLIT_UNIT = "bearing-run"
_STRATEGY = "condition-stratified-rotating-holdout"
_EXPECTED_FOLD_IDS = tuple(f"fold-{index}" for index in range(1, 6))
_SUPPORTED_SAMPLING_POLICY_IDS = (
    "acquisition-uniform-v1",
    "bearing-balanced-resample-v1",
    "reference-window-uniform-v1",
    "sequence-window-uniform-v1",
)
_EXPECTED_ASSETS = tuple(
    f"Bearing{condition}_{index}" for condition in range(1, 4) for index in range(1, 6)
)


class XjtuExperimentProtocolError(ValueError):
    """Raised when the packaged XJTU-SY experiment split violates its protocol."""


@dataclass(frozen=True, slots=True)
class XjtuSplitFold:
    """One leakage-free XJTU-SY train/validation/test bearing-run partition."""

    fold_id: str
    train: tuple[str, ...]
    validation: tuple[str, ...]
    test: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class XjtuSplitManifest:
    """Authoritative bearing-run assignments for the XJTU-SY reference protocol."""

    split_id: str
    dataset_id: str
    split_unit: str
    strategy: str
    folds: tuple[XjtuSplitFold, ...]

    @classmethod
    def from_toml(cls, content: str) -> XjtuSplitManifest:
        """Parse and validate a version-controlled XJTU-SY split manifest."""
        raw = tomllib.loads(content)
        fold_tables = _required_table_list(raw, "fold")
        manifest = cls(
            split_id=_required_str(raw, "id"),
            dataset_id=_required_str(raw, "dataset_id"),
            split_unit=_required_str(raw, "split_unit"),
            strategy=_required_str(raw, "strategy"),
            folds=tuple(_parse_fold(table) for table in fold_tables),
        )
        manifest.validate()
        return manifest

    def validate(self) -> None:
        """Reject asset leakage, incomplete coverage, or protocol drift."""
        if self.dataset_id != _DATASET_ID:
            raise XjtuExperimentProtocolError(
                f"XJTU-SY split dataset_id must be {_DATASET_ID!r}, got {self.dataset_id!r}"
            )
        if self.split_unit != _SPLIT_UNIT:
            raise XjtuExperimentProtocolError(
                f"XJTU-SY split unit must be {_SPLIT_UNIT!r}, got {self.split_unit!r}"
            )
        if self.strategy != _STRATEGY:
            raise XjtuExperimentProtocolError(
                f"XJTU-SY split strategy must be {_STRATEGY!r}, got {self.strategy!r}"
            )

        fold_ids = tuple(fold.fold_id for fold in self.folds)
        if fold_ids != _EXPECTED_FOLD_IDS:
            raise XjtuExperimentProtocolError(
                f"XJTU-SY split folds must be {_EXPECTED_FOLD_IDS}, got {fold_ids}"
            )

        train_counts: Counter[str] = Counter()
        validation_counts: Counter[str] = Counter()
        test_counts: Counter[str] = Counter()

        for fold in self.folds:
            _validate_fold(fold)
            train_counts.update(fold.train)
            validation_counts.update(fold.validation)
            test_counts.update(fold.test)

        for asset_id in _EXPECTED_ASSETS:
            counts = (
                train_counts[asset_id],
                validation_counts[asset_id],
                test_counts[asset_id],
            )
            if counts != (3, 1, 1):
                raise XjtuExperimentProtocolError(
                    "XJTU-SY rotating holdout requires each bearing run to appear "
                    "three times in train, once in validation, and once in test; "
                    f"{asset_id} has train/validation/test counts {counts}"
                )


def _validate_fold(fold: XjtuSplitFold) -> None:
    partitions = {
        "train": fold.train,
        "validation": fold.validation,
        "test": fold.test,
    }
    expected_assets = set(_EXPECTED_ASSETS)

    for name, assets in partitions.items():
        if len(assets) != len(set(assets)):
            raise XjtuExperimentProtocolError(
                f"XJTU-SY {fold.fold_id} {name} partition contains duplicate bearing runs"
            )
        unknown = set(assets) - expected_assets
        if unknown:
            raise XjtuExperimentProtocolError(
                f"XJTU-SY {fold.fold_id} {name} partition contains unknown bearing runs: "
                f"{sorted(unknown)}"
            )

    train = set(fold.train)
    validation = set(fold.validation)
    test = set(fold.test)
    overlap = (train & validation) | (train & test) | (validation & test)
    if overlap:
        raise XjtuExperimentProtocolError(
            f"XJTU-SY {fold.fold_id} has bearing-run leakage across partitions: {sorted(overlap)}"
        )

    observed_assets = train | validation | test
    if observed_assets != expected_assets:
        missing = sorted(expected_assets - observed_assets)
        raise XjtuExperimentProtocolError(
            f"XJTU-SY {fold.fold_id} does not cover all bearing runs; missing={missing}"
        )

    expected_sizes = {"train": 9, "validation": 3, "test": 3}
    for name, expected_size in expected_sizes.items():
        observed_size = len(partitions[name])
        if observed_size != expected_size:
            raise XjtuExperimentProtocolError(
                f"XJTU-SY {fold.fold_id} {name} partition must contain "
                f"{expected_size} bearing runs, got {observed_size}"
            )

    expected_per_condition = {"train": 3, "validation": 1, "test": 1}
    for condition in range(1, 4):
        prefix = f"Bearing{condition}_"
        for name, expected_count in expected_per_condition.items():
            observed_count = sum(asset_id.startswith(prefix) for asset_id in partitions[name])
            if observed_count != expected_count:
                raise XjtuExperimentProtocolError(
                    f"XJTU-SY {fold.fold_id} {name} partition must contain "
                    f"{expected_count} run(s) from condition {condition}, got {observed_count}"
                )


def _parse_fold(values: Mapping[str, object]) -> XjtuSplitFold:
    return XjtuSplitFold(
        fold_id=_required_str(values, "id"),
        train=_required_str_tuple(values, "train"),
        validation=_required_str_tuple(values, "validation"),
        test=_required_str_tuple(values, "test"),
    )


def _required_str(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value.strip():
        raise XjtuExperimentProtocolError(f"XJTU-SY split field {key!r} must be a non-empty string")
    return value.strip()


def _required_str_tuple(values: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = values.get(key)
    if not isinstance(value, list) or not value:
        raise XjtuExperimentProtocolError(
            f"XJTU-SY split field {key!r} must be a non-empty string array"
        )

    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise XjtuExperimentProtocolError(
                f"XJTU-SY split field {key!r} must contain only non-empty strings"
            )
        result.append(item.strip())
    return tuple(result)


def _required_table_list(
    values: Mapping[str, object],
    key: str,
) -> tuple[Mapping[str, object], ...]:
    value = values.get(key)
    if not isinstance(value, list) or not value:
        raise XjtuExperimentProtocolError(
            f"XJTU-SY split field {key!r} must contain one or more tables"
        )

    tables: list[Mapping[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            raise XjtuExperimentProtocolError(
                f"XJTU-SY split field {key!r} must contain only tables"
            )
        tables.append(cast(Mapping[str, object], item))
    return tuple(tables)


@lru_cache(maxsize=1)
def get_xjtu_reference_split() -> XjtuSplitManifest:
    """Load the packaged XJTU-SY reference split manifest."""
    manifest = resources.files("industrial_phm.experiments.manifests").joinpath(
        "xjtu-sy-condition-stratified-5fold-v1.toml"
    )
    return XjtuSplitManifest.from_toml(manifest.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def xjtu_experiment_context() -> ExperimentContext:
    """Return the dataset-owned split and feature context every XJTU config resolves against."""
    split = get_xjtu_reference_split()
    return ExperimentContext(
        dataset_id=split.dataset_id,
        split_id=split.split_id,
        fold_ids=tuple(fold.fold_id for fold in split.folds),
        feature_set_id=VIBRATION_STATISTICAL_FEATURE_SET_ID,
        feature_names=vibration_feature_names(XJTU_SY_CHANNELS),
        supported_sampling_policy_ids=_SUPPORTED_SAMPLING_POLICY_IDS,
    )


def load_packaged_xjtu_experiment_configs(manifest_name: str) -> tuple[ExperimentConfig, ...]:
    """Load one packaged XJTU experiment manifest through dataset-neutral config validation."""
    manifest = resources.files("industrial_phm.experiments.manifests").joinpath(manifest_name)
    return load_experiment_configs(
        manifest.read_text(encoding="utf-8"),
        context=xjtu_experiment_context(),
    )


@lru_cache(maxsize=1)
def get_xjtu_isolation_forest_candidates() -> tuple[ExperimentConfig, ...]:
    """Load the packaged fold-1 candidates through dataset-neutral config validation."""
    return load_packaged_xjtu_experiment_configs(
        "xjtu-sy-isolation-forest-fold-1-candidates-v2.toml"
    )
