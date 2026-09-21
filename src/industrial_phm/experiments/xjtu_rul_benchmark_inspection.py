"""Schema-specific inspection for frozen XJTU RUL benchmark evidence."""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from statistics import fmean

from industrial_phm.adapters import XJTU_SY_CHANNELS, get_xjtu_expected_acquisition_count
from industrial_phm.experiments.result_inspection import (
    ExperimentInspection,
    ExperimentResultInspectionError,
    InspectionFact,
    InspectionStage,
    _boolean,
    _capability_stage,
    _integer,
    _mapping,
    _mapping_field,
    _number,
    _positive_int,
    _revision,
    _sequence,
    _text,
    _text_sequence,
    _expect_close,
    _expect_equal,
)
from industrial_phm.experiments.xjtu import get_xjtu_reference_split
from industrial_phm.experiments.xjtu_rul import (
    XJTU_RUL_PROTOCOL_ID,
    XJTU_RUL_TARGET_DEFINITION_ID,
    XJTU_RUL_TARGET_UNIT,
)
from industrial_phm.experiments.xjtu_rul_benchmark_result import (
    XJTU_RUL_LSTM_BENCHMARK_AVAILABLE_CAPABILITIES,
    XJTU_RUL_LSTM_BENCHMARK_EVIDENCE_CLASS,
    XJTU_RUL_LSTM_BENCHMARK_RESULT_SCHEMA_ID,
    XJTU_RUL_LSTM_BENCHMARK_UNSUPPORTED_CAPABILITIES,
)
from industrial_phm.experiments.xjtu_rul_lstm import XJTU_RUL_LSTM_METHOD_ID


