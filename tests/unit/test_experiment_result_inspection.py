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
from industrial_phm.experiments.xjtu_rul_benchmark_result import (
    XJTU_RUL_LSTM_BENCHMARK_AVAILABLE_CAPABILITIES,
    XJTU_RUL_LSTM_BENCHMARK_EVIDENCE_CLASS,
    XJTU_RUL_LSTM_BENCHMARK_RESULT_SCHEMA_ID,
    XJTU_RUL_LSTM_BENCHMARK_UNSUPPORTED_CAPABILITIES,
)
from industrial_phm.experiments.xjtu_rul_lstm import XJTU_RUL_LSTM_METHOD_ID
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


@pytest.mark.parametrize("result_path", (_XJTU_RESULT, _IMS_RESULT))
def test_acquisition_level_model_reports_sequence_construction_not_applicable(
    result_path: Path,
) -> None:
    inspection = inspect_experiment_result(result_path)
    sequence_stage = next(
        stage for stage in inspection.stages if stage.name == "Sequence Construction"
    )

    assert sequence_stage.status == "not applicable"
    assert tuple((fact.label, fact.value) for fact in sequence_stage.facts) == (
        ("Reason", "model consumes acquisition-level feature observations"),
    )


def test_xjtu_lstm_inspection_resolves_sequence_and_reconstruction_pipeline(
    tmp_path: Path,
) -> None:
    result_path = _write_xjtu_lstm_result(tmp_path)

    inspection = inspect_experiment_result(result_path)
    summary = render_experiment_inspection_text(inspection)

    assert tuple(stage.name for stage in inspection.stages) == _STAGES
    assert "Schema: xjtu-lstm-development-result-v1" in summary
    assert "Status: completed" in summary
    assert "Sequence Construction" in summary
    assert "Status: not applicable" not in summary
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


def _benchmark_lifecycle_prediction_count(asset_id: str, position: str) -> int:
    run_length = get_xjtu_expected_acquisition_count(asset_id)
    early_end = (run_length + 2) // 3
    middle_end = (2 * run_length + 2) // 3
    if position == "early":
        return max(early_end - 7, 0)
    if position == "middle":
        return middle_end - early_end
    if position == "late":
        return run_length - middle_end
    raise AssertionError(f"unexpected lifecycle position: {position}")


