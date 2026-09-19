import json
from pathlib import Path
from typing import cast

import pytest

from industrial_phm.adapters import get_xjtu_expected_acquisition_count
from industrial_phm.experiments.result_inspection import (
    ExperimentInspection,
    ExperimentResultInspectionError,
    inspect_experiment_result,
    render_experiment_inspection_text,
)
from industrial_phm.experiments.xjtu import get_xjtu_reference_split
from industrial_phm.experiments.xjtu_lifecycle import early_third_length
from industrial_phm.experiments.xjtu_lstm import get_xjtu_lstm_development_configuration
from industrial_phm.experiments.xjtu_lstm_evaluation import (
    evaluate_xjtu_lstm_development_scores,
)
from industrial_phm.experiments.xjtu_lstm_result import (
    XjtuLstmDevelopmentResult,
    write_xjtu_lstm_development_result,
)
from industrial_phm.experiments.xjtu_sequence import (
    XJTU_LSTM_DEVELOPMENT_PROTOCOL_ID,
    XJTU_LSTM_SEQUENCE_SPEC,
)
from industrial_phm.models import (
    MEAN_SQUARED_RECONSTRUCTION_ERROR_ID,
    LstmAutoencoderTrainingProvenance,
    ReconstructionScores,
)

_REPOSITORY_ROOT = Path(__file__).parents[2]
_RESULTS = _REPOSITORY_ROOT / "docs" / "research" / "results"
_XJTU_RESULT = _RESULTS / "xjtu-sy-iforest-fold-1-holdout-v1.json"
_IMS_RESULT = _RESULTS / "ims-bearings-iforest-single-channel-cross-test-v1.json"
_STAGES = (
    "Source",
    "Canonical",
    "Feature",
    "Preprocessing",
    "Reference",
    "Population",
    "Model",
    "Scoring",
    "Evaluation",
    "Capability",
    "Provenance",
)
_LSTM_STAGES = (
    "Source",
    "Canonical",
    "Feature",
    "Preprocessing",
    "Reference",
    "Sequence Construction",
    "Population",
    "Model",
    "Scoring",
    "Evaluation",
    "Capability",
    "Provenance",
)


def test_xjtu_holdout_inspection_resolves_effective_pipeline() -> None:
    inspection = inspect_experiment_result(_XJTU_RESULT)
    summary = render_experiment_inspection_text(inspection)

    assert isinstance(inspection, ExperimentInspection)
    assert tuple(stage.name for stage in inspection.stages) == _STAGES
    assert _stage_positions(summary) == sorted(_stage_positions(summary))
    assert "Schema: xjtu-fold-1-holdout-result-v1" in summary
    assert "Status: consumed" in summary
    assert "Cardinality: 1 acquisition CSV -> 1 two-channel bearing observation" in summary
    assert "n_estimators=256" in summary
    assert "Score semantics: higher-is-more-anomalous" in summary
    assert "Unsupported: thresholded-state-detection" in summary
    assert "Declared code revision:" in summary
    assert "Checkout attestation: unavailable" in summary


def test_ims_cross_test_inspection_exposes_source_to_observation_cardinality() -> None:
    inspection = inspect_experiment_result(_IMS_RESULT)
    summary = render_experiment_inspection_text(inspection)

    assert tuple(stage.name for stage in inspection.stages) == _STAGES
    assert "Schema: ims-single-channel-cross-test-result-v1" in summary
    assert "Train scope: set-2 complete / 984 files" in summary
    assert "Evaluation scope: set-3 readme-documented / 4448 files" in summary
    assert "Excluded: set-1, set-3:archive-extension" in summary
    assert "Cardinality: 1 acquisition file -> 4 bearing observations" in summary
    assert "Scope: one-time-cross-test-evaluation" in summary
    assert "Aggregation: four-bearing-equal-weight-mean" in summary
    assert "Declared code revision:" in summary


def test_xjtu_lstm_inspection_resolves_sequence_and_reconstruction_pipeline(
    tmp_path: Path,
) -> None:
    result_path = _write_xjtu_lstm_result(tmp_path)

    inspection = inspect_experiment_result(result_path)
    summary = render_experiment_inspection_text(inspection)

    assert tuple(stage.name for stage in inspection.stages) == _LSTM_STAGES
    assert "Schema: xjtu-lstm-development-result-v1" in summary
    assert "Status: completed" in summary
    assert "Sequence Construction" in summary
    assert "Model-fit windows:" in summary
    assert "Framework: pytorch 2.14.0" in summary
    assert "Final epoch mean training loss:" in summary
    assert "Semantics: mean-squared-reconstruction-error-v1" in summary
    assert "Trajectory evidence: 2797 acquisition-aligned scores / 16 residual features" in summary
    assert "Scope: retrospective-development-evidence" in summary
    assert "Unsupported: thresholded-state-detection" in summary


