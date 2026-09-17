"""Read generated XJTU-SY characterization artifacts for research interfaces."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
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
    values: tuple[float, ...]


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
    """Load matching generated artifacts without exposing holdout-test data."""
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise XjtuCharacterizationArtifactError(
            f"cannot read characterization summary: {summary_path}"
        ) from error
    if not isinstance(summary, dict):
        raise XjtuCharacterizationArtifactError("characterization summary must be a JSON object")
    if summary.get("schema_id") != XJTU_FEATURE_CHARACTERIZATION_SCHEMA_ID:
        raise XjtuCharacterizationArtifactError(
            f"unsupported characterization schema: {summary.get('schema_id')!r}"
        )
    if summary.get("dataset_id") != "xjtu-sy":
        raise XjtuCharacterizationArtifactError("characterization summary is not for XJTU-SY")

    feature_set_id = _string(summary, "feature_set_id")
    feature_names = _string_tuple(summary, "feature_names")
    scope = summary.get("experiment_scope")
    if not isinstance(scope, dict):
        raise XjtuCharacterizationArtifactError(
            "characterization summary requires object 'experiment_scope'"
        )
    split_id = _string(scope, "split_id")
    fold_id = _string(scope, "fold_id")
    partition_value = _string(scope, "partition")
    if partition_value not in {"train", "validation"}:
        raise XjtuCharacterizationArtifactError(
            "interactive characterization analysis only permits train or validation artifacts"
        )
    if scope.get("test_partition_included") is not False:
        raise XjtuCharacterizationArtifactError(
            "characterization summary must explicitly exclude the holdout-test partition"
        )
    partition = cast(XjtuCharacterizationPartition, partition_value)

    records = _read_feature_table(feature_table_path, feature_set_id, feature_names)
    if len(records) != _non_negative_int(summary, "acquisition_count"):
        raise XjtuCharacterizationArtifactError(
            "feature table and characterization summary acquisition counts differ"
        )
    if len({record.asset_id for record in records}) != _non_negative_int(
        summary, "bearing_run_count"
    ):
        raise XjtuCharacterizationArtifactError(
            "feature table and characterization summary bearing-run counts differ"
        )
    if len({record.operating_condition for record in records}) != _non_negative_int(
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
            _record(row, row_number, feature_set_id, feature_names)
            for row_number, row in enumerate(reader, start=2)
        )
    if not records:
        raise XjtuCharacterizationArtifactError("feature table must contain at least one record")
    return records


def _record(
    row: dict[str, str | None],
    row_number: int,
    feature_set_id: str,
    feature_names: tuple[str, ...],
) -> XjtuCharacterizationRecord:
    if row.get("feature_set_id") != feature_set_id or row.get("meta.dataset_id") != "xjtu-sy":
        raise XjtuCharacterizationArtifactError(
            f"feature table row {row_number} has inconsistent provenance"
        )
    asset_id = _cell(row, "asset_id", row_number)
    condition = _cell(row, "meta.operating_condition", row_number)
    try:
        acquisition_index = int(_cell(row, "meta.acquisition_index", row_number))
        values = tuple(float(_cell(row, name, row_number)) for name in feature_names)
    except ValueError as error:
        raise XjtuCharacterizationArtifactError(
            f"feature table row {row_number} contains invalid numeric data"
        ) from error
    if acquisition_index <= 0 or not all(math.isfinite(value) for value in values):
        raise XjtuCharacterizationArtifactError(
            f"feature table row {row_number} contains invalid numeric data"
        )
    return XjtuCharacterizationRecord(asset_id, acquisition_index, condition, values)


def _cell(row: dict[str, str | None], name: str, row_number: int) -> str:
    value = row.get(name)
    if not isinstance(value, str) or not value:
        raise XjtuCharacterizationArtifactError(
            f"feature table row {row_number} requires non-empty {name!r}"
        )
    return value


def _string(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise XjtuCharacterizationArtifactError(f"characterization summary requires string {key!r}")
    return value


def _string_tuple(document: dict[str, Any], key: str) -> tuple[str, ...]:
    value = document.get(key)
    if not isinstance(value, list) or not value:
        raise XjtuCharacterizationArtifactError(
            f"characterization summary requires non-empty string list {key!r}"
        )
    if not all(isinstance(item, str) and item for item in value):
        raise XjtuCharacterizationArtifactError(
            f"characterization summary contains invalid values in {key!r}"
        )
    return tuple(cast(list[str], value))


def _non_negative_int(document: dict[str, Any], key: str) -> int:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise XjtuCharacterizationArtifactError(
            f"characterization summary requires non-negative integer {key!r}"
        )
    return value
