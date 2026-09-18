import inspect
import json
from pathlib import Path

import pytest

from industrial_phm.adapters import get_xjtu_expected_acquisition_count
from industrial_phm.experiments import (
    XJTU_HOLDOUT_RESULT_SCHEMA_ID,
    XjtuHoldoutEvaluationError,
    evaluate_xjtu_fold_1_holdout,
    get_xjtu_finalized_configuration,
    get_xjtu_reference_split,
    write_xjtu_holdout_result,
)
from industrial_phm.features import VibrationFeatureVector

_CODE_REVISION = "c" * 40
_FOLD_1 = "fold-1"


def _fold_1() -> object:
    return next(fold for fold in get_xjtu_reference_split().folds if fold.fold_id == _FOLD_1)


def _vectors(assets: tuple[str, ...]) -> tuple[VibrationFeatureVector, ...]:
    config = get_xjtu_finalized_configuration()
    feature_names = tuple(config.selected_features)
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


def test_holdout_evaluation_exposes_no_selection_or_tuning_surface() -> None:
    parameters = set(inspect.signature(evaluate_xjtu_fold_1_holdout).parameters)

    assert parameters == {
        "train_vectors",
        "test_vectors",
        "code_revision",
        "source_acquisition_count",
    }


def test_holdout_evaluation_requires_full_git_revision_before_model_work() -> None:
    with pytest.raises(XjtuHoldoutEvaluationError, match="full 40-character"):
        evaluate_xjtu_fold_1_holdout(
            (),
            (),
            code_revision="c7d24f9",
            source_acquisition_count=0,
        )


def test_holdout_evaluation_scores_exactly_the_fold_1_test_bearings() -> None:
    fold = _fold_1()
    result = evaluate_xjtu_fold_1_holdout(
        _vectors(fold.train),  # type: ignore[attr-defined]
        _vectors(fold.test),  # type: ignore[attr-defined]
        code_revision=_CODE_REVISION,
        source_acquisition_count=9216,
    )

    assert result.partition == "test"
    assert {bearing.asset_id for bearing in result.bearing_results} == set(fold.test)  # type: ignore[attr-defined]
    assert result.experiment_id == get_xjtu_finalized_configuration().experiment_id
    assert result.reference_strategy == "train-bearing-early-third-v1"
    for bearing in result.bearing_results:
        assert bearing.full_run_observation_count == get_xjtu_expected_acquisition_count(
            bearing.asset_id
        )


def test_holdout_evaluation_rejects_validation_bearings_as_holdout_input() -> None:
    fold = _fold_1()

    with pytest.raises(ValueError, match="test bearing runs"):
        evaluate_xjtu_fold_1_holdout(
            _vectors(fold.train),  # type: ignore[attr-defined]
            _vectors(fold.validation),  # type: ignore[attr-defined]
            code_revision=_CODE_REVISION,
            source_acquisition_count=9216,
        )


def test_holdout_evaluation_records_both_statistics_without_ranking_them() -> None:
    fold = _fold_1()
    result = evaluate_xjtu_fold_1_holdout(
        _vectors(fold.train),  # type: ignore[attr-defined]
        _vectors(fold.test),  # type: ignore[attr-defined]
        code_revision=_CODE_REVISION,
        source_acquisition_count=9216,
    )

    assert result.mean_bearing_acquisition_order_spearman_rho is not None
    assert result.mean_bearing_late_vs_middle_rank_probability is not None
    for bearing in result.bearing_results:
        assert bearing.acquisition_order_spearman_rho is not None
        assert bearing.late_vs_middle_rank_probability is not None


def test_holdout_result_writes_deterministic_configuration_provenance(tmp_path: Path) -> None:
    fold = _fold_1()
    result = evaluate_xjtu_fold_1_holdout(
        _vectors(fold.train),  # type: ignore[attr-defined]
        _vectors(fold.test),  # type: ignore[attr-defined]
        code_revision=_CODE_REVISION,
        source_acquisition_count=9216,
    )
    output = tmp_path / "holdout.json"

    write_xjtu_holdout_result(result, output)
    first = output.read_text(encoding="utf-8")
    write_xjtu_holdout_result(result, output)

    assert output.read_text(encoding="utf-8") == first
    document = json.loads(first)
    assert document["schema_id"] == XJTU_HOLDOUT_RESULT_SCHEMA_ID
    assert document["partition"] == "test"
    assert document["code_revision"] == _CODE_REVISION
    assert document["configuration"]["reference_strategy"] == "train-bearing-early-third-v1"
    assert document["complete_train_observation_count"] == 3246
    assert document["reference_observation_count"] < 3246
    assert "selection_rule" not in document
    assert "decision_rule" not in document
