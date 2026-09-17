"""Automated evidence generation for XJTU-SY feature characterization."""

from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Literal

from industrial_phm.adapters import XjtuSyAdapter, validate_xjtu_source
from industrial_phm.experiments.xjtu import XjtuSplitFold, get_xjtu_reference_split
from industrial_phm.features import (
    VIBRATION_STATISTICAL_FEATURE_SET_ID,
    VibrationFeatureVector,
    iter_vibration_features,
)

XJTU_FEATURE_CHARACTERIZATION_SCHEMA_ID = "xjtu-feature-characterization-summary-v1"
XjtuCharacterizationPartition = Literal["train", "validation"]
_LIFECYCLE_SEGMENTS = ("early_third", "middle_third", "late_third")


class XjtuFeatureCharacterizationError(ValueError):
    """Raised when feature records cannot form a valid XJTU characterization artifact."""


@dataclass(frozen=True, slots=True)
class XjtuCharacterizationArtifacts:
    """Paths and high-level counts for one generated characterization artifact set."""

    output_dir: Path
    feature_table_path: Path
    summary_path: Path
    feature_set_id: str
    split_id: str
    fold_id: str
    partition: XjtuCharacterizationPartition
    acquisition_count: int
    bearing_run_count: int
    operating_condition_count: int


@dataclass(frozen=True, slots=True)
class _Run:
    operating_condition: str
    asset_id: str
    vectors: tuple[VibrationFeatureVector, ...]


def characterize_xjtu_source(
    source: Path,
    output_dir: Path,
    *,
    fold_id: str,
    partition: XjtuCharacterizationPartition,
) -> XjtuCharacterizationArtifacts:
    """Generate train/validation characterization artifacts from a complete XJTU source.

    The complete source is compatibility-checked first. Every waveform is parsed through the
    production Adapter/feature path, but only the explicitly requested non-test partition is
    retained for characterization evidence. Test bearings are intentionally unavailable here.
    """
    validation = validate_xjtu_source(source)
    if not validation.profile_matches:
        issues = "; ".join(validation.profile_issues)
        raise XjtuFeatureCharacterizationError(
            "XJTU-SY source does not match the observed complete profile: " + issues
        )

    _, _, selected_assets = _resolve_partition(fold_id, partition)
    selected_asset_set = set(selected_assets)
    vectors = (
        vector
        for vector in iter_vibration_features(XjtuSyAdapter().iter_series(source))
        if vector.asset_id in selected_asset_set
    )
    return write_xjtu_characterization_artifacts(
        vectors,
        output_dir,
        fold_id=fold_id,
        partition=partition,
    )


