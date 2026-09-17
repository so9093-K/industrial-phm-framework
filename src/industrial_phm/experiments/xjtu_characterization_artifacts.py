"""Read generated XJTU-SY characterization artifacts for research interfaces."""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from industrial_phm.experiments.xjtu_characterization import (
    XJTU_FEATURE_CHARACTERIZATION_SCHEMA_ID,
    XjtuCharacterizationPartition,
)


class XjtuCharacterizationArtifactError(ValueError):
    """Raised when generated characterization artifacts are inconsistent or unsupported."""


@dataclass(frozen=True, slots=True)
class XjtuCharacterizationRecord:
    """One acquisition row from a generated XJTU feature table."""

    asset_id: str
    acquisition_index: int
    operating_condition: str
    feature_values: Mapping[str, float] = field(default_factory=dict)
    source_file: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "feature_values", MappingProxyType(dict(self.feature_values)))


@dataclass(frozen=True, slots=True)
class XjtuCharacterizationData:
    """Validated train/validation characterization data for read-only analysis."""

    feature_set_id: str
    split_id: str
    fold_id: str
    partition: XjtuCharacterizationPartition
    feature_names: tuple[str, ...]
    records: tuple[XjtuCharacterizationRecord, ...]

    @property
    def asset_ids(self) -> tuple[str, ...]:
        return tuple(sorted({record.asset_id for record in self.records}))

    @property
    def operating_conditions(self) -> tuple[str, ...]:
        return tuple(sorted({record.operating_condition for record in self.records}))


def load_xjtu_characterization_artifacts(
    feature_table_path: Path,
    summary_path: Path,
) -> XjtuCharacterizationData:
    """Load one generated non-test characterization result.

    This is an artifact reader only. It does not parse raw waveforms, recompute features,
    select features, or expose a holdout-test partition for development analysis.
    """
    summary = _read_json_object(summary_path)
    if summary.get("schema_id") != XJTU_FEATURE_CHARACTERIZATION_SCHEMA_ID:
        raise XjtuCharacterizationArtifactError(
            f"unsupported characterization schema: {summary.get('schema_id')!r}"
        )
    if summary.get("dataset_id") != "xjtu-sy":
        raise XjtuCharacterizationArtifactError("characterization summary is not for XJTU-SY")

    feature_set_id = _required_str(summary, "feature_set_id")
    feature_names = _required_str_tuple(summary, "feature_names")
    scope = _required_mapping(summary, "experiment_scope")
    split_id = _required_str(scope, "split_id")
    fold_id = _required_str(scope, "fold_id")
    partition_value = _required_str(scope, "partition")
    if partition_value not in {"train", "validation"}:
        raise XjtuCharacterizationArtifactError(
            "interactive characterization analysis only permits train or validation artifacts"
        )
    if scope.get("test_partition_included") is not False:
        raise XjtuCharacterizationArtifactError(
            "characterization summary must explicitly exclude the holdout-test partition"
        )
    partition = cast(XjtuCharacterizationPartition, partition_value)

    records = _read_feature_table(
        feature_table_path,
        feature_set_id=feature_set_id,
        feature_names=feature_names,
    )
    if len(records) != _required_non_negative_int(summary, "acquisition_count"):
        raise XjtuCharacterizationArtifactError(
            "feature table and characterization summary acquisition counts differ"
        )
    if len({record.asset_id for record in records}) != _required_non_negative_int(
        summary, "bearing_run_count"
    ):
        raise XjtuCharacterizationArtifactError(
            "feature table and characterization summary bearing-run counts differ"
        )
    if len({record.operating_condition for record in records}) != _required_non_negative_int(
        summary, "operating_condition_count"
    ):
        raise XjtuCharacterizationArtifactError(
            "feature table and characterization summary operating-condition counts differ"
        )

    return XjtuCharacterizationData(
        feature_set_id=feature_set_id,
        split_id=split_id,
        fold_id=fold_id,
        partition=partition,
        feature_names=feature_names,
        records=records,
    )