def test_xjtu_lstm_inspection_rejects_sequence_population_drift(tmp_path: Path) -> None:
    result_path = _write_xjtu_lstm_result(tmp_path)
    document = _read_object(result_path)
    sequence = cast(dict[str, object], document["sequence_construction"])
    validation = cast(dict[str, object], sequence["validation"])
    validation["window_count"] = cast(int, validation["window_count"]) - 1
    drifted = tmp_path / "drifted-lstm.json"
    drifted.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        ExperimentResultInspectionError,
        match=r"sequence_construction\.validation\.window_count",
    ):
        inspect_experiment_result(drifted)


def test_xjtu_lstm_inspection_rejects_trajectory_alignment_drift(tmp_path: Path) -> None:
    result_path = _write_xjtu_lstm_result(tmp_path)
    document = _read_object(result_path)
    scoring = cast(dict[str, object], document["scoring"])
    trajectories = cast(list[dict[str, object]], scoring["trajectories"])
    observations = cast(list[dict[str, object]], trajectories[0]["observations"])
    observations[0]["acquisition_index"] = 9
    drifted = tmp_path / "drifted-lstm-trajectory.json"
    drifted.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        ExperimentResultInspectionError,
        match=r"scoring\.trajectories\[0\]\.observations\[0\]\.acquisition_index",
    ):
        inspect_experiment_result(drifted)


def test_xjtu_lstm_inspection_rejects_trajectory_residual_drift(tmp_path: Path) -> None:
    result_path = _write_xjtu_lstm_result(tmp_path)
    document = _read_object(result_path)
    scoring = cast(dict[str, object], document["scoring"])
    trajectories = cast(list[dict[str, object]], scoring["trajectories"])
    observations = cast(list[dict[str, object]], trajectories[0]["observations"])
    observations[0]["feature_residuals"] = [0.0] * 16
    drifted = tmp_path / "drifted-lstm-residual.json"
    drifted.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        ExperimentResultInspectionError,
        match="mean feature residual",
    ):
        inspect_experiment_result(drifted)


def test_xjtu_lstm_inspection_rejects_aggregate_drift_from_raw_trajectory(
    tmp_path: Path,
) -> None:
    result_path = _write_xjtu_lstm_result(tmp_path)
    document = _read_object(result_path)
    evaluation = cast(dict[str, object], document["evaluation"])
    bearings = cast(list[dict[str, object]], evaluation["bearings"])
    bearings[0]["acquisition_order_spearman_rho"] = 0.5
    drifted = tmp_path / "drifted-lstm-aggregate.json"
    drifted.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        ExperimentResultInspectionError,
        match="acquisition_order_spearman_rho from score trajectory",
    ):
        inspect_experiment_result(drifted)


def test_inspection_rejects_unknown_schema(tmp_path: Path) -> None:
    result = tmp_path / "unknown.json"
    result.write_text('{"schema_id": "generic-result-v1"}\n', encoding="utf-8")

    with pytest.raises(ExperimentResultInspectionError, match=r"unsupported.*generic-result-v1"):
        inspect_experiment_result(result)


def test_inspection_rejects_malformed_json(tmp_path: Path) -> None:
    result = tmp_path / "malformed.json"
    result.write_text("{", encoding="utf-8")

    with pytest.raises(ExperimentResultInspectionError, match="invalid result JSON"):
        inspect_experiment_result(result)


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    (
        ("experiment_id", "drifted-experiment", "experiment_id does not match"),
        ("source_acquisition_count", 9_215, "XJTU source acquisition count"),
        ("complete_train_observation_count", 9_999, "XJTU complete train population"),
        ("model_fit_observation_count", 1_083, "model fit and reference observation counts"),
    ),
)
def test_xjtu_inspection_rejects_protocol_drift(
    tmp_path: Path,
    field: str,
    replacement: str | int,
    message: str,
) -> None:
    document = _read_object(_XJTU_RESULT)
    document[field] = replacement
    result = tmp_path / "drifted-xjtu.json"
    result.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ExperimentResultInspectionError, match=message):
        inspect_experiment_result(result)


def test_xjtu_inspection_rejects_holdout_bearing_count_drift(tmp_path: Path) -> None:
    document = _read_object(_XJTU_RESULT)
    bearings = cast(list[dict[str, object]], document["holdout_bearings"])
    bearings[0]["full_run_observation_count"] = 122
    result = tmp_path / "drifted-xjtu-bearing.json"
    result.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        ExperimentResultInspectionError,
        match=r"holdout_bearings\[0\]\.full_run_observation_count",
    ):
        inspect_experiment_result(result)


