"""Experiment command handlers."""

from __future__ import annotations

import argparse
import subprocess
import sys

from industrial_phm.data.registry import UnknownDatasetError, get_dataset
from industrial_phm.experiments.ims import (
    IMS_BEARING_COUNT,
    IMS_EVALUATION_ACQUISITION_COUNT,
    IMS_EVALUATION_ARCHIVE_SCOPE,
    IMS_EVALUATION_TEST_ID,
    IMS_TRAIN_ACQUISITION_COUNT,
    IMS_TRAIN_TEST_ID,
    get_ims_cross_test_configuration,
)
from industrial_phm.experiments.ims_cross_test import run_ims_cross_test_evaluation
from industrial_phm.experiments.mimii import (
    MIMII_DEVELOPMENT_SECTIONS,
    MIMII_EXTERNAL_SECTIONS,
    MIMII_MACHINE_TYPES,
    get_mimii_development_configuration,
    get_mimii_external_section_configuration,
)
from industrial_phm.experiments.mimii_development import run_mimii_development_evaluation
from industrial_phm.experiments.mimii_external_evaluation import run_mimii_external_evaluation
from industrial_phm.experiments.mimii_external_scoring import run_mimii_external_scoring
from industrial_phm.experiments.result_inspection import (
    ExperimentResultInspectionError,
    inspect_experiment_result,
    render_experiment_inspection_text,
)
from industrial_phm.experiments.xjtu_cross_fold import run_xjtu_cross_fold_robustness
from industrial_phm.experiments.xjtu_holdout import run_xjtu_fold_1_holdout_evaluation
from industrial_phm.experiments.xjtu_lstm import get_xjtu_lstm_development_configuration
from industrial_phm.experiments.xjtu_lstm_result import run_xjtu_lstm_development_evaluation
from industrial_phm.experiments.xjtu_reference_comparison import (
    run_xjtu_fold_1_reference_comparison,
)
from industrial_phm.experiments.xjtu_rul_baseline_result import (
    XJTU_RUL_BASELINE_VALIDATION_EVIDENCE_CLASS,
    run_xjtu_rul_baseline_validation,
)
from industrial_phm.experiments.xjtu_rul_benchmark_result import (
    XJTU_RUL_LSTM_BENCHMARK_EVIDENCE_CLASS,
    run_xjtu_rul_lstm_heldout_benchmark,
)
from industrial_phm.experiments.xjtu_rul_validation_result import (
    XJTU_RUL_THREE_MODEL_VALIDATION_EVIDENCE_CLASS,
    run_xjtu_rul_three_model_validation,
)
from industrial_phm.experiments.xjtu_sequence import XJTU_LSTM_SEQUENCE_SPEC
from industrial_phm.experiments.xjtu_validation import run_xjtu_fold_1_validation


def _verify_clean_git_revision(declared_revision: str) -> None:
    """Require a clean tracked checkout whose HEAD matches the declared evidence revision."""
    try:
        head_result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        status_result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(
            "cannot verify the current Git checkout; run authoritative evidence "
            "from a Git working tree"
        ) from error

    observed_revision = head_result.stdout.strip()
    if observed_revision != declared_revision:
        raise ValueError(
            "declared code revision does not match current Git HEAD; "
            f"declared={declared_revision}, head={observed_revision}"
        )
    if status_result.stdout.strip():
        raise ValueError(
            "tracked Git working tree is dirty; commit or revert tracked changes before "
            "authoritative evidence execution"
        )