def write_xjtu_characterization_artifacts(
    vectors: Iterable[VibrationFeatureVector],
    output_dir: Path,
    *,
    fold_id: str,
    partition: XjtuCharacterizationPartition,
) -> XjtuCharacterizationArtifacts:
    """Write deterministic train/validation feature and summary artifacts.

    The summary automates descriptive evidence generation. It does not select features,
    define fault onset, choose a normal reference, inspect a test partition, or make a model
    decision.
    """
    split_id, _, selected_assets = _resolve_partition(fold_id, partition)
    materialized = tuple(vectors)
    feature_names, runs = _validate_and_group(materialized)
    observed_assets = {run.asset_id for run in runs}
    expected_assets = set(selected_assets)
    if observed_assets != expected_assets:
        missing = sorted(expected_assets - observed_assets)
        unexpected = sorted(observed_assets - expected_assets)
        raise XjtuFeatureCharacterizationError(
            "XJTU characterization records must exactly cover the requested partition; "
            f"missing={missing}, unexpected={unexpected}"
        )

    summary = _build_summary(
        materialized,
        feature_names,
        runs,
        split_id=split_id,
        fold_id=fold_id,
        partition=partition,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    feature_table_path = output_dir / (
        f"vibration-statistical-v1-{fold_id}-{partition}-features.csv"
    )
    summary_path = output_dir / (
        f"xjtu-feature-characterization-summary-v1-{fold_id}-{partition}.json"
    )
    _write_feature_table(materialized, feature_names, feature_table_path)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return XjtuCharacterizationArtifacts(
        output_dir=output_dir,
        feature_table_path=feature_table_path,
        summary_path=summary_path,
        feature_set_id=VIBRATION_STATISTICAL_FEATURE_SET_ID,
        split_id=split_id,
        fold_id=fold_id,
        partition=partition,
        acquisition_count=len(materialized),
        bearing_run_count=len(runs),
        operating_condition_count=len({run.operating_condition for run in runs}),
    )


def _resolve_partition(
    fold_id: str,
    partition: XjtuCharacterizationPartition,
) -> tuple[str, XjtuSplitFold, tuple[str, ...]]:
    manifest = get_xjtu_reference_split()
    fold = next((candidate for candidate in manifest.folds if candidate.fold_id == fold_id), None)
    if fold is None:
        raise XjtuFeatureCharacterizationError(f"unknown XJTU reference fold: {fold_id!r}")
    if partition == "train":
        assets = fold.train
    elif partition == "validation":
        assets = fold.validation
    else:
        raise XjtuFeatureCharacterizationError(
            "feature characterization only permits train or validation partitions; "
            "test is reserved for final evaluation"
        )
    return manifest.split_id, fold, assets


def _validate_and_group(
    vectors: tuple[VibrationFeatureVector, ...],
) -> tuple[tuple[str, ...], tuple[_Run, ...]]:
    if not vectors:
        raise XjtuFeatureCharacterizationError("XJTU characterization requires feature vectors")

    expected_feature_names = tuple(vectors[0].feature_names)
    grouped: dict[tuple[str, str], list[VibrationFeatureVector]] = defaultdict(list)
    condition_by_asset: dict[str, str] = {}

    for vector in vectors:
        if vector.feature_set_id != VIBRATION_STATISTICAL_FEATURE_SET_ID:
            raise XjtuFeatureCharacterizationError(
                f"unexpected feature set for XJTU characterization: {vector.feature_set_id!r}"
            )
        if tuple(vector.feature_names) != expected_feature_names:
            raise XjtuFeatureCharacterizationError(
                "all XJTU feature vectors must share identical feature names and order"
            )
        dataset_id = vector.metadata.get("dataset_id")
        if dataset_id != "xjtu-sy":
            raise XjtuFeatureCharacterizationError(
                f"XJTU feature vector has unexpected dataset_id: {dataset_id!r}"
            )
        operating_condition = vector.metadata.get("operating_condition")
        if not isinstance(operating_condition, str) or not operating_condition:
            raise XjtuFeatureCharacterizationError(
                "XJTU feature vector requires non-empty operating_condition metadata"
            )
        previous_condition = condition_by_asset.setdefault(vector.asset_id, operating_condition)
        if previous_condition != operating_condition:
            raise XjtuFeatureCharacterizationError(
                f"XJTU asset {vector.asset_id!r} appears in multiple operating conditions"
            )
        _acquisition_index(vector)
        grouped[(operating_condition, vector.asset_id)].append(vector)

    runs: list[_Run] = []
    for (operating_condition, asset_id), run_vectors in sorted(grouped.items()):
        ordered = tuple(sorted(run_vectors, key=_acquisition_index))
        observed = tuple(_acquisition_index(vector) for vector in ordered)
        expected = tuple(range(1, len(ordered) + 1))
        if observed != expected:
            raise XjtuFeatureCharacterizationError(
                "XJTU feature vectors must preserve contiguous 1..N lifecycle order for "
                f"{operating_condition}/{asset_id}; observed={observed[:10]}"
            )
        runs.append(
            _Run(
                operating_condition=operating_condition,
                asset_id=asset_id,
                vectors=ordered,
            )
        )

    return expected_feature_names, tuple(runs)


def _acquisition_index(vector: VibrationFeatureVector) -> int:
    acquisition_index = vector.metadata.get("acquisition_index")
    if (
        isinstance(acquisition_index, bool)
        or not isinstance(acquisition_index, int)
        or acquisition_index <= 0
    ):
        raise XjtuFeatureCharacterizationError(
            "XJTU feature vector requires positive integer acquisition_index metadata"
        )
    return acquisition_index


def _build_summary(
    vectors: tuple[VibrationFeatureVector, ...],
    feature_names: tuple[str, ...],
    runs: tuple[_Run, ...],
    *,
    split_id: str,
    fold_id: str,
    partition: XjtuCharacterizationPartition,
) -> dict[str, Any]:
    conditions = sorted({run.operating_condition for run in runs})
    by_condition = {
        condition: tuple(
            vector for vector in vectors if vector.metadata["operating_condition"] == condition
        )
        for condition in conditions
    }

    feature_summaries = {
        feature_name: {
            "global": _distribution(_feature_values(vectors, feature_name)),
            "by_condition": {
                condition: _distribution(_feature_values(condition_vectors, feature_name))
                for condition, condition_vectors in by_condition.items()
            },
        }
        for feature_name in feature_names
    }

    correlations = {
        "global": _correlation_entries(vectors, feature_names),
        "by_condition": {
            condition: _correlation_entries(condition_vectors, feature_names)
            for condition, condition_vectors in by_condition.items()
        },
    }

    by_run = []
    lifecycle_runs = []
    for run in runs:
        by_run.append(
            {
                "operating_condition": run.operating_condition,
                "asset_id": run.asset_id,
                "acquisition_count": len(run.vectors),
                "features": {
                    feature_name: _distribution(_feature_values(run.vectors, feature_name))
                    for feature_name in feature_names
                },
            }
        )
        lifecycle_runs.append(_lifecycle_summary(run, feature_names))

    run_lengths = [len(run.vectors) for run in runs]
    return {
        "schema_id": XJTU_FEATURE_CHARACTERIZATION_SCHEMA_ID,
        "dataset_id": "xjtu-sy",
        "feature_set_id": VIBRATION_STATISTICAL_FEATURE_SET_ID,
        "experiment_scope": {
            "split_id": split_id,
            "fold_id": fold_id,
            "partition": partition,
            "test_partition_included": False,
        },
        "acquisition_count": len(vectors),
        "bearing_run_count": len(runs),
        "operating_condition_count": len(conditions),
        "feature_names": list(feature_names),
        "numerical_validity": {
            "non_finite_feature_values": 0,
            "note": (
                "Included VibrationFeatureVector values are finite by contract. "
                "Artifact generation is fail-fast and does not silently skip invalid vectors."
            ),
        },
        "run_length_imbalance": {
            "min_acquisitions": min(run_lengths),
            "max_acquisitions": max(run_lengths),
            "median_acquisitions": float(median(run_lengths)),
            "max_to_min_ratio": max(run_lengths) / min(run_lengths),
            "by_run": [
                {
                    "operating_condition": run.operating_condition,
                    "asset_id": run.asset_id,
                    "acquisition_count": len(run.vectors),
                }
                for run in runs
            ],
        },
        "feature_summaries": feature_summaries,
        "by_run": by_run,
        "correlations": correlations,
        "lifecycle_segments": {
            "definition": (
                "Retrospective per-run thirds based on the known final acquisition count. "
                "These segments are characterization-only and must not be model inputs."
            ),
            "runs": lifecycle_runs,
        },
        "decision_boundary": {
            "feature_selection": "undecided",
            "normal_reference": "undecided",
            "normalization": "undecided",
            "sampling_or_weighting": "undecided",
            "note": (
                "This artifact supplies descriptive development evidence only; experiment "
                "decisions must be versioned separately before test evaluation."
            ),
        },
    }


def _write_feature_table(
    vectors: tuple[VibrationFeatureVector, ...],
    feature_names: tuple[str, ...],
    destination: Path,
) -> None:
    metadata_keys = sorted({key for vector in vectors for key in vector.metadata})
    fieldnames = [
        "feature_set_id",
        "asset_id",
        *(f"meta.{key}" for key in metadata_keys),
        *feature_names,
    ]
    with destination.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=fieldnames)
        writer.writeheader()
        for vector in vectors:
            writer.writerow(vector.to_flat_record())