def _write_rul_benchmark_document(tmp_path: Path) -> Path:
    fold = get_xjtu_reference_split().folds[0]
    all_bearings = (*fold.train, *fold.validation, *fold.test)
    source_count = sum(get_xjtu_expected_acquisition_count(asset_id) for asset_id in all_bearings)
    train_count = sum(get_xjtu_expected_acquisition_count(asset_id) for asset_id in fold.train)
    benchmark_count = sum(get_xjtu_expected_acquisition_count(asset_id) for asset_id in fold.test)

    point_rows = [
        {
            "asset_id": asset_id,
            "partition_id": "test",
            "prediction_count": get_xjtu_expected_acquisition_count(asset_id) - 7,
            "mean_absolute_error": float(index),
            "root_mean_squared_error": float(index + 1),
            "mean_signed_error": float(-index),
            "normalized_mean_absolute_error": float(index) / 10.0,
        }
        for index, asset_id in enumerate(sorted(fold.test), start=1)
    ]
    lifecycle_rows = [
        {
            "asset_id": asset_id,
            "partition_id": "test",
            "position": position,
            "prediction_count": _benchmark_lifecycle_prediction_count(asset_id, position),
            "mean_absolute_error": float(position_index),
            "root_mean_squared_error": float(position_index + 1),
            "mean_signed_error": float(-position_index),
            "normalized_mean_absolute_error": float(position_index) / 10.0,
        }
        for asset_id in fold.test
        for position_index, position in enumerate(("early", "middle", "late"), start=1)
    ]
    lifecycle_summaries = [
        {
            "position": position,
            "bearing_count": len(fold.test),
            "mean_asset_mean_absolute_error": float(position_index),
            "mean_asset_root_mean_squared_error": float(position_index + 1),
            "mean_asset_mean_signed_error": float(-position_index),
            "mean_asset_normalized_mean_absolute_error": float(position_index) / 10.0,
        }
        for position_index, position in enumerate(("early", "middle", "late"), start=1)
    ]

    document = {
        "schema_id": XJTU_RUL_LSTM_BENCHMARK_RESULT_SCHEMA_ID,
        "provenance": {
            "code_revision": "b" * 40,
            "protocol_id": "xjtu-sy-rul-prognostics-protocol-v1",
            "dataset_id": "xjtu-sy",
            "split_id": "xjtu-sy-condition-stratified-5fold-v1",
            "fold_id": "fold-1",
            "evidence_class": XJTU_RUL_LSTM_BENCHMARK_EVIDENCE_CLASS,
        },
        "source_scope": {
            "verified_source_acquisition_count": source_count,
            "train_bearings": list(fold.train),
            "benchmark_bearings": list(fold.test),
            "train_source_acquisition_count": train_count,
            "benchmark_source_acquisition_count": benchmark_count,
            "project_history_limitation": (
                "fold-1 test bearings were previously observed by project anomaly/robustness "
                "work; this is not a pristine external holdout"
            ),
        },
        "selection": {
            "validation_selected_method_id": XJTU_RUL_LSTM_METHOD_ID,
            "operational_primary_method_id": None,
            "selection_rule": "fold-1-validation-equal-bearing-mean-mae",
        },
        "target": {
            "definition_id": "xjtu-sy-recorded-end-rul-v1",
            "unit": "acquisition-interval",
            "endpoint_semantics": "last-recorded-acquisition",
            "formula": "N-k",
            "prediction_alignment": "right-edge-acquisition",
            "target_clipping": False,
            "target_normalization": False,
        },
        "method": {
            "method_id": XJTU_RUL_LSTM_METHOD_ID,
            "kind": "temporal-sequence-lstm-regression",
            "feature_schema": {
                "feature_set_id": "vibration-statistical-v1",
                "selected_features": ["rms"],
                "selected_feature_count": 1,
            },
            "preprocessing": {
                "fit_partition": "train",
                "scaling_strategy": "robust",
                "fit_observation_count": train_count,
            },
            "sequence": {
                "length": 8,
                "stride": 1,
                "alignment": "right-edge",
                "train_window_count": train_count - 63,
                "benchmark_dropped_prefix_per_bearing": 7,
            },
            "model": {
                "random_seed": 42,
                "device": "cpu",
                "numeric_precision": "float32",
                "deterministic_algorithms": True,
            },
        },
        "evaluation": {
            "point": {
                "aggregation": "equal-bearing-mean",
                "prediction_method_id": XJTU_RUL_LSTM_METHOD_ID,
                "target_definition_id": "xjtu-sy-recorded-end-rul-v1",
                "unit": "acquisition-interval",
                "mean_asset_mean_absolute_error": 2.0,
                "mean_asset_root_mean_squared_error": 3.0,
                "mean_asset_mean_signed_error": -2.0,
                "mean_asset_normalized_mean_absolute_error": 0.2,
                "bearings": point_rows,
            },
            "lifecycle_position": {
                "boundary": {
                    "early": "1..ceil(N/3)",
                    "middle": "ceil(N/3)+1..ceil(2N/3)",
                    "late": "ceil(2N/3)+1..N",
                    "semantics": "retrospective-evaluation-only",
                },
                "prediction_method_id": XJTU_RUL_LSTM_METHOD_ID,
                "target_definition_id": "xjtu-sy-recorded-end-rul-v1",
                "unit": "acquisition-interval",
                "aggregation": "equal-bearing-mean-within-lifecycle-position",
                "bearing_positions": lifecycle_rows,
                "position_summaries": lifecycle_summaries,
            },
        },
        "capability_scope": {
            "available": list(XJTU_RUL_LSTM_BENCHMARK_AVAILABLE_CAPABILITIES),
            "unsupported_or_not_validated": list(
                XJTU_RUL_LSTM_BENCHMARK_UNSUPPORTED_CAPABILITIES
            ),
        },
        "interpretation": "protocol-frozen retrospective benchmark evidence",
    }
    output = tmp_path / "xjtu-rul-benchmark.json"
    output.write_text(json.dumps(document), encoding="utf-8")
    return output


def _stage_positions(summary: str) -> list[int]:
    return [summary.index(f"\n{stage}\n") for stage in _STAGES]


def _read_object(path: Path) -> dict[str, object]:
    value = cast(object, json.loads(path.read_text(encoding="utf-8")))
    if not isinstance(value, dict):
        raise AssertionError("test fixture must be a JSON object")
    return cast(dict[str, object], value)


_RUL_RESULT = _RESULTS / "xjtu-sy-rul-three-model-fold-1-validation-v1.json"


def test_rul_three_model_result_uses_the_shared_stage_vocabulary() -> None:
    """Prognostics evidence must be readable through the same inspection read model."""
    inspection = inspect_experiment_result(_RUL_RESULT)

    assert inspection.schema_id == "xjtu-rul-three-model-validation-result-v1"
    assert tuple(stage.name for stage in inspection.stages) == _STAGES
    assert {stage.status for stage in inspection.stages} == {"completed"}