def _run_experiment_validate(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    if manifest.dataset_id != "xjtu-sy":
        print(
            f"experiment validation is not implemented for {manifest.dataset_id}",
            file=sys.stderr,
        )
        return 2

    try:
        result = run_xjtu_fold_1_validation(
            args.source,
            args.output,
            code_revision=args.code_revision,
            score_trajectory_dir=args.score_trajectory_dir,
        )
    except (OSError, ValueError) as error:
        print(f"experiment validation failed: {error}", file=sys.stderr)
        return 1

    print(f"dataset: {result.dataset_id}")
    print(f"split_id: {result.split_id}")
    print(f"fold_id: {result.fold_id}")
    print(f"partition: {result.partition}")
    print(f"candidates: {len(result.candidates)}")
    print(f"selection_rule_id: {result.selection_rule_id}")
    print(f"selected_experiment_id: {result.selected_experiment_id}")
    print(f"result: {args.output}")
    if args.score_trajectory_dir is not None:
        print(f"score_trajectory_dir: {args.score_trajectory_dir}")
    return 0


def _run_experiment_inspect(args: argparse.Namespace) -> int:
    try:
        inspection = inspect_experiment_result(args.result)
    except (OSError, ExperimentResultInspectionError) as error:
        print(f"experiment result inspection failed: {error}", file=sys.stderr)
        return 1

    print(render_experiment_inspection_text(inspection))
    return 0


def _run_experiment_reference_compare(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    if manifest.dataset_id != "xjtu-sy":
        print(
            f"reference comparison is not implemented for {manifest.dataset_id}",
            file=sys.stderr,
        )
        return 2

    try:
        result = run_xjtu_fold_1_reference_comparison(
            args.source,
            args.output,
            code_revision=args.code_revision,
        )
    except (OSError, ValueError) as error:
        print(f"reference comparison failed: {error}", file=sys.stderr)
        return 1

    print(f"dataset: {result.dataset_id}")
    print(f"fold_id: {result.fold_id}")
    print(f"partition: {result.partition}")
    print(f"hypotheses: {len(result.hypotheses)}")
    for hypothesis in result.hypotheses:
        print(
            f"  {hypothesis.reference_strategy}: "
            f"complete={hypothesis.complete_train_observation_count} "
            f"reference={hypothesis.reference_observation_count} "
            f"fit={hypothesis.model_fit_observation_count} "
            f"mean_late_vs_middle="
            f"{hypothesis.mean_bearing_late_vs_middle_rank_probability}"
        )
    print(f"decision_rule_id: {result.decision_rule_id}")
    print(f"selected_reference_strategy: {result.selected_reference_strategy}")
    print(f"selected_experiment_id: {result.selected_experiment_id}")
    print(f"result: {args.output}")
    return 0


def _run_experiment_holdout(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    if manifest.dataset_id != "xjtu-sy":
        print(
            f"holdout evaluation is not implemented for {manifest.dataset_id}",
            file=sys.stderr,
        )
        return 2

    try:
        result = run_xjtu_fold_1_holdout_evaluation(
            args.source,
            args.output,
            code_revision=args.code_revision,
        )
    except (OSError, ValueError) as error:
        print(f"holdout evaluation failed: {error}", file=sys.stderr)
        return 1

    print(f"dataset: {result.dataset_id}")
    print(f"experiment_id: {result.experiment_id}")
    print(f"fold_id: {result.fold_id}")
    print(f"partition: {result.partition}")
    print(f"reference_strategy: {result.reference_strategy}")
    print(
        f"populations: complete={result.complete_train_observation_count} "
        f"reference={result.reference_observation_count} "
        f"fit={result.model_fit_observation_count}"
    )
    for bearing in result.bearing_results:
        print(
            f"  {bearing.asset_id} ({bearing.operating_condition}) "
            f"n={bearing.full_run_observation_count} "
            f"rho={bearing.acquisition_order_spearman_rho} "
            f"late_vs_middle={bearing.late_vs_middle_rank_probability}"
        )
    print(f"mean_rho: {result.mean_bearing_acquisition_order_spearman_rho}")
    print(f"mean_late_vs_middle: {result.mean_bearing_late_vs_middle_rank_probability}")
    print(f"result: {args.output}")
    return 0


def _run_experiment_cross_test(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    if manifest.dataset_id != "ims-bearings":
        print(
            f"cross-test evaluation is not implemented for {manifest.dataset_id}",
            file=sys.stderr,
        )
        return 2

    config = get_ims_cross_test_configuration()
    train_vectors = IMS_TRAIN_ACQUISITION_COUNT * IMS_BEARING_COUNT
    evaluation_vectors = IMS_EVALUATION_ACQUISITION_COUNT * IMS_BEARING_COUNT
    print("execution plan: IMS single-channel cross-test v1")
    print(
        f"train: {IMS_TRAIN_TEST_ID} complete / "
        f"{IMS_TRAIN_ACQUISITION_COUNT} acquisitions / {train_vectors} bearing vectors"
    )
    print(
        f"evaluation: {IMS_EVALUATION_TEST_ID} {IMS_EVALUATION_ARCHIVE_SCOPE} / "
        f"{IMS_EVALUATION_ACQUISITION_COUNT} acquisitions / "
        f"{evaluation_vectors} bearing vectors"
    )
    print(f"feature: {config.feature_set_id} / {len(config.selected_features)} selected features")
    print(f"reference: {config.reference_strategy.value}")
    print(f"scaling: {config.scaling_strategy.value}")
    print(f"sampling: {config.sampling_policy_id}")
    print(f"model: {config.model_family.value} / seed {config.random_seed}")
    print("excluded: set-1, set-3:archive-extension")
    print("selection/calibration: none")

    try:
        result = run_ims_cross_test_evaluation(
            args.source,
            args.output,
            code_revision=args.code_revision,
        )
    except (OSError, ValueError) as error:
        print(f"cross-test evaluation failed: {error}", file=sys.stderr)
        return 1

    print("pipeline:")
    print("  source validation: completed")
    print("  feature extraction: completed")
    print("  preprocessing: completed")
    print("  model fit: completed")
    print("  model scoring: completed")
    print("  evaluation: completed")
    print(
        "populations: "
        f"complete={result.complete_train_observation_count} "
        f"reference={result.reference_observation_count} "
        f"fit={result.model_fit_observation_count} "
        f"scoring={result.scoring_observation_count}"
    )
    for bearing in result.bearing_results:
        print(
            f"  {bearing.asset_id}: n={bearing.full_run_observation_count} "
            f"rho={bearing.acquisition_order_spearman_rho:.4f} "
            f"late_vs_middle={bearing.late_vs_middle_rank_probability:.4f}"
        )
    print(f"mean_rho: {result.mean_bearing_acquisition_order_spearman_rho:.4f}")
    print(f"mean_late_vs_middle: {result.mean_bearing_late_vs_middle_rank_probability:.4f}")
    print(f"code_revision: {result.code_revision}")
    print(f"result: {args.output}")
    return 0


def _run_experiment_lstm_development(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    if manifest.dataset_id != "xjtu-sy":
        print(
            f"LSTM development evaluation is not implemented for {manifest.dataset_id}",
            file=sys.stderr,
        )
        return 2

    config = get_xjtu_lstm_development_configuration()
    print("execution plan: XJTU LSTM retrospective development v1")
    print(f"scope: {config.split_id} / {config.fold_id} / train -> validation")
    print(f"feature: {config.feature_set_id} / {len(config.selected_features)} selected features")
    print(f"preprocessing: {config.scaling_strategy.value} / fit={config.fit_partition.value}")
    print(f"reference: {config.reference_strategy.value}")
    print(
        "sequence: "
        f"length={XJTU_LSTM_SEQUENCE_SPEC.length} "
        f"stride={XJTU_LSTM_SEQUENCE_SPEC.stride} "
        f"alignment={XJTU_LSTM_SEQUENCE_SPEC.alignment.value}"
    )
    print(f"model: {config.model_family.value} / seed {config.random_seed}")
    print("evidence: retrospective-development-evidence")
    print("holdout test: excluded")
    print("selection/calibration: none")

    try:
        result = run_xjtu_lstm_development_evaluation(
            args.source,
            args.output,
            code_revision=args.code_revision,
        )
    except (OSError, ValueError) as error:
        print(f"LSTM development evaluation failed: {error}", file=sys.stderr)
        return 1

    print("pipeline:")
    print("  source validation: completed")
    print("  feature extraction: completed")
    print("  preprocessing: completed")
    print("  sequence construction: completed")
    print("  model fit: completed")
    print("  reconstruction scoring: completed")
    print("  evaluation: completed")
    print(
        "populations: "
        f"complete={result.preprocessing_fit_observation_count} acquisitions "
        f"reference={result.reference_source_acquisition_count} acquisitions "
        f"fit={result.reference_window_count} windows "
        f"scoring={result.validation_window_count} windows"
    )
    print(f"framework: {result.training.runtime} {result.training.runtime_version}")
    print(f"code_revision: {result.code_revision}")
    print(f"result: {args.output}")
    return 0


def _run_experiment_rul_baseline_validation(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    if manifest.dataset_id != "xjtu-sy":
        print(
            f"RUL baseline validation is not implemented for {manifest.dataset_id}",
            file=sys.stderr,
        )
        return 2

    try:
        _verify_clean_git_revision(args.code_revision)
    except ValueError as error:
        print(f"RUL baseline revision verification failed: {error}", file=sys.stderr)
        return 1

    print("execution plan: XJTU RUL baseline validation v1")
    print("scope: xjtu-sy-condition-stratified-5fold-v1 / fold-1 / train -> validation")
    print("target: recorded-end N-k / acquisition-interval / no clipping")
    print("age baseline: train mean endpoint - current acquisition index")
    print(
        "feature baseline: 16 vibration features / train-only robust scaling / "
        "bearing-balanced Ridge(alpha=1.0)"
    )
    print(f"evidence: {XJTU_RUL_BASELINE_VALIDATION_EVIDENCE_CLASS}")
    print("holdout test: excluded")
    print("uncertainty/calibration: unsupported in this result")
    print(f"revision verification: clean tracked checkout @ {args.code_revision}")

    try:
        result = run_xjtu_rul_baseline_validation(
            args.source,
            args.output,
            code_revision=args.code_revision,
        )
    except (OSError, ValueError) as error:
        print(f"RUL baseline validation failed: {error}", file=sys.stderr)
        return 1

    print("pipeline:")
    print("  source validation: completed")
    print("  feature extraction: completed")
    print("  RUL target construction: completed")
    print("  age-only fit/prediction: completed")
    print("  feature preprocessing/Ridge fit/prediction: completed")
    print("  bearing-first evaluation: completed")
    print(
        "populations: "
        f"train={result.train_source_acquisition_count} acquisitions "
        f"validation={result.validation_source_acquisition_count} acquisitions"
    )
    age_normalized_mae = result.age_evaluation.mean_asset_normalized_mean_absolute_error
    feature_normalized_mae = result.feature_evaluation.mean_asset_normalized_mean_absolute_error
    if age_normalized_mae is None or feature_normalized_mae is None:
        print("RUL baseline result is missing normalized MAE evidence", file=sys.stderr)
        return 1

    print(
        "age-only: "
        f"mae={result.age_evaluation.mean_asset_mean_absolute_error:.6f} "
        f"rmse={result.age_evaluation.mean_asset_root_mean_squared_error:.6f} "
        f"normalized_mae={age_normalized_mae:.6f}"
    )
    print(
        "feature-ridge: "
        f"mae={result.feature_evaluation.mean_asset_mean_absolute_error:.6f} "
        f"rmse={result.feature_evaluation.mean_asset_root_mean_squared_error:.6f} "
        f"normalized_mae={feature_normalized_mae:.6f}"
    )
    print(f"code_revision: {result.code_revision}")
    print(f"result: {args.output}")
    return 0


def _run_experiment_rul_validation(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    if manifest.dataset_id != "xjtu-sy":
        print(
            f"RUL three-model validation is not implemented for {manifest.dataset_id}",
            file=sys.stderr,
        )
        return 2

    try:
        _verify_clean_git_revision(args.code_revision)
    except ValueError as error:
        print(f"RUL validation revision verification failed: {error}", file=sys.stderr)
        return 1

    print("execution plan: XJTU RUL three-model validation v1")
    print("scope: xjtu-sy-condition-stratified-5fold-v1 / fold-1 / train -> validation")
    print("target: recorded-end N-k / acquisition-interval / no clipping")
    print("methods: age-only / feature-Ridge / 8-acquisition temporal LSTM")
    print("temporal prefix: acquisitions 1-7 excluded from temporal prediction only")
    print(
        "metric support: full-run age/Ridge retained; pairwise three-model deltas use "
        "acquisition 8..N common support"
    )
    print(f"evidence: {XJTU_RUL_THREE_MODEL_VALIDATION_EVIDENCE_CLASS}")
    print("holdout test: excluded")
    print("uncertainty/calibration: unsupported in this result")
    print(f"revision verification: clean tracked checkout @ {args.code_revision}")

    try:
        result = run_xjtu_rul_three_model_validation(
            args.source,
            args.output,
            code_revision=args.code_revision,
        )
    except (OSError, ValueError) as error:
        print(f"RUL three-model validation failed: {error}", file=sys.stderr)
        return 1

    age = result.baseline_result.age_evaluation
    feature = result.baseline_result.feature_evaluation
    temporal = result.temporal_evaluation
    normalized = (
        age.mean_asset_normalized_mean_absolute_error,
        feature.mean_asset_normalized_mean_absolute_error,
        temporal.mean_asset_normalized_mean_absolute_error,
    )
    if any(value is None for value in normalized):
        print("RUL validation result is missing normalized MAE evidence", file=sys.stderr)
        return 1
    age_nmae, feature_nmae, temporal_nmae = normalized
    assert age_nmae is not None
    assert feature_nmae is not None
    assert temporal_nmae is not None

    print("pipeline:")
    print("  source validation / feature extraction / RUL targets: completed")
    print("  age-only fit/prediction: completed")
    print("  feature preprocessing/Ridge fit/prediction: completed")
    print("  temporal preprocessing/sequence/LSTM fit/prediction: completed")
    print("  shared bearing-first evaluation: completed")
    print(
        "populations: "
        f"train={result.baseline_result.train_source_acquisition_count} acquisitions "
        f"validation={result.baseline_result.validation_source_acquisition_count} acquisitions "
        f"temporal_fit={result.temporal_train_window_count} windows "
        "temporal_validation_predictions="
        f"{sum(len(series.observations) for series in result.temporal_predictions)}"
    )
    print(
        "age-only(full-run): "
        f"mae={age.mean_asset_mean_absolute_error:.6f} "
        f"rmse={age.mean_asset_root_mean_squared_error:.6f} "
        f"normalized_mae={age_nmae:.6f}"
    )
    print(
        "feature-ridge(full-run): "
        f"mae={feature.mean_asset_mean_absolute_error:.6f} "
        f"rmse={feature.mean_asset_root_mean_squared_error:.6f} "
        f"normalized_mae={feature_nmae:.6f}"
    )
    print(
        "temporal-lstm(acq8..N): "
        f"mae={temporal.mean_asset_mean_absolute_error:.6f} "
        f"rmse={temporal.mean_asset_root_mean_squared_error:.6f} "
        f"normalized_mae={temporal_nmae:.6f}"
    )
    print(f"code_revision: {result.code_revision}")
    print(f"result: {args.output}")
    return 0


def _run_experiment_rul_benchmark(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    if manifest.dataset_id != "xjtu-sy":
        print(
            f"RUL held-out benchmark is not implemented for {manifest.dataset_id}",
            file=sys.stderr,
        )
        return 2

    try:
        _verify_clean_git_revision(args.code_revision)
    except ValueError as error:
        print(f"RUL benchmark revision verification failed: {error}", file=sys.stderr)
        return 1

    print("execution plan: XJTU RUL frozen held-out benchmark v1")
    print("scope: xjtu-sy-condition-stratified-5fold-v1 / fold-1 / train -> test")
    print("selected method: xjtu-sy-rul-lstm-fold-1-v1 / frozen from validation")
    print("target: recorded-end N-k / acquisition-interval / no clipping")
    print("sequence: length=8 / right-edge / acquisitions 1-7 have no prediction")
    print("lifecycle diagnostics: complete-run early/middle/late thirds / equal-bearing mean")
    print(f"evidence: {XJTU_RUL_LSTM_BENCHMARK_EVIDENCE_CLASS}")
    print("benchmark status: retrospective project-history benchmark; not pristine external")
    print("uncertainty/calibration: unsupported in RUL v1")
    print("operational primary method: none")
    print(f"revision verification: clean tracked checkout @ {args.code_revision}")

    try:
        result = run_xjtu_rul_lstm_heldout_benchmark(
            args.source,
            args.output,
            code_revision=args.code_revision,
        )
    except (OSError, ValueError) as error:
        print(f"RUL held-out benchmark failed: {error}", file=sys.stderr)
        return 1

    point = result.point_evaluation
    normalized_mae = point.mean_asset_normalized_mean_absolute_error
    if normalized_mae is None:
        print("RUL benchmark result is missing normalized MAE evidence", file=sys.stderr)
        return 1

    print("pipeline:")
    print("  source validation / feature extraction / RUL targets: completed")
    print("  train-only preprocessing / temporal LSTM fit: completed")
    print("  held-out point prediction: completed")
    print("  lifecycle-position diagnostics: completed")
    print(
        "benchmark: "
        f"mae={point.mean_asset_mean_absolute_error:.6f} "
        f"rmse={point.mean_asset_root_mean_squared_error:.6f} "
        f"signed={point.mean_asset_mean_signed_error:.6f} "
        f"normalized_mae={normalized_mae:.6f}"
    )
    for summary in result.lifecycle_evaluation.position_summaries:
        print(
            f"  {summary.position}: "
            f"mae={summary.mean_asset_mean_absolute_error:.6f} "
            f"rmse={summary.mean_asset_root_mean_squared_error:.6f} "
            f"signed={summary.mean_asset_mean_signed_error:.6f} "
            f"normalized_mae={summary.mean_asset_normalized_mean_absolute_error:.6f}"
        )
    print(f"code_revision: {result.code_revision}")
    print(f"result: {args.output}")
    return 0


def _run_experiment_mimii_development(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    if manifest.dataset_id != "mimii-due":
        print(
            f"MIMII development evaluation is not implemented for {manifest.dataset_id}",
            file=sys.stderr,
        )
        return 2

    try:
        _verify_clean_git_revision(args.code_revision)
    except ValueError as error:
        print(f"MIMII development revision verification failed: {error}", file=sys.stderr)
        return 1

    config = get_mimii_development_configuration()
    print("execution plan: MIMII DUE domain-shift development v1")
    print(
        f"scope: {config.split_id} / {config.fold_id} / "
        f"{len(MIMII_MACHINE_TYPES)} machine types x {len(MIMII_DEVELOPMENT_SECTIONS)} sections"
    )
    print(f"feature: {config.feature_set_id} / {len(config.selected_features)} selected features")
    print(f"preprocessing: {config.scaling_strategy.value} / fit={config.fit_partition.value}")
    print(f"reference: {config.reference_strategy.value}")
    print(f"sampling: {config.sampling_policy_id}")
    print(f"model: {config.model_family.value} / seed {config.random_seed}")
    print("scoring: source_test + target_test / higher-is-more-anomalous")
    print("labels: evaluator edge only")
    print("external evaluation: sections 03-05 excluded")
    print("threshold/calibration: none")
    print(f"revision verification: clean tracked checkout @ {args.code_revision}")

    try:
        result = run_mimii_development_evaluation(
            args.source,
            args.output,
            code_revision=args.code_revision,
        )
    except (OSError, ValueError) as error:
        print(f"MIMII development evaluation failed: {error}", file=sys.stderr)
        return 1

    source_summary = next(
        item for item in result.domain_summaries if item.scope_id == "domain:source"
    )
    target_summary = next(
        item for item in result.domain_summaries if item.scope_id == "domain:target"
    )
    print("pipeline:")
    print("  source validation: completed")
    print("  audio representation: completed")
    print("  section preprocessing/model fit: completed")
    print("  source/target scoring: completed")
    print("  label late-binding evaluation: completed")
    print(f"section_models: {len(result.section_results)}")
    print(
        "source_domain: "
        f"auc_hmean={source_summary.roc_auc_harmonic_mean:.6f} "
        f"pauc_hmean={source_summary.partial_roc_auc_harmonic_mean:.6f}"
    )
    print(
        "target_domain: "
        f"auc_hmean={target_summary.roc_auc_harmonic_mean:.6f} "
        f"pauc_hmean={target_summary.partial_roc_auc_harmonic_mean:.6f}"
    )
    print(
        "overall: "
        f"auc_hmean={result.overall_summary.roc_auc_harmonic_mean:.6f} "
        f"pauc_hmean={result.overall_summary.partial_roc_auc_harmonic_mean:.6f}"
    )
    print(f"mimii_domain_shift_summary: {result.mimii_domain_shift_summary:.6f}")
    print(f"code_revision: {result.code_revision}")
    print(f"result: {args.output}")
    return 0


def _run_experiment_cross_fold(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    if manifest.dataset_id != "xjtu-sy":
        print(
            f"cross-fold robustness is not implemented for {manifest.dataset_id}",
            file=sys.stderr,
        )
        return 2

    try:
        result = run_xjtu_cross_fold_robustness(
            args.source,
            args.output,
            code_revision=args.code_revision,
        )
    except (OSError, ValueError) as error:
        print(f"cross-fold robustness failed: {error}", file=sys.stderr)
        return 1

    print(f"dataset: {result.dataset_id}")
    print(f"finalized_experiment_id: {result.finalized_experiment_id}")
    for fold in result.folds:
        print(
            f"  {fold.fold_id}: test={','.join(fold.test_bearings)} "
            f"complete={fold.complete_train_observation_count} "
            f"reference={fold.reference_observation_count} "
            f"fit={fold.model_fit_observation_count} "
            f"mean_rho={fold.mean_bearing_acquisition_order_spearman_rho:.4f} "
            f"mean_late_vs_middle={fold.mean_bearing_late_vs_middle_rank_probability:.4f}"
        )
    for summary in result.condition_summaries:
        print(
            f"  {summary.operating_condition} (n={summary.bearing_count}): "
            f"mean_rho={summary.mean_bearing_acquisition_order_spearman_rho:.4f} "
            f"mean_late_vs_middle={summary.mean_bearing_late_vs_middle_rank_probability:.4f}"
        )
    print(
        f"overall (n={result.overall_bearing_count}): "
        f"mean_rho={result.overall_mean_bearing_acquisition_order_spearman_rho:.4f} "
        f"mean_late_vs_middle="
        f"{result.overall_mean_bearing_late_vs_middle_rank_probability:.4f}"
    )
    print(f"result: {args.output}")
    return 0


def _run_experiment_mimii_external_score(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    if manifest.dataset_id != "mimii-due":
        print(
            f"MIMII external scoring is not implemented for {manifest.dataset_id}",
            file=sys.stderr,
        )
        return 2

    try:
        _verify_clean_git_revision(args.code_revision)
    except ValueError as error:
        print(f"MIMII external scoring revision verification failed: {error}", file=sys.stderr)
        return 1

    config = get_mimii_external_section_configuration("fan", "03")
    print("execution plan: MIMII DUE external scoring v1 (label-blind)")
    print(
        f"scope: {config.split_id} / {len(MIMII_MACHINE_TYPES)} machine types x "
        f"{len(MIMII_EXTERNAL_SECTIONS)} sections"
    )
    print(f"feature: {config.feature_set_id} / {len(config.selected_features)} selected features")
    print(f"preprocessing: {config.scaling_strategy.value} / fit={config.fit_partition.value}")
    print(f"reference: {config.reference_strategy.value}")
    print(f"sampling: {config.sampling_policy_id}")
    print(f"model: {config.model_family.value} / seed {config.random_seed}")
    print("train population: sections 03-05 normal train only")
    print("scoring: evaluation source_test + target_test / higher-is-more-anomalous")
    print("ground truth: not read by this path")
    print("threshold/calibration: none")
    print(f"revision verification: clean tracked checkout @ {args.code_revision}")

    try:
        result = run_mimii_external_scoring(
            args.source,
            args.evaluation_source,
            args.output,
            code_revision=args.code_revision,
        )
    except (OSError, ValueError) as error:
        print(f"MIMII external scoring failed: {error}", file=sys.stderr)
        return 1

    print(f"section_models: {len(result.sections)}")
    print(f"verified evaluation clips: {result.verified_evaluation_clip_count}")
    print(f"scored clips: {result.scored_clip_count}")
    print(f"code_revision: {result.code_revision}")
    print(f"result: {args.output}")
    return 0


def _run_experiment_mimii_external_evaluate(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    if manifest.dataset_id != "mimii-due":
        print(
            f"MIMII external evaluation is not implemented for {manifest.dataset_id}",
            file=sys.stderr,
        )
        return 2

    try:
        _verify_clean_git_revision(args.code_revision)
    except ValueError as error:
        print(f"MIMII external evaluation revision verification failed: {error}", file=sys.stderr)
        return 1

    print("execution plan: MIMII DUE external evaluation v1 (late-bound labels)")
    print(f"score artifact: {args.score_artifact}")
    print(f"ground truth: {args.ground_truth_dir}")
    print("label mapping: 0=normal, 1=anomaly (Zenodo 5257674 description)")
    print("evaluator reads: fixed scores + ground truth only; no audio, no model fit")
    print("threshold/calibration: none")
    print(f"revision verification: clean tracked checkout @ {args.code_revision}")

    try:
        result = run_mimii_external_evaluation(
            args.score_artifact,
            args.ground_truth_dir,
            args.output,
            code_revision=args.code_revision,
        )
    except (OSError, ValueError) as error:
        print(f"MIMII external evaluation failed: {error}", file=sys.stderr)
        return 1

    print(f"strata: {len(result.strata)}")
    print(f"score artifact sha256: {result.score_artifact_sha256}")
    for summary in result.domain_summaries:
        print(
            f"  {summary.scope_id}: auc_hmean={summary.roc_auc_harmonic_mean:.6f} "
            f"pauc_hmean={summary.partial_roc_auc_harmonic_mean:.6f}"
        )
    print(
        f"  overall: auc_hmean={result.overall_summary.roc_auc_harmonic_mean:.6f} "
        f"pauc_hmean={result.overall_summary.partial_roc_auc_harmonic_mean:.6f}"
    )
    print(f"mimii_domain_shift_summary: {result.domain_shift_summary:.6f}")
    print(f"result: {args.output}")
    return 0

