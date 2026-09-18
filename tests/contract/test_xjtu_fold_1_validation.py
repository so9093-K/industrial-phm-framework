import json
from dataclasses import replace
from pathlib import Path

import pytest

from industrial_phm.adapters import get_xjtu_expected_acquisition_count
from industrial_phm.experiments import (
    XJTU_CANDIDATE_SELECTION_RULE_ID,
    XJTU_FOLD_1_VALIDATION_SCHEMA_ID,
    XjtuBearingScoreEvaluation,
    XjtuCandidateValidationResult,
    XjtuDevelopmentEvaluation,
    XjtuFoldValidationError,
    XjtuFoldValidationResult,
    evaluate_xjtu_fold_1_candidates,
    get_xjtu_isolation_forest_candidates,
    get_xjtu_reference_split,
    select_xjtu_validation_candidate,
    write_xjtu_fold_1_validation_result,
)
from industrial_phm.features import VibrationFeatureVector

_CODE_REVISION = "a" * 40


def _candidate_result(
    index: int,
    mean_rho: float | None,
) -> XjtuCandidateValidationResult:
    config = get_xjtu_isolation_forest_candidates()[index]
    bearing_results = tuple(
        XjtuBearingScoreEvaluation(
            asset_id=f"Bearing{condition}_2",
            operating_condition=f"condition-{condition}",
            observation_count=condition + 1,
            acquisition_order_spearman_rho=mean_rho,
        )
        for condition in range(1, 4)
    )
    return XjtuCandidateValidationResult(
        experiment_id=config.experiment_id,
        feature_set_id=config.feature_set_id,
        selected_features=tuple(config.selected_features),
        sampling_policy_id=config.sampling_policy_id,
        scaling_strategy=config.scaling_strategy.value,
        model_family=config.model_family.value,
        model_parameters=tuple(sorted(config.model_parameters.items())),
        random_seed=config.random_seed,
        source_observation_count=100,
        fit_observation_count=100,
        evaluation=XjtuDevelopmentEvaluation(
            experiment_id=config.experiment_id,
            split_id=config.split_id,
            fold_id=config.fold_id,
            bearing_results=bearing_results,
            mean_bearing_acquisition_order_spearman_rho=mean_rho,
        ),
    )


def test_candidate_selection_maximizes_defined_mean_rho() -> None:
    candidates = (
        _candidate_result(0, None),
        _candidate_result(1, 0.4),
        _candidate_result(2, 0.6),
        _candidate_result(3, 0.5),
    )

    selected = select_xjtu_validation_candidate(candidates)

    assert selected.experiment_id == candidates[2].experiment_id


def test_candidate_selection_uses_frozen_simplicity_tie_breakers() -> None:
    candidates = tuple(_candidate_result(index, 0.5) for index in range(4))

    selected = select_xjtu_validation_candidate(candidates)

    assert len(selected.selected_features) == 14
    assert selected.sampling_policy_id == "acquisition-uniform-v1"


def test_candidate_selection_rejects_all_undefined_means() -> None:
    with pytest.raises(XjtuFoldValidationError, match="at least one defined"):
        select_xjtu_validation_candidate(
            tuple(_candidate_result(index, None) for index in range(4))
        )


def test_validation_result_writes_complete_deterministic_evidence(tmp_path: Path) -> None:
    candidate = _candidate_result(1, 0.75)
    result = XjtuFoldValidationResult(
        code_revision=_CODE_REVISION,
        dataset_id="xjtu-sy",
        split_id="xjtu-sy-condition-stratified-5fold-v1",
        fold_id="fold-1",
        partition="validation",
        source_acquisition_count=10_000,
        candidates=(candidate,),
        selected_experiment_id=candidate.experiment_id,
    )
    output = tmp_path / "result.json"

    write_xjtu_fold_1_validation_result(result, output)
    first_content = output.read_text(encoding="utf-8")
    write_xjtu_fold_1_validation_result(result, output)

    assert output.read_text(encoding="utf-8") == first_content
    document = json.loads(first_content)
    assert document["schema_id"] == XJTU_FOLD_1_VALIDATION_SCHEMA_ID
    assert document["code_revision"] == _CODE_REVISION
    assert document["selection_rule"]["id"] == XJTU_CANDIDATE_SELECTION_RULE_ID
    assert document["selected_experiment_id"] == candidate.experiment_id
    assert document["candidates"][0]["validation_bearings"][0] == {
        "acquisition_order_spearman_rho": 0.75,
        "asset_id": "Bearing1_2",
        "observation_count": 2,
        "operating_condition": "condition-1",
    }


def test_validation_execution_requires_full_git_revision_before_model_work() -> None:
    with pytest.raises(XjtuFoldValidationError, match="full 40-character"):
        evaluate_xjtu_fold_1_candidates(
            (),
            (),
            code_revision="067778d",
            source_acquisition_count=0,
        )


def test_candidate_selection_uses_experiment_id_as_total_order() -> None:
    candidate = _candidate_result(1, 0.5)
    later = replace(candidate, experiment_id="z-candidate")
    earlier = replace(candidate, experiment_id="a-candidate")

    assert select_xjtu_validation_candidate((later, earlier)) is earlier


def _fold_1_vectors(assets: tuple[str, ...]) -> tuple[VibrationFeatureVector, ...]:
    config = get_xjtu_isolation_forest_candidates()[0]
    feature_names = tuple(config.selected_features)
    vectors: list[VibrationFeatureVector] = []
    for asset_id in assets:
        condition = f"condition-{asset_id[len('Bearing')]}"
        for acquisition_index in range(1, get_xjtu_expected_acquisition_count(asset_id) + 1):
            vectors.append(
                VibrationFeatureVector(
                    feature_set_id=config.feature_set_id,
                    asset_id=asset_id,
                    feature_names=feature_names,
                    values=tuple(
                        float(acquisition_index + position)
                        for position in range(len(feature_names))
                    ),
                    metadata={
                        "dataset_id": "xjtu-sy",
                        "operating_condition": condition,
                        "acquisition_index": acquisition_index,
                    },
                )
            )
    return tuple(vectors)


def test_train_partition_is_scored_only_when_diagnosis_is_requested() -> None:
    fold = next(item for item in get_xjtu_reference_split().folds if item.fold_id == "fold-1")
    train_vectors = _fold_1_vectors(fold.train)
    validation_vectors = _fold_1_vectors(fold.validation)

    without = evaluate_xjtu_fold_1_candidates(
        train_vectors,
        validation_vectors,
        code_revision=_CODE_REVISION,
        source_acquisition_count=9216,
    )
    with_diagnosis = evaluate_xjtu_fold_1_candidates(
        train_vectors,
        validation_vectors,
        code_revision=_CODE_REVISION,
        source_acquisition_count=9216,
        collect_score_trajectories=True,
    )

    assert without.score_trajectories == ()
    assert len(with_diagnosis.score_trajectories) == len(with_diagnosis.candidates)
    scored = {
        (bearing.partition, bearing.asset_id)
        for bearing in with_diagnosis.score_trajectories[0].bearings
    }
    assert {asset_id for partition, asset_id in scored if partition == "train"} == set(fold.train)
    assert without.selected_experiment_id == with_diagnosis.selected_experiment_id
    assert without.candidates == with_diagnosis.candidates
