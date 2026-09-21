import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from industrial_phm.adapters import get_xjtu_expected_acquisition_count
from industrial_phm.experiments import (
    XJTU_RUL_LSTM_BENCHMARK_EVIDENCE_CLASS,
    XJTU_RUL_LSTM_BENCHMARK_RESULT_SCHEMA_ID,
    XJTU_RUL_LSTM_METHOD_ID,
    XJTU_RUL_TARGET_DEFINITION_ID,
    XJTU_RUL_TARGET_UNIT,
    XjtuRulLstmBenchmarkResult,
    XjtuRulLstmBenchmarkResultError,
    evaluate_xjtu_rul_lifecycle_position_errors,
    evaluate_xjtu_rul_point_predictions,
    get_xjtu_reference_split,
    get_xjtu_rul_lstm_configuration,
    run_xjtu_rul_lstm_heldout_benchmark,
    write_xjtu_rul_lstm_benchmark_result,
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
            partition_id="test",
            observations=tuple(
                RulTargetObservation(
                    asset_id=asset_id,
                    partition_id="test",
                    source_observation_id=f"{asset_id}:acquisition-{index}",
                    remaining_useful_life=float(run_length - index),
                )
                for index in range(1, run_length + 1)
            ),
        )
        for asset_id in get_xjtu_reference_split().folds[0].test
        for run_length in (get_xjtu_expected_acquisition_count(asset_id),)
    )


def _predictions() -> tuple[RulPredictionSeries, ...]:
    return tuple(
        RulPredictionSeries(
            prediction_method_id=XJTU_RUL_LSTM_METHOD_ID,
            target_definition_id=series.target_definition_id,
            unit=series.unit,
            asset_id=series.asset_id,
            partition_id="test",
            observations=tuple(
                RulPredictionObservation(
                    asset_id=series.asset_id,
                    partition_id="test",
                    source_observation_id=observation.source_observation_id,
                    predicted_remaining_useful_life=observation.remaining_useful_life + 1.0,
                )
                for observation in series.observations[7:]
            ),
        )
        for series in _targets()
    )


def _result() -> XjtuRulLstmBenchmarkResult:
    config = get_xjtu_rul_lstm_configuration()
    targets = _targets()
    predictions = _predictions()
    feature_count = len(config.selected_features)
    benchmark_count = sum(len(series.observations) for series in targets)
    return XjtuRulLstmBenchmarkResult(
        code_revision="a" * 40,
        source_acquisition_count=9_216,
        dataset_id=config.dataset_id,
        split_id=config.split_id,
        fold_id=config.fold_id,
        train_source_acquisition_count=3_246,
        benchmark_source_acquisition_count=benchmark_count,
        feature_set_id=config.feature_set_id,
        selected_features=tuple(config.selected_features),
        preprocessing_fit_partition="train",
        scaling_strategy="robust",
        preprocessing_fit_observation_count=3_246,
        fitted_center=(0.0,) * feature_count,
        fitted_scale=(1.0,) * feature_count,
        zero_iqr_features=(),
        sequence_length=8,
        sequence_stride=1,
        sequence_alignment="right-edge",
        train_window_count=3_183,
        model_family="lstm-regression",
        model_parameters=tuple(sorted(config.model_parameters.items())),
        random_seed=42,
        sampling_policy_id="sequence-window-uniform-v1",
        runtime="pytorch",
        runtime_version="test-runtime",
        device="cpu",
        numeric_precision="float32",
        deterministic_algorithms=True,
        parameter_count=6_433,
        batch_size=64,
        epochs=50,
        epoch_losses=tuple(float(50 - index) for index in range(50)),
        predictions=predictions,
        point_evaluation=evaluate_xjtu_rul_point_predictions(
            targets,
            predictions,
            partition="test",
        ),
        lifecycle_evaluation=evaluate_xjtu_rul_lifecycle_position_errors(
            targets,
            predictions,
            partition="test",
        ),
    )


def test_benchmark_result_records_frozen_candidate_and_scope(tmp_path: Path) -> None:
    output = tmp_path / "benchmark.json"

    write_xjtu_rul_lstm_benchmark_result(_result(), output)

    document = cast(dict[str, object], json.loads(output.read_text(encoding="utf-8")))
    assert document["schema_id"] == XJTU_RUL_LSTM_BENCHMARK_RESULT_SCHEMA_ID
    provenance = cast(dict[str, object], document["provenance"])
    assert provenance["evidence_class"] == XJTU_RUL_LSTM_BENCHMARK_EVIDENCE_CLASS

    selection = cast(dict[str, object], document["selection"])
    assert selection["validation_selected_method_id"] == XJTU_RUL_LSTM_METHOD_ID
    assert selection["operational_primary_method_id"] is None

    source_scope = cast(dict[str, object], document["source_scope"])
    assert source_scope["benchmark_bearings"] == [
        "Bearing1_1",
        "Bearing2_1",
        "Bearing3_1",
    ]
    assert "not a pristine external holdout" in cast(
        str,
        source_scope["project_history_limitation"],
    )

    capability = cast(dict[str, object], document["capability_scope"])
    unsupported = cast(list[str], capability["unsupported_or_not_validated"])
    assert "prediction-interval" in unsupported
    assert "uncertainty-calibration" in unsupported


def test_benchmark_result_records_point_and_lifecycle_evidence(tmp_path: Path) -> None:
    output = tmp_path / "benchmark.json"

    write_xjtu_rul_lstm_benchmark_result(_result(), output)

    document = cast(dict[str, object], json.loads(output.read_text(encoding="utf-8")))
    evaluation = cast(dict[str, object], document["evaluation"])
    point = cast(dict[str, object], evaluation["point"])
    lifecycle = cast(dict[str, object], evaluation["lifecycle_position"])

    assert point["mean_asset_mean_absolute_error"] == 1.0
    summaries = cast(list[dict[str, object]], lifecycle["position_summaries"])
    assert [item["position"] for item in summaries] == ["early", "middle", "late"]
    assert all(item["bearing_count"] == 3 for item in summaries)
    assert all(item["mean_asset_mean_absolute_error"] == 1.0 for item in summaries)


def test_benchmark_result_rejects_non_selected_method() -> None:
    result = _result()
    first = result.predictions[0]
    invalid = replace(first, prediction_method_id="another-method")

    with pytest.raises(
        XjtuRulLstmBenchmarkResultError,
        match="validation-selected LSTM",
    ):
        replace(result, predictions=(invalid, *result.predictions[1:]))


def test_benchmark_runner_rejects_invalid_revision_before_source_io(tmp_path: Path) -> None:
    with pytest.raises(XjtuRulLstmBenchmarkResultError, match="40-character"):
        run_xjtu_rul_lstm_heldout_benchmark(
            tmp_path / "missing-source",
            tmp_path / "result.json",
            code_revision="not-a-revision",
        )