def _feature_values(
    vectors: Sequence[VibrationFeatureVector],
    feature_name: str,
) -> tuple[float, ...]:
    if not vectors:
        raise XjtuFeatureCharacterizationError("cannot read features from an empty sequence")
    try:
        feature_index = tuple(vectors[0].feature_names).index(feature_name)
    except ValueError as error:
        raise XjtuFeatureCharacterizationError(
            f"feature is not present in XJTU vectors: {feature_name}"
        ) from error
    return tuple(vector.values[feature_index] for vector in vectors)


def _distribution(values: Sequence[float]) -> dict[str, int | float]:
    if not values:
        raise XjtuFeatureCharacterizationError("cannot summarize an empty feature sequence")
    mean = math.fsum(values) / len(values)
    variance = math.fsum((value - mean) ** 2 for value in values) / len(values)
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "mean": mean,
        "population_std": math.sqrt(max(variance, 0.0)),
    }


def _correlation_entries(
    vectors: Sequence[VibrationFeatureVector],
    feature_names: tuple[str, ...],
) -> list[dict[str, str | float | None]]:
    values = {
        feature_name: _feature_values(vectors, feature_name) for feature_name in feature_names
    }
    entries: list[dict[str, str | float | None]] = []
    for left_index, left in enumerate(feature_names):
        for right in feature_names[left_index + 1 :]:
            left_values = values[left]
            right_values = values[right]
            entries.append(
                {
                    "left": left,
                    "right": right,
                    "pearson": _pearson(left_values, right_values),
                    "spearman": _pearson(
                        _average_ranks(left_values),
                        _average_ranks(right_values),
                    ),
                }
            )
    return entries


