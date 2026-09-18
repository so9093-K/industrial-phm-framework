import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from industrial_phm.experiments import (
    XJTU_LSTM_DEVELOPMENT_EVIDENCE_CLASS,
    XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID,
    XjtuLstmBearingEvaluation,
    XjtuLstmDevelopmentEvaluation,
    XjtuLstmDevelopmentResult,
    XjtuLstmDevelopmentResultError,
    get_xjtu_lstm_development_configuration,
    write_xjtu_lstm_development_result,
)
from industrial_phm.models import LstmAutoencoderTrainingProvenance


def _result() -> XjtuLstmDevelopmentResult:
    config = get_xjtu_lstm_development_configuration()
    features = tuple(config.selected_features)
    residuals = tuple(float(index + 1) / 100.0 for index in range(len(features)))
    bearings = (
        XjtuLstmBearingEvaluation(
            asset_id="Bearing1_2",
            source_acquisition_count=161,
            score_window_count=154,
            dropped_prefix_count=7,
            acquisition_order_spearman_rho=0.2,
            late_vs_middle_rank_probability=0.6,
            mean_feature_residuals=residuals,
        ),
        XjtuLstmBearingEvaluation(
            asset_id="Bearing2_2",
            source_acquisition_count=161,
            score_window_count=154,
            dropped_prefix_count=7,
            acquisition_order_spearman_rho=0.3,
            late_vs_middle_rank_probability=0.7,
            mean_feature_residuals=residuals,
        ),
        XjtuLstmBearingEvaluation(
            asset_id="Bearing3_2",
            source_acquisition_count=2_496,
            score_window_count=2_489,
            dropped_prefix_count=7,
            acquisition_order_spearman_rho=0.4,
            late_vs_middle_rank_probability=0.8,
            mean_feature_residuals=residuals,
        ),
    )
    evaluation = XjtuLstmDevelopmentEvaluation(
        experiment_id=config.experiment_id,
        split_id=config.split_id,
        fold_id=config.fold_id,
        feature_names=features,
        bearing_results=bearings,
        mean_bearing_acquisition_order_spearman_rho=0.3,
        mean_bearing_late_vs_middle_rank_probability=0.7,
        mean_bearing_feature_residuals=residuals,
    )
    training = LstmAutoencoderTrainingProvenance(
        runtime="pytorch",
        runtime_version="2.14.0",
        device="cpu",
        numeric_precision="float32",
        deterministic_algorithms=True,
        random_seed=42,
        sampling_policy_id=config.sampling_policy_id,
        fit_window_count=1_021,
        parameter_count=15_376,
        batch_size=64,
        epochs=2,
        epoch_losses=(1.0, 0.75),
    )
    return XjtuLstmDevelopmentResult(
        code_revision="a" * 40,
        source_acquisition_count=9_216,
        experiment_id=config.experiment_id,
        dataset_id=config.dataset_id,
        split_id=config.split_id,
        fold_id=config.fold_id,
        feature_set_id=config.feature_set_id,
        selected_features=features,
        fit_partition=config.fit_partition.value,
        scaling_strategy=config.scaling_strategy.value,
        preprocessing_fit_observation_count=3_246,
        fitted_center=(0.0,) * len(features),
        fitted_scale=(1.0,) * len(features),
        zero_iqr_features=(),
        reference_strategy=config.reference_strategy.value,
        sampling_policy_id=config.sampling_policy_id,
        reference_source_acquisition_count=1_084,
        reference_window_count=1_021,
        reference_dropped_prefix_count=63,
        validation_source_acquisition_count=2_818,
        validation_window_count=2_797,
        validation_dropped_prefix_count=21,
        sequence_length=8,
        sequence_stride=1,
        sequence_alignment="right-edge",
        model_family=config.model_family.value,
        model_parameters=tuple(sorted(config.model_parameters.items())),
        random_seed=config.random_seed,
        training=training,
        score_semantics_id="mean-squared-reconstruction-error-v1",
        evaluation=evaluation,
    )


def test_xjtu_lstm_result_writes_reviewable_execution_contract(tmp_path: Path) -> None:
    output = tmp_path / "result.json"

    write_xjtu_lstm_development_result(_result(), output)

    document = cast(dict[str, object], json.loads(output.read_text(encoding="utf-8")))
    assert document["schema_id"] == XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID

    provenance = cast(dict[str, object], document["provenance"])
    assert provenance["evidence_class"] == XJTU_LSTM_DEVELOPMENT_EVIDENCE_CLASS
    assert provenance["code_revision"] == "a" * 40

    sequence = cast(dict[str, object], document["sequence_construction"])
    assert sequence["length"] == 8
    assert sequence["stride"] == 1
    assert sequence["alignment"] == "right-edge"
    validation = cast(dict[str, object], sequence["validation"])
    assert validation["source_acquisition_count"] == 2_818
    assert validation["window_count"] == 2_797
    assert validation["dropped_prefix_acquisition_count"] == 21

    model = cast(dict[str, object], document["model"])
    training = cast(dict[str, object], model["training"])
    assert training["framework"] == "pytorch"
    assert training["numeric_precision"] == "float32"
    assert training["final_epoch_mean_training_loss"] == pytest.approx(0.75)

    scoring = cast(dict[str, object], document["scoring"])
    assert scoring["score_semantics_id"] == "mean-squared-reconstruction-error-v1"
    assert scoring["direction"] == "higher-is-more-anomalous"
    assert scoring["window_count"] == 2_797

    capability = cast(dict[str, object], document["capability_scope"])
    assert "reconstruction-residual-evidence" in cast(list[str], capability["available"])
    assert "prognostics-rul" in cast(list[str], capability["unsupported_or_not_validated"])


def test_xjtu_lstm_result_rejects_non_revision_identity() -> None:
    with pytest.raises(XjtuLstmDevelopmentResultError, match="40-character"):
        replace(_result(), code_revision="not-a-revision")