def inspect_xjtu_rul_lstm_benchmark(
    root: Mapping[str, object],
    path: Path,
) -> ExperimentInspection:
    """Read the protocol-frozen RUL held-out benchmark through the shared read model."""
    split = get_xjtu_reference_split()
    fold = split.folds[0]

    provenance = _mapping_field(root, "provenance", "result root")
    _expect_equal(
        _text(provenance, "evidence_class", "provenance"),
        XJTU_RUL_LSTM_BENCHMARK_EVIDENCE_CLASS,
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
    _expect_equal(dataset_id, split.dataset_id, "provenance.dataset_id")
    _expect_equal(split_id, split.split_id, "provenance.split_id")
    _expect_equal(fold_id, fold.fold_id, "provenance.fold_id")

    source_scope = _mapping_field(root, "source_scope", "result root")
    train_bearings = _text_sequence(source_scope, "train_bearings", "source_scope")
    benchmark_bearings = _text_sequence(source_scope, "benchmark_bearings", "source_scope")
    _expect_equal(train_bearings, fold.train, "source_scope.train_bearings")
    _expect_equal(benchmark_bearings, fold.test, "source_scope.benchmark_bearings")
    verified_acquisitions = _positive_int(
        source_scope,
        "verified_source_acquisition_count",
        "source_scope",
    )
    train_acquisitions = _positive_int(
        source_scope,
        "train_source_acquisition_count",
        "source_scope",
    )
    benchmark_acquisitions = _positive_int(
        source_scope,
        "benchmark_source_acquisition_count",
        "source_scope",
    )
    expected_train = sum(get_xjtu_expected_acquisition_count(asset_id) for asset_id in fold.train)
    expected_benchmark = sum(
        get_xjtu_expected_acquisition_count(asset_id) for asset_id in fold.test
    )
    all_bearings = (*fold.train, *fold.validation, *fold.test)
    expected_source = sum(
        get_xjtu_expected_acquisition_count(asset_id) for asset_id in all_bearings
    )
    _expect_equal(train_acquisitions, expected_train, "source_scope.train_source_acquisition_count")
    _expect_equal(
        benchmark_acquisitions,
        expected_benchmark,
        "source_scope.benchmark_source_acquisition_count",
    )
    _expect_equal(
        verified_acquisitions,
        expected_source,
        "source_scope.verified_source_acquisition_count",
    )
    project_history_limitation = _text(
        source_scope,
        "project_history_limitation",
        "source_scope",
    )

    selection = _mapping_field(root, "selection", "result root")
    _expect_equal(
        _text(selection, "validation_selected_method_id", "selection"),
        XJTU_RUL_LSTM_METHOD_ID,
        "selection.validation_selected_method_id",
    )
    if selection.get("operational_primary_method_id") is not None:
        raise ExperimentResultInspectionError(
            "selection.operational_primary_method_id must remain null"
        )
    selection_rule = _text(selection, "selection_rule", "selection")

    target = _mapping_field(root, "target", "result root")
    _expect_equal(
        _text(target, "definition_id", "target"),
        XJTU_RUL_TARGET_DEFINITION_ID,
        "target.definition_id",
    )
    _expect_equal(_text(target, "unit", "target"), XJTU_RUL_TARGET_UNIT, "target.unit")
    _expect_equal(_text(target, "formula", "target"), "N-k", "target.formula")
    _expect_equal(
        _text(target, "endpoint_semantics", "target"),
        "last-recorded-acquisition",
        "target.endpoint_semantics",
    )
    _expect_equal(
        _text(target, "prediction_alignment", "target"),
        "right-edge-acquisition",
        "target.prediction_alignment",
    )
    _expect_equal(_boolean(target, "target_clipping", "target"), False, "target.target_clipping")
    _expect_equal(
        _boolean(target, "target_normalization", "target"),
        False,
        "target.target_normalization",
    )

    method = _mapping_field(root, "method", "result root")
    _expect_equal(
        _text(method, "method_id", "method"),
        XJTU_RUL_LSTM_METHOD_ID,
        "method.method_id",
    )
    feature_schema = _mapping_field(method, "feature_schema", "method")
    preprocessing = _mapping_field(method, "preprocessing", "method")
    sequence = _mapping_field(method, "sequence", "method")
    model = _mapping_field(method, "model", "method")
    _expect_equal(_positive_int(sequence, "length", "sequence"), 8, "method.sequence.length")
    _expect_equal(_positive_int(sequence, "stride", "sequence"), 1, "method.sequence.stride")
    _expect_equal(
        _text(sequence, "alignment", "sequence"),
        "right-edge",
        "method.sequence.alignment",
    )
    _expect_equal(
        _integer(sequence, "benchmark_dropped_prefix_per_bearing", "sequence"),
        7,
        "method.sequence.benchmark_dropped_prefix_per_bearing",
    )
    _expect_equal(_integer(model, "random_seed", "model"), 42, "method.model.random_seed")
    _expect_equal(_text(model, "device", "model"), "cpu", "method.model.device")
    _expect_equal(
        _text(model, "numeric_precision", "model"),
        "float32",
        "method.model.numeric_precision",
    )
    _expect_equal(
        _boolean(model, "deterministic_algorithms", "model"),
        True,
        "method.model.deterministic_algorithms",
    )

    evaluation = _mapping_field(root, "evaluation", "result root")
    point = _mapping_field(evaluation, "point", "evaluation")
    lifecycle = _mapping_field(evaluation, "lifecycle_position", "evaluation")
    _expect_equal(
        _text(point, "prediction_method_id", "evaluation.point"),
        XJTU_RUL_LSTM_METHOD_ID,
        "evaluation.point.prediction_method_id",
    )
    _expect_equal(
        _text(point, "target_definition_id", "evaluation.point"),
        XJTU_RUL_TARGET_DEFINITION_ID,
        "evaluation.point.target_definition_id",
    )
    _expect_equal(
        _text(point, "unit", "evaluation.point"),
        XJTU_RUL_TARGET_UNIT,
        "evaluation.point.unit",
    )
    _expect_equal(
        _text(point, "aggregation", "evaluation.point"),
        "equal-bearing-mean",
        "evaluation.point.aggregation",
    )
    bearing_rows = tuple(
        _mapping(item, "evaluation.point.bearings entry")
        for item in _sequence(point, "bearings", "evaluation.point")
    )
    _validate_rul_benchmark_point_rows(bearing_rows, fold.test, point)

    _expect_equal(
        _text(lifecycle, "prediction_method_id", "evaluation.lifecycle_position"),
        XJTU_RUL_LSTM_METHOD_ID,
        "evaluation.lifecycle_position.prediction_method_id",
    )
    _expect_equal(
        _text(lifecycle, "target_definition_id", "evaluation.lifecycle_position"),
        XJTU_RUL_TARGET_DEFINITION_ID,
        "evaluation.lifecycle_position.target_definition_id",
    )
    _expect_equal(
        _text(lifecycle, "unit", "evaluation.lifecycle_position"),
        XJTU_RUL_TARGET_UNIT,
        "evaluation.lifecycle_position.unit",
    )
    _expect_equal(
        _text(lifecycle, "aggregation", "evaluation.lifecycle_position"),
        "equal-bearing-mean-within-lifecycle-position",
        "evaluation.lifecycle_position.aggregation",
    )
    boundary = _mapping_field(lifecycle, "boundary", "evaluation.lifecycle_position")
    _expect_equal(_text(boundary, "early", "lifecycle boundary"), "1..ceil(N/3)", "boundary.early")
    _expect_equal(
        _text(boundary, "middle", "lifecycle boundary"),
        "ceil(N/3)+1..ceil(2N/3)",
        "boundary.middle",
    )
    _expect_equal(
        _text(boundary, "late", "lifecycle boundary"),
        "ceil(2N/3)+1..N",
        "boundary.late",
    )
    lifecycle_rows = tuple(
        _mapping(item, "evaluation.lifecycle_position.bearing_positions entry")
        for item in _sequence(lifecycle, "bearing_positions", "evaluation.lifecycle_position")
    )
    position_summaries = tuple(
        _mapping(item, "evaluation.lifecycle_position.position_summaries entry")
        for item in _sequence(lifecycle, "position_summaries", "evaluation.lifecycle_position")
    )
    _validate_rul_benchmark_lifecycle_rows(lifecycle_rows, position_summaries, fold.test)

    capability = _mapping_field(root, "capability_scope", "result root")
    available = _text_sequence(capability, "available", "capability_scope")
    unsupported = _text_sequence(capability, "unsupported_or_not_validated", "capability_scope")
    _expect_equal(
        available,
        XJTU_RUL_LSTM_BENCHMARK_AVAILABLE_CAPABILITIES,
        "benchmark available capability scope",
    )
    _expect_equal(
        unsupported,
        XJTU_RUL_LSTM_BENCHMARK_UNSUPPORTED_CAPABILITIES,
        "benchmark unsupported capability scope",
    )

    point_mae = _number(point, "mean_asset_mean_absolute_error", "evaluation.point")
    point_rmse = _number(point, "mean_asset_root_mean_squared_error", "evaluation.point")
    point_signed = _number(point, "mean_asset_mean_signed_error", "evaluation.point")
    point_normalized = _number(
        point,
        "mean_asset_normalized_mean_absolute_error",
        "evaluation.point",
    )

    return ExperimentInspection(
        schema_id=XJTU_RUL_LSTM_BENCHMARK_RESULT_SCHEMA_ID,
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
                    InspectionFact("Benchmark bearing runs", ", ".join(benchmark_bearings)),
                ),
                (project_history_limitation,),
            ),
            InspectionStage(
                "Canonical",
                "completed",
                (
                    InspectionFact("Channels", ", ".join(XJTU_SY_CHANNELS)),
                    InspectionFact("Cardinality", "1 acquisition -> 1 canonical waveform segment"),
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
                        "Fit observations",
                        _positive_int(
                            preprocessing,
                            "fit_observation_count",
                            "preprocessing",
                        ),
                    ),
                ),
            ),
            InspectionStage(
                "Reference",
                "completed",
                (
                    InspectionFact("Selection rule", selection_rule),
                    InspectionFact("Validation-selected method", XJTU_RUL_LSTM_METHOD_ID),
                    InspectionFact("Operational primary method", "none"),
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
                        "Benchmark dropped prefix per bearing",
                        _integer(sequence, "benchmark_dropped_prefix_per_bearing", "sequence"),
                    ),
                ),
            ),
            InspectionStage(
                "Population",
                "completed",
                (
                    InspectionFact("Train source acquisitions", train_acquisitions),
                    InspectionFact("Benchmark source acquisitions", benchmark_acquisitions),
                    InspectionFact(
                        "Benchmark predictions",
                        sum(
                            _positive_int(
                                row,
                                "prediction_count",
                                "evaluation.point.bearings entry",
                            )
                            for row in bearing_rows
                        ),
                    ),
                ),
            ),
            InspectionStage(
                "Model",
                "completed",
                (
                    InspectionFact("Method", XJTU_RUL_LSTM_METHOD_ID),
                    InspectionFact("Kind", _text(method, "kind", "method")),
                    InspectionFact("Random seed", _integer(model, "random_seed", "model")),
                    InspectionFact("Device", _text(model, "device", "model")),
                    InspectionFact(
                        "Numeric precision",
                        _text(model, "numeric_precision", "model"),
                    ),
                ),
            ),
            InspectionStage(
                "Scoring",
                "completed",
                (
                    InspectionFact("Target definition", XJTU_RUL_TARGET_DEFINITION_ID),
                    InspectionFact("Target unit", XJTU_RUL_TARGET_UNIT),
                    InspectionFact("Formula", "N-k"),
                    InspectionFact("Endpoint semantics", "last-recorded-acquisition"),
                    InspectionFact("Prediction alignment", "right-edge-acquisition"),
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
                    InspectionFact("Aggregation", "equal-bearing-mean"),
                    InspectionFact("Mean asset MAE", point_mae),
                    InspectionFact("Mean asset RMSE", point_rmse),
                    InspectionFact("Mean asset signed error", point_signed),
                    InspectionFact("Mean asset normalized MAE", point_normalized),
                    InspectionFact("Lifecycle positions", "early, middle, late"),
                ),
                (
                    "Protocol-frozen retrospective benchmark evidence; project history means "
                    "this is not a pristine external holdout.",
                    "Point-error and lifecycle metrics do not create uncertainty intervals, "
                    "a validated failure threshold, field validation, or a maintenance "
                    "recommendation.",
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
                        XJTU_RUL_LSTM_BENCHMARK_EVIDENCE_CLASS,
                    ),
                    InspectionFact("Declared code revision", declared_revision),
                    InspectionFact("Checkout attestation", "unavailable"),
                    InspectionFact("Artifact", str(path)),
                ),
            ),
        ),
    )


