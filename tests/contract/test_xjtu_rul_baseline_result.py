import json
from dataclasses import replace
from pathlib import Path
from statistics import fmean
from typing import cast

import pytest

from industrial_phm.adapters import get_xjtu_expected_acquisition_count
from industrial_phm.experiments import (
    XJTU_AGE_ONLY_RUL_METHOD_ID,
    XJTU_FEATURE_RIDGE_RUL_METHOD_ID,
    XJTU_RUL_BASELINE_VALIDATION_EVIDENCE_CLASS,
    XJTU_RUL_BASELINE_VALIDATION_RESULT_SCHEMA_ID,
    XJTU_RUL_TARGET_DEFINITION_ID,
    XJTU_RUL_TARGET_UNIT,
    XjtuRulBaselineValidationResult,
    XjtuRulBaselineValidationResultError,
    evaluate_xjtu_rul_point_predictions,
    get_xjtu_feature_rul_configuration,
    get_xjtu_reference_split,
    write_xjtu_rul_baseline_validation_result,
)
from industrial_phm.prognostics import (
    RulPredictionObservation,
    RulPredictionSeries,
    RulTargetObservation,
    RulTargetSeries,
)


def _targets() -> tuple[RulTargetSeries, ...]:
    return tuple(
        RulTargetSeries(
            target_definition_id=XJTU_RUL_TARGET_DEFINITION_ID,
            unit=XJTU_RUL_TARGET_UNIT,
            asset_id=asset_id,
            partition_id="validation",
            observations=tuple(
                RulTargetObservation(
                    asset_id=asset_id,
                    partition_id="validation",
                    source_observation_id=f"{asset_id}:acquisition-{index}",
                    remaining_useful_life=float(run_length - index),
                )
                for index in range(1, run_length + 1)
            ),
        )
        for asset_id in get_xjtu_reference_split().folds[0].validation
        for run_length in (get_xjtu_expected_acquisition_count(asset_id),)
    )


def _predictions(
    method_id: str,
    *,
    offset: float,
) -> tuple[RulPredictionSeries, ...]:
    return tuple(
        RulPredictionSeries(
            prediction_method_id=method_id,
            target_definition_id=series.target_definition_id,
            unit=series.unit,
            asset_id=series.asset_id,
            partition_id=series.partition_id,
            observations=tuple(
                RulPredictionObservation(
                    asset_id=series.asset_id,
                    partition_id=series.partition_id,
                    source_observation_id=observation.source_observation_id,
                    predicted_remaining_useful_life=(
                        observation.remaining_useful_life + offset
                    ),
                )
                for observation in series.observations
            ),
        )
        for series in _targets()
    )


def _result() -> XjtuRulBaselineValidationResult:
    fold = get_xjtu_reference_split().folds[0]
    config = get_xjtu_feature_rul_configuration()
    age_predictions = _predictions(XJTU_AGE_ONLY_RUL_METHOD_ID, offset=2.0)
    feature_predictions = _predictions(XJTU_FEATURE_RIDGE_RUL_METHOD_ID, offset=1.0)
    targets = _targets()
    age_evaluation = evaluate_xjtu_rul_point_predictions(
        targets,
        age_predictions,
        partition="validation",
    )
    feature_evaluation = evaluate_xjtu_rul_point_predictions(
        targets,
        feature_predictions,
        partition="validation",
    )
    endpoints = tuple(
        float(get_xjtu_expected_acquisition_count(asset_id))
        for asset_id in fold.train
    )
    feature_count = len(config.selected_features)
    return XjtuRulBaselineValidationResult(
        code_revision="a" * 40,
        source_acquisition_count=9_216,
        dataset_id=config.dataset_id,
        split_id=config.split_id,
        fold_id=config.fold_id,
        target_definition_id=XJTU_RUL_TARGET_DEFINITION_ID,
        target_unit=XJTU_RUL_TARGET_UNIT,
        train_source_acquisition_count=3_246,
        validation_source_acquisition_count=2_818,
        age_train_asset_ids=fold.train,
        age_train_endpoint_acquisitions=endpoints,
        age_fitted_mean_endpoint_acquisition=float(fmean(endpoints)),
        age_predictions=age_predictions,
        age_evaluation=age_evaluation,
        feature_set_id=config.feature_set_id,
        selected_features=tuple(config.selected_features),
        feature_fit_partition=config.fit_partition.value,
        feature_scaling_strategy=config.scaling_strategy.value,
        feature_preprocessing_fit_observation_count=3_246,
        feature_fitted_center=(0.0,) * feature_count,
        feature_fitted_scale=(1.0,) * feature_count,
        feature_zero_iqr_features=(),
        feature_reference_strategy=config.reference_strategy.value,
        feature_sampling_policy_id=config.sampling_policy_id,
        feature_model_family=config.model_family.value,
        feature_model_parameters=tuple(sorted(config.model_parameters.items())),
        feature_random_seed=config.random_seed,
        feature_model_fit_observation_count=3_246,
        feature_predictions=feature_predictions,
        feature_evaluation=feature_evaluation,
    )