def test_xjtu_inspection_rejects_reference_population_drift(tmp_path: Path) -> None:
    document = _read_object(_XJTU_RESULT)
    document["reference_observation_count"] = 1_083
    document["model_fit_observation_count"] = 1_083
    result = tmp_path / "drifted-xjtu-reference.json"
    result.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ExperimentResultInspectionError, match="XJTU reference population"):
        inspect_experiment_result(result)


def test_ims_inspection_rejects_population_drift(tmp_path: Path) -> None:
    document = _read_object(_IMS_RESULT)
    population = cast(dict[str, object], document["population_flow"])
    population["scoring_observation_count"] = 17_791
    result = tmp_path / "drifted-ims.json"
    result.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ExperimentResultInspectionError, match="scoring population"):
        inspect_experiment_result(result)


def _write_xjtu_lstm_result(tmp_path: Path) -> Path:
    config = get_xjtu_lstm_development_configuration()
    fold = get_xjtu_reference_split().folds[0]
    features = tuple(config.selected_features)
    all_assets = tuple(dict.fromkeys((*fold.train, *fold.validation, *fold.test)))
    source_count = sum(get_xjtu_expected_acquisition_count(asset_id) for asset_id in all_assets)
    train_count = sum(get_xjtu_expected_acquisition_count(asset_id) for asset_id in fold.train)
    reference_count = sum(
        early_third_length(get_xjtu_expected_acquisition_count(asset_id)) for asset_id in fold.train
    )
    validation_count = sum(
        get_xjtu_expected_acquisition_count(asset_id) for asset_id in fold.validation
    )
    prefix_width = XJTU_LSTM_SEQUENCE_SPEC.length - 1
    reference_prefix = len(fold.train) * prefix_width
    validation_prefix = len(fold.validation) * prefix_width
    reference_windows = reference_count - reference_prefix
    validation_windows = validation_count - validation_prefix

    scores = _xjtu_lstm_scores()
    evaluation = evaluate_xjtu_lstm_development_scores(scores)
    epochs = int(config.model_parameters["epochs"])
    epoch_losses = tuple(1.0 - index / 100.0 for index in range(epochs))
    training = LstmAutoencoderTrainingProvenance(
        runtime="pytorch",
        runtime_version="2.14.0",
        device=str(config.model_parameters["device"]),
        numeric_precision=str(config.model_parameters["numeric_precision"]),
        deterministic_algorithms=bool(config.model_parameters["deterministic_algorithms"]),
        random_seed=config.random_seed,
        sampling_policy_id=config.sampling_policy_id,
        fit_window_count=reference_windows,
        parameter_count=15_376,
        batch_size=int(config.model_parameters["batch_size"]),
        epochs=epochs,
        epoch_losses=epoch_losses,
    )
    result = XjtuLstmDevelopmentResult(
        code_revision="a" * 40,
        source_acquisition_count=source_count,
        experiment_id=config.experiment_id,
        dataset_id=config.dataset_id,
        split_id=config.split_id,
        fold_id=config.fold_id,
        feature_set_id=config.feature_set_id,
        selected_features=features,
        fit_partition=config.fit_partition.value,
        scaling_strategy=config.scaling_strategy.value,
        preprocessing_fit_observation_count=train_count,
        fitted_center=(0.0,) * len(features),
        fitted_scale=(1.0,) * len(features),
        zero_iqr_features=(),
        reference_strategy=config.reference_strategy.value,
        sampling_policy_id=config.sampling_policy_id,
        reference_source_acquisition_count=reference_count,
        reference_window_count=reference_windows,
        reference_dropped_prefix_count=reference_prefix,
        validation_source_acquisition_count=validation_count,
        validation_window_count=validation_windows,
        validation_dropped_prefix_count=validation_prefix,
        sequence_length=XJTU_LSTM_SEQUENCE_SPEC.length,
        sequence_stride=XJTU_LSTM_SEQUENCE_SPEC.stride,
        sequence_alignment=XJTU_LSTM_SEQUENCE_SPEC.alignment.value,
        model_family=config.model_family.value,
        model_parameters=tuple(sorted(config.model_parameters.items())),
        random_seed=config.random_seed,
        training=training,
        score_semantics_id=MEAN_SQUARED_RECONSTRUCTION_ERROR_ID,
        scores=scores,
        evaluation=evaluation,
    )
    output = tmp_path / "xjtu-lstm.json"
    write_xjtu_lstm_development_result(result, output)
    return output


def _xjtu_lstm_scores() -> ReconstructionScores:
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


def _stage_positions(summary: str) -> list[int]:
    return [summary.index(f"\n{stage}\n") for stage in _STAGES]


def _read_object(path: Path) -> dict[str, object]:
    value = cast(object, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(value, dict):
        raise AssertionError("test fixture must be a JSON object")
    return cast(dict[str, object], value)
