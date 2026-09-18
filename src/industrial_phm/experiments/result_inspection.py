"""Read-only summaries for explicitly supported experiment result schemas."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from industrial_phm.adapters import XJTU_SY_CHANNELS
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


class ExperimentResultInspectionError(ValueError):
    """Raised when a result cannot be inspected as a supported evidence schema."""


def inspect_experiment_result(path: Path) -> str:
    """Validate and summarize one supported result artifact without modifying it."""
    try:
        document = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as error:
        raise ExperimentResultInspectionError(f"invalid result JSON: {error}") from error

    root = _mapping(document, "result root")
    schema_id = _text(root, "schema_id", "result root")
    if schema_id == XJTU_HOLDOUT_RESULT_SCHEMA_ID:
        lines = _inspect_xjtu_holdout(root, path)
    elif schema_id == IMS_CROSS_TEST_RESULT_SCHEMA_ID:
        lines = _inspect_ims_cross_test(root, path)
    else:
        raise ExperimentResultInspectionError(
            f"unsupported experiment result schema_id {schema_id!r}; expected one of "
            f"{XJTU_HOLDOUT_RESULT_SCHEMA_ID!r}, {IMS_CROSS_TEST_RESULT_SCHEMA_ID!r}"
        )
    return "\n".join(lines)


def _inspect_xjtu_holdout(root: Mapping[str, object], path: Path) -> list[str]:
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

    parameters = _format_parameters(config.model_parameters)
    declared_revision = _revision(root, "code_revision", "result root")
    return [
        "Experiment Result",
        f"  Schema: {XJTU_HOLDOUT_RESULT_SCHEMA_ID}",
        "  Status: consumed",
        "",
        "Source",
        "  Status: completed",
        f"  Dataset: {config.dataset_id}",
        f"  Complete source profile: {source_count} acquisition CSV files",
        f"  Split scope: {config.split_id} / {config.fold_id} / test",
        f"  Selected holdout bearings: {', '.join(artifact_assets)}",
        "",
        "Canonical",
        "  Status: completed",
        f"  Channels: {', '.join(XJTU_SY_CHANNELS)}",
        "  Cardinality: 1 acquisition CSV -> 1 two-channel bearing observation",
        "",
        "Feature",
        "  Status: completed",
        f"  Feature set: {config.feature_set_id}",
        f"  Selected features ({len(config.selected_features)}): "
        f"{', '.join(config.selected_features)}",
        "",
        "Preprocessing",
        "  Status: completed",
        f"  Fit scope: {config.fit_partition.value} / {complete_count} observations",
        f"  Scaling: {config.scaling_strategy.value}",
        "",
        "Reference",
        "  Status: completed",
        f"  Strategy: {config.reference_strategy.value}",
        f"  Eligible observations: {reference_count}",
        "",
        "Population",
        "  Status: completed",
        f"  Sampling policy: {config.sampling_policy_id}",
        f"  Train observations: {complete_count}",
        f"  Reference-eligible observations: {reference_count}",
        f"  Model-fit observations: {fit_count}",
        f"  Holdout scoring observations: {scoring_count}",
        "",
        "Model",
        "  Status: completed",
        f"  Family: {config.model_family.value}",
        f"  Parameters: {parameters}",
        f"  Random seed: {config.random_seed}",
        f"  Score semantics: {_SCORE_SEMANTICS}",
        "",
        "Scoring",
        "  Status: completed",
        f"  Scope: {len(bearings)} unseen holdout bearings / {scoring_count} observations",
        "",
        "Evaluation",
        "  Status: consumed",
        "  Statistics: acquisition-order-spearman-rho, lifecycle-late-vs-middle-rank-probability",
        f"  Aggregation: {len(bearings)}-bearing equal-weight mean",
        *evaluation_lines,
        f"  Mean rho: {mean_rho:.6g}",
        f"  Mean late-vs-middle: {mean_rank_probability:.6g}",
        "  Selection or threshold calibration: none",
        "",
        "Capability",
        f"  Available: {', '.join(_AVAILABLE_CAPABILITIES)}",
        f"  Unsupported: {', '.join(_UNSUPPORTED_CAPABILITIES)}",
        "",
        "Provenance",
        f"  Experiment: {config.experiment_id}",
        f"  Split: {config.split_id} / {config.fold_id}",
        f"  Declared code revision: {declared_revision}",
        "  Checkout attestation: unavailable",
        f"  Artifact: {path}",
    ]


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


def _inspect_ims_cross_test(root: Mapping[str, object], path: Path) -> list[str]:
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

    return [
        "Experiment Result",
        f"  Schema: {IMS_CROSS_TEST_RESULT_SCHEMA_ID}",
        "  Status: consumed",
        "",
        "Source",
        "  Status: completed",
        f"  Dataset: {config.dataset_id}",
        f"  Verified source profile: {verified_source_count} acquisition files",
        f"  Train scope: {IMS_TRAIN_TEST_ID} complete / {train_acquisitions} files",
        f"  Evaluation scope: {IMS_EVALUATION_TEST_ID} {IMS_EVALUATION_ARCHIVE_SCOPE} / "
        f"{evaluation_acquisitions} files",
        f"  Excluded: {', '.join(excluded)}",
        "",
        "Canonical",
        "  Status: completed",
        "  Channels: vibration",
        f"  Cardinality: 1 acquisition file -> {IMS_BEARING_COUNT} bearing observations",
        f"  Train conversion: {train_acquisitions} files -> {train_observations} observations",
        f"  Evaluation conversion: {evaluation_acquisitions} files -> "
        f"{scoring_observations} observations",
        "",
        "Feature",
        "  Status: completed",
        f"  Feature set: {config.feature_set_id}",
        f"  Selected features ({len(selected_features)}): {', '.join(selected_features)}",
        "",
        "Preprocessing",
        "  Status: completed",
        f"  Fit scope: {config.fit_partition.value} / {complete_count} observations",
        f"  Scaling: {config.scaling_strategy.value}",
        "",
        "Reference",
        "  Status: completed",
        f"  Strategy: {config.reference_strategy.value}",
        f"  Eligible observations: {reference_count}",
        "",
        "Population",
        "  Status: completed",
        f"  Sampling policy: {config.sampling_policy_id}",
        f"  Train observations: {complete_count}",
        f"  Reference-eligible observations: {reference_count}",
        f"  Model-fit observations: {fit_count}",
        f"  Cross-test scoring observations: {artifact_scoring_count}",
        "",
        "Model",
        "  Status: completed",
        f"  Family: {config.model_family.value}",
        f"  Parameters: {_format_parameters(config.model_parameters)}",
        f"  Random seed: {config.random_seed}",
        f"  Score semantics: {_SCORE_SEMANTICS}",
        "",
        "Scoring",
        "  Status: completed",
        f"  Scope: {evaluation_bearings} Set 3 bearings / {artifact_scoring_count} observations",
        "",
        "Evaluation",
        "  Status: consumed",
        f"  Scope: {partition_semantics}",
        f"  Statistics: {', '.join(statistics)}",
        f"  Aggregation: {aggregation}",
        *evaluation_lines,
        f"  Mean rho: {mean_rho:.6g}",
        f"  Mean late-vs-middle: {mean_rank_probability:.6g}",
        "  Selection or threshold calibration: none",
        "",
        "Capability",
        f"  Available: {', '.join(available)}",
        f"  Unsupported: {', '.join(unsupported)}",
        "",
        "Provenance",
        f"  Experiment: {config.experiment_id}",
        f"  Split: {config.split_id} / {config.fold_id}",
        f"  Declared code revision: {declared_revision}",
        "  Checkout attestation: unavailable",
        f"  Artifact: {path}",
    ]


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


def _expect_equal(actual: object, expected: object, field_name: str) -> None:
    if actual != expected:
        raise ExperimentResultInspectionError(
            f"{field_name} does not match the packaged protocol; "
            f"expected {expected!r}, got {actual!r}"
        )
