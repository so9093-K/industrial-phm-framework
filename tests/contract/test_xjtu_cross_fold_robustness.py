import json
from dataclasses import replace
from pathlib import Path

import pytest

from industrial_phm.adapters import get_xjtu_expected_acquisition_count
from industrial_phm.experiments import (
    XJTU_CROSS_FOLD_RESULT_SCHEMA_ID,
    XjtuCrossFoldRobustnessError,
    evaluate_xjtu_cross_fold_robustness,
    fold_scoped_configuration,
    get_xjtu_finalized_configuration,
    get_xjtu_reference_split,
    write_xjtu_cross_fold_robustness_result,
)
from industrial_phm.features import VibrationFeatureVector

_CODE_REVISION = "d" * 40
_ROBUSTNESS_FOLDS = ("fold-2", "fold-3", "fold-4", "fold-5")


def _all_vectors() -> tuple[VibrationFeatureVector, ...]:
    config = get_xjtu_finalized_configuration()
    feature_names = tuple(config.selected_features)
    assets = sorted(
        {
            asset_id
            for fold in get_xjtu_reference_split().folds
            for asset_id in (*fold.train, *fold.validation, *fold.test)
        }
    )
    return tuple(
        VibrationFeatureVector(
            feature_set_id=config.feature_set_id,
            asset_id=asset_id,
            feature_names=feature_names,
            values=tuple(
                float(acquisition_index + position) for position in range(len(feature_names))
            ),
            metadata={
                "dataset_id": "xjtu-sy",
                "operating_condition": f"condition-{asset_id[len('Bearing')]}",
                "acquisition_index": acquisition_index,
            },
        )
        for asset_id in assets
        for acquisition_index in range(1, get_xjtu_expected_acquisition_count(asset_id) + 1)
    )


def _result():
    return evaluate_xjtu_cross_fold_robustness(
        _all_vectors(),
        code_revision=_CODE_REVISION,
        source_acquisition_count=9216,
    )


def test_fold_scoped_configuration_changes_only_the_fold_target() -> None:
    finalized = get_xjtu_finalized_configuration()

    scoped = fold_scoped_configuration(finalized, "fold-3")

    assert scoped.fold_id == "fold-3"
    assert scoped.experiment_id != finalized.experiment_id
    assert "fold-3" in scoped.experiment_id
    for axis in (
        "dataset_id",
        "split_id",
        "fit_partition",
        "feature_set_id",
        "reference_strategy",
        "sampling_policy_id",
        "scaling_strategy",
        "model_family",
        "random_seed",
    ):
        assert getattr(scoped, axis) == getattr(finalized, axis), axis
    assert tuple(scoped.selected_features) == tuple(finalized.selected_features)
    assert dict(scoped.model_parameters) == dict(finalized.model_parameters)


def test_fold_scoped_configuration_refuses_the_consumed_holdout_fold() -> None:
    with pytest.raises(XjtuCrossFoldRobustnessError, match="cross-fold robustness covers"):
        fold_scoped_configuration(get_xjtu_finalized_configuration(), "fold-1")


def test_cross_fold_run_never_scores_fold_1_or_any_validation_partition() -> None:
    split = get_xjtu_reference_split()
    folds = {fold.fold_id: fold for fold in split.folds}
    result = _result()

    assert tuple(fold.fold_id for fold in result.folds) == _ROBUSTNESS_FOLDS
    for fold_result in result.folds:
        expected = folds[fold_result.fold_id]
        scored = {bearing.asset_id for bearing in fold_result.bearing_results}
        assert scored == set(expected.test)
        assert not (scored & set(expected.validation))
    assert "fold-1" not in {fold.fold_id for fold in result.folds}


def test_cross_fold_run_covers_twelve_test_bearings_in_one_pass() -> None:
    result = _result()

    bearings = [bearing for fold in result.folds for bearing in fold.bearing_results]
    assert len(bearings) == 12
    assert result.overall_bearing_count == 12
    assert {summary.bearing_count for summary in result.condition_summaries} == {4}
    assert len(result.condition_summaries) == 3


def test_cross_fold_refits_preprocessing_per_fold() -> None:
    result = _result()

    complete_counts = {fold.complete_train_observation_count for fold in result.folds}
    assert len(complete_counts) > 1
    for fold in result.folds:
        assert fold.reference_observation_count < fold.complete_train_observation_count
        assert fold.model_fit_observation_count == fold.reference_observation_count


def test_cross_fold_result_records_only_the_frozen_summaries(tmp_path: Path) -> None:
    output = tmp_path / "cross-fold.json"
    result = _result()

    write_xjtu_cross_fold_robustness_result(result, output)
    first = output.read_text(encoding="utf-8")
    write_xjtu_cross_fold_robustness_result(result, output)

    assert output.read_text(encoding="utf-8") == first
    document = json.loads(first)
    assert document["schema_id"] == XJTU_CROSS_FOLD_RESULT_SCHEMA_ID
    assert document["evaluated_folds"] == list(_ROBUSTNESS_FOLDS)
    assert document["scored_partition"] == "test"
    assert set(document["overall_summary"]) == {
        "bearing_count",
        "mean_bearing_acquisition_order_spearman_rho",
        "mean_bearing_late_vs_middle_rank_probability",
    }
    assert _keys(document).isdisjoint(
        {
            "p_value",
            "threshold",
            "pooled_mean",
            "weighted_mean",
            "pass_fail",
            "selection_rule",
            "decision_rule",
            "ranking",
        }
    )
    assert "fold-1" not in {fold["fold_id"] for fold in document["folds"]}


def _keys(node: object) -> set[str]:
    if isinstance(node, dict):
        return set(node) | {key for value in node.values() for key in _keys(value)}
    if isinstance(node, list):
        return {key for item in node for key in _keys(item)}
    return set()


def test_cross_fold_execution_requires_full_git_revision_before_model_work() -> None:
    with pytest.raises(XjtuCrossFoldRobustnessError, match="full 40-character"):
        evaluate_xjtu_cross_fold_robustness(
            (),
            code_revision="ec1b983",
            source_acquisition_count=0,
        )


def test_cross_fold_refuses_to_record_a_partial_run() -> None:
    config = get_xjtu_finalized_configuration()
    constant = tuple(
        replace(vector, values=(0.0,) * len(vector.feature_names)) for vector in _all_vectors()
    )
    del config

    with pytest.raises(XjtuCrossFoldRobustnessError, match="undefined statistic"):
        evaluate_xjtu_cross_fold_robustness(
            constant,
            code_revision=_CODE_REVISION,
            source_acquisition_count=9216,
        )
