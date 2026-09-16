from dataclasses import replace

import pytest

from industrial_phm.experiments import (
    XjtuExperimentProtocolError,
    get_xjtu_reference_split,
)


def test_packaged_xjtu_reference_split_has_stable_rotating_holdout_assignments() -> None:
    manifest = get_xjtu_reference_split()

    assert manifest.split_id == "xjtu-sy-condition-stratified-5fold-v1"
    assert manifest.dataset_id == "xjtu-sy"
    assert manifest.split_unit == "bearing-run"
    assert manifest.strategy == "condition-stratified-rotating-holdout"
    assert tuple(fold.fold_id for fold in manifest.folds) == (
        "fold-1",
        "fold-2",
        "fold-3",
        "fold-4",
        "fold-5",
    )

    first = manifest.folds[0]
    assert first.validation == ("Bearing1_2", "Bearing2_2", "Bearing3_2")
    assert first.test == ("Bearing1_1", "Bearing2_1", "Bearing3_1")
    assert set(first.train) == {
        "Bearing1_3",
        "Bearing1_4",
        "Bearing1_5",
        "Bearing2_3",
        "Bearing2_4",
        "Bearing2_5",
        "Bearing3_3",
        "Bearing3_4",
        "Bearing3_5",
    }


def test_xjtu_split_contract_rejects_bearing_run_leakage() -> None:
    manifest = get_xjtu_reference_split()
    first = manifest.folds[0]
    leaking_first = replace(
        first,
        validation=(*first.validation, first.test[0]),
    )
    invalid = replace(manifest, folds=(leaking_first, *manifest.folds[1:]))

    with pytest.raises(XjtuExperimentProtocolError, match="bearing-run leakage"):
        invalid.validate()
