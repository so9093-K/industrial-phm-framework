"""Schema-specific inspection for XJTU fold-1 holdout evidence."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from industrial_phm.adapters import XJTU_SY_CHANNELS, get_xjtu_expected_acquisition_count
from industrial_phm.experiments.config import ExperimentConfig
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
    _provenance_stage,
    _revision,
    _sequence,
    _text,
)
from industrial_phm.experiments.xjtu import get_xjtu_reference_split
from industrial_phm.experiments.xjtu_finalized import get_xjtu_finalized_configuration
from industrial_phm.experiments.xjtu_holdout import XJTU_HOLDOUT_RESULT_SCHEMA_ID
from industrial_phm.experiments.xjtu_inspection_support import (
    AVAILABLE_CAPABILITIES,
    SCORE_SEMANTICS,
    UNSUPPORTED_CAPABILITIES,
    format_parameters,
)
from industrial_phm.experiments.xjtu_lifecycle import early_third_length


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


def inspect_xjtu_holdout(root: Mapping[str, object], path: Path) -> ExperimentInspection:
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

    parameters = format_parameters(config.model_parameters)
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
                    InspectionFact("Score semantics", SCORE_SEMANTICS),
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
            _capability_stage(AVAILABLE_CAPABILITIES, UNSUPPORTED_CAPABILITIES),
            _provenance_stage(config, declared_revision, path),
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