def _validate_rul_benchmark_point_rows(
    rows: tuple[Mapping[str, object], ...],
    expected_assets: tuple[str, ...],
    aggregate: Mapping[str, object],
) -> None:
    if len(rows) != len(expected_assets):
        raise ExperimentResultInspectionError(
            f"benchmark point evaluation requires {len(expected_assets)} bearings, got {len(rows)}"
        )
    observed_assets = tuple(_text(row, "asset_id", "benchmark point row") for row in rows)
    _expect_equal(observed_assets, tuple(sorted(expected_assets)), "benchmark point bearing order")
    for row in rows:
        asset_id = _text(row, "asset_id", "benchmark point row")
        _expect_equal(_text(row, "partition_id", "benchmark point row"), "test", "partition_id")
        expected_count = get_xjtu_expected_acquisition_count(asset_id) - 7
        _expect_equal(
            _positive_int(row, "prediction_count", "benchmark point row"),
            expected_count,
            f"{asset_id} benchmark prediction count",
        )

    metric_fields = (
        "mean_absolute_error",
        "root_mean_squared_error",
        "mean_signed_error",
        "normalized_mean_absolute_error",
    )
    aggregate_fields = (
        "mean_asset_mean_absolute_error",
        "mean_asset_root_mean_squared_error",
        "mean_asset_mean_signed_error",
        "mean_asset_normalized_mean_absolute_error",
    )
    for row_field, aggregate_field in zip(metric_fields, aggregate_fields, strict=True):
        expected = fmean(_number(row, row_field, "benchmark point row") for row in rows)
        _expect_close(
            _number(aggregate, aggregate_field, "evaluation.point"),
            expected,
            f"evaluation.point.{aggregate_field}",
        )


