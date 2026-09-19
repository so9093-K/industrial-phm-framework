import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from industrial_phm.adapters import get_xjtu_expected_acquisition_count
from industrial_phm.experiments import (
    XJTU_LSTM_DEVELOPMENT_EVIDENCE_CLASS,
    XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID,
    XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID,
    XJTU_LSTM_SEQUENCE_SPEC,
    XjtuLstmDevelopmentResult,
    XjtuLstmDevelopmentResultError,
    evaluate_xjtu_lstm_development_scores,
    get_xjtu_lstm_development_configuration,
    get_xjtu_reference_split,
    write_xjtu_lstm_development_result,
)
from industrial_phm.models import LstmAutoencoderTrainingProvenance, ReconstructionScores


def _scores() -> ReconstructionScores:
    config = get_xjtu_lstm_development_configuration()
    feature_names = tuple(config.selected_features)
    window_ids: list[str] = []
    asset_ids: list[str] = []
    source_ids: list[str] = []
    positions: list[int] = []
    scores: list[float] = []
    residuals: list[tuple[float, ...]] = []
    for asset_index, asset_id in enumerate(get_xjtu_reference_split().folds[0].validation):
        source_count = get_xjtu_expected_acquisition_count(asset_id)
        for position in range(XJTU_LSTM_SEQUENCE_SPEC.length, source_count + 1):
            score = float(asset_index + 1 + position / 100_000.0)
            window_ids.append(
                f"{asset_id}:window-{position - XJTU_LSTM_SEQUENCE_SPEC.length + 1}-{position}"
            )
            asset_ids.append(asset_id)
            source_ids.append(f"{asset_id}:acquisition-{position}")
            positions.append(position)
            scores.append(score)
            residuals.append((score,) * len(feature_names))
    return ReconstructionScores(
        experiment_id=XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID,
        feature_set_id=config.feature_set_id,
        feature_names=feature_names,
        spec=XJTU_LSTM_SEQUENCE_SPEC,
        window_ids=tuple(window_ids),
        sequence_ids=tuple(asset_ids),
        asset_ids=tuple(asset_ids),
        partition_ids=("validation",) * len(scores),
        aligned_source_observation_ids=tuple(source_ids),
        aligned_source_positions=tuple(positions),
        scores=tuple(scores),
        feature_residuals=tuple(residuals),
    )


def _result() -> XjtuLstmDevelopmentResult:
    config = get_xjtu_lstm_development_configuration()
    features = tuple(config.selected_features)
    scores = _scores()
    evaluation = evaluate_xjtu_lstm_development_scores(scores)
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
        scores=scores,
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
    trajectories = cast(list[dict[str, object]], scoring["trajectories"])
    assert [trajectory["asset_id"] for trajectory in trajectories] == [
        "Bearing1_2",
        "Bearing2_2",
        "Bearing3_2",
    ]
    first_observations = cast(list[dict[str, object]], trajectories[0]["observations"])
    assert first_observations[0]["window_id"] == "Bearing1_2:window-1-8"
    assert first_observations[0]["source_observation_id"] == "Bearing1_2:acquisition-8"
    assert first_observations[0]["acquisition_index"] == 8
    assert len(cast(list[float], first_observations[0]["feature_residuals"])) == 16
    assert sum(len(cast(list[object], item["observations"])) for item in trajectories) == 2_797

    capability = cast(dict[str, object], document["capability_scope"])
    assert "reconstruction-residual-evidence" in cast(list[str], capability["available"])
    assert "prognostics-rul" in cast(list[str], capability["unsupported_or_not_validated"])


def test_xjtu_lstm_result_rejects_non_revision_identity() -> None:
    with pytest.raises(XjtuLstmDevelopmentResultError, match="40-character"):
        replace(_result(), code_revision="not-a-revision")


def test_xjtu_lstm_result_rejects_score_contract_drift() -> None:
    result = _result()

    with pytest.raises(XjtuLstmDevelopmentResultError, match="feature_set_id"):
        replace(result, scores=replace(result.scores, feature_set_id="other-features-v1"))
