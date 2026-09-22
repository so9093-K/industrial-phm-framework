"""Schema-specific inspection for XJTU three-model RUL validation evidence."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from industrial_phm.adapters import XJTU_SY_CHANNELS
from industrial_phm.experiments.result_inspection_support import (
    ExperimentInspection,
    ExperimentResultInspectionError,
    InspectionFact,
    InspectionStage,
    _capability_stage,
    _expect_equal,
    _integer,
    _mapping,
    _mapping_field,
    _number,
    _positive_int,
    _revision,
    _sequence,
    _text,
    _text_sequence,
)
from industrial_phm.experiments.xjtu_rul import (
    XJTU_RUL_PROTOCOL_ID,
    XJTU_RUL_TARGET_DEFINITION_ID,
    XJTU_RUL_TARGET_UNIT,
)
from industrial_phm.experiments.xjtu_rul_validation_result import (
    XJTU_RUL_THREE_MODEL_VALIDATION_EVIDENCE_CLASS,
    XJTU_RUL_THREE_MODEL_VALIDATION_RESULT_SCHEMA_ID,
)


def inspect_xjtu_rul_three_model_validation(
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
