"""XJTU-SY recorded-end RUL target construction for prognostics protocol v1."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Literal

from industrial_phm.adapters import XJTU_SY_CHANNELS, get_xjtu_expected_acquisition_count
from industrial_phm.experiments.xjtu import XjtuSplitFold, get_xjtu_reference_split
from industrial_phm.features import (
    VIBRATION_STATISTICAL_FEATURE_SET_ID,
    VibrationFeatureVector,
    vibration_feature_names,
)
from industrial_phm.prognostics import RulTargetObservation, RulTargetSeries

XJTU_RUL_PROTOCOL_ID = "xjtu-sy-recorded-end-rul-v1"
XJTU_RUL_TARGET_DEFINITION_ID = "xjtu-sy-recorded-end-acquisition-interval-v1"
XJTU_RUL_TARGET_UNIT = "acquisition-interval"

_DATASET_ID = "xjtu-sy"
_FOLD_ID = "fold-1"
_Partition = Literal["train", "validation", "test"]


class XjtuRulTargetError(ValueError):
    """Raised when XJTU feature observations cannot form protocol-defined RUL targets."""


def build_xjtu_recorded_end_rul_targets(
    vectors: Sequence[VibrationFeatureVector],
    *,
    partition: _Partition,
) -> tuple[RulTargetSeries, ...]:
    """Build complete fold-1 RUL target series aligned to feature observation identities."""
    expected_assets = get_xjtu_rul_partition_assets(partition)
    ordered_by_asset = _complete_partition_vectors(
        vectors,
        partition=partition,
        expected_assets=expected_assets,
    )

    series: list[RulTargetSeries] = []
    for asset_id in expected_assets:
        run_length = get_xjtu_expected_acquisition_count(asset_id)
        observations = tuple(
            RulTargetObservation(
                asset_id=asset_id,
                partition_id=partition,
                source_observation_id=f"{asset_id}:acquisition-{acquisition_index}",
                remaining_useful_life=float(run_length - acquisition_index),
            )
            for acquisition_index in range(1, run_length + 1)
        )
        series.append(
            RulTargetSeries(
                target_definition_id=XJTU_RUL_TARGET_DEFINITION_ID,
                unit=XJTU_RUL_TARGET_UNIT,
                asset_id=asset_id,
                partition_id=partition,
                observations=observations,
            )
        )

        vectors_for_asset = ordered_by_asset[asset_id]
        for acquisition_index, (vector, target) in enumerate(
            zip(vectors_for_asset, observations, strict=True),
            start=1,
        ):
            observed_index = _acquisition_index(vector, vector_index=acquisition_index - 1)
            expected_source_id = f"{asset_id}:acquisition-{observed_index}"
            if (
                observed_index != acquisition_index
                or target.source_observation_id != expected_source_id
            ):
                raise XjtuRulTargetError(
                    "XJTU RUL target source identity drifted from the ordered feature observation"
                )

    return validate_xjtu_recorded_end_rul_targets(series, partition=partition)


def validate_xjtu_recorded_end_rul_targets(
    targets: Sequence[RulTargetSeries],
    *,
    partition: _Partition,
) -> tuple[RulTargetSeries, ...]:
    """Validate complete recorded-end target semantics and return manifest-ordered series."""
    target_series = tuple(targets)
    expected_assets = get_xjtu_rul_partition_assets(partition)
    expected_asset_set = set(expected_assets)

    observed_assets = {series.asset_id for series in target_series}
    if observed_assets != expected_asset_set:
        raise XjtuRulTargetError(
            f"XJTU RUL targets must cover configured {partition} bearing runs; "
            f"missing={sorted(expected_asset_set - observed_assets)}, "
            f"unexpected={sorted(observed_assets - expected_asset_set)}"
        )
    if len(target_series) != len(expected_assets):
        raise XjtuRulTargetError("XJTU RUL target series must contain unique bearing runs")

    by_asset = {series.asset_id: series for series in target_series}
    ordered: list[RulTargetSeries] = []
    for asset_id in expected_assets:
        series = by_asset[asset_id]
        _validate_recorded_end_target_series(series, partition=partition)
        ordered.append(series)
    return tuple(ordered)


def get_xjtu_rul_partition_assets(partition: _Partition) -> tuple[str, ...]:
    """Return the authoritative fold-1 bearing runs for one RUL partition."""
    return _partition_assets(_fold_1(), partition)


def _validate_recorded_end_target_series(
    series: RulTargetSeries,
    *,
    partition: str,
) -> None:
    if series.partition_id != partition:
        raise XjtuRulTargetError(f"XJTU RUL target series must preserve partition {partition!r}")
    if series.target_definition_id != XJTU_RUL_TARGET_DEFINITION_ID:
        raise XjtuRulTargetError(
            "XJTU RUL target series must use the recorded-end target definition"
        )
    if series.unit != XJTU_RUL_TARGET_UNIT:
        raise XjtuRulTargetError("XJTU RUL target series must use acquisition-interval unit")

    run_length = get_xjtu_expected_acquisition_count(series.asset_id)
    expected_ids = tuple(
        f"{series.asset_id}:acquisition-{acquisition_index}"
        for acquisition_index in range(1, run_length + 1)
    )
    observed_ids = tuple(observation.source_observation_id for observation in series.observations)
    if observed_ids != expected_ids:
        raise XjtuRulTargetError(
            f"XJTU RUL targets for {series.asset_id} must cover complete ordered acquisition 1.."
            f"{run_length}"
        )

    expected_values = tuple(float(run_length - index) for index in range(1, run_length + 1))
    observed_values = tuple(
        observation.remaining_useful_life for observation in series.observations
    )
    if observed_values != expected_values:
        raise XjtuRulTargetError(
            f"XJTU RUL targets for {series.asset_id} must preserve N-k recorded-end semantics"
        )


def _fold_1() -> XjtuSplitFold:
    split = get_xjtu_reference_split()
    for fold in split.folds:
        if fold.fold_id == _FOLD_ID:
            return fold
    raise XjtuRulTargetError(f"XJTU split does not contain required fold {_FOLD_ID!r}")


def _partition_assets(fold: XjtuSplitFold, partition: str) -> tuple[str, ...]:
    if partition == "train":
        return fold.train
    if partition == "validation":
        return fold.validation
    if partition == "test":
        return fold.test
    raise XjtuRulTargetError("XJTU RUL partition must be one of 'train', 'validation', or 'test'")


def _complete_partition_vectors(
    vectors: Sequence[VibrationFeatureVector],
    *,
    partition: str,
    expected_assets: Sequence[str],
) -> dict[str, tuple[VibrationFeatureVector, ...]]:
    if not vectors:
        raise XjtuRulTargetError(
            f"XJTU RUL {partition} target construction requires feature vectors"
        )

    by_asset: dict[str, dict[int, VibrationFeatureVector]] = defaultdict(dict)
    for vector_index, vector in enumerate(vectors):
        _validate_vector(vector, vector_index=vector_index)
        acquisition_index = _acquisition_index(vector, vector_index=vector_index)
        if acquisition_index in by_asset[vector.asset_id]:
            raise XjtuRulTargetError(
                f"XJTU RUL {partition} contains duplicate acquisition {acquisition_index} "
                f"for {vector.asset_id}"
            )
        by_asset[vector.asset_id][acquisition_index] = vector

    expected_asset_set = set(expected_assets)
    observed_asset_set = set(by_asset)
    if observed_asset_set != expected_asset_set:
        raise XjtuRulTargetError(
            f"XJTU RUL target input must cover configured {partition} bearing runs; "
            f"missing={sorted(expected_asset_set - observed_asset_set)}, "
            f"unexpected={sorted(observed_asset_set - expected_asset_set)}"
        )

    result: dict[str, tuple[VibrationFeatureVector, ...]] = {}
    for asset_id in expected_assets:
        expected_count = get_xjtu_expected_acquisition_count(asset_id)
        expected_indices = set(range(1, expected_count + 1))
        observed_indices = set(by_asset[asset_id])
        if observed_indices != expected_indices:
            raise XjtuRulTargetError(
                f"XJTU RUL target input must cover the complete {partition} acquisition "
                f"sequence for {asset_id}; expected=1..{expected_count}, "
                f"missing={sorted(expected_indices - observed_indices)[:10]}, "
                f"unexpected={sorted(observed_indices - expected_indices)[:10]}"
            )
        result[asset_id] = tuple(
            by_asset[asset_id][acquisition_index]
            for acquisition_index in range(1, expected_count + 1)
        )
    return result


def _validate_vector(vector: VibrationFeatureVector, *, vector_index: int) -> None:
    if not isinstance(vector, VibrationFeatureVector):
        raise XjtuRulTargetError(
            f"XJTU RUL feature vector {vector_index} must be a VibrationFeatureVector"
        )
    if vector.feature_set_id != VIBRATION_STATISTICAL_FEATURE_SET_ID:
        raise XjtuRulTargetError(
            f"XJTU RUL feature vector {vector_index} feature_set_id does not match protocol"
        )
    if tuple(vector.feature_names) != vibration_feature_names(XJTU_SY_CHANNELS):
        raise XjtuRulTargetError(
            f"XJTU RUL feature vector {vector_index} schema does not match protocol"
        )
    if vector.metadata.get("dataset_id") != _DATASET_ID:
        raise XjtuRulTargetError(
            f"XJTU RUL feature vector {vector_index} must preserve dataset_id {_DATASET_ID!r}"
        )


def _acquisition_index(vector: VibrationFeatureVector, *, vector_index: int) -> int:
    value = vector.metadata.get("acquisition_index")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise XjtuRulTargetError(
            f"XJTU RUL feature vector {vector_index} requires a positive integer acquisition_index"
        )
    return value
