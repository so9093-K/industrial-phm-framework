from dataclasses import replace
from functools import cache
from itertools import pairwise

import pytest

from industrial_phm.adapters import XJTU_SY_CHANNELS, get_xjtu_expected_acquisition_count
from industrial_phm.experiments import (
    XJTU_RUL_PROTOCOL_ID,
    XJTU_RUL_TARGET_DEFINITION_ID,
    XJTU_RUL_TARGET_UNIT,
    XjtuRulTargetError,
    build_xjtu_recorded_end_rul_targets,
    get_xjtu_reference_split,
)
from industrial_phm.features import (
    VIBRATION_STATISTICAL_FEATURE_SET_ID,
    VibrationFeatureVector,
    vibration_feature_names,
)

_FEATURE_NAMES = vibration_feature_names(XJTU_SY_CHANNELS)


@cache
def _vectors(partition: str) -> tuple[VibrationFeatureVector, ...]:
    fold = get_xjtu_reference_split().folds[0]
    vectors: list[VibrationFeatureVector] = []
    for asset_id in getattr(fold, partition):
        for acquisition_index in range(1, get_xjtu_expected_acquisition_count(asset_id) + 1):
            vectors.append(
                VibrationFeatureVector(
                    feature_set_id=VIBRATION_STATISTICAL_FEATURE_SET_ID,
                    asset_id=asset_id,
                    feature_names=_FEATURE_NAMES,
                    values=tuple(
                        float(acquisition_index + feature_index)
                        for feature_index in range(len(_FEATURE_NAMES))
                    ),
                    metadata={
                        "dataset_id": "xjtu-sy",
                        "acquisition_index": acquisition_index,
                    },
                )
            )
    return tuple(vectors)


def test_xjtu_rul_targets_preserve_fold_1_population_and_recorded_end_semantics() -> None:
    targets = build_xjtu_recorded_end_rul_targets(_vectors("train"), partition="train")

    assert XJTU_RUL_PROTOCOL_ID == "xjtu-sy-recorded-end-rul-v1"
    assert len(targets) == 9
    assert sum(len(series.observations) for series in targets) == 3_246
    assert all(series.target_definition_id == XJTU_RUL_TARGET_DEFINITION_ID for series in targets)
    assert all(series.unit == XJTU_RUL_TARGET_UNIT for series in targets)
    assert all(series.partition_id == "train" for series in targets)

    for series in targets:
        run_length = get_xjtu_expected_acquisition_count(series.asset_id)
        assert series.observations[0].remaining_useful_life == float(run_length - 1)
        assert series.observations[-1].remaining_useful_life == 0.0
        assert all(
            current.remaining_useful_life == previous.remaining_useful_life - 1.0
            for previous, current in pairwise(series.observations)
        )

    by_asset = {series.asset_id: series for series in targets}
    bearing = by_asset["Bearing1_5"]
    assert len(bearing.observations) == 52
    assert bearing.observations[0].source_observation_id == "Bearing1_5:acquisition-1"
    assert bearing.observations[0].remaining_useful_life == 51.0
    assert bearing.observations[1].remaining_useful_life == 50.0
    assert bearing.observations[-1].source_observation_id == "Bearing1_5:acquisition-52"
    assert bearing.observations[-1].remaining_useful_life == 0.0


def test_xjtu_rul_targets_cover_validation_and_held_out_benchmark_without_row_leakage() -> None:
    validation = build_xjtu_recorded_end_rul_targets(
        _vectors("validation"),
        partition="validation",
    )
    held_out = build_xjtu_recorded_end_rul_targets(_vectors("test"), partition="test")

    assert {series.asset_id for series in validation} == {
        "Bearing1_2",
        "Bearing2_2",
        "Bearing3_2",
    }
    assert {series.asset_id for series in held_out} == {
        "Bearing1_1",
        "Bearing2_1",
        "Bearing3_1",
    }
    assert sum(len(series.observations) for series in validation) == 2_818
    assert sum(len(series.observations) for series in held_out) == 3_152
    assert {series.asset_id for series in validation}.isdisjoint(
        series.asset_id for series in held_out
    )


def test_xjtu_rul_targets_canonicalize_reversed_feature_input() -> None:
    expected = build_xjtu_recorded_end_rul_targets(_vectors("validation"), partition="validation")
    reordered = build_xjtu_recorded_end_rul_targets(
        tuple(reversed(_vectors("validation"))),
        partition="validation",
    )

    assert reordered == expected


def test_xjtu_rul_targets_reject_incomplete_partition_coverage() -> None:
    with pytest.raises(XjtuRulTargetError, match="complete validation acquisition"):
        build_xjtu_recorded_end_rul_targets(
            _vectors("validation")[:-1],
            partition="validation",
        )


def test_xjtu_rul_targets_reject_duplicate_acquisition_identity() -> None:
    train = _vectors("train")
    duplicate = replace(
        train[0],
        metadata={"dataset_id": "xjtu-sy", "acquisition_index": 2},
    )

    with pytest.raises(XjtuRulTargetError, match="duplicate acquisition 2"):
        build_xjtu_recorded_end_rul_targets(
            (duplicate, *train[1:]),
            partition="train",
        )


def test_xjtu_rul_targets_reject_dataset_identity_drift() -> None:
    validation = _vectors("validation")
    invalid = replace(
        validation[0],
        metadata={"dataset_id": "another-dataset", "acquisition_index": 1},
    )

    with pytest.raises(XjtuRulTargetError, match="dataset_id"):
        build_xjtu_recorded_end_rul_targets(
            (invalid, *validation[1:]),
            partition="validation",
        )


def test_xjtu_rul_targets_reject_feature_schema_drift() -> None:
    validation = _vectors("validation")
    invalid = replace(
        validation[0],
        feature_names=tuple(reversed(validation[0].feature_names)),
        values=tuple(reversed(validation[0].values)),
    )

    with pytest.raises(XjtuRulTargetError, match="schema"):
        build_xjtu_recorded_end_rul_targets(
            (invalid, *validation[1:]),
            partition="validation",
        )


def test_xjtu_rul_targets_reject_unknown_partition() -> None:
    with pytest.raises(XjtuRulTargetError, match="partition must be"):
        build_xjtu_recorded_end_rul_targets(
            _vectors("train"),
            partition="benchmark",  # type: ignore[arg-type]
        )
