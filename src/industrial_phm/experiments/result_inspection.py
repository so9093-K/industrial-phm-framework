"""Read-only summaries for explicitly supported experiment result schemas."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from industrial_phm.adapters import XJTU_SY_CHANNELS, get_xjtu_expected_acquisition_count
from industrial_phm.data import get_dataset
from industrial_phm.experiments.binary_ranking import harmonic_mean_unit_interval
from industrial_phm.experiments.config import ExperimentConfig, ExperimentParameter
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
from industrial_phm.experiments.mimii import (
    MIMII_DEVELOPMENT_CONFIGURATION_ID,
    MIMII_DEVELOPMENT_FOLD_ID,
    MIMII_DEVELOPMENT_PROTOCOL_ID,
    MIMII_DEVELOPMENT_SECTIONS,
    MIMII_DEVELOPMENT_SPLIT_ID,
    MIMII_DUE_DATASET_ID,
    MIMII_MACHINE_TYPES,
    get_mimii_development_configuration,
    get_mimii_section_configuration,
    iter_mimii_development_section_scopes,
    mimii_expected_train_domain_counts,
)
from industrial_phm.experiments.mimii_development import (
    MIMII_DEVELOPMENT_AVAILABLE_CAPABILITIES,
    MIMII_DEVELOPMENT_EVIDENCE_CLASS,
    MIMII_DEVELOPMENT_MAX_FALSE_POSITIVE_RATE,
    MIMII_DEVELOPMENT_RESULT_SCHEMA_ID,
    MIMII_DEVELOPMENT_UNSUPPORTED_CAPABILITIES,
)
from industrial_phm.experiments.xjtu import get_xjtu_reference_split
from industrial_phm.experiments.xjtu_finalized import get_xjtu_finalized_configuration
from industrial_phm.experiments.xjtu_holdout import XJTU_HOLDOUT_RESULT_SCHEMA_ID
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
from industrial_phm.experiments.xjtu_rul import (
    XJTU_RUL_PROTOCOL_ID,
    XJTU_RUL_TARGET_DEFINITION_ID,
    XJTU_RUL_TARGET_UNIT,
)
from industrial_phm.experiments.xjtu_rul_benchmark_result import (
    XJTU_RUL_LSTM_BENCHMARK_RESULT_SCHEMA_ID,
)
from industrial_phm.experiments.xjtu_rul_validation_result import (
    XJTU_RUL_THREE_MODEL_VALIDATION_EVIDENCE_CLASS,
    XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID,
)
from industrial_phm.experiments.xjtu_sequence import XJTU_LSTM_SEQUENCE_SPEC
from industrial_phm.features import (
    audio_logmel_feature_names,
    audio_logmel_representation_spec,
)
from industrial_phm.models.reconstruction_scoring import (
    MEAN_SQUARED_RECONSTRUCTION_ERROR_ID,
    ReconstructionScores,
    ReconstructionScoringError,
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
_LSTM_AVAILABLE_CAPABILITIES = (
    *_AVAILABLE_CAPABILITIES,
    "reconstruction-residual-evidence",
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


def _clip_level_sequence_stage() -> InspectionStage:
    return InspectionStage(
        "Sequence Construction",
        "not applicable",
        (
            InspectionFact(
                "Reason",
                "model consumes one fixed feature vector per audio clip",
            ),
        ),
    )


def _validated_capability_scope(
    root: Mapping[str, object],
    expected_available: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    capability = _mapping_field(root, "capability_scope", "result root")
    available = _text_sequence(capability, "available", "capability_scope")
    unsupported = _text_sequence(capability, "unsupported_or_not_validated", "capability_scope")
    _expect_equal(available, expected_available, "available capability scope")
    _expect_equal(unsupported, _UNSUPPORTED_CAPABILITIES, "unsupported capability scope")
    return available, unsupported


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
    elif schema_id == XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID:
        return _inspect_xjtu_rul_three_model_validation(root, path)
    elif schema_id == XJTU_RUL_LSTM_BENCHMARK_RESULT_SCHEMA_ID:
        from industrial_phm.experiments.xjtu_rul_benchmark_inspection import (
            inspect_xjtu_rul_lstm_benchmark,
        )

        return inspect_xjtu_rul_lstm_benchmark(root, path)
    elif schema_id == MIMII_DEVELOPMENT_RESULT_SCHEMA_ID:
        return _inspect_mimii_development(root, path)
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
            _acquisition_level_sequence_stage(),
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
            _capability_stage(_AVAILABLE_CAPABILITIES, _UNSUPPORTED_CAPABILITIES),
            _provenance_stage(config, declared_revision, path),
        ),
    )


def _inspect_xjtu_rul_three_model_validation(
    root: Mapping[str, object],
    path: Path,
) -> ExperimentInspection:
    """Read protocol-frozen three-model RUL validation evidence as a common read model."""
    provenance = _mapping_field(root, "provenance", "result root")
    _expect_equal(
        _text(provenance, "evidence_class", "provenance"),
        XJTU_RUL_THREE_MODEL_VALIDATION_EVIDENCE_CLASS,
        "provenance.evidence_class",
    )
    _expect_equal(
        _text(provenance, "protocol_id", "provenance"),
        XJTU_RUL_PROTOCOL_ID,
        "provenance.protocol_id",
    )
    dataset_id = _text(provenance, "dataset_id", "provenance")
    split_id = _text(provenance, "split_id", "provenance")
    fold_id = _text(provenance, "fold_id", "provenance")
    declared_revision = _revision(provenance, "code_revision", "provenance")

    target = _mapping_field(root, "target", "result root")
    _expect_equal(
        _text(target, "definition_id", "target"),
        XJTU_RUL_TARGET_DEFINITION_ID,
        "target.definition_id",
    )
    _expect_equal(_text(target, "unit", "target"), XJTU_RUL_TARGET_UNIT, "target.unit")

    source_scope = _mapping_field(root, "source_scope", "result root")
    train_bearings = _text_sequence(source_scope, "train_bearings", "source_scope")
    validation_bearings = _text_sequence(source_scope, "validation_bearings", "source_scope")
    excluded = _text_sequence(source_scope, "excluded", "source_scope")
    verified_acquisitions = _positive_int(
        source_scope,
        "verified_source_acquisition_count",
        "source_scope",
    )

    methods = _sequence(root, "methods", "result root")
    if len(methods) != 3:
        raise ExperimentResultInspectionError(
            f"three-model RUL evidence requires three methods, got {len(methods)}"
        )
    method_documents = tuple(_mapping(item, "methods entry") for item in methods)
    feature_method = method_documents[1]
    feature_model = _mapping_field(feature_method, "model", "feature method")
    temporal = method_documents[-1]
    sequence = _mapping_field(temporal, "sequence", "temporal method")
    feature_schema = _mapping_field(temporal, "feature_schema", "temporal method")
    temporal_model = _mapping_field(temporal, "model", "temporal method")
    preprocessing = _mapping_field(temporal, "preprocessing", "temporal method")

    comparison = _mapping_field(root, "common_support_comparison", "result root")
    support = _mapping_field(comparison, "support", "common_support_comparison")
    evaluations = _mapping_field(comparison, "evaluations", "common_support_comparison")
    capability = _mapping_field(root, "capability_scope", "result root")
    available = _text_sequence(capability, "available", "capability_scope")
    unsupported = _text_sequence(capability, "unsupported_or_not_validated", "capability_scope")

    return ExperimentInspection(
        schema_id=XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID,
        status="completed",
        stages=(
            InspectionStage(
                "Source",
                "completed",
                (
                    InspectionFact("Dataset", dataset_id),
                    InspectionFact("Split", f"{split_id} / {fold_id}"),
                    InspectionFact("Verified source acquisitions", verified_acquisitions),
                    InspectionFact("Train bearing runs", ", ".join(train_bearings)),
                    InspectionFact("Validation bearing runs", ", ".join(validation_bearings)),
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
                        "1 acquisition -> 1 canonical waveform segment",
                    ),
                ),
            ),
            InspectionStage(
                "Feature",
                "completed",
                (
                    InspectionFact(
                        "Feature set",
                        _text(feature_schema, "feature_set_id", "feature_schema"),
                    ),
                    InspectionFact(
                        "Selected feature count",
                        _positive_int(feature_schema, "selected_feature_count", "feature_schema"),
                    ),
                    InspectionFact(
                        "Age-only baseline",
                        "uses acquisition index only; no vibration feature input",
                    ),
                ),
            ),
            InspectionStage(
                "Preprocessing",
                "completed",
                (
                    InspectionFact(
                        "Fit partition",
                        _text(preprocessing, "fit_partition", "preprocessing"),
                    ),
                    InspectionFact(
                        "Fit observation count",
                        _positive_int(preprocessing, "fit_observation_count", "preprocessing"),
                    ),
                ),
            ),
            InspectionStage(
                "Reference",
                "completed",
                (
                    InspectionFact(
                        "Strategy",
                        _text(feature_model, "reference_strategy", "feature model"),
                    ),
                    InspectionFact(
                        "Sampling policy",
                        _text(feature_model, "sampling_policy_id", "feature model"),
                    ),
                ),
            ),
            InspectionStage(
                "Sequence Construction",
                "completed",
                (
                    InspectionFact("Length", _positive_int(sequence, "length", "sequence")),
                    InspectionFact("Stride", _positive_int(sequence, "stride", "sequence")),
                    InspectionFact("Alignment", _text(sequence, "alignment", "sequence")),
                    InspectionFact(
                        "Train windows",
                        _positive_int(sequence, "train_window_count", "sequence"),
                    ),
                    InspectionFact(
                        "Train dropped prefix acquisitions",
                        _integer(sequence, "train_dropped_prefix_observation_count", "sequence"),
                    ),
                    InspectionFact(
                        "Validation dropped prefix per bearing",
                        _integer(sequence, "validation_dropped_prefix_per_bearing", "sequence"),
                    ),
                    InspectionFact(
                        "Acquisition-level methods",
                        "age-only and feature Ridge consume one acquisition per prediction",
                    ),
                ),
            ),
            InspectionStage(
                "Population",
                "completed",
                (
                    InspectionFact(
                        "Train source acquisitions",
                        _positive_int(sequence, "train_source_observation_count", "sequence"),
                    ),
                    InspectionFact(
                        "Acquisition-level model-fit observations",
                        _positive_int(feature_model, "fit_observation_count", "feature model"),
                    ),
                    InspectionFact(
                        "Temporal model-fit windows",
                        _positive_int(sequence, "train_window_count", "sequence"),
                    ),
                    InspectionFact(
                        "Common-support predictions",
                        _positive_int(support, "total_prediction_count", "support"),
                    ),
                ),
            ),
            InspectionStage(
                "Model",
                "completed",
                (
                    *(
                        InspectionFact(
                            _text(document, "method_id", "methods entry"),
                            _text(document, "kind", "methods entry"),
                        )
                        for document in method_documents
                    ),
                    InspectionFact(
                        "Random seed",
                        _integer(temporal_model, "random_seed", "temporal model"),
                    ),
                ),
            ),
            InspectionStage(
                "Scoring",
                "completed",
                (
                    InspectionFact("Target definition", XJTU_RUL_TARGET_DEFINITION_ID),
                    InspectionFact("Target unit", XJTU_RUL_TARGET_UNIT),
                    InspectionFact("Formula", _text(target, "formula", "target")),
                    InspectionFact(
                        "Endpoint semantics",
                        _text(target, "endpoint_semantics", "target"),
                    ),
                    InspectionFact(
                        "Prediction alignment",
                        _text(target, "prediction_alignment", "target"),
                    ),
                ),
                (
                    "Target is the recorded-end acquisition interval, not a validated "
                    "physical failure time.",
                ),
            ),
            InspectionStage(
                "Evaluation",
                "completed",
                (
                    InspectionFact("Support", _text(support, "definition", "support")),
                    InspectionFact(
                        "First acquisition",
                        _integer(support, "first_acquisition", "support"),
                    ),
                    *_rul_method_metric_facts(evaluations),
                ),
                (
                    "Development evidence on fold-1 validation bearing runs; holdout test "
                    "is excluded.",
                    "Point-error metrics do not create uncertainty intervals, a validated "
                    "failure threshold, or a maintenance recommendation.",
                ),
            ),
            _capability_stage(available, unsupported),
            InspectionStage(
                "Provenance",
                "completed",
                (
                    InspectionFact("Protocol", XJTU_RUL_PROTOCOL_ID),
                    InspectionFact("Split", f"{split_id} / {fold_id}"),
                    InspectionFact(
                        "Evidence class",
                        XJTU_RUL_THREE_MODEL_VALIDATION_EVIDENCE_CLASS,
                    ),
                    InspectionFact("Declared code revision", declared_revision),
                    InspectionFact("Checkout attestation", "unavailable"),
                    InspectionFact("Artifact", str(path)),
                ),
            ),
        ),
    )


def _rul_method_metric_facts(
    evaluations: Mapping[str, object],
) -> tuple[InspectionFact, ...]:
    facts: list[InspectionFact] = []
    for method_id in sorted(evaluations):
        evaluation = _mapping(evaluations[method_id], f"evaluations[{method_id}]")
        mae = _number(evaluation, "mean_asset_mean_absolute_error", method_id)
        rmse = _number(evaluation, "mean_asset_root_mean_squared_error", method_id)
        signed = _number(evaluation, "mean_asset_mean_signed_error", method_id)
        facts.append(
            InspectionFact(
                method_id,
                f"MAE {mae:.6g} / RMSE {rmse:.6g} / signed {signed:.6g}",
            )
        )
    return tuple(facts)


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

    available, unsupported = _validated_capability_scope(root, _AVAILABLE_CAPABILITIES)
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


def _inspect_mimii_development(
    root: Mapping[str, object],
    path: Path,
) -> ExperimentInspection:
    config = get_mimii_development_configuration()
    provenance = _mapping_field(root, "provenance", "result root")
    expected_identity = (
        ("protocol_id", MIMII_DEVELOPMENT_PROTOCOL_ID),
        ("configuration_id", MIMII_DEVELOPMENT_CONFIGURATION_ID),
        ("dataset_id", MIMII_DUE_DATASET_ID),
        ("split_id", MIMII_DEVELOPMENT_SPLIT_ID),
        ("fold_id", MIMII_DEVELOPMENT_FOLD_ID),
        ("evidence_class", MIMII_DEVELOPMENT_EVIDENCE_CLASS),
    )
    for field_name, expected in expected_identity:
        _expect_equal(
            _text(provenance, field_name, "provenance"),
            expected,
            f"provenance.{field_name}",
        )
    declared_revision = _revision(provenance, "code_revision", "provenance")

    source_scope = _mapping_field(root, "source_scope", "result root")
    source_record = get_dataset(MIMII_DUE_DATASET_ID)
    if source_record.citation_doi is None:
        raise ExperimentResultInspectionError(
            "packaged MIMII DUE dataset manifest must declare citation_doi"
        )
    dataset_record = _mapping_field(source_scope, "dataset_record", "source_scope")
    expected_source_record = (
        ("version", source_record.version),
        ("provider", source_record.provider),
        ("source_url", source_record.source_url),
        ("citation_doi", source_record.citation_doi),
        ("license", source_record.license_name),
    )
    for field_name, expected_record_value in expected_source_record:
        _expect_equal(
            _text(dataset_record, field_name, "source_scope.dataset_record"),
            expected_record_value,
            f"source_scope.dataset_record.{field_name}",
        )
    verified_source_count = _positive_int(
        source_scope,
        "verified_source_clip_count",
        "source_scope",
    )
    _expect_equal(
        _text(source_scope, "source_group", "source_scope"),
        "dev",
        "source_scope.source_group",
    )
    machine_types = _text_sequence(source_scope, "machine_types", "source_scope")
    sections = _text_sequence(source_scope, "sections", "source_scope")
    train_domains = _text_sequence(source_scope, "train_domains", "source_scope")
    scoring_domains = _text_sequence(source_scope, "scoring_domains", "source_scope")
    excluded = _text_sequence(source_scope, "excluded", "source_scope")
    _expect_equal(machine_types, MIMII_MACHINE_TYPES, "source_scope.machine_types")
    _expect_equal(sections, MIMII_DEVELOPMENT_SECTIONS, "source_scope.sections")
    _expect_equal(train_domains, ("source", "target"), "source_scope.train_domains")
    _expect_equal(scoring_domains, ("source", "target"), "source_scope.scoring_domains")
    _expect_equal(
        excluded,
        (
            "eval:sections-03-05",
            "development-test-labels-from-model-fit-and-scoring",
        ),
        "source_scope.excluded",
    )

    representation = _mapping_field(root, "representation", "result root")
    selected_features = _text_sequence(
        representation,
        "selected_features",
        "representation",
    )
    expected_features = audio_logmel_feature_names()
    _expect_equal(selected_features, expected_features, "representation.selected_features")
    _expect_equal(
        _positive_int(
            representation,
            "selected_feature_count",
            "representation",
        ),
        len(expected_features),
        "representation.selected_feature_count",
    )
    _expect_equal(
        _text(representation, "feature_set_id", "representation"),
        config.feature_set_id,
        "representation.feature_set_id",
    )
    spec = audio_logmel_representation_spec()
    representation_text = (
        ("window", spec.window),
        ("padding", spec.padding),
        ("power_normalization", spec.power_normalization),
        ("mel_scale", spec.mel_scale),
        ("mel_filter_normalization", spec.mel_filter_normalization),
        ("clip_aggregation", spec.clip_aggregation),
    )
    for field_name, expected_text in representation_text:
        _expect_equal(
            _text(representation, field_name, "representation"),
            expected_text,
            f"representation.{field_name}",
        )
    representation_int = (
        ("sample_count", spec.sample_count),
        ("frame_length_samples", spec.frame_length_samples),
        ("hop_length_samples", spec.hop_length_samples),
        ("fft_size", spec.fft_size),
        ("mel_band_count", spec.mel_band_count),
        ("frame_count", spec.frame_count),
        ("feature_count", spec.feature_count),
    )
    for field_name, expected_int in representation_int:
        _expect_equal(
            _positive_int(representation, field_name, "representation"),
            expected_int,
            f"representation.{field_name}",
        )
    representation_number = (
        ("sample_rate_hz", spec.sample_rate_hz),
        ("pcm_full_scale_divisor", spec.pcm_full_scale_divisor),
        ("minimum_frequency_hz", spec.minimum_frequency_hz),
        ("maximum_frequency_hz", spec.maximum_frequency_hz),
        ("log_floor", spec.log_floor),
    )
    for field_name, expected_number in representation_number:
        _expect_close(
            _number(representation, field_name, "representation"),
            expected_number,
            f"representation.{field_name}",
        )
    _expect_equal(
        _boolean(representation, "centering", "representation"),
        spec.centering,
        "representation.centering",
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
    _expect_equal(
        _text(preprocessing, "fit_scope", "preprocessing"),
        "per-machine-section-complete-normal-train",
        "preprocessing.fit_scope",
    )

    model = _mapping_field(root, "model", "result root")
    model_text = (
        ("model_family", config.model_family.value),
        ("reference_strategy", config.reference_strategy.value),
        ("sampling_policy_id", config.sampling_policy_id),
        ("score_semantics", _SCORE_SEMANTICS),
        ("model_unit", "machine-type-x-section"),
    )
    for field_name, expected in model_text:
        _expect_equal(
            _text(model, field_name, "model"),
            expected,
            f"model.{field_name}",
        )
    _expect_equal(
        _integer(model, "random_seed", "model"),
        config.random_seed,
        "model.random_seed",
    )
    parameters = _mapping_field(model, "parameters", "model")
    _expect_equal(dict(parameters), dict(config.model_parameters), "model.parameters")

    raw_sections = _sequence(root, "section_models", "result root")
    expected_scopes = iter_mimii_development_section_scopes()
    _expect_equal(len(raw_sections), len(expected_scopes), "section_models count")

    total_source_train = 0
    total_target_train = 0
    total_source_scoring = 0
    total_target_scoring = 0
    evaluations: dict[tuple[str, str, str], tuple[float, float]] = {}

    for index, (raw_section, scope) in enumerate(zip(raw_sections, expected_scopes, strict=True)):
        context = f"section_models[{index}]"
        section = _mapping(raw_section, context)
        _expect_equal(
            _text(section, "machine_type", context),
            scope.machine_type,
            f"{context}.machine_type",
        )
        _expect_equal(
            _text(section, "section", context),
            scope.section,
            f"{context}.section",
        )
        section_config = get_mimii_section_configuration(
            scope.machine_type,
            scope.section,
        )
        _expect_equal(
            _text(section, "experiment_id", context),
            section_config.experiment_id,
            f"{context}.experiment_id",
        )

        population = _mapping_field(section, "population_flow", context)
        source_train = _positive_int(
            population,
            "source_train_clip_count",
            f"{context}.population_flow",
        )
        target_train = _positive_int(
            population,
            "target_train_clip_count",
            f"{context}.population_flow",
        )
        expected_source_train, expected_target_train = mimii_expected_train_domain_counts(
            scope.machine_type,
            scope.section,
        )
        _expect_equal(
            source_train,
            expected_source_train,
            f"{context}.population_flow.source_train_clip_count",
        )
        _expect_equal(
            target_train,
            expected_target_train,
            f"{context}.population_flow.target_train_clip_count",
        )
        complete_train = source_train + target_train
        for field_name in (
            "preprocessing_fit_clip_count",
            "reference_clip_count",
            "model_fit_clip_count",
        ):
            _expect_equal(
                _positive_int(
                    population,
                    field_name,
                    f"{context}.population_flow",
                ),
                complete_train,
                f"{context}.population_flow.{field_name}",
            )
        source_scoring = _positive_int(
            population,
            "source_scoring_clip_count",
            f"{context}.population_flow",
        )
        target_scoring = _positive_int(
            population,
            "target_scoring_clip_count",
            f"{context}.population_flow",
        )
        total_source_train += source_train
        total_target_train += target_train
        total_source_scoring += source_scoring
        total_target_scoring += target_scoring

        state = _mapping_field(section, "preprocessing_state", context)
        fitted_center = _number_sequence(
            state,
            "fitted_center",
            f"{context}.preprocessing_state",
        )
        fitted_scale = _number_sequence(
            state,
            "fitted_scale",
            f"{context}.preprocessing_state",
        )
        zero_iqr_features = _text_sequence(
            state,
            "zero_iqr_features",
            f"{context}.preprocessing_state",
        )
        _expect_equal(
            len(fitted_center),
            len(expected_features),
            f"{context}.preprocessing_state.fitted_center width",
        )
        _expect_equal(
            len(fitted_scale),
            len(expected_features),
            f"{context}.preprocessing_state.fitted_scale width",
        )
        if any(value <= 0.0 for value in fitted_scale):
            raise ExperimentResultInspectionError(
                f"{context}.preprocessing_state.fitted_scale must be positive"
            )
        unknown_zero_iqr = sorted(set(zero_iqr_features) - set(expected_features))
        if unknown_zero_iqr:
            raise ExperimentResultInspectionError(
                f"{context}.preprocessing_state.zero_iqr_features contains "
                f"unknown feature(s): {unknown_zero_iqr}"
            )

        section_evaluation = _mapping_field(section, "evaluation", context)
        for domain, expected_count in (
            ("source", source_scoring),
            ("target", target_scoring),
        ):
            evaluation = _mapping_field(
                section_evaluation,
                domain,
                f"{context}.evaluation",
            )
            evaluations[(scope.machine_type, scope.section, domain)] = (
                *_mimii_evaluation_metrics(
                    evaluation,
                    context=f"{context}.evaluation.{domain}",
                    expected_observation_count=expected_count,
                ),
            )

    evaluation = _mapping_field(root, "evaluation", "result root")
    _expect_equal(
        _text(evaluation, "label_join", "evaluation"),
        "source-file-identity-at-evaluator-edge",
        "evaluation.label_join",
    )
    _expect_equal(
        _text(evaluation, "stratum_unit", "evaluation"),
        "machine-type-x-section-x-domain",
        "evaluation.stratum_unit",
    )
    _expect_equal(
        _text_sequence(evaluation, "metrics", "evaluation"),
        (
            "roc-auc",
            "standardized-partial-roc-auc:max-fpr=0.1",
        ),
        "evaluation.metrics",
    )
    _expect_close(
        _number(evaluation, "max_false_positive_rate", "evaluation"),
        MIMII_DEVELOPMENT_MAX_FALSE_POSITIVE_RATE,
        "evaluation.max_false_positive_rate",
    )
    _expect_equal(
        _text(evaluation, "aggregation", "evaluation"),
        "harmonic-mean-with-zero-preserved",
        "evaluation.aggregation",
    )

    machine_summaries = _sequence(evaluation, "machine_summaries", "evaluation")
    _expect_equal(
        len(machine_summaries),
        len(MIMII_MACHINE_TYPES),
        "evaluation.machine_summaries count",
    )
    for index, machine_type in enumerate(MIMII_MACHINE_TYPES):
        machine_values = tuple(
            evaluations[(machine_type, section, domain)]
            for section in MIMII_DEVELOPMENT_SECTIONS
            for domain in ("source", "target")
        )
        _validate_mimii_aggregate(
            _mapping(
                machine_summaries[index],
                f"evaluation.machine_summaries[{index}]",
            ),
            context=f"evaluation.machine_summaries[{index}]",
            expected_scope=f"machine:{machine_type}",
            expected_values=machine_values,
        )

    domain_summaries = _sequence(evaluation, "domain_summaries", "evaluation")
    _expect_equal(len(domain_summaries), 2, "evaluation.domain_summaries count")
    domain_summary_values: dict[str, tuple[float, float]] = {}
    for index, domain in enumerate(("source", "target")):
        domain_values = tuple(
            evaluations[(machine_type, section, domain)]
            for machine_type in MIMII_MACHINE_TYPES
            for section in MIMII_DEVELOPMENT_SECTIONS
        )
        domain_summary_values[domain] = _validate_mimii_aggregate(
            _mapping(
                domain_summaries[index],
                f"evaluation.domain_summaries[{index}]",
            ),
            context=f"evaluation.domain_summaries[{index}]",
            expected_scope=f"domain:{domain}",
            expected_values=domain_values,
        )

    all_values = tuple(
        evaluations[(machine_type, section, domain)]
        for machine_type in MIMII_MACHINE_TYPES
        for section in MIMII_DEVELOPMENT_SECTIONS
        for domain in ("source", "target")
    )
    overall_values = _validate_mimii_aggregate(
        _mapping_field(evaluation, "overall_summary", "evaluation"),
        context="evaluation.overall_summary",
        expected_scope="mimii-only:all-strata",
        expected_values=all_values,
    )
    expected_combined = harmonic_mean_unit_interval(
        tuple(metric for pair in all_values for metric in pair)
    )
    combined = _number(
        evaluation,
        "mimii_domain_shift_summary",
        "evaluation",
    )
    _expect_close(
        combined,
        expected_combined,
        "evaluation.mimii_domain_shift_summary",
    )
    _expect_equal(
        _boolean(evaluation, "dcase_official_score", "evaluation"),
        False,
        "evaluation.dcase_official_score",
    )

    capability = _mapping_field(root, "capability", "result root")
    available = _text_sequence(capability, "available", "capability")
    unsupported = _text_sequence(capability, "unsupported", "capability")
    _expect_equal(
        available,
        MIMII_DEVELOPMENT_AVAILABLE_CAPABILITIES,
        "capability.available",
    )
    _expect_equal(
        unsupported,
        MIMII_DEVELOPMENT_UNSUPPORTED_CAPABILITIES,
        "capability.unsupported",
    )

    section_model_count = len(expected_scopes)
    train_total = total_source_train + total_target_train
    scoring_total = total_source_scoring + total_target_scoring
    return ExperimentInspection(
        schema_id=MIMII_DEVELOPMENT_RESULT_SCHEMA_ID,
        status="completed",
        stages=(
            InspectionStage(
                "Source",
                "completed",
                (
                    InspectionFact("Dataset", MIMII_DUE_DATASET_ID),
                    InspectionFact("Dataset version", source_record.version),
                    InspectionFact("Source provider", source_record.provider),
                    InspectionFact("Source URL", source_record.source_url),
                    InspectionFact("Citation DOI", source_record.citation_doi),
                    InspectionFact("License", source_record.license_name),
                    InspectionFact(
                        "Verified source profile",
                        f"{verified_source_count} WAV clips",
                    ),
                    InspectionFact("Source group", "dev"),
                    InspectionFact("Machine types", ", ".join(machine_types)),
                    InspectionFact("Sections", ", ".join(sections)),
                    InspectionFact("Excluded", ", ".join(excluded)),
                ),
            ),
            InspectionStage(
                "Canonical",
                "completed",
                (
                    InspectionFact("Channels", "pcm_amplitude"),
                    InspectionFact("Sampling rate", f"{spec.sample_rate_hz:g} Hz"),
                    InspectionFact(
                        "Cardinality",
                        "1 WAV clip -> 1 mono 10-second canonical waveform",
                    ),
                ),
            ),
            InspectionStage(
                "Feature",
                "completed",
                (
                    InspectionFact("Feature set", config.feature_set_id),
                    InspectionFact("Selected feature count", len(expected_features)),
                    InspectionFact(
                        "Representation",
                        f"{spec.mel_band_count} HTK mel bands / frame mean+population-std",
                    ),
                ),
            ),
            InspectionStage(
                "Preprocessing",
                "completed",
                (
                    InspectionFact("Fit scope", "per machine type x section complete normal train"),
                    InspectionFact("Scaling", config.scaling_strategy.value),
                    InspectionFact("Fitted states", section_model_count),
                ),
            ),
            InspectionStage(
                "Reference",
                "completed",
                (
                    InspectionFact("Strategy", config.reference_strategy.value),
                    InspectionFact("Eligible train clips", train_total),
                ),
            ),
            _clip_level_sequence_stage(),
            InspectionStage(
                "Population",
                "completed",
                (
                    InspectionFact("Section models", section_model_count),
                    InspectionFact("Source train clips", total_source_train),
                    InspectionFact("Target train clips", total_target_train),
                    InspectionFact("Model-fit clips", train_total),
                    InspectionFact("Source scoring clips", total_source_scoring),
                    InspectionFact("Target scoring clips", total_target_scoring),
                    InspectionFact("Total scoring clips", scoring_total),
                ),
            ),
            InspectionStage(
                "Model",
                "completed",
                (
                    InspectionFact("Family", config.model_family.value),
                    InspectionFact("Model unit", "machine-type-x-section"),
                    InspectionFact("Parameters", _format_parameters(config.model_parameters)),
                    InspectionFact("Random seed", config.random_seed),
                    InspectionFact("Score semantics", _SCORE_SEMANTICS),
                ),
            ),
            InspectionStage(
                "Scoring",
                "completed",
                (
                    InspectionFact("Scope", "dev source_test + target_test"),
                    InspectionFact("Scored clips", scoring_total),
                    InspectionFact("Label access", "evaluator edge only"),
                ),
            ),
            InspectionStage(
                "Evaluation",
                "completed",
                (
                    InspectionFact("Evidence class", MIMII_DEVELOPMENT_EVIDENCE_CLASS),
                    InspectionFact("Strata", len(all_values)),
                    InspectionFact(
                        "Metrics",
                        "roc-auc, standardized-partial-roc-auc:max-fpr=0.1",
                    ),
                    InspectionFact("Aggregation", "harmonic-mean-with-zero-preserved"),
                    InspectionFact(
                        "Source AUC harmonic mean",
                        f"{domain_summary_values['source'][0]:.6g}",
                    ),
                    InspectionFact(
                        "Source pAUC harmonic mean",
                        f"{domain_summary_values['source'][1]:.6g}",
                    ),
                    InspectionFact(
                        "Target AUC harmonic mean",
                        f"{domain_summary_values['target'][0]:.6g}",
                    ),
                    InspectionFact(
                        "Target pAUC harmonic mean",
                        f"{domain_summary_values['target'][1]:.6g}",
                    ),
                    InspectionFact("Overall AUC harmonic mean", f"{overall_values[0]:.6g}"),
                    InspectionFact(
                        "Overall pAUC harmonic mean",
                        f"{overall_values[1]:.6g}",
                    ),
                    InspectionFact("MIMII domain-shift summary", f"{combined:.6g}"),
                    InspectionFact("DCASE official score", "false"),
                    InspectionFact("Selection or threshold calibration", "none"),
                ),
                warnings=(
                    "Development evidence on sections 00-02; sections 03-05 external "
                    "evaluation is not included.",
                    "Ranking metrics do not create thresholded state, diagnosis, health "
                    "indicator, maintenance priority, or RUL.",
                ),
            ),
            _capability_stage(available, unsupported),
            _provenance_stage(
                config,
                declared_revision,
                path,
                evidence_facts=(
                    InspectionFact("Protocol", MIMII_DEVELOPMENT_PROTOCOL_ID),
                    InspectionFact("Evidence class", MIMII_DEVELOPMENT_EVIDENCE_CLASS),
                    InspectionFact("Section models", section_model_count),
                ),
            ),
        ),
    )


def _mimii_evaluation_metrics(
    values: Mapping[str, object],
    *,
    context: str,
    expected_observation_count: int,
) -> tuple[float, float]:
    observation_count = _positive_int(values, "observation_count", context)
    _expect_equal(
        observation_count,
        expected_observation_count,
        f"{context}.observation_count",
    )
    normal_count = _positive_int(values, "normal_count", context)
    anomaly_count = _positive_int(values, "anomaly_count", context)
    _expect_equal(
        normal_count + anomaly_count,
        observation_count,
        f"{context} normal/anomaly count",
    )
    roc_auc = _number(values, "roc_auc", context)
    partial_roc_auc = _number(values, "partial_roc_auc", context)
    for field_name, value in (
        ("roc_auc", roc_auc),
        ("partial_roc_auc", partial_roc_auc),
    ):
        if not 0.0 <= value <= 1.0:
            raise ExperimentResultInspectionError(f"{context}.{field_name} must be in [0, 1]")
    _expect_close(
        _number(values, "max_false_positive_rate", context),
        MIMII_DEVELOPMENT_MAX_FALSE_POSITIVE_RATE,
        f"{context}.max_false_positive_rate",
    )
    return roc_auc, partial_roc_auc


def _validate_mimii_aggregate(
    values: Mapping[str, object],
    *,
    context: str,
    expected_scope: str,
    expected_values: Sequence[tuple[float, float]],
) -> tuple[float, float]:
    _expect_equal(
        _text(values, "scope_id", context),
        expected_scope,
        f"{context}.scope_id",
    )
    _expect_equal(
        _positive_int(values, "stratum_count", context),
        len(expected_values),
        f"{context}.stratum_count",
    )
    roc_auc = _number(values, "roc_auc_harmonic_mean", context)
    partial_roc_auc = _number(
        values,
        "partial_roc_auc_harmonic_mean",
        context,
    )
    _expect_close(
        roc_auc,
        harmonic_mean_unit_interval(tuple(pair[0] for pair in expected_values)),
        f"{context}.roc_auc_harmonic_mean",
    )
    _expect_close(
        partial_roc_auc,
        harmonic_mean_unit_interval(tuple(pair[1] for pair in expected_values)),
        f"{context}.partial_roc_auc_harmonic_mean",
    )
    return roc_auc, partial_roc_auc


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

    available, unsupported = _validated_capability_scope(root, _LSTM_AVAILABLE_CAPABILITIES)

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
