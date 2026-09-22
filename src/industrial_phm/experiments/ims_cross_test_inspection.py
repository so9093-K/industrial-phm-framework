"""Schema-specific inspection for IMS cross-test evidence."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from industrial_phm.experiments.config import ExperimentConfig, ExperimentParameter
from industrial_phm.experiments.ims import (
    IMS_BEARING_COUNT,
    IMS_EVALUATION_ACQUISITION_COUNT,
    IMS_EVALUATION_ARCHIVE_SCOPE,
    IMS_EVALUATION_TEST_ID,
    IMS_TRAIN_ACQUISITION_COUNT,
    IMS_TRAIN_TEST_ID,
    get_ims_cross_test_configuration,
)
from industrial_phm.experiments.ims_cross_test import IMS_CROSS_TEST_RESULT_SCHEMA_ID
from industrial_phm.experiments.result_inspection_support import (
    ExperimentInspection,
    InspectionFact,
    InspectionStage,
    _capability_stage,
    _expect_equal,
    _integer,
    _mapping,
    _mapping_field,
    _number,
    _positive_int,
    _provenance_stage,
    _revision,
    _sequence,
    _text,
    _text_sequence,
)

_SCORE_SEMANTICS = "higher-is-more-anomalous"
_AVAILABLE_CAPABILITIES = (
    "anomaly-scoring",
    "descriptive-score-trajectory-evaluation",
)
_UNSUPPORTED_CAPABILITIES = (
    "thresholded-state-detection",
    "health-assessment",
    "fault-diagnostics",
    "prognostics-rul",
)


def _acquisition_level_sequence_stage() -> InspectionStage:
    return InspectionStage(
        "Sequence Construction",
        "not applicable",
        (
            InspectionFact(
                "Reason",
                "model consumes acquisition-level feature observations",
            ),
        ),
    )


def _validated_capability_scope(
    root: Mapping[str, object],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    capability = _mapping_field(root, "capability_scope", "result root")
    available = _text_sequence(capability, "available", "capability_scope")
    unsupported = _text_sequence(capability, "unsupported_or_not_validated", "capability_scope")
    _expect_equal(available, _AVAILABLE_CAPABILITIES, "available capability scope")
    _expect_equal(unsupported, _UNSUPPORTED_CAPABILITIES, "unsupported capability scope")
    return available, unsupported


def inspect_ims_cross_test(root: Mapping[str, object], path: Path) -> ExperimentInspection:
    config = get_ims_cross_test_configuration()
    provenance = _mapping_field(root, "provenance", "result root")
    _validate_ims_identity(provenance, config)
    source_scope = _mapping_field(root, "source_scope", "result root")
    train_scope = _mapping_field(source_scope, "train", "source_scope")
    evaluation_scope = _mapping_field(source_scope, "evaluation", "source_scope")
    _validate_ims_source_scope(train_scope, evaluation_scope)

    verified_source_count = _positive_int(
        source_scope, "verified_source_acquisition_count", "source_scope"
    )
    train_acquisitions = _positive_int(train_scope, "acquisition_count", "source_scope.train")
    train_bearings = _positive_int(train_scope, "bearing_count", "source_scope.train")
    evaluation_acquisitions = _positive_int(
        evaluation_scope, "acquisition_count", "source_scope.evaluation"
    )
    evaluation_bearings = _positive_int(
        evaluation_scope, "bearing_count", "source_scope.evaluation"
    )
    train_observations = train_acquisitions * train_bearings
    scoring_observations = evaluation_acquisitions * evaluation_bearings

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

    population = _mapping_field(root, "population_flow", "result root")
    complete_count = _positive_int(
        population, "complete_train_observation_count", "population_flow"
    )
    reference_count = _positive_int(population, "reference_observation_count", "population_flow")
    fit_count = _positive_int(population, "model_fit_observation_count", "population_flow")
    artifact_scoring_count = _positive_int(
        population, "scoring_observation_count", "population_flow"
    )
    _expect_equal(complete_count, train_observations, "complete train population")
    _expect_equal(reference_count, train_observations, "reference population")
    _expect_equal(fit_count, train_observations, "model-fit population")
    _expect_equal(artifact_scoring_count, scoring_observations, "scoring population")

    model = _mapping_field(root, "model", "result root")
    _validate_ims_model(model, config)
    evaluation = _mapping_field(root, "evaluation", "result root")
    raw_evaluation_bearings = _sequence(evaluation, "bearings", "evaluation")
    _expect_equal(len(raw_evaluation_bearings), evaluation_bearings, "evaluation bearing count")
    evaluation_lines = []
    evaluated_observations = 0
    for index, raw_bearing in enumerate(raw_evaluation_bearings):
        context = f"evaluation.bearings[{index}]"
        bearing = _mapping(raw_bearing, context)
        _expect_equal(
            _text(bearing, "test_id", context), IMS_EVALUATION_TEST_ID, f"{context}.test_id"
        )
        observation_count = _positive_int(bearing, "full_run_observation_count", context)
        _expect_equal(
            observation_count,
            evaluation_acquisitions,
            f"{context}.full_run_observation_count",
        )
        evaluated_observations += observation_count
        asset_id = _text(bearing, "asset_id", context)
        rho = _number(bearing, "acquisition_order_spearman_rho", context)
        rank_probability = _number(bearing, "late_vs_middle_rank_probability", context)
        evaluation_lines.append(
            f"  {asset_id}: observations={observation_count}, rho={rho:.6g}, "
            f"late_vs_middle={rank_probability:.6g}"
        )
    _expect_equal(evaluated_observations, scoring_observations, "evaluated observation count")
    statistics = _text_sequence(evaluation, "statistics", "evaluation")
    aggregation = _text(evaluation, "aggregation", "evaluation")
    partition_semantics = _text(evaluation, "partition_semantics", "evaluation")
    mean_rho = _number(evaluation, "mean_bearing_acquisition_order_spearman_rho", "evaluation")
    mean_rank_probability = _number(
        evaluation, "mean_bearing_late_vs_middle_rank_probability", "evaluation"
    )

    available, unsupported = _validated_capability_scope(root)
    excluded = _text_sequence(source_scope, "excluded", "source_scope")
    declared_revision = _revision(provenance, "code_revision", "provenance")

    return ExperimentInspection(
        schema_id=IMS_CROSS_TEST_RESULT_SCHEMA_ID,
        status="consumed",
        stages=(
            InspectionStage(
                "Source",
                "completed",
                (
                    InspectionFact("Dataset", config.dataset_id),
                    InspectionFact(
                        "Verified source profile",
                        f"{verified_source_count} acquisition files",
                    ),
                    InspectionFact(
                        "Train scope",
                        f"{IMS_TRAIN_TEST_ID} complete / {train_acquisitions} files",
                    ),
                    InspectionFact(
                        "Evaluation scope",
                        f"{IMS_EVALUATION_TEST_ID} {IMS_EVALUATION_ARCHIVE_SCOPE} / "
                        f"{evaluation_acquisitions} files",
                    ),
                    InspectionFact("Excluded", ", ".join(excluded)),
                ),
            ),
            InspectionStage(
                "Canonical",
                "completed",
                (
                    InspectionFact("Channels", "vibration"),
                    InspectionFact(
                        "Cardinality",
                        f"1 acquisition file -> {IMS_BEARING_COUNT} bearing observations",
                    ),
                    InspectionFact(
                        "Train conversion",
                        f"{train_acquisitions} files -> {train_observations} observations",
                    ),
                    InspectionFact(
                        "Evaluation conversion",
                        f"{evaluation_acquisitions} files -> {scoring_observations} observations",
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
                        f"{config.fit_partition.value} / {complete_count} observations",
                    ),
                    InspectionFact("Scaling", config.scaling_strategy.value),
                ),
            ),
            InspectionStage(
                "Reference",
                "completed",
                (
                    InspectionFact("Strategy", config.reference_strategy.value),
                    InspectionFact("Eligible observations", reference_count),
                ),
            ),
            _acquisition_level_sequence_stage(),
            InspectionStage(
                "Population",
                "completed",
                (
                    InspectionFact("Sampling policy", config.sampling_policy_id),
                    InspectionFact("Train observations", complete_count),
                    InspectionFact("Reference-eligible observations", reference_count),
                    InspectionFact("Model-fit observations", fit_count),
                    InspectionFact("Cross-test scoring observations", artifact_scoring_count),
                ),
            ),
            InspectionStage(
                "Model",
                "completed",
                (
                    InspectionFact("Family", config.model_family.value),
                    InspectionFact("Parameters", _format_parameters(config.model_parameters)),
                    InspectionFact("Random seed", config.random_seed),
                    InspectionFact("Score semantics", _SCORE_SEMANTICS),
                ),
            ),
            InspectionStage(
                "Scoring",
                "completed",
                (
                    InspectionFact(
                        "Scope",
                        f"{evaluation_bearings} Set 3 bearings / "
                        f"{artifact_scoring_count} observations",
                    ),
                ),
            ),
            InspectionStage(
                "Evaluation",
                "consumed",
                (
                    InspectionFact("Scope", partition_semantics),
                    InspectionFact("Statistics", ", ".join(statistics)),
                    InspectionFact("Aggregation", aggregation),
                    *(
                        InspectionFact("Bearing evidence", line.removeprefix("  "))
                        for line in evaluation_lines
                    ),
                    InspectionFact("Mean rho", f"{mean_rho:.6g}"),
                    InspectionFact("Mean late-vs-middle", f"{mean_rank_probability:.6g}"),
                    InspectionFact("Selection or threshold calibration", "none"),
                ),
            ),
            _capability_stage(available, unsupported),
            _provenance_stage(config, declared_revision, path),
        ),
    )


def _validate_ims_identity(provenance: Mapping[str, object], config: ExperimentConfig) -> None:
    expected = (
        ("dataset_id", config.dataset_id),
        ("experiment_id", config.experiment_id),
        ("split_id", config.split_id),
        ("fold_id", config.fold_id),
    )
    for field_name, expected_value in expected:
        _expect_equal(
            _text(provenance, field_name, "provenance"),
            expected_value,
            f"provenance.{field_name}",
        )


def _validate_ims_source_scope(
    train: Mapping[str, object], evaluation: Mapping[str, object]
) -> None:
    expected: tuple[tuple[Mapping[str, object], str, str, str], ...] = (
        (train, "test_id", IMS_TRAIN_TEST_ID, "source_scope.train"),
        (train, "scope", "complete-archive-set", "source_scope.train"),
        (evaluation, "test_id", IMS_EVALUATION_TEST_ID, "source_scope.evaluation"),
        (
            evaluation,
            "archive_scope",
            IMS_EVALUATION_ARCHIVE_SCOPE,
            "source_scope.evaluation",
        ),
    )
    for values, field_name, expected_value, context in expected:
        _expect_equal(
            _text(values, field_name, context),
            expected_value,
            f"{context}.{field_name}",
        )

    numeric_expected = (
        (train, "acquisition_count", IMS_TRAIN_ACQUISITION_COUNT, "source_scope.train"),
        (train, "bearing_count", IMS_BEARING_COUNT, "source_scope.train"),
        (
            evaluation,
            "acquisition_count",
            IMS_EVALUATION_ACQUISITION_COUNT,
            "source_scope.evaluation",
        ),
        (evaluation, "bearing_count", IMS_BEARING_COUNT, "source_scope.evaluation"),
    )
    for numeric_values, numeric_field, numeric_expected_value, numeric_context in numeric_expected:
        _expect_equal(
            _positive_int(numeric_values, numeric_field, numeric_context),
            numeric_expected_value,
            f"{numeric_context}.{numeric_field}",
        )


def _validate_ims_model(model: Mapping[str, object], config: ExperimentConfig) -> None:
    expected_text = (
        ("model_family", config.model_family.value),
        ("reference_strategy", config.reference_strategy.value),
        ("sampling_policy_id", config.sampling_policy_id),
        ("score_semantics", _SCORE_SEMANTICS),
    )
    for field_name, expected in expected_text:
        _expect_equal(_text(model, field_name, "model"), expected, f"model.{field_name}")
    _expect_equal(_integer(model, "random_seed", "model"), config.random_seed, "model.random_seed")
    parameters = _mapping_field(model, "parameters", "model")
    _expect_equal(dict(parameters), dict(config.model_parameters), "model parameters")


def _format_parameters(parameters: Mapping[str, ExperimentParameter]) -> str:
    return ", ".join(f"{name}={value!r}" for name, value in sorted(parameters.items()))
