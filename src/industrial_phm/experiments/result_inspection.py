"""Read-only summaries for explicitly supported experiment result schemas."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from industrial_phm.adapters import XJTU_SY_CHANNELS, get_xjtu_expected_acquisition_count
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
from industrial_phm.experiments.xjtu import get_xjtu_reference_split
from industrial_phm.experiments.xjtu_finalized import get_xjtu_finalized_configuration
from industrial_phm.experiments.xjtu_holdout import XJTU_HOLDOUT_RESULT_SCHEMA_ID
from industrial_phm.experiments.xjtu_lifecycle import early_third_length
from industrial_phm.experiments.xjtu_lstm import get_xjtu_lstm_development_configuration
from industrial_phm.experiments.xjtu_lstm_result import (
    XJTU_LSTM_DEVELOPMENT_EVIDENCE_CLASS,
    XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID,
)
from industrial_phm.experiments.xjtu_sequence import XJTU_LSTM_SEQUENCE_SPEC
from industrial_phm.models.reconstruction_scoring import (
    MEAN_SQUARED_RECONSTRUCTION_ERROR_ID,
)

_SCORE_SEMANTICS = "higher-is-more-anomalous"
_FULL_GIT_REVISION = re.compile(r"^[0-9a-f]{40}$")
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
_LSTM_AVAILABLE_CAPABILITIES = (
    *_AVAILABLE_CAPABILITIES,
    "reconstruction-residual-evidence",
)


class ExperimentResultInspectionError(ValueError):
    """Raised when a result cannot be inspected as a supported evidence schema."""


InspectionFactValue = str | int | float


@dataclass(frozen=True, slots=True)
class InspectionFact:
    """One display-independent fact resolved from evidence and packaged contracts."""

    label: str
    value: InspectionFactValue


@dataclass(frozen=True, slots=True)
class InspectionStage:
    """One ordered pipeline stage in an experiment inspection read model."""

    name: str
    status: str
    facts: tuple[InspectionFact, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExperimentInspection:
    """Presentation-neutral read model for one validated experiment result."""

    schema_id: str
    status: str
    stages: tuple[InspectionStage, ...]


def inspect_experiment_result(path: Path) -> ExperimentInspection:
    """Validate and interpret one supported result artifact without modifying it."""
    try:
        document = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as error:
        raise ExperimentResultInspectionError(f"invalid result JSON: {error}") from error

    root = _mapping(document, "result root")
    schema_id = _text(root, "schema_id", "result root")
    if schema_id == XJTU_HOLDOUT_RESULT_SCHEMA_ID:
        return _inspect_xjtu_holdout(root, path)
    elif schema_id == IMS_CROSS_TEST_RESULT_SCHEMA_ID:
        return _inspect_ims_cross_test(root, path)
    elif schema_id == XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID:
        return _inspect_xjtu_lstm_development(root, path)
    raise ExperimentResultInspectionError(
        f"unsupported experiment result schema_id {schema_id!r}; expected one of "
        f"{XJTU_HOLDOUT_RESULT_SCHEMA_ID!r}, {IMS_CROSS_TEST_RESULT_SCHEMA_ID!r}, "
        f"{XJTU_LSTM_DEVELOPMENT_RESULT_SCHEMA_ID!r}"
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


def _inspect_xjtu_holdout(root: Mapping[str, object], path: Path) -> ExperimentInspection:
    config = get_xjtu_finalized_configuration()
    _validate_xjtu_identity(root, config)

    source_count = _positive_int(root, "source_acquisition_count", "result root")
    complete_count = _positive_int(root, "complete_train_observation_count", "result root")
    reference_count = _positive_int(root, "reference_observation_count", "result root")
    fit_count = _positive_int(root, "model_fit_observation_count", "result root")
    _expect_equal(fit_count, reference_count, "model fit and reference observation counts")

    raw_bearings = _sequence(root, "holdout_bearings", "result root")
    if not raw_bearings:
        raise ExperimentResultInspectionError("holdout_bearings must contain at least one bearing")
    bearings = tuple(
        _mapping(value, f"holdout_bearings[{index}]") for index, value in enumerate(raw_bearings)
    )
    scoring_count = sum(
        _positive_int(bearing, "full_run_observation_count", f"holdout_bearings[{index}]")
        for index, bearing in enumerate(bearings)
    )
    evaluation_lines: list[str] = []
    for index, bearing in enumerate(bearings):
        context = f"holdout_bearings[{index}]"
        asset_id = _text(bearing, "asset_id", context)
        condition = _text(bearing, "operating_condition", context)
        observation_count = _positive_int(bearing, "full_run_observation_count", context)
        rho = _number(bearing, "acquisition_order_spearman_rho", context)
        rank_probability = _number(bearing, "late_vs_middle_rank_probability", context)
        evaluation_lines.append(
            f"  {asset_id} ({condition}): observations={observation_count}, "
            f"rho={rho:.6g}, late_vs_middle={rank_probability:.6g}"
        )
    mean_rho = _number(root, "mean_bearing_acquisition_order_spearman_rho", "result root")
    mean_rank_probability = _number(
        root, "mean_bearing_late_vs_middle_rank_probability", "result root"
    )

    fold = next(
        (item for item in get_xjtu_reference_split().folds if item.fold_id == config.fold_id),
        None,
    )
    if fold is None:
        raise ExperimentResultInspectionError(
            f"packaged XJTU split does not contain {config.fold_id!r}"
        )
    artifact_assets = tuple(
        _text(bearing, "asset_id", f"holdout_bearings[{index}]")
        for index, bearing in enumerate(bearings)
    )
    _expect_equal(artifact_assets, tuple(fold.test), "XJTU holdout bearing order")
    profile_assets = tuple(dict.fromkeys((*fold.train, *fold.validation, *fold.test)))
    expected_source_count = sum(
        get_xjtu_expected_acquisition_count(asset_id) for asset_id in profile_assets
    )
    expected_complete_count = sum(
        get_xjtu_expected_acquisition_count(asset_id) for asset_id in fold.train
    )
    expected_reference_count = sum(
        early_third_length(get_xjtu_expected_acquisition_count(asset_id)) for asset_id in fold.train
    )
    expected_scoring_count = sum(
        get_xjtu_expected_acquisition_count(asset_id) for asset_id in fold.test
    )
    _expect_equal(source_count, expected_source_count, "XJTU source acquisition count")
    _expect_equal(complete_count, expected_complete_count, "XJTU complete train population")
    _expect_equal(reference_count, expected_reference_count, "XJTU reference population")
    _expect_equal(fit_count, expected_reference_count, "XJTU model-fit population")
    for index, (bearing, asset_id) in enumerate(zip(bearings, artifact_assets, strict=True)):
        _expect_equal(
            _positive_int(
                bearing,
                "full_run_observation_count",
                f"holdout_bearings[{index}]",
            ),
            get_xjtu_expected_acquisition_count(asset_id),
            f"holdout_bearings[{index}].full_run_observation_count",
        )
    _expect_equal(scoring_count, expected_scoring_count, "XJTU scoring population")

    parameters = _format_parameters(config.model_parameters)
    declared_revision = _revision(root, "code_revision", "result root")
    return ExperimentInspection(
        schema_id=XJTU_HOLDOUT_RESULT_SCHEMA_ID,
        status="consumed",
        stages=(
            InspectionStage(
                "Source",
                "completed",
                (
                    InspectionFact("Dataset", config.dataset_id),
                    InspectionFact(
                        "Complete source profile", f"{source_count} acquisition CSV files"
                    ),
                    InspectionFact("Split scope", f"{config.split_id} / {config.fold_id} / test"),
                    InspectionFact("Selected holdout bearings", ", ".join(artifact_assets)),
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
                        f"Selected features ({len(config.selected_features)})",
                        ", ".join(config.selected_features),
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
            InspectionStage(
                "Population",
                "completed",
                (
                    InspectionFact("Sampling policy", config.sampling_policy_id),
                    InspectionFact("Train observations", complete_count),
                    InspectionFact("Reference-eligible observations", reference_count),
                    InspectionFact("Model-fit observations", fit_count),
                    InspectionFact("Holdout scoring observations", scoring_count),
                ),
            ),
            InspectionStage(
                "Model",
                "completed",
                (
                    InspectionFact("Family", config.model_family.value),
                    InspectionFact("Parameters", parameters),
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
                        f"{len(bearings)} unseen holdout bearings / {scoring_count} observations",
                    ),
                ),
            ),
            InspectionStage(
                "Evaluation",
                "consumed",
                (
                    InspectionFact(
                        "Statistics",
                        "acquisition-order-spearman-rho, lifecycle-late-vs-middle-rank-probability",
                    ),
                    InspectionFact("Aggregation", f"{len(bearings)}-bearing equal-weight mean"),
                    *(
                        InspectionFact("Bearing evidence", line.removeprefix("  "))
                        for line in evaluation_lines
                    ),
                    InspectionFact("Mean rho", f"{mean_rho:.6g}"),
                    InspectionFact("Mean late-vs-middle", f"{mean_rank_probability:.6g}"),
                    InspectionFact("Selection or threshold calibration", "none"),
                ),
            ),
            InspectionStage(
                "Capability",
                "completed",
                (
                    InspectionFact("Available", ", ".join(_AVAILABLE_CAPABILITIES)),
                    InspectionFact("Unsupported", ", ".join(_UNSUPPORTED_CAPABILITIES)),
                ),
            ),
            InspectionStage(
                "Provenance",
                "completed",
                (
                    InspectionFact("Experiment", config.experiment_id),
                    InspectionFact("Split", f"{config.split_id} / {config.fold_id}"),
                    InspectionFact("Declared code revision", declared_revision),
                    InspectionFact("Checkout attestation", "unavailable"),
                    InspectionFact("Artifact", str(path)),
                ),
            ),
        ),
    )


def _validate_xjtu_identity(root: Mapping[str, object], config: ExperimentConfig) -> None:
    expected_root = (
        ("dataset_id", config.dataset_id),
        ("experiment_id", config.experiment_id),
        ("split_id", config.split_id),
        ("fold_id", config.fold_id),
        ("partition", "test"),
    )
    for field_name, expected in expected_root:
        _expect_equal(_text(root, field_name, "result root"), expected, field_name)

    configuration = _mapping_field(root, "configuration", "result root")
    expected_config: tuple[tuple[str, str | int], ...] = (
        ("reference_strategy", config.reference_strategy.value),
        ("sampling_policy_id", config.sampling_policy_id),
        ("scaling_strategy", config.scaling_strategy.value),
        ("model_family", config.model_family.value),
        ("random_seed", config.random_seed),
    )
    for config_field, config_expected in expected_config:
        value = (
            _integer(configuration, config_field, "configuration")
            if isinstance(config_expected, int)
            else _text(configuration, config_field, "configuration")
        )
        _expect_equal(value, config_expected, f"configuration.{config_field}")


def _inspect_ims_cross_test(root: Mapping[str, object], path: Path) -> ExperimentInspection:
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

    capability = _mapping_field(root, "capability_scope", "result root")
    available = _text_sequence(capability, "available", "capability_scope")
    unsupported = _text_sequence(capability, "unsupported_or_not_validated", "capability_scope")
    _expect_equal(available, _AVAILABLE_CAPABILITIES, "available capability scope")
    _expect_equal(unsupported, _UNSUPPORTED_CAPABILITIES, "unsupported capability scope")
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
            InspectionStage(
                "Capability",
                "completed",
                (
                    InspectionFact("Available", ", ".join(available)),
                    InspectionFact("Unsupported", ", ".join(unsupported)),
                ),
            ),
            InspectionStage(
                "Provenance",
                "completed",
                (
                    InspectionFact("Experiment", config.experiment_id),
                    InspectionFact("Split", f"{config.split_id} / {config.fold_id}"),
                    InspectionFact("Declared code revision", declared_revision),
                    InspectionFact("Checkout attestation", "unavailable"),
                    InspectionFact("Artifact", str(path)),
                ),
            ),
        ),
    )


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
        _SCORE_SEMANTICS,
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
        feature_summary_values.append(residual)

    raw_bearings = _sequence(evaluation, "bearings", "evaluation")
    _expect_equal(len(raw_bearings), len(fold.validation), "evaluation bearing count")
    bearing_lines: list[str] = []
    bearing_rhos: list[float] = []
    bearing_rank_probabilities: list[float] = []
    bearing_feature_residuals: list[tuple[float, ...]] = []
    for index, (raw_bearing, expected_asset) in enumerate(
        zip(raw_bearings, fold.validation, strict=True)
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

    capability = _mapping_field(root, "capability_scope", "result root")
    available = _text_sequence(capability, "available", "capability_scope")
    unsupported = _text_sequence(
        capability,
        "unsupported_or_not_validated",
        "capability_scope",
    )
    _expect_equal(available, _LSTM_AVAILABLE_CAPABILITIES, "available capability scope")
    _expect_equal(unsupported, _UNSUPPORTED_CAPABILITIES, "unsupported capability scope")

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
                    InspectionFact("Parameters", _format_parameters(config.model_parameters)),
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
                    InspectionFact("Direction", _SCORE_SEMANTICS),
                    InspectionFact("Alignment", XJTU_LSTM_SEQUENCE_SPEC.alignment.value),
                    InspectionFact(
                        "Scope",
                        f"{len(validation_bearings)} validation bearings / "
                        f"{scoring_window_count} windows",
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
            InspectionStage(
                "Capability",
                "completed",
                (
                    InspectionFact("Available", ", ".join(available)),
                    InspectionFact("Unsupported", ", ".join(unsupported)),
                ),
            ),
            InspectionStage(
                "Provenance",
                "completed",
                (
                    InspectionFact("Experiment", config.experiment_id),
                    InspectionFact("Split", f"{config.split_id} / {config.fold_id}"),
                    InspectionFact(
                        "Evidence class",
                        XJTU_LSTM_DEVELOPMENT_EVIDENCE_CLASS,
                    ),
                    InspectionFact("Declared code revision", declared_revision),
                    InspectionFact("Checkout attestation", "unavailable"),
                    InspectionFact("Artifact", str(path)),
                ),
            ),
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


def _mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ExperimentResultInspectionError(f"{context} must be a JSON object")
    for key in value:
        if not isinstance(key, str):
            raise ExperimentResultInspectionError(f"{context} keys must be strings")
    return cast(Mapping[str, object], value)


def _mapping_field(values: Mapping[str, object], key: str, context: str) -> Mapping[str, object]:
    if key not in values:
        raise ExperimentResultInspectionError(f"{context}.{key} is required")
    return _mapping(values[key], f"{context}.{key}")


def _sequence(values: Mapping[str, object], key: str, context: str) -> Sequence[object]:
    value = values.get(key)
    if not isinstance(value, list):
        raise ExperimentResultInspectionError(f"{context}.{key} must be a JSON array")
    return cast(Sequence[object], value)


def _text(values: Mapping[str, object], key: str, context: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise ExperimentResultInspectionError(f"{context}.{key} must be a non-empty string")
    return value


def _text_sequence(values: Mapping[str, object], key: str, context: str) -> tuple[str, ...]:
    raw = _sequence(values, key, context)
    result: list[str] = []
    for index, value in enumerate(raw):
        if not isinstance(value, str) or not value:
            raise ExperimentResultInspectionError(
                f"{context}.{key}[{index}] must be a non-empty string"
            )
        result.append(value)
    return tuple(result)


def _integer(values: Mapping[str, object], key: str, context: str) -> int:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExperimentResultInspectionError(f"{context}.{key} must be an integer")
    return value


def _positive_int(values: Mapping[str, object], key: str, context: str) -> int:
    value = _integer(values, key, context)
    if value <= 0:
        raise ExperimentResultInspectionError(f"{context}.{key} must be positive")
    return value


def _boolean(values: Mapping[str, object], key: str, context: str) -> bool:
    value = values.get(key)
    if not isinstance(value, bool):
        raise ExperimentResultInspectionError(f"{context}.{key} must be a boolean")
    return value


def _number_sequence(
    values: Mapping[str, object],
    key: str,
    context: str,
) -> tuple[float, ...]:
    raw = _sequence(values, key, context)
    result: list[float] = []
    for index, value in enumerate(raw):
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ExperimentResultInspectionError(f"{context}.{key}[{index}] must be a number")
        number = float(value)
        if not math.isfinite(number):
            raise ExperimentResultInspectionError(f"{context}.{key}[{index}] must be finite")
        result.append(number)
    return tuple(result)


def _number(values: Mapping[str, object], key: str, context: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ExperimentResultInspectionError(f"{context}.{key} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ExperimentResultInspectionError(f"{context}.{key} must be finite")
    return result


def _revision(values: Mapping[str, object], key: str, context: str) -> str:
    value = _text(values, key, context)
    if _FULL_GIT_REVISION.fullmatch(value) is None:
        raise ExperimentResultInspectionError(
            f"{context}.{key} must be a full lowercase 40-character Git SHA"
        )
    return value


def _expect_close(actual: float, expected: float, field_name: str) -> None:
    if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-15):
        raise ExperimentResultInspectionError(
            f"{field_name} does not match the artifact aggregation; "
            f"expected {expected!r}, got {actual!r}"
        )


def _expect_equal(actual: object, expected: object, field_name: str) -> None:
    if actual != expected:
        raise ExperimentResultInspectionError(
            f"{field_name} does not match the packaged protocol; "
            f"expected {expected!r}, got {actual!r}"
        )