def test_xjtu_rul_baseline_result_writes_reviewable_validation_evidence(
    tmp_path: Path,
) -> None:
    output = tmp_path / "rul-baselines.json"

    write_xjtu_rul_baseline_validation_result(_result(), output)

    document = cast(dict[str, object], json.loads(output.read_text(encoding="utf-8")))
    assert document["schema_id"] == XJTU_RUL_BASELINE_VALIDATION_RESULT_SCHEMA_ID

    provenance = cast(dict[str, object], document["provenance"])
    assert provenance["evidence_class"] == XJTU_RUL_BASELINE_VALIDATION_EVIDENCE_CLASS
    assert provenance["code_revision"] == "a" * 40

    source_scope = cast(dict[str, object], document["source_scope"])
    assert source_scope["validation_bearings"] == [
        "Bearing1_2",
        "Bearing2_2",
        "Bearing3_2",
    ]
    assert source_scope["excluded"] == [
        "test:Bearing1_1",
        "test:Bearing2_1",
        "test:Bearing3_1",
    ]

    target = cast(dict[str, object], document["target"])
    assert target["definition_id"] == XJTU_RUL_TARGET_DEFINITION_ID
    assert target["formula"] == "N-k"
    assert target["target_clipping"] is False

    methods = cast(list[dict[str, object]], document["methods"])
    assert [method["method_id"] for method in methods] == [
        XJTU_AGE_ONLY_RUL_METHOD_ID,
        XJTU_FEATURE_RIDGE_RUL_METHOD_ID,
    ]
    assert cast(dict[str, object], methods[0]["evaluation"])[
        "mean_asset_mean_absolute_error"
    ] == pytest.approx(2.0)
    assert cast(dict[str, object], methods[1]["evaluation"])[
        "mean_asset_mean_absolute_error"
    ] == pytest.approx(1.0)

    feature_predictions = cast(list[dict[str, object]], methods[1]["predictions"])
    assert sum(
        len(cast(list[object], series["observations"]))
        for series in feature_predictions
    ) == 2_818

    comparison = cast(dict[str, object], document["comparison"])
    assert comparison["feature_minus_age_mean_asset_mae"] == pytest.approx(-1.0)
    assert comparison["feature_minus_age_mean_asset_rmse"] == pytest.approx(-1.0)


def test_xjtu_rul_baseline_result_rejects_non_revision_identity() -> None:
    with pytest.raises(XjtuRulBaselineValidationResultError, match="40-character"):
        replace(_result(), code_revision="not-a-revision")


def test_xjtu_rul_baseline_result_rejects_incomplete_prediction_population() -> None:
    result = _result()
    first = result.feature_predictions[0]
    incomplete_first = replace(first, observations=first.observations[:-1])

    with pytest.raises(
        XjtuRulBaselineValidationResultError,
        match="must contain 161 acquisitions",
    ):
        replace(
            result,
            feature_predictions=(incomplete_first, *result.feature_predictions[1:]),
        )


def test_xjtu_rul_baseline_result_rejects_test_partition_prediction() -> None:
    result = _result()
    first = result.age_predictions[0]
    invalid_observations = tuple(
        replace(observation, partition_id="test")
        for observation in first.observations
    )
    invalid_first = replace(
        first,
        partition_id="test",
        observations=invalid_observations,
    )

    with pytest.raises(
        XjtuRulBaselineValidationResultError,
        match="validation predictions",
    ):
        replace(
            result,
            age_predictions=(invalid_first, *result.age_predictions[1:]),
        )
