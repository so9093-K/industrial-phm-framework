"""Read generated XJTU-SY characterization artifacts for research interfaces."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import median
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
class XjtuRunLengthSummary:
    """Acquisition-count imbalance across bearing runs."""

    min_acquisitions: int
    max_acquisitions: int
    median_acquisitions: float
    max_to_min_ratio: float


@dataclass(frozen=True, slots=True)
class XjtuFeatureCorrelation:
    """One pairwise feature correlation from the generated summary."""

    left: str
    right: str
    pearson: float | None
    spearman: float | None


@dataclass(frozen=True, slots=True)
class XjtuLifecycleRun:
    """Retrospective lifecycle-third means for one bearing run."""

    asset_id: str
    operating_condition: str
    acquisition_count: int
    early_means: tuple[float | None, ...]
    middle_means: tuple[float | None, ...]
    late_means: tuple[float | None, ...]


@dataclass(frozen=True, slots=True)
class XjtuCharacterizationData:
    """Validated train/validation characterization data for read-only analysis."""

    feature_set_id: str
    split_id: str
    fold_id: str
    partition: XjtuCharacterizationPartition
    feature_names: tuple[str, ...]
    records: tuple[XjtuCharacterizationRecord, ...]
    run_length_summary: XjtuRunLengthSummary
    global_correlations: tuple[XjtuFeatureCorrelation, ...]
    correlations_by_condition: tuple[tuple[str, tuple[XjtuFeatureCorrelation, ...]], ...]
    lifecycle_runs: tuple[XjtuLifecycleRun, ...]

    @property
    def asset_ids(self) -> tuple[str, ...]:
        return tuple(sorted({record.asset_id for record in self.records}))

    @property
    def operating_conditions(self) -> tuple[str, ...]:
        return tuple(sorted({record.operating_condition for record in self.records}))

    def correlations_for(
        self, operating_condition: str | None
    ) -> tuple[XjtuFeatureCorrelation, ...]:
        if operating_condition is None:
            return self.global_correlations
        for condition, correlations in self.correlations_by_condition:
            if condition == operating_condition:
                return correlations
        raise KeyError(operating_condition)


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

    run_length_summary = _run_length_summary(summary, records)
    global_correlations, correlations_by_condition = _correlations(
        summary,
        feature_names,
        tuple(sorted({record.operating_condition for record in records})),
    )
    lifecycle_runs = _lifecycle_runs(summary, feature_names, records)

    return XjtuCharacterizationData(
        feature_set_id=feature_set_id,
        split_id=split_id,
        fold_id=fold_id,
        partition=partition,
        feature_names=feature_names,
        records=records,
        run_length_summary=run_length_summary,
        global_correlations=global_correlations,
        correlations_by_condition=correlations_by_condition,
        lifecycle_runs=lifecycle_runs,
    )


def _run_length_summary(
    summary: dict[str, Any],
    records: tuple[XjtuCharacterizationRecord, ...],
) -> XjtuRunLengthSummary:
    document = _object(summary, "run_length_imbalance")
    result = XjtuRunLengthSummary(
        min_acquisitions=_positive_int(document, "min_acquisitions"),
        max_acquisitions=_positive_int(document, "max_acquisitions"),
        median_acquisitions=_finite_number(document, "median_acquisitions"),
        max_to_min_ratio=_finite_number(document, "max_to_min_ratio"),
    )
    counts_by_asset: dict[str, int] = {}
    for record in records:
        counts_by_asset[record.asset_id] = counts_by_asset.get(record.asset_id, 0) + 1
    counts = tuple(counts_by_asset.values())
    expected = XjtuRunLengthSummary(
        min_acquisitions=min(counts),
        max_acquisitions=max(counts),
        median_acquisitions=float(median(counts)),
        max_to_min_ratio=max(counts) / min(counts),
    )
    if result != expected:
        raise XjtuCharacterizationArtifactError(
            "feature table and characterization summary run-length statistics differ"
        )
    return result


def _correlations(
    summary: dict[str, Any],
    feature_names: tuple[str, ...],
    operating_conditions: tuple[str, ...],
) -> tuple[
    tuple[XjtuFeatureCorrelation, ...],
    tuple[tuple[str, tuple[XjtuFeatureCorrelation, ...]], ...],
]:
    document = _object(summary, "correlations")
    global_correlations = _correlation_entries(document, "global", feature_names)
    by_condition_document = _object(document, "by_condition")
    if set(by_condition_document) != set(operating_conditions):
        raise XjtuCharacterizationArtifactError(
            "characterization summary correlation conditions do not match feature table"
        )
    by_condition = tuple(
        (
            condition,
            _correlation_entries(by_condition_document, condition, feature_names),
        )
        for condition in operating_conditions
    )
    return global_correlations, by_condition


def _correlation_entries(
    document: dict[str, Any],
    key: str,
    feature_names: tuple[str, ...],
) -> tuple[XjtuFeatureCorrelation, ...]:
    value = document.get(key)
    if not isinstance(value, list):
        raise XjtuCharacterizationArtifactError(
            f"characterization summary requires correlation list {key!r}"
        )
    entries = []
    for item in value:
        if not isinstance(item, dict):
            raise XjtuCharacterizationArtifactError(
                f"characterization summary contains invalid correlation in {key!r}"
            )
        left = _string(item, "left")
        right = _string(item, "right")
        if left not in feature_names or right not in feature_names or left == right:
            raise XjtuCharacterizationArtifactError(
                f"characterization summary contains invalid correlation features in {key!r}"
            )
        entries.append(
            XjtuFeatureCorrelation(
                left=left,
                right=right,
                pearson=_optional_finite_number(item, "pearson"),
                spearman=_optional_finite_number(item, "spearman"),
            )
        )
    expected_count = len(feature_names) * (len(feature_names) - 1) // 2
    observed_pairs = {frozenset((entry.left, entry.right)) for entry in entries}
    if len(entries) != expected_count or len(observed_pairs) != expected_count:
        raise XjtuCharacterizationArtifactError(
            f"characterization summary correlation pairs differ in {key!r}"
        )
    return tuple(entries)


def _lifecycle_runs(
    summary: dict[str, Any],
    feature_names: tuple[str, ...],
    records: tuple[XjtuCharacterizationRecord, ...],
) -> tuple[XjtuLifecycleRun, ...]:
    document = _object(summary, "lifecycle_segments")
    value = document.get("runs")
    if not isinstance(value, list):
        raise XjtuCharacterizationArtifactError(
            "characterization summary requires lifecycle run list"
        )
    expected_runs: dict[str, tuple[str, int]] = {}
    for record in records:
        condition, count = expected_runs.get(record.asset_id, (record.operating_condition, 0))
        if condition != record.operating_condition:
            raise XjtuCharacterizationArtifactError(
                "feature table maps one bearing run to multiple operating conditions"
            )
        expected_runs[record.asset_id] = (condition, count + 1)

    runs = []
    observed_assets: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise XjtuCharacterizationArtifactError(
                "characterization summary contains invalid lifecycle run"
            )
        asset_id = _string(item, "asset_id")
        condition = _string(item, "operating_condition")
        acquisition_count = _positive_int(item, "acquisition_count")
        if asset_id in observed_assets or expected_runs.get(asset_id) != (
            condition,
            acquisition_count,
        ):
            raise XjtuCharacterizationArtifactError(
                "characterization summary lifecycle runs do not match feature table"
            )
        observed_assets.add(asset_id)
        segments = _object(item, "segments")
        early_count, early_means = _segment_means(segments, "early_third", feature_names)
        middle_count, middle_means = _segment_means(segments, "middle_third", feature_names)
        late_count, late_means = _segment_means(segments, "late_third", feature_names)
        if early_count + middle_count + late_count != acquisition_count:
            raise XjtuCharacterizationArtifactError(
                "characterization summary lifecycle segment counts do not match bearing run"
            )
        runs.append(
            XjtuLifecycleRun(
                asset_id=asset_id,
                operating_condition=condition,
                acquisition_count=acquisition_count,
                early_means=early_means,
                middle_means=middle_means,
                late_means=late_means,
            )
        )
    if observed_assets != set(expected_runs):
        raise XjtuCharacterizationArtifactError(
            "characterization summary lifecycle runs do not match feature table"
        )
    return tuple(runs)


def _segment_means(
    segments: dict[str, Any],
    segment_name: str,
    feature_names: tuple[str, ...],
) -> tuple[int, tuple[float | None, ...]]:
    segment = _object(segments, segment_name)
    acquisition_count = _non_negative_int(segment, "acquisition_count")
    means = _object(segment, "feature_means")
    if set(means) != set(feature_names):
        raise XjtuCharacterizationArtifactError(
            f"characterization summary {segment_name!r} feature means do not match feature names"
        )
    values = tuple(_optional_finite_number(means, name) for name in feature_names)
    if (acquisition_count > 0) != all(value is not None for value in values):
        raise XjtuCharacterizationArtifactError(
            f"characterization summary {segment_name!r} means do not match segment count"
        )
    return acquisition_count, values


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


def _object(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise XjtuCharacterizationArtifactError(f"characterization summary requires object {key!r}")
    return cast(dict[str, Any], value)


def _non_negative_int(document: dict[str, Any], key: str) -> int:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise XjtuCharacterizationArtifactError(
            f"characterization summary requires non-negative integer {key!r}"
        )
    return value


def _positive_int(document: dict[str, Any], key: str) -> int:
    value = _non_negative_int(document, key)
    if value == 0:
        raise XjtuCharacterizationArtifactError(
            f"characterization summary requires positive integer {key!r}"
        )
    return value


def _finite_number(document: dict[str, Any], key: str) -> float:
    value = document.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise XjtuCharacterizationArtifactError(
            f"characterization summary requires finite number {key!r}"
        )
    result = float(value)
    if not math.isfinite(result):
        raise XjtuCharacterizationArtifactError(
            f"characterization summary requires finite number {key!r}"
        )
    return result


def _optional_finite_number(document: dict[str, Any], key: str) -> float | None:
    if document.get(key) is None:
        return None
    return _finite_number(document, key)