def _pearson(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or not left:
        raise XjtuFeatureCharacterizationError(
            "correlation requires non-empty equally sized feature sequences"
        )
    left_mean = math.fsum(left) / len(left)
    right_mean = math.fsum(right) / len(right)
    left_centered = tuple(value - left_mean for value in left)
    right_centered = tuple(value - right_mean for value in right)
    left_ss = math.fsum(value * value for value in left_centered)
    right_ss = math.fsum(value * value for value in right_centered)
    if left_ss <= 0.0 or right_ss <= 0.0:
        return None
    covariance = math.fsum(
        left_value * right_value
        for left_value, right_value in zip(left_centered, right_centered, strict=True)
    )
    return covariance / math.sqrt(left_ss * right_ss)


def _average_ranks(values: Sequence[float]) -> tuple[float, ...]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and ordered[end][1] == ordered[start][1]:
            end += 1
        average_rank = (start + 1 + end) / 2.0
        for position in range(start, end):
            ranks[ordered[position][0]] = average_rank
        start = end
    return tuple(ranks)


def _lifecycle_summary(
    run: _Run,
    feature_names: tuple[str, ...],
) -> dict[str, Any]:
    segments: dict[str, list[VibrationFeatureVector]] = {name: [] for name in _LIFECYCLE_SEGMENTS}
    run_length = len(run.vectors)
    for position, vector in enumerate(run.vectors):
        segment_index = min(2, (position * 3) // run_length)
        segments[_LIFECYCLE_SEGMENTS[segment_index]].append(vector)

    return {
        "operating_condition": run.operating_condition,
        "asset_id": run.asset_id,
        "acquisition_count": run_length,
        "segments": {
            segment_name: {
                "acquisition_count": len(segment_vectors),
                "feature_means": {
                    feature_name: (
                        math.fsum(_feature_values(segment_vectors, feature_name))
                        / len(segment_vectors)
                    )
                    if segment_vectors
                    else None
                    for feature_name in feature_names
                },
            }
            for segment_name, segment_vectors in segments.items()
        },
    }