def _read_feature_table(
    path: Path,
    *,
    feature_set_id: str,
    feature_names: tuple[str, ...],
) -> tuple[XjtuCharacterizationRecord, ...]:
    try:
        source = path.open(newline="", encoding="utf-8")
    except OSError as error:
        raise XjtuCharacterizationArtifactError(f"cannot read feature table: {path}") from error

    with source:
        reader = csv.DictReader(source)
        fieldnames = tuple(reader.fieldnames or ())
        required = {
            "feature_set_id",
            "asset_id",
            "meta.dataset_id",
            "meta.acquisition_index",
            "meta.operating_condition",
        }
        missing = sorted(required - set(fieldnames))
        if missing:
            raise XjtuCharacterizationArtifactError(
                f"feature table is missing required columns: {missing}"
            )
        observed_features = tuple(name for name in fieldnames if name.startswith("feature."))
        if observed_features != feature_names:
            raise XjtuCharacterizationArtifactError(
                "feature table columns do not match characterization summary feature names"
            )

        records = tuple(
            _parse_record(
                row,
                row_number=row_number,
                feature_set_id=feature_set_id,
                feature_names=feature_names,
            )
            for row_number, row in enumerate(reader, start=2)
        )
    if not records:
        raise XjtuCharacterizationArtifactError("feature table must contain at least one record")
    return records


def _parse_record(
    row: dict[str, str | None],
    *,
    row_number: int,
    feature_set_id: str,
    feature_names: tuple[str, ...],
) -> XjtuCharacterizationRecord:
    if row.get("feature_set_id") != feature_set_id:
        raise XjtuCharacterizationArtifactError(
            f"feature table row {row_number} has an unexpected feature_set_id"
        )
    if row.get("meta.dataset_id") != "xjtu-sy":
        raise XjtuCharacterizationArtifactError(
            f"feature table row {row_number} is not from dataset 'xjtu-sy'"
        )

    asset_id = _required_cell(row, "asset_id", row_number)
    operating_condition = _required_cell(row, "meta.operating_condition", row_number)
    acquisition_text = _required_cell(row, "meta.acquisition_index", row_number)
    try:
        acquisition_index = int(acquisition_text)
    except ValueError as error:
        raise XjtuCharacterizationArtifactError(
            f"feature table row {row_number} has an invalid acquisition index"
        ) from error
    if acquisition_index <= 0:
        raise XjtuCharacterizationArtifactError(
            f"feature table row {row_number} has a non-positive acquisition index"
        )

    feature_values: dict[str, float] = {}
    for feature_name in feature_names:
        raw_value = _required_cell(row, feature_name, row_number)
        try:
            value = float(raw_value)
        except ValueError as error:
            raise XjtuCharacterizationArtifactError(
                f"feature table row {row_number} has an invalid value for {feature_name!r}"
            ) from error
        if not math.isfinite(value):
            raise XjtuCharacterizationArtifactError(
                f"feature table row {row_number} has a non-finite value for {feature_name!r}"
            )
        feature_values[feature_name] = value

    return XjtuCharacterizationRecord(
        asset_id=asset_id,
        acquisition_index=acquisition_index,
        operating_condition=operating_condition,
        feature_values=feature_values,
        source_file=row.get("meta.source_file") or None,
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise XjtuCharacterizationArtifactError(
            f"cannot read characterization summary: {path}"
        ) from error
    if not isinstance(document, dict):
        raise XjtuCharacterizationArtifactError("characterization summary must be a JSON object")
    return document


def _required_mapping(document: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise XjtuCharacterizationArtifactError(f"characterization summary requires object {key!r}")
    return value


def _required_str(document: Mapping[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise XjtuCharacterizationArtifactError(f"characterization summary requires string {key!r}")
    return value


def _required_str_tuple(document: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = document.get(key)
    if not isinstance(value, list) or not value:
        raise XjtuCharacterizationArtifactError(
            f"characterization summary requires a non-empty string list {key!r}"
        )
    if not all(isinstance(item, str) and item for item in value):
        raise XjtuCharacterizationArtifactError(
            f"characterization summary contains invalid values in {key!r}"
        )
    return tuple(cast(list[str], value))


def _required_non_negative_int(document: Mapping[str, Any], key: str) -> int:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise XjtuCharacterizationArtifactError(
            f"characterization summary requires non-negative integer {key!r}"
        )
    return value


def _required_cell(row: Mapping[str, str | None], name: str, row_number: int) -> str:
    value = row.get(name)
    if not isinstance(value, str) or not value:
        raise XjtuCharacterizationArtifactError(
            f"feature table row {row_number} requires non-empty {name!r}"
        )
    return value
