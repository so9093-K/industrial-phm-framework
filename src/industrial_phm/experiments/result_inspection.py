"""Read-only summaries for explicitly supported experiment result schemas."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from industrial_phm.adapters import XJTU_SY_CHANNELS, get_xjtu_expected_acquisition_count
from industrial_phm.experiments.ims_cross_test import IMS_CROSS_TEST_RESULT_SCHEMA_ID
from industrial_phm.experiments.mimii_development import MIMII_DEVELOPMENT_RESULT_SCHEMA_ID
from industrial_phm.experiments.result_inspection_support import (
    ExperimentInspection,
    ExperimentResultInspectionError,
    InspectionFact,
    InspectionStage,
    _boolean,
    _capability_stage,
    _expect_close,
    _expect_equal,
    _integer,
    _mapping,
    _mapping_field,
    _number,
    _number_sequence,
    _positive_int,
    _provenance_stage,
    _revision,
    _sequence,
    _text,
    _text_sequence,
)
from industrial_phm.experiments.xjtu import get_xjtu_reference_split
from industrial_phm.experiments.xjtu_holdout import XJTU_HOLDOUT_RESULT_SCHEMA_ID
from industrial_phm.experiments.xjtu_inspection_support import (
    LSTM_AVAILABLE_CAPABILITIES,
    SCORE_SEMANTICS,
    format_parameters,
    validated_capability_scope,
)
from industrial_phm.experiments.xjtu_lifecycle import early_third_length
from industrial_phm.experiments.xjtu_lstm import get_xjtu_lstm_development_configuration
from industrial_phm.experiments.xjtu_lstm_evaluation import (
    XjtuLstmDevelopmentEvaluationError,
    evaluate_xjtu_lstm_development_scores,
)
from industrial_phm.experiments.xjtu_lstm_result import (
    XJTU_LSTM_DEVELOPMENT_EVIDENCE_CLASS,
    XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID,
)
from industrial_phm.experiments.xjtu_rul_benchmark_result import (
    XJTU_RUL_LSTM_BENCHMARK_RESULT_SCHEMA_ID,
)
from industrial_phm.experiments.xjtu_rul_validation_result import (
    XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID,
)
from industrial_phm.experiments.xjtu_sequence import XJTU_LSTM_SEQUENCE_SPEC
from industrial_phm.models.reconstruction_scoring import (
    MEAN_SQUARED_RECONSTRUCTION_ERROR_ID,
    ReconstructionScores,
    ReconstructionScoringError,
)

__all__ = [
    "ExperimentInspection",
    "ExperimentResultInspectionError",
    "InspectionFact",
    "InspectionStage",
    "inspect_experiment_result",
]


def inspect_experiment_result(path: Path) -> ExperimentInspection:
    """Validate and interpret one supported result artifact without modifying it."""
    try:
        document = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as error:
        raise ExperimentResultInspectionError(f"invalid result JSON: {error}") from error

    root = _mapping(document, "result root")
    schema_id = _text(root, "schema_id", "result root")
    if schema_id == XJTU_HOLDOUT_RESULT_SCHEMA_ID:
        from industrial_phm.experiments.xjtu_holdout_inspection import (
            inspect_xjtu_holdout,
        )

        return inspect_xjtu_holdout(root, path)
    elif schema_id == IMS_CROSS_TEST_RESULT_SCHEMA_ID:
        from industrial_phm.experiments.ims_cross_test_inspection import (
            inspect_ims_cross_test,
        )

        return inspect_ims_cross_test(root, path)
    elif schema_id == XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID:
        return _inspect_xjtu_lstm_development(root, path)
    elif schema_id == XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID:
        from industrial_phm.experiments.xjtu_rul_validation_inspection import (
            inspect_xjtu_rul_three_model_validation,
        )

        return inspect_xjtu_rul_three_model_validation(root, path)
    elif schema_id == XJTU_RUL_LSTM_BENCHMARK_RESULT_SCHEMA_ID:
        from industrial_phm.experiments.xjtu_rul_benchmark_inspection import (
            inspect_xjtu_rul_lstm_benchmark,
        )

        return inspect_xjtu_rul_lstm_benchmark(root, path)
    elif schema_id == MIMII_DEVELOPMENT_RESULT_SCHEMA_ID:
        from industrial_phm.experiments.mimii_development_inspection import (
            inspect_mimii_development,
        )

        return inspect_mimii_development(root, path)
    raise ExperimentResultInspectionError(
        f"unsupported experiment result schema_id {schema_id!r}; expected one of "
        f"{XJTU_HOLDOUT_RESULT_SCHEMA_ID!r}, {IMS_CROSS_TEST_RESULT_SCHEMA_ID!r}, "
        f"{XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID!r}, "
        f"{MIMII_DEVELOPMENT_RESULT_SCHEMA_ID!r}, "
        f"{XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID!r}, "
        f"{XJTU_RUL_LSTM_BENCHMARK_RESULT_SCHEMA_ID!r}"
    )


def render_experiment_inspection_text(inspection: ExperimentInspection) -> str:
    """Render an experiment inspection for the developer-facing CLI surface."""
    lines = [
        "Experiment Result",
        f"  Schema: {inspection.schema_id}",
        f"  Status: {inspection.status}",
    ]
    for stage in inspection.stages:
        lines.extend(("", stage.name, f"  Status: {stage.status}"))
        lines.extend(f"  {fact.label}: {fact.value}" for fact in stage.facts)
        lines.extend(f"  Warning: {warning}" for warning in stage.warnings)
    return "\n".join(lines)


def _inspect_xjtu_lstm_development(
    root: Mapping[str, object],
    path: Path,
) -> ExperimentInspection:
    config = get_xjtu_lstm_development_configuration()
    fold = next(
        (item for item in get_xjtu_reference_split().folds if item.fold_id == config.fold_id),
        None,
    )
    if fold is None:
        raise ExperimentResultInspectionError(
            f"packaged XJTU split does not contain {config.fold_id!r}"
        )

    provenance = _mapping_field(root, "provenance", "result root")
    expected_identity = (
        ("experiment_id", config.experiment_id),
        ("dataset_id", config.dataset_id),
        ("split_id", config.split_id),
        ("fold_id", config.fold_id),
        ("evidence_class", XJTU_LSTM_DEVELOPMENT_EVIDENCE_CLASS),
    )
    for field_name, expected in expected_identity:
        _expect_equal(
            _text(provenance, field_name, "provenance"),
            expected,
            f"provenance.{field_name}",
        )
    declared_revision = _revision(provenance, "code_revision", "provenance")

    profile_assets = tuple(dict.fromkeys((*fold.train, *fold.validation, *fold.test)))
    expected_source_count = sum(
        get_xjtu_expected_acquisition_count(asset_id) for asset_id in profile_assets
    )
    expected_train_count = sum(
        get_xjtu_expected_acquisition_count(asset_id) for asset_id in fold.train
    )
    expected_reference_count = sum(
        early_third_length(get_xjtu_expected_acquisition_count(asset_id)) for asset_id in fold.train
    )
    expected_validation_count = sum(
        get_xjtu_expected_acquisition_count(asset_id) for asset_id in fold.validation
    )
    prefix_width = XJTU_LSTM_SEQUENCE_SPEC.length - 1
    expected_reference_prefix = len(fold.train) * prefix_width
    expected_validation_prefix = len(fold.validation) * prefix_width
    expected_reference_windows = expected_reference_count - expected_reference_prefix
    expected_validation_windows = expected_validation_count - expected_validation_prefix

    source_scope = _mapping_field(root, "source_scope", "result root")
    source_count = _positive_int(
        source_scope,
        "verified_source_acquisition_count",
        "source_scope",
    )
    _expect_equal(source_count, expected_source_count, "XJTU verified source acquisition count")
    train_bearings = _text_sequence(source_scope, "train_bearings", "source_scope")
    validation_bearings = _text_sequence(source_scope, "validation_bearings", "source_scope")
    excluded = _text_sequence(source_scope, "excluded", "source_scope")
    _expect_equal(train_bearings, tuple(fold.train), "XJTU LSTM train bearing order")
    _expect_equal(validation_bearings, tuple(fold.validation), "XJTU LSTM validation bearing order")
    _expect_equal(
        excluded,
        tuple(f"test:{asset_id}" for asset_id in fold.test),
        "XJTU LSTM excluded holdout bearings",
    )

    feature_schema = _mapping_field(root, "feature_schema", "result root")
    selected_features = _text_sequence(feature_schema, "selected_features", "feature_schema")
    _expect_equal(selected_features, tuple(config.selected_features), "selected feature schema")
    _expect_equal(
        _positive_int(feature_schema, "selected_feature_count", "feature_schema"),
        len(selected_features),
        "selected feature count",
    )
    _expect_equal(
        _text(feature_schema, "feature_set_id", "feature_schema"),
        config.feature_set_id,
        "feature_set_id",
    )

    preprocessing = _mapping_field(root, "preprocessing", "result root")
    _expect_equal(
        _text(preprocessing, "fit_partition", "preprocessing"),
        config.fit_partition.value,
        "preprocessing.fit_partition",
    )
    _expect_equal(
        _text(preprocessing, "scaling_strategy", "preprocessing"),
        config.scaling_strategy.value,
        "preprocessing.scaling_strategy",
    )
    preprocessing_fit_count = _positive_int(
        preprocessing,
        "fit_observation_count",
        "preprocessing",
    )
    _expect_equal(
        preprocessing_fit_count,
        expected_train_count,
        "XJTU LSTM preprocessing fit population",
    )
    fitted_center = _number_sequence(preprocessing, "fitted_center", "preprocessing")
    fitted_scale = _number_sequence(preprocessing, "fitted_scale", "preprocessing")
    zero_iqr_features = _text_sequence(preprocessing, "zero_iqr_features", "preprocessing")
    _expect_equal(len(fitted_center), len(selected_features), "preprocessing fitted center width")
    _expect_equal(len(fitted_scale), len(selected_features), "preprocessing fitted scale width")
    if any(value <= 0.0 for value in fitted_scale):
        raise ExperimentResultInspectionError("preprocessing.fitted_scale must be positive")
    unknown_zero_iqr = sorted(set(zero_iqr_features) - set(selected_features))
    if unknown_zero_iqr:
        raise ExperimentResultInspectionError(
            f"preprocessing.zero_iqr_features contains unknown feature(s): {unknown_zero_iqr}"
        )

    reference = _mapping_field(root, "reference", "result root")
    _expect_equal(
        _text(reference, "strategy", "reference"),
        config.reference_strategy.value,
        "reference.strategy",
    )
    _expect_equal(
        _text(reference, "sampling_policy_id", "reference"),
        config.sampling_policy_id,
        "reference.sampling_policy_id",
    )
    reference_source_count = _positive_int(
        reference,
        "source_acquisition_count",
        "reference",
    )
    reference_window_count = _positive_int(reference, "window_count", "reference")
    _expect_equal(
        reference_source_count,
        expected_reference_count,
        "XJTU LSTM reference acquisition population",
    )
    _expect_equal(
        reference_window_count,
        expected_reference_windows,
        "XJTU LSTM reference window population",
    )

    sequence = _mapping_field(root, "sequence_construction", "result root")
    _expect_equal(
        _positive_int(sequence, "length", "sequence_construction"),
        XJTU_LSTM_SEQUENCE_SPEC.length,
        "sequence_construction.length",
    )
    _expect_equal(
        _positive_int(sequence, "stride", "sequence_construction"),
        XJTU_LSTM_SEQUENCE_SPEC.stride,
        "sequence_construction.stride",
    )
    _expect_equal(
        _text(sequence, "alignment", "sequence_construction"),
        XJTU_LSTM_SEQUENCE_SPEC.alignment.value,
        "sequence_construction.alignment",
    )
    _expect_equal(
        _positive_int(sequence, "feature_width", "sequence_construction"),
        len(selected_features),
        "sequence_construction.feature_width",
    )
    sequence_reference = _mapping_field(
        sequence,
        "reference",
        "sequence_construction",
    )
    sequence_validation = _mapping_field(
        sequence,
        "validation",
        "sequence_construction",
    )
    sequence_expected = (
        (
            sequence_reference,
            "sequence_construction.reference",
            expected_reference_count,
            expected_reference_windows,
            expected_reference_prefix,
        ),
        (
            sequence_validation,
            "sequence_construction.validation",
            expected_validation_count,
            expected_validation_windows,
            expected_validation_prefix,
        ),
    )
    for values, context, source_expected, window_expected, prefix_expected in sequence_expected:
        _expect_equal(
            _positive_int(values, "source_acquisition_count", context),
            source_expected,
            f"{context}.source_acquisition_count",
        )
        _expect_equal(
            _positive_int(values, "window_count", context),
            window_expected,
            f"{context}.window_count",
        )
        _expect_equal(
            _integer(values, "dropped_prefix_acquisition_count", context),
            prefix_expected,
            f"{context}.dropped_prefix_acquisition_count",
        )

    model = _mapping_field(root, "model", "result root")
    _expect_equal(
        _text(model, "family", "model"),
        config.model_family.value,
        "model.family",
    )
    parameters = _mapping_field(model, "parameters", "model")
    _expect_equal(dict(parameters), dict(config.model_parameters), "model parameters")
    _expect_equal(
        _integer(model, "random_seed", "model"),
        config.random_seed,
        "model.random_seed",
    )
    training = _mapping_field(model, "training", "model")
    _expect_equal(_text(training, "framework", "model.training"), "pytorch", "training framework")
    framework_version = _text(training, "framework_version", "model.training")
    if not framework_version.startswith("2.14."):
        raise ExperimentResultInspectionError(
            "model.training.framework_version must match the PyTorch 2.14 reference runtime"
        )
    configured_device = config.model_parameters["device"]
    configured_precision = config.model_parameters["numeric_precision"]
    configured_deterministic = config.model_parameters["deterministic_algorithms"]
    configured_batch_size = config.model_parameters["batch_size"]
    configured_epochs = config.model_parameters["epochs"]
    if not isinstance(configured_device, str):
        raise ExperimentResultInspectionError("configured model device must be a string")
    if not isinstance(configured_precision, str):
        raise ExperimentResultInspectionError("configured numeric_precision must be a string")
    if not isinstance(configured_deterministic, bool):
        raise ExperimentResultInspectionError(
            "configured deterministic_algorithms must be a boolean"
        )
    for field_name, expected in (
        ("device", configured_device),
        ("numeric_precision", configured_precision),
        ("sampling_policy_id", config.sampling_policy_id),
    ):
        _expect_equal(
            _text(training, field_name, "model.training"),
            expected,
            f"model.training.{field_name}",
        )
    _expect_equal(
        _boolean(training, "deterministic_algorithms", "model.training"),
        configured_deterministic,
        "model.training.deterministic_algorithms",
    )
    _expect_equal(
        _positive_int(training, "fit_window_count", "model.training"),
        expected_reference_windows,
        "model.training.fit_window_count",
    )
    parameter_count = _positive_int(training, "parameter_count", "model.training")
    if (
        isinstance(configured_batch_size, bool)
        or not isinstance(configured_batch_size, int)
        or configured_batch_size <= 0
    ):
        raise ExperimentResultInspectionError("configured batch_size must be a positive integer")
    if (
        isinstance(configured_epochs, bool)
        or not isinstance(configured_epochs, int)
        or configured_epochs <= 0
    ):
        raise ExperimentResultInspectionError("configured epochs must be a positive integer")
    _expect_equal(
        _positive_int(training, "batch_size", "model.training"),
        configured_batch_size,
        "model.training.batch_size",
    )
    epochs = _positive_int(training, "epochs", "model.training")
    _expect_equal(epochs, configured_epochs, "model.training.epochs")
    epoch_losses = _number_sequence(training, "epoch_losses", "model.training")
    _expect_equal(len(epoch_losses), epochs, "model.training.epoch_losses length")
    if any(loss < 0.0 for loss in epoch_losses):
        raise ExperimentResultInspectionError("model.training.epoch_losses must be non-negative")
    final_epoch_loss = _number(
        training,
        "final_epoch_mean_training_loss",
        "model.training",
    )
    if not math.isclose(final_epoch_loss, epoch_losses[-1], rel_tol=1e-12, abs_tol=1e-15):
        raise ExperimentResultInspectionError(
            "model.training.final_epoch_mean_training_loss must equal the final epoch loss"
        )

    scoring = _mapping_field(root, "scoring", "result root")
    _expect_equal(
        _text(scoring, "score_semantics_id", "scoring"),
        MEAN_SQUARED_RECONSTRUCTION_ERROR_ID,
        "scoring.score_semantics_id",
    )
    _expect_equal(
        _text(scoring, "direction", "scoring"),
        SCORE_SEMANTICS,
        "scoring.direction",
    )
    _expect_equal(
        _text(scoring, "alignment", "scoring"),
        XJTU_LSTM_SEQUENCE_SPEC.alignment.value,
        "scoring.alignment",
    )
    _expect_equal(
        _text(scoring, "input_numeric_precision", "scoring"),
        configured_precision,
        "scoring.input_numeric_precision",
    )
    scoring_window_count = _positive_int(scoring, "window_count", "scoring")
    _expect_equal(
        scoring_window_count,
        expected_validation_windows,
        "XJTU LSTM scoring window population",
    )
    trajectory_scores = _xjtu_lstm_trajectory_scores(
        scoring,
        experiment_id=config.experiment_id,
        feature_set_id=config.feature_set_id,
        feature_names=selected_features,
        validation_assets=tuple(fold.validation),
    )
    try:
        trajectory_evaluation = evaluate_xjtu_lstm_development_scores(trajectory_scores)
    except XjtuLstmDevelopmentEvaluationError as error:
        raise ExperimentResultInspectionError(
            f"scoring.trajectories violate the XJTU LSTM evaluation contract: {error}"
        ) from error

    evaluation = _mapping_field(root, "evaluation", "result root")
    _expect_equal(
        _text(evaluation, "partition_semantics", "evaluation"),
        XJTU_LSTM_DEVELOPMENT_EVIDENCE_CLASS,
        "evaluation.partition_semantics",
    )
    _expect_equal(
        _text(evaluation, "lifecycle_segmentation", "evaluation"),
        "original-full-run-thirds",
        "evaluation.lifecycle_segmentation",
    )
    statistics = _text_sequence(evaluation, "statistics", "evaluation")
    _expect_equal(
        statistics,
        (
            "acquisition-order-spearman-rho",
            "lifecycle-late-vs-middle-rank-probability",
            "feature-mean-reconstruction-residual",
        ),
        "evaluation.statistics",
    )
    aggregation = _text(evaluation, "aggregation", "evaluation")
    _expect_equal(
        aggregation,
        "three-bearing-equal-weight-mean",
        "evaluation.aggregation",
    )
    mean_rho = _number(
        evaluation,
        "mean_bearing_acquisition_order_spearman_rho",
        "evaluation",
    )
    mean_rank_probability = _number(
        evaluation,
        "mean_bearing_late_vs_middle_rank_probability",
        "evaluation",
    )
    _expect_close(
        mean_rho,
        trajectory_evaluation.mean_bearing_acquisition_order_spearman_rho,
        "evaluation.mean_bearing_acquisition_order_spearman_rho from score trajectories",
    )
    _expect_close(
        mean_rank_probability,
        trajectory_evaluation.mean_bearing_late_vs_middle_rank_probability,
        "evaluation.mean_bearing_late_vs_middle_rank_probability from score trajectories",
    )

    raw_feature_summary = _sequence(evaluation, "feature_residual_summary", "evaluation")
    _expect_equal(
        len(raw_feature_summary),
        len(selected_features),
        "evaluation.feature_residual_summary length",
    )
    feature_summary_values: list[float] = []
    for index, (raw_feature, expected_name) in enumerate(
        zip(raw_feature_summary, selected_features, strict=True)
    ):
        context = f"evaluation.feature_residual_summary[{index}]"
        feature = _mapping(raw_feature, context)
        _expect_equal(
            _text(feature, "feature_name", context),
            expected_name,
            f"{context}.feature_name",
        )
        residual = _number(feature, "mean_residual", context)
        if residual < 0.0:
            raise ExperimentResultInspectionError(f"{context}.mean_residual must be non-negative")
        _expect_close(
            residual,
            trajectory_evaluation.mean_bearing_feature_residuals[index],
            f"{context}.mean_residual from score trajectories",
        )
        feature_summary_values.append(residual)

    raw_bearings = _sequence(evaluation, "bearings", "evaluation")
    _expect_equal(len(raw_bearings), len(fold.validation), "evaluation bearing count")
    bearing_lines: list[str] = []
    bearing_rhos: list[float] = []
    bearing_rank_probabilities: list[float] = []
    bearing_feature_residuals: list[tuple[float, ...]] = []
    for index, (raw_bearing, expected_asset, trajectory_bearing) in enumerate(
        zip(
            raw_bearings,
            fold.validation,
            trajectory_evaluation.bearing_results,
            strict=True,
        )
    ):
        context = f"evaluation.bearings[{index}]"
        bearing = _mapping(raw_bearing, context)
        asset_id = _text(bearing, "asset_id", context)
        _expect_equal(asset_id, expected_asset, f"{context}.asset_id")
        source_acquisitions = _positive_int(
            bearing,
            "source_acquisition_count",
            context,
        )
        expected_acquisitions = get_xjtu_expected_acquisition_count(expected_asset)
        _expect_equal(
            source_acquisitions,
            expected_acquisitions,
            f"{context}.source_acquisition_count",
        )
        score_windows = _positive_int(bearing, "score_window_count", context)
        _expect_equal(
            score_windows,
            expected_acquisitions - prefix_width,
            f"{context}.score_window_count",
        )
        _expect_equal(
            _integer(bearing, "dropped_prefix_count", context),
            prefix_width,
            f"{context}.dropped_prefix_count",
        )
        rho = _number(bearing, "acquisition_order_spearman_rho", context)
        rank_probability = _number(bearing, "late_vs_middle_rank_probability", context)
        _expect_close(
            rho,
            trajectory_bearing.acquisition_order_spearman_rho,
            f"{context}.acquisition_order_spearman_rho from score trajectory",
        )
        _expect_close(
            rank_probability,
            trajectory_bearing.late_vs_middle_rank_probability,
            f"{context}.late_vs_middle_rank_probability from score trajectory",
        )
        residuals = _number_sequence(bearing, "mean_feature_residuals", context)
        _expect_equal(
            len(residuals),
            len(selected_features),
            f"{context}.mean_feature_residuals width",
        )
        if any(value < 0.0 for value in residuals):
            raise ExperimentResultInspectionError(
                f"{context}.mean_feature_residuals must be non-negative"
            )
        for feature_index, (residual, expected_residual) in enumerate(
            zip(residuals, trajectory_bearing.mean_feature_residuals, strict=True)
        ):
            _expect_close(
                residual,
                expected_residual,
                f"{context}.mean_feature_residuals[{feature_index}] from score trajectory",
            )
        bearing_rhos.append(rho)
        bearing_rank_probabilities.append(rank_probability)
        bearing_feature_residuals.append(residuals)
        bearing_lines.append(
            f"{asset_id}: source={source_acquisitions}, windows={score_windows}, "
            f"rho={rho:.6g}, late_vs_middle={rank_probability:.6g}"
        )

    _expect_close(
        mean_rho,
        math.fsum(bearing_rhos) / len(bearing_rhos),
        "evaluation.mean_bearing_acquisition_order_spearman_rho",
    )
    _expect_close(
        mean_rank_probability,
        math.fsum(bearing_rank_probabilities) / len(bearing_rank_probabilities),
        "evaluation.mean_bearing_late_vs_middle_rank_probability",
    )
    for feature_index, summary_value in enumerate(feature_summary_values):
        expected_residual = math.fsum(
            values[feature_index] for values in bearing_feature_residuals
        ) / len(bearing_feature_residuals)
        _expect_close(
            summary_value,
            expected_residual,
            f"evaluation.feature_residual_summary[{feature_index}].mean_residual",
        )

    available, unsupported = validated_capability_scope(root, LSTM_AVAILABLE_CAPABILITIES)

    return ExperimentInspection(
        schema_id=XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID,
        status="completed",
        stages=(
            InspectionStage(
                "Source",
                "completed",
                (
                    InspectionFact("Dataset", config.dataset_id),
                    InspectionFact(
                        "Verified source profile",
                        f"{source_count} acquisition CSV files",
                    ),
                    InspectionFact("Split scope", f"{config.split_id} / {config.fold_id}"),
                    InspectionFact("Train bearings", ", ".join(train_bearings)),
                    InspectionFact("Validation bearings", ", ".join(validation_bearings)),
                    InspectionFact("Excluded", ", ".join(excluded)),
                ),
            ),
            InspectionStage(
                "Canonical",
                "completed",
                (
                    InspectionFact("Channels", ", ".join(XJTU_SY_CHANNELS)),
                    InspectionFact(
                        "Cardinality",
                        "1 acquisition CSV -> 1 two-channel bearing observation",
                    ),
                ),
            ),
            InspectionStage(
                "Feature",
                "completed",
                (
                    InspectionFact("Feature set", config.feature_set_id),
                    InspectionFact(
                        f"Selected features ({len(selected_features)})",
                        ", ".join(selected_features),
                    ),
                ),
            ),
            InspectionStage(
                "Preprocessing",
                "completed",
                (
                    InspectionFact(
                        "Fit scope",
                        f"{config.fit_partition.value} / {preprocessing_fit_count} acquisitions",
                    ),
                    InspectionFact("Scaling", config.scaling_strategy.value),
                    InspectionFact("Zero-IQR features", len(zero_iqr_features)),
                ),
            ),
            InspectionStage(
                "Reference",
                "completed",
                (
                    InspectionFact("Strategy", config.reference_strategy.value),
                    InspectionFact("Source acquisitions", reference_source_count),
                    InspectionFact("Sampling policy", config.sampling_policy_id),
                ),
            ),
            InspectionStage(
                "Sequence Construction",
                "completed",
                (
                    InspectionFact("Length", XJTU_LSTM_SEQUENCE_SPEC.length),
                    InspectionFact("Stride", XJTU_LSTM_SEQUENCE_SPEC.stride),
                    InspectionFact("Alignment", XJTU_LSTM_SEQUENCE_SPEC.alignment.value),
                    InspectionFact("Feature width", len(selected_features)),
                    InspectionFact(
                        "Reference population",
                        f"{expected_reference_count} acquisitions -> "
                        f"{expected_reference_windows} windows / "
                        f"{expected_reference_prefix} dropped prefix",
                    ),
                    InspectionFact(
                        "Validation population",
                        f"{expected_validation_count} acquisitions -> "
                        f"{expected_validation_windows} windows / "
                        f"{expected_validation_prefix} dropped prefix",
                    ),
                ),
            ),
            InspectionStage(
                "Population",
                "completed",
                (
                    InspectionFact("Complete train acquisitions", preprocessing_fit_count),
                    InspectionFact("Reference acquisitions", reference_source_count),
                    InspectionFact("Model-fit windows", expected_reference_windows),
                    InspectionFact("Validation acquisitions", expected_validation_count),
                    InspectionFact("Scoring windows", scoring_window_count),
                ),
            ),
            InspectionStage(
                "Model",
                "completed",
                (
                    InspectionFact("Family", config.model_family.value),
                    InspectionFact("Parameters", format_parameters(config.model_parameters)),
                    InspectionFact("Framework", f"pytorch {framework_version}"),
                    InspectionFact("Device", _text(training, "device", "model.training")),
                    InspectionFact(
                        "Numeric precision",
                        _text(training, "numeric_precision", "model.training"),
                    ),
                    InspectionFact("Random seed", config.random_seed),
                    InspectionFact("Epochs", epochs),
                    InspectionFact("Parameter count", parameter_count),
                    InspectionFact(
                        "Final epoch mean training loss",
                        f"{final_epoch_loss:.6g}",
                    ),
                ),
            ),
            InspectionStage(
                "Scoring",
                "completed",
                (
                    InspectionFact(
                        "Semantics",
                        MEAN_SQUARED_RECONSTRUCTION_ERROR_ID,
                    ),
                    InspectionFact("Direction", SCORE_SEMANTICS),
                    InspectionFact("Alignment", XJTU_LSTM_SEQUENCE_SPEC.alignment.value),
                    InspectionFact(
                        "Scope",
                        f"{len(validation_bearings)} validation bearings / "
                        f"{scoring_window_count} windows",
                    ),
                    InspectionFact(
                        "Trajectory evidence",
                        f"{trajectory_scores.window_count} acquisition-aligned scores / "
                        f"{len(selected_features)} residual features",
                    ),
                ),
            ),
            InspectionStage(
                "Evaluation",
                "completed",
                (
                    InspectionFact("Scope", XJTU_LSTM_DEVELOPMENT_EVIDENCE_CLASS),
                    InspectionFact("Lifecycle", "original-full-run-thirds"),
                    InspectionFact("Statistics", ", ".join(statistics)),
                    InspectionFact("Aggregation", aggregation),
                    *(InspectionFact("Bearing evidence", line) for line in bearing_lines),
                    InspectionFact("Mean rho", f"{mean_rho:.6g}"),
                    InspectionFact("Mean late-vs-middle", f"{mean_rank_probability:.6g}"),
                    InspectionFact(
                        "Feature residual summary",
                        f"{len(feature_summary_values)} robust-scaled features",
                    ),
                    InspectionFact("Selection or threshold calibration", "none"),
                ),
                warnings=(
                    "Retrospective development evidence; not a fresh holdout or test result.",
                ),
            ),
            _capability_stage(available, unsupported),
            _provenance_stage(
                config,
                declared_revision,
                path,
                evidence_facts=(
                    InspectionFact("Evidence class", XJTU_LSTM_DEVELOPMENT_EVIDENCE_CLASS),
                ),
            ),
        ),
    )


def _xjtu_lstm_trajectory_scores(
    scoring: Mapping[str, object],
    *,
    experiment_id: str,
    feature_set_id: str,
    feature_names: tuple[str, ...],
    validation_assets: tuple[str, ...],
) -> ReconstructionScores:
    raw_trajectories = _sequence(scoring, "trajectories", "scoring")
    _expect_equal(
        len(raw_trajectories),
        len(validation_assets),
        "scoring.trajectories bearing count",
    )

    window_ids: list[str] = []
    sequence_ids: list[str] = []
    asset_ids: list[str] = []
    partition_ids: list[str] = []
    source_observation_ids: list[str] = []
    acquisition_indexes: list[int] = []
    scores: list[float] = []
    feature_residuals: list[tuple[float, ...]] = []

    for trajectory_index, (raw_trajectory, expected_asset) in enumerate(
        zip(raw_trajectories, validation_assets, strict=True)
    ):
        trajectory_context = f"scoring.trajectories[{trajectory_index}]"
        trajectory = _mapping(raw_trajectory, trajectory_context)
        asset_id = _text(trajectory, "asset_id", trajectory_context)
        _expect_equal(asset_id, expected_asset, f"{trajectory_context}.asset_id")
        observations = _sequence(trajectory, "observations", trajectory_context)
        source_count = get_xjtu_expected_acquisition_count(asset_id)
        expected_positions = tuple(
            range(
                XJTU_LSTM_SEQUENCE_SPEC.length,
                source_count + 1,
                XJTU_LSTM_SEQUENCE_SPEC.stride,
            )
        )
        _expect_equal(
            len(observations),
            len(expected_positions),
            f"{trajectory_context}.observations length",
        )

        for observation_index, (raw_observation, expected_position) in enumerate(
            zip(observations, expected_positions, strict=True)
        ):
            context = f"{trajectory_context}.observations[{observation_index}]"
            observation = _mapping(raw_observation, context)
            position = _positive_int(observation, "acquisition_index", context)
            _expect_equal(position, expected_position, f"{context}.acquisition_index")
            expected_window_id = (
                f"{asset_id}:window-{position - XJTU_LSTM_SEQUENCE_SPEC.length + 1}-{position}"
            )
            window_id = _text(observation, "window_id", context)
            _expect_equal(window_id, expected_window_id, f"{context}.window_id")
            source_observation_id = _text(observation, "source_observation_id", context)
            _expect_equal(
                source_observation_id,
                f"{asset_id}:acquisition-{position}",
                f"{context}.source_observation_id",
            )
            score = _number(observation, "score", context)
            if score < 0.0:
                raise ExperimentResultInspectionError(f"{context}.score must be non-negative")
            residuals = _number_sequence(observation, "feature_residuals", context)
            _expect_equal(
                len(residuals),
                len(feature_names),
                f"{context}.feature_residuals width",
            )
            if any(residual < 0.0 for residual in residuals):
                raise ExperimentResultInspectionError(
                    f"{context}.feature_residuals must be non-negative"
                )

            window_ids.append(window_id)
            sequence_ids.append(asset_id)
            asset_ids.append(asset_id)
            partition_ids.append("validation")
            source_observation_ids.append(source_observation_id)
            acquisition_indexes.append(position)
            scores.append(score)
            feature_residuals.append(residuals)

    try:
        return ReconstructionScores(
            experiment_id=experiment_id,
            feature_set_id=feature_set_id,
            feature_names=feature_names,
            spec=XJTU_LSTM_SEQUENCE_SPEC,
            window_ids=tuple(window_ids),
            sequence_ids=tuple(sequence_ids),
            asset_ids=tuple(asset_ids),
            partition_ids=tuple(partition_ids),
            aligned_source_observation_ids=tuple(source_observation_ids),
            aligned_source_positions=tuple(acquisition_indexes),
            scores=tuple(scores),
            feature_residuals=tuple(feature_residuals),
        )
    except ReconstructionScoringError as error:
        raise ExperimentResultInspectionError(
            f"scoring.trajectories violate the reconstruction score contract: {error}"
        ) from error
