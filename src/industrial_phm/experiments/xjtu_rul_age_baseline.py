"""Leakage-safe age-only RUL baseline for XJTU-SY prognostics protocol v1."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from statistics import fmean
from typing import Literal

from industrial_phm.experiments.xjtu_rul import (
    XJTU_RUL_TARGET_DEFINITION_ID,
    XJTU_RUL_TARGET_UNIT,
    XjtuRulTargetError,
    get_xjtu_rul_partition_assets,
    validate_xjtu_recorded_end_rul_targets,
)
from industrial_phm.features import VibrationFeatureVector
from industrial_phm.prognostics import (
    RulPredictionObservation,
    RulPredictionSeries,
    RulTargetSeries,
)

XJTU_AGE_ONLY_RUL_METHOD_ID = "xjtu-sy-age-only-mean-train-endpoint-v1"

_DATASET_ID = "xjtu-sy"
_Partition = Literal["train", "validation", "test"]


class XjtuAgeOnlyRulBaselineError(ValueError):
    """Raised when the XJTU age-only RUL baseline contract is violated."""


@dataclass(frozen=True, slots=True)
class XjtuAgeOnlyRulBaseline:
    """Train-fitted mean-endpoint state for the protocol-defined age-only comparator."""

    train_asset_ids: Sequence[str]
    train_endpoint_acquisitions: Sequence[float]
    fitted_mean_endpoint_acquisition: float
    prediction_method_id: str = field(default=XJTU_AGE_ONLY_RUL_METHOD_ID, init=False)
    target_definition_id: str = field(default=XJTU_RUL_TARGET_DEFINITION_ID, init=False)
    unit: str = field(default=XJTU_RUL_TARGET_UNIT, init=False)

    def __post_init__(self) -> None:
        train_asset_ids = tuple(self.train_asset_ids)
        endpoints = tuple(float(value) for value in self.train_endpoint_acquisitions)
        if not train_asset_ids:
            raise XjtuAgeOnlyRulBaselineError("train_asset_ids must not be empty")
        if len(train_asset_ids) != len(set(train_asset_ids)):
            raise XjtuAgeOnlyRulBaselineError("train_asset_ids must be unique")
        if len(endpoints) != len(train_asset_ids):
            raise XjtuAgeOnlyRulBaselineError(
                "train_endpoint_acquisitions must align one-to-one with train_asset_ids"
            )
        if any(not math.isfinite(value) or value <= 0.0 for value in endpoints):
            raise XjtuAgeOnlyRulBaselineError(
                "train_endpoint_acquisitions must contain finite positive values"
            )
        expected_mean = float(fmean(endpoints))
        if (
            not math.isfinite(self.fitted_mean_endpoint_acquisition)
            or self.fitted_mean_endpoint_acquisition <= 0.0
            or self.fitted_mean_endpoint_acquisition != expected_mean
        ):
            raise XjtuAgeOnlyRulBaselineError(
                "fitted_mean_endpoint_acquisition must equal the train-bearing endpoint mean"
            )

        object.__setattr__(self, "train_asset_ids", train_asset_ids)
        object.__setattr__(self, "train_endpoint_acquisitions", endpoints)


def fit_xjtu_age_only_rul_baseline(
    train_targets: Sequence[RulTargetSeries],
) -> XjtuAgeOnlyRulBaseline:
    """Fit the age-only baseline using only complete fold-1 train RUL targets."""
    try:
        validated = validate_xjtu_recorded_end_rul_targets(
            train_targets,
            partition="train",
        )
    except XjtuRulTargetError as error:
        raise XjtuAgeOnlyRulBaselineError(
            f"invalid XJTU train targets for age-only baseline: {error}"
        ) from error

    endpoints = tuple(
        series.observations[0].remaining_useful_life + 1.0 for series in validated
    )
    return XjtuAgeOnlyRulBaseline(
        train_asset_ids=tuple(series.asset_id for series in validated),
        train_endpoint_acquisitions=endpoints,
        fitted_mean_endpoint_acquisition=float(fmean(endpoints)),
    )


def predict_xjtu_age_only_rul(
    baseline: XjtuAgeOnlyRulBaseline,
    vectors: Sequence[VibrationFeatureVector],
    *,
    partition: _Partition,
) -> tuple[RulPredictionSeries, ...]:
    """Predict RUL from train-fitted mean endpoint and current acquisition index only."""
    if not isinstance(baseline, XjtuAgeOnlyRulBaseline):
        raise XjtuAgeOnlyRulBaselineError(
            "baseline must be an XjtuAgeOnlyRulBaseline"
        )
    ordered = _ordered_prediction_vectors(vectors, partition=partition)

    return tuple(
        RulPredictionSeries(
            prediction_method_id=baseline.prediction_method_id,
            target_definition_id=baseline.target_definition_id,
            unit=baseline.unit,
            asset_id=asset_id,
            partition_id=partition,
            observations=tuple(
                RulPredictionObservation(
                    asset_id=asset_id,
                    partition_id=partition,
                    source_observation_id=f"{asset_id}:acquisition-{acquisition_index}",
                    predicted_remaining_useful_life=(
                        baseline.fitted_mean_endpoint_acquisition - acquisition_index
                    ),
                )
                for acquisition_index, _vector in asset_vectors
            ),
        )
        for asset_id, asset_vectors in ordered
    )


def _ordered_prediction_vectors(
    vectors: Sequence[VibrationFeatureVector],
    *,
    partition: _Partition,
) -> tuple[tuple[str, tuple[tuple[int, VibrationFeatureVector], ...]], ...]:
    if not vectors:
        raise XjtuAgeOnlyRulBaselineError(
            f"XJTU age-only {partition} prediction requires feature observations"
        )

    expected_assets = get_xjtu_rul_partition_assets(partition)
    expected_asset_set = set(expected_assets)
    by_asset: dict[str, dict[int, VibrationFeatureVector]] = defaultdict(dict)

    for vector_index, vector in enumerate(vectors):
        if not isinstance(vector, VibrationFeatureVector):
            raise XjtuAgeOnlyRulBaselineError(
                f"XJTU age-only feature observation {vector_index} "
                "must be a VibrationFeatureVector"
            )
        if vector.metadata.get("dataset_id") != _DATASET_ID:
            raise XjtuAgeOnlyRulBaselineError(
                f"XJTU age-only feature observation {vector_index} must preserve "
                f"dataset_id {_DATASET_ID!r}"
            )
        if vector.asset_id not in expected_asset_set:
            raise XjtuAgeOnlyRulBaselineError(
                f"XJTU age-only prediction received asset outside {partition}: "
                f"{vector.asset_id!r}"
            )

        acquisition_index = _positive_acquisition_index(vector, vector_index=vector_index)
        if acquisition_index in by_asset[vector.asset_id]:
            raise XjtuAgeOnlyRulBaselineError(
                f"XJTU age-only {partition} prediction contains duplicate acquisition "
                f"{acquisition_index} for {vector.asset_id}"
            )
        by_asset[vector.asset_id][acquisition_index] = vector

    observed_asset_set = set(by_asset)
    if observed_asset_set != expected_asset_set:
        raise XjtuAgeOnlyRulBaselineError(
            f"XJTU age-only prediction requires configured {partition} bearing runs; "
            f"missing={sorted(expected_asset_set - observed_asset_set)}, "
            f"unexpected={sorted(observed_asset_set - expected_asset_set)}"
        )

    ordered: list[tuple[str, tuple[tuple[int, VibrationFeatureVector], ...]]] = []
    for asset_id in expected_assets:
        observed_indices = sorted(by_asset[asset_id])
        expected_prefix = list(range(1, observed_indices[-1] + 1))
        if observed_indices != expected_prefix:
            raise XjtuAgeOnlyRulBaselineError(
                f"XJTU age-only prediction observations for {asset_id} "
                "must form a contiguous prefix starting at acquisition 1"
            )
        ordered.append(
            (
                asset_id,
                tuple(
                    (acquisition_index, by_asset[asset_id][acquisition_index])
                    for acquisition_index in observed_indices
                ),
            )
        )
    return tuple(ordered)


def _positive_acquisition_index(
    vector: VibrationFeatureVector,
    *,
    vector_index: int,
) -> int:
    value = vector.metadata.get("acquisition_index")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise XjtuAgeOnlyRulBaselineError(
            f"XJTU age-only feature observation {vector_index} requires "
            "a positive integer acquisition_index"
        )
    return value
