"""Read-only helpers for interactive analysis of XJTU feature artifacts."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from industrial_phm.experiments.xjtu_characterization import (
    XJTU_FEATURE_CHARACTERIZATION_SCHEMA_ID,
    XjtuCharacterizationPartition,
)


class XjtuFeatureAnalysisError(ValueError):
    """Raised when characterization artifacts are inconsistent or unsupported."""


@dataclass(frozen=True, slots=True)
class XjtuFeatureRecord:
    """One acquisition-level row from a generated XJTU feature table."""

    asset_id: str
    acquisition_index: int
    operating_condition: str
    source_file: str | None
    values: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class XjtuFeaturePoint:
    """One selected feature value for retrospective interactive analysis."""

    asset_id: str
    acquisition_index: int
    operating_condition: str
    retrospective_lifecycle_fraction: float
    value: float


@dataclass(frozen=True, slots=True)
class XjtuFeatureAnalysis:
    """Validated development artifacts used by notebooks or interactive analysis tools."""

    feature_set_id: str
    split_id: str
    fold_id: str
    partition: XjtuCharacterizationPartition
    feature_names: tuple[str, ...]
    records: tuple[XjtuFeatureRecord, ...]
    bearing_run_count: int
    operating_condition_count: int

    @property
    def operating_conditions(self) -> tuple[str, ...]:
        """Return deterministic operating-condition options for an analysis UI."""
        return tuple(sorted({record.operating_condition for record in self.records}))

    @property
    def asset_ids(self) -> tuple[str, ...]:
        """Return deterministic bearing-run options for an analysis UI."""
        return tuple(sorted({record.asset_id for record in self.records}))

    def feature_series(
        self,
        feature_name: str,
        *,
        operating_condition: str | None = None,
        asset_ids: Iterable[str] | None = None,
    ) -> tuple[XjtuFeaturePoint, ...]:
        """Select one feature without duplicating artifact parsing in a UI.

        ``retrospective_lifecycle_fraction`` uses the known final acquisition index of each
        selected development run. It is provided only for retrospective visualization and
        must not be used as an online model input.
        """
        try:
            feature_index = self.feature_names.index(feature_name)
        except ValueError as error:
            raise XjtuFeatureAnalysisError(
                f"unknown feature in characterization artifacts: {feature_name!r}"
            ) from error

        selected_assets = None if asset_ids is None else frozenset(asset_ids)
        if selected_assets is not None:
            unknown_assets = sorted(selected_assets - set(self.asset_ids))
            if unknown_assets:
                raise XjtuFeatureAnalysisError(
                    f"unknown XJTU asset ids requested for analysis: {unknown_assets}"
                )

        if operating_condition is not None and operating_condition not in self.operating_conditions:
            raise XjtuFeatureAnalysisError(
                f"unknown operating condition requested for analysis: {operating_condition!r}"
            )
        selected = tuple(
            record
            for record in self.records
            if (operating_condition is None or record.operating_condition == operating_condition)
            and (selected_assets is None or record.asset_id in selected_assets)
        )
        if not selected:
            return ()

        final_index_by_asset: dict[str, int] = {}
        for record in selected:
            final_index_by_asset[record.asset_id] = max(
                final_index_by_asset.get(record.asset_id, 0), record.acquisition_index
            )

        return tuple(
            XjtuFeaturePoint(
                asset_id=record.asset_id,
                acquisition_index=record.acquisition_index,
                operating_condition=record.operating_condition,
                retrospective_lifecycle_fraction=(
                    record.acquisition_index / final_index_by_asset[record.asset_id]
                ),
                value=record.values[feature_index],
            )
            for record in selected
        )


def load_xjtu_feature_analysis(
    feature_table_path: Path,
    summary_path: Path,
) -> XjtuFeatureAnalysis:
    """Load and cross-check one generated train/validation characterization result.

    This function intentionally reads only generated characterization artifacts. It does not
    parse raw XJTU waveforms, recompute features, make feature-selection decisions, or expose a
    test partition for interactive development analysis.
    """
    summary = _read_summary(summary_path)
    feature_names = _string_tuple(summary, "feature_names")
    feature_set_id = _string_value(summary, "feature_set_id")
    scope = _mapping_value(summary, "experiment_scope")
    split_id = _string_value(scope, "split_id")
    fold_id = _string_value(scope, "fold_id")
    partition_value = _string_value(scope, "partition")
    if partition_value not in {"train", "validation"}:
        raise XjtuFeatureAnalysisError(
            "interactive feature analysis only permits train or validation artifacts"
        )
    partition = cast(XjtuCharacterizationPartition, partition_value)
    if scope.get("test_partition_included") is not False:
        raise XjtuFeatureAnalysisError(
            "interactive feature analysis requires characterization artifacts without test data"
        )

    records = _read_feature_table(
        feature_table_path,
        expected_feature_set_id=feature_set_id,
        expected_feature_names=feature_names,
    )
    expected_count = _integer_value(summary, "acquisition_count")
    if len(records) != expected_count:
        raise XjtuFeatureAnalysisError(
            "feature table and characterization summary acquisition counts differ: "
            f"table={len(records)}, summary={expected_count}"
        )

    observed_assets = {record.asset_id for record in records}
    observed_conditions = {record.operating_condition for record in records}
    bearing_run_count = _integer_value(summary, "bearing_run_count")
    operating_condition_count = _integer_value(summary, "operating_condition_count")
    if len(observed_assets) != bearing_run_count:
        raise XjtuFeatureAnalysisError(
            "feature table and characterization summary bearing-run counts differ"
        )
    if len(observed_conditions) != operating_condition_count:
        raise XjtuFeatureAnalysisError(
            "feature table and characterization summary operating-condition counts differ"
        )

    return XjtuFeatureAnalysis(
        feature_set_id=feature_set_id,
        split_id=split_id,
        fold_id=fold_id,
        partition=partition,
        feature_names=feature_names,
        records=records,
        bearing_run_count=bearing_run_count,
        operating_condition_count=operating_condition_count,
    )


def _read_summary(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise XjtuFeatureAnalysisError(
            f"cannot read XJTU characterization summary: {path}"
        ) from error
    if not isinstance(document, dict):
        raise XjtuFeatureAnalysisError("XJTU characterization summary must be a JSON object")
    if document.get("schema_id") != XJTU_FEATURE_CHARACTERIZATION_SCHEMA_ID:
        raise XjtuFeatureAnalysisError(
            "unsupported XJTU characterization summary schema: "
            f"{document.get('schema_id')!r}"
        )
    if document.get("dataset_id") != "xjtu-sy":
        raise XjtuFeatureAnalysisError("characterization summary is not for XJTU-SY")
    return document


def _read_feature_table(
    path: Path,
    *,
    expected_feature_set_id: str,
    expected_feature_names: tuple[str, ...],
) -> tuple[XjtuFeatureRecord, ...]:
    try:
        source = path.open(newline="", encoding="utf-8")
    except OSError as error:
        raise XjtuFeatureAnalysisError(f"cannot read XJTU feature table: {path}") from error

    with source:
        reader = csv.DictReader(source)
        fieldnames = tuple(reader.fieldnames or ())
        required = {
            "feature_set_id",
            "asset_id",
            "meta.acquisition_index",
            "meta.dataset_id",
            "meta.operating_condition",
        }
        missing = sorted(required - set(fieldnames))
        if missing:
            raise XjtuFeatureAnalysisError(
                f"XJTU feature table is missing required columns: {missing}"
            )
        observed_feature_names = tuple(name for name in fieldnames if name.startswith("feature."))
        if observed_feature_names != expected_feature_names:
            raise XjtuFeatureAnalysisError(
                "feature table columns do not match characterization summary feature names"
            )

        records: list[XjtuFeatureRecord] = []
        for row_number, row in enumerate(reader, start=2):
            records.append(
                _parse_record(
                    row,
                    row_number=row_number,
                    expected_feature_set_id=expected_feature_set_id,
                    feature_names=expected_feature_names,
                )
            )
    if not records:
        raise XjtuFeatureAnalysisError("XJTU feature table must contain at least one record")
    return tuple(
        sorted(
            records,
            key=lambda record: (
                record.operating_condition,
                record.asset_id,
                record.acquisition_index,
            ),
        )
    )


def _parse_record(
    row: dict[str, str | None],
    *,
    row_number: int,
    expected_feature_set_id: str,
    feature_names: tuple[str, ...],
) -> XjtuFeatureRecord:
    feature_set_id = row.get("feature_set_id")
    if feature_set_id != expected_feature_set_id:
        raise XjtuFeatureAnalysisError(
            f"feature table row {row_number} has unexpected feature_set_id: {feature_set_id!r}"
        )
    if row.get("meta.dataset_id") != "xjtu-sy":
        raise XjtuFeatureAnalysisError(
            f"feature table row {row_number} is not from dataset 'xjtu-sy'"
        )

    asset_id = _required_cell(row, "asset_id", row_number)
    operating_condition = _required_cell(row, "meta.operating_condition", row_number)
    acquisition_text = _required_cell(row, "meta.acquisition_index", row_number)
    try:
        acquisition_index = int(acquisition_text)
    except ValueError as error:
        raise XjtuFeatureAnalysisError(
            f"feature table row {row_number} has invalid acquisition index"
        ) from error
    if acquisition_index <= 0:
        raise XjtuFeatureAnalysisError(
            f"feature table row {row_number} has non-positive acquisition index"
        )

    values: list[float] = []
    for feature_name in feature_names:
        raw_value = _required_cell(row, feature_name, row_number)
        try:
            values.append(float(raw_value))
        except ValueError as error:
            raise XjtuFeatureAnalysisError(
                f"feature table row {row_number} has invalid value for {feature_name!r}"
            ) from error

    return XjtuFeatureRecord(
        asset_id=asset_id,
        acquisition_index=acquisition_index,
        operating_condition=operating_condition,
        source_file=row.get("meta.source_file") or None,
        values=tuple(values),
    )


def _required_cell(row: dict[str, str | None], name: str, row_number: int) -> str:
    value = row.get(name)
    if not isinstance(value, str) or not value:
        raise XjtuFeatureAnalysisError(
            f"feature table row {row_number} requires non-empty {name!r}"
        )
    return value


def _mapping_value(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise XjtuFeatureAnalysisError(f"characterization summary requires object {key!r}")
    return value


def _string_value(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value:
        raise XjtuFeatureAnalysisError(f"characterization summary requires string {key!r}")
    return value


def _integer_value(document: dict[str, Any], key: str) -> int:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise XjtuFeatureAnalysisError(
            f"characterization summary requires non-negative integer {key!r}"
        )
    return value


def _string_tuple(document: dict[str, Any], key: str) -> tuple[str, ...]:
    value = document.get(key)
    if not isinstance(value, list) or not value:
        raise XjtuFeatureAnalysisError(
            f"characterization summary requires non-empty string list {key!r}"
        )
    if not all(isinstance(item, str) and item for item in value):
        raise XjtuFeatureAnalysisError(
            f"characterization summary contains invalid values in {key!r}"
        )
    return tuple(value)