def test_rul_inspection_reports_target_semantics_not_physical_failure() -> None:
    inspection = inspect_experiment_result(_RUL_RESULT)
    scoring = next(stage for stage in inspection.stages if stage.name == "Scoring")

    facts = {fact.label: fact.value for fact in scoring.facts}
    assert facts["Target unit"] == "acquisition-interval"
    assert facts["Endpoint semantics"] == "last-recorded-acquisition"
    assert any("not a validated physical failure time" in text for text in scoring.warnings)


def test_rul_inspection_lists_every_compared_method_on_common_support() -> None:
    inspection = inspect_experiment_result(_RUL_RESULT)
    model = next(stage for stage in inspection.stages if stage.name == "Model")
    evaluation = next(stage for stage in inspection.stages if stage.name == "Evaluation")

    method_ids = {fact.label for fact in model.facts if fact.label.startswith("xjtu-sy-")}
    assert len(method_ids) == 3
    metric_labels = {fact.label for fact in evaluation.facts if fact.label.startswith("xjtu-sy-")}
    assert metric_labels == method_ids
    facts = {fact.label: fact.value for fact in evaluation.facts}
    assert facts["Support"] == "temporal-common-support"
    assert facts["First acquisition"] == 8


def test_rul_inspection_keeps_uncertainty_unsupported() -> None:
    inspection = inspect_experiment_result(_RUL_RESULT)
    capability = next(stage for stage in inspection.stages if stage.name == "Capability")

    unsupported = next(fact.value for fact in capability.facts if fact.label == "Unsupported")
    assert "prediction-interval" in str(unsupported)
    assert "uncertainty-calibration" in str(unsupported)
    assert "validated-physical-failure-threshold" in str(unsupported)


def test_rul_inspection_rejects_evidence_class_drift(tmp_path: Path) -> None:
    document = cast(dict[str, object], json.loads(_RUL_RESULT.read_text(encoding="utf-8")))
    provenance = cast(dict[str, object], document["provenance"])
    provenance["evidence_class"] = "field-validated-rul-evidence"
    drifted = tmp_path / "drifted.json"
    drifted.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ExperimentResultInspectionError, match="evidence_class"):
        inspect_experiment_result(drifted)


def test_rul_benchmark_inspection_uses_shared_stage_vocabulary(tmp_path: Path) -> None:
    result = _write_rul_benchmark_document(tmp_path)

    inspection = inspect_experiment_result(result)
    summary = render_experiment_inspection_text(inspection)

    assert inspection.schema_id == XJTU_RUL_LSTM_BENCHMARK_RESULT_SCHEMA_ID
    assert tuple(stage.name for stage in inspection.stages) == _STAGES
    assert "Validation-selected method: xjtu-sy-rul-lstm-fold-1-v1" in summary
    assert "Operational primary method: none" in summary
    assert "Lifecycle positions: early, middle, late" in summary
    assert "protocol-frozen-retrospective-benchmark-evidence" in summary
    assert "not a pristine external holdout" in summary


def test_rul_benchmark_inspection_rejects_point_aggregate_drift(tmp_path: Path) -> None:
    result = _write_rul_benchmark_document(tmp_path)
    document = _read_object(result)
    evaluation = cast(dict[str, object], document["evaluation"])
    point = cast(dict[str, object], evaluation["point"])
    point["mean_asset_mean_absolute_error"] = 999.0
    result.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        ExperimentResultInspectionError,
        match="mean_asset_mean_absolute_error",
    ):
        inspect_experiment_result(result)


def test_rul_benchmark_inspection_rejects_operational_primary(tmp_path: Path) -> None:
    result = _write_rul_benchmark_document(tmp_path)
    document = _read_object(result)
    selection = cast(dict[str, object], document["selection"])
    selection["operational_primary_method_id"] = XJTU_RUL_LSTM_METHOD_ID
    result.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        ExperimentResultInspectionError,
        match="operational_primary_method_id must remain null",
    ):
        inspect_experiment_result(result)


def test_rul_benchmark_inspection_rejects_capability_drift(tmp_path: Path) -> None:
    result = _write_rul_benchmark_document(tmp_path)
    document = _read_object(result)
    capability = cast(dict[str, object], document["capability_scope"])
    capability["available"] = [
        *XJTU_RUL_LSTM_BENCHMARK_AVAILABLE_CAPABILITIES,
        "prediction-interval",
    ]
    result.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(
        ExperimentResultInspectionError,
        match="benchmark available capability scope",
    ):
        inspect_experiment_result(result)


def test_rul_inspection_requires_three_methods(tmp_path: Path) -> None:
    document = cast(dict[str, object], json.loads(_RUL_RESULT.read_text(encoding="utf-8")))
    methods = cast(list[object], document["methods"])
    document["methods"] = methods[:2]
    drifted = tmp_path / "two-methods.json"
    drifted.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ExperimentResultInspectionError, match="three methods"):
        inspect_experiment_result(drifted)