def _validate_rul_benchmark_lifecycle_rows(
    rows: tuple[Mapping[str, object], ...],
    summaries: tuple[Mapping[str, object], ...],
    expected_assets: tuple[str, ...],
) -> None:
    positions = ("early", "middle", "late")
    expected_pairs = tuple(
        (asset_id, position) for asset_id in expected_assets for position in positions
    )
    observed_pairs = tuple(
        (
            _text(row, "asset_id", "benchmark lifecycle row"),
            _text(row, "position", "benchmark lifecycle row"),
        )
        for row in rows
    )
    _expect_equal(observed_pairs, expected_pairs, "benchmark lifecycle bearing/position order")
    if len(summaries) != len(positions):
        raise ExperimentResultInspectionError(
            f"benchmark lifecycle evaluation requires {len(positions)} summaries"
        )

    metric_fields = (
        "mean_absolute_error",
        "root_mean_squared_error",
        "mean_signed_error",
        "normalized_mean_absolute_error",
    )
    aggregate_fields = (
        "mean_asset_mean_absolute_error",
        "mean_asset_root_mean_squared_error",
        "mean_asset_mean_signed_error",
        "mean_asset_normalized_mean_absolute_error",
    )
    for row in rows:
        asset_id = _text(row, "asset_id", "benchmark lifecycle row")
        position = _text(row, "position", "benchmark lifecycle row")
        _expect_equal(
            _text(row, "partition_id", "benchmark lifecycle row"),
            "test",
            f"{asset_id} {position} lifecycle partition",
        )
        run_length = get_xjtu_expected_acquisition_count(asset_id)
        early_end = math.ceil(run_length / 3)
        middle_end = math.ceil(2 * run_length / 3)
        expected_counts = {
            "early": max(early_end - 7, 0),
            "middle": middle_end - early_end,
            "late": run_length - middle_end,
        }
        _expect_equal(
            _positive_int(row, "prediction_count", "benchmark lifecycle row"),
            expected_counts[position],
            f"{asset_id} {position} lifecycle prediction count",
        )

    for summary, position in zip(summaries, positions, strict=True):
        _expect_equal(
            _text(summary, "position", "benchmark lifecycle summary"),
            position,
            "benchmark lifecycle summary position",
        )
        _expect_equal(
            _positive_int(summary, "bearing_count", "benchmark lifecycle summary"),
            len(expected_assets),
            f"{position} lifecycle bearing count",
        )
        position_rows = tuple(
            row for row in rows if _text(row, "position", "benchmark lifecycle row") == position
        )
        for row_field, aggregate_field in zip(metric_fields, aggregate_fields, strict=True):
            expected = fmean(
                _number(row, row_field, "benchmark lifecycle row") for row in position_rows
            )
            _expect_close(
                _number(summary, aggregate_field, "benchmark lifecycle summary"),
                expected,
                f"{position} lifecycle {aggregate_field}",
            )
