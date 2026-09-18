"""Command-line interface for explicit industrial PHM workflows."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from industrial_phm import __version__
from industrial_phm.adapters import (
    ImsBearingSourceError,
    XjtuSySourceError,
    validate_ims_source,
    validate_xjtu_source,
)
from industrial_phm.data.acquisition import (
    ManualAcquisitionRequired,
    dataset_archive_path,
    fetch_dataset,
)
from industrial_phm.data.registry import UnknownDatasetError, get_dataset, list_datasets
from industrial_phm.data.validation import (
    DatasetIntegrityError,
    inspect_file,
    inspect_source,
    verify_sha256,
)
from industrial_phm.experiments.xjtu_characterization import (
    XjtuFeatureCharacterizationError,
    characterize_xjtu_source,
)
from industrial_phm.experiments.xjtu_cross_fold import run_xjtu_cross_fold_robustness
from industrial_phm.experiments.xjtu_holdout import run_xjtu_fold_1_holdout_evaluation
from industrial_phm.experiments.xjtu_reference_comparison import (
    run_xjtu_fold_1_reference_comparison,
)
from industrial_phm.experiments.xjtu_validation import run_xjtu_fold_1_validation
from industrial_phm.features import VibrationFeatureError

DATA_ROOT_ENV = "INDUSTRIAL_PHM_DATA_DIR"


def default_data_root() -> Path:
    """Return the explicit environment override or repository-local raw-data default."""

    configured = os.environ.get(DATA_ROOT_ENV)
    return Path(configured) if configured else Path("data/raw")


def build_parser() -> argparse.ArgumentParser:
    """Build the stable CLI surface for currently implemented features."""

    parser = argparse.ArgumentParser(prog="industrial-phm")
    subcommands = parser.add_subparsers(dest="command", required=True)

    doctor = subcommands.add_parser("doctor", help="show runtime and data-root information")
    doctor.set_defaults(handler=_run_doctor)

    data = subcommands.add_parser("data", help="inspect, validate, and acquire registered datasets")
    data_commands = data.add_subparsers(dest="data_command", required=True)

    data_list = data_commands.add_parser("list", help="list registered datasets")
    data_list.set_defaults(handler=_run_data_list)

    data_status = data_commands.add_parser("status", help="show source and local acquisition state")
    data_status.add_argument("dataset_id")
    _add_data_root_argument(data_status)
    data_status.set_defaults(handler=_run_data_status)

    data_fetch = data_commands.add_parser("fetch", help="explicitly acquire a registered dataset")
    data_fetch.add_argument("dataset_id")
    _add_data_root_argument(data_fetch)
    data_fetch.set_defaults(handler=_run_data_fetch)

    data_verify = data_commands.add_parser(
        "verify",
        help="inspect or verify a managed dataset archive",
    )
    data_verify.add_argument("dataset_id")
    _add_data_root_argument(data_verify)
    data_verify.set_defaults(handler=_run_data_verify)

    data_inspect = data_commands.add_parser(
        "inspect",
        help="summarize the structural inventory of a local dataset source",
    )
    data_inspect.add_argument("dataset_id")
    data_inspect.add_argument(
        "--source",
        type=Path,
        required=True,
        help="local file, ZIP archive, or directory acquired from the registered source",
    )
    data_inspect.add_argument(
        "--details",
        action="store_true",
        help="show bounded path samples from structural metadata",
    )
    data_inspect.set_defaults(handler=_run_data_inspect)

    data_validate = data_commands.add_parser(
        "validate",
        help="validate a prepared local dataset against dataset-specific structure",
    )
    data_validate.add_argument("dataset_id")
    data_validate.add_argument(
        "--source",
        type=Path,
        required=True,
        help="prepared local dataset root consumed by its Domain Adapter",
    )
    data_validate.add_argument(
        "--full",
        action="store_true",
        help="parse every acquisition instead of representative first/middle/last samples",
    )
    data_validate.set_defaults(handler=_run_data_validate)

    feature = subcommands.add_parser(
        "feature",
        help="run implemented feature extraction and characterization workflows",
    )
    feature_commands = feature.add_subparsers(dest="feature_command", required=True)

    feature_characterize = feature_commands.add_parser(
        "characterize",
        help="generate split-aware descriptive feature characterization artifacts",
    )
    feature_characterize.add_argument("dataset_id")
    feature_characterize.add_argument(
        "--source",
        type=Path,
        required=True,
        help="prepared local dataset root consumed by its Domain Adapter",
    )
    feature_characterize.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="local output directory for generated characterization artifacts",
    )
    feature_characterize.add_argument(
        "--fold-id",
        required=True,
        help="version-controlled reference fold, for example fold-1",
    )
    feature_characterize.add_argument(
        "--partition",
        choices=("train", "validation"),
        default="train",
        help="development partition to characterize; holdout test is unavailable",
    )
    feature_characterize.set_defaults(handler=_run_feature_characterize)

    experiment = subcommands.add_parser(
        "experiment",
        help="run implemented model experiment workflows",
    )
    experiment_commands = experiment.add_subparsers(
        dest="experiment_command",
        required=True,
    )
    experiment_validate = experiment_commands.add_parser(
        "validate",
        help="execute frozen development candidates against a validation partition",
    )
    experiment_validate.add_argument("dataset_id")
    experiment_validate.add_argument(
        "--source",
        type=Path,
        required=True,
        help="prepared local dataset root consumed by its Domain Adapter",
    )
    experiment_validate.add_argument(
        "--output",
        type=Path,
        required=True,
        help="destination for the generated validation result JSON",
    )
    experiment_validate.add_argument(
        "--code-revision",
        required=True,
        help="full Git commit SHA for the exact execution code",
    )
    experiment_validate.add_argument(
        "--score-trajectory-dir",
        type=Path,
        default=None,
        help=(
            "also write development-only train/validation anomaly-score trajectories "
            "to this local directory"
        ),
    )
    experiment_validate.set_defaults(handler=_run_experiment_validate)

    experiment_reference = experiment_commands.add_parser(
        "reference-compare",
        help="run the frozen fold-1 H0/H1 reference-strategy development comparison",
    )
    experiment_reference.add_argument("dataset_id")
    experiment_reference.add_argument(
        "--source",
        type=Path,
        required=True,
        help="prepared local dataset root consumed by its Domain Adapter",
    )
    experiment_reference.add_argument(
        "--output",
        type=Path,
        required=True,
        help="destination for the generated reference comparison result JSON",
    )
    experiment_reference.add_argument(
        "--code-revision",
        required=True,
        help="full Git commit SHA for the exact execution code",
    )
    experiment_reference.set_defaults(handler=_run_experiment_reference_compare)

    experiment_holdout = experiment_commands.add_parser(
        "holdout",
        help="evaluate the finalized fold-1 configuration on the holdout test partition once",
    )
    experiment_holdout.add_argument("dataset_id")
    experiment_holdout.add_argument(
        "--source",
        type=Path,
        required=True,
        help="prepared local dataset root consumed by its Domain Adapter",
    )
    experiment_holdout.add_argument(
        "--output",
        type=Path,
        required=True,
        help="destination for the generated holdout result JSON",
    )
    experiment_holdout.add_argument(
        "--code-revision",
        required=True,
        help="full Git commit SHA for the exact execution code",
    )
    experiment_holdout.set_defaults(handler=_run_experiment_holdout)

    experiment_cross_fold = experiment_commands.add_parser(
        "cross-fold",
        help="collect post-holdout robustness evidence across folds 2-5 in one pass",
    )
    experiment_cross_fold.add_argument("dataset_id")
    experiment_cross_fold.add_argument(
        "--source",
        type=Path,
        required=True,
        help="prepared local dataset root consumed by its Domain Adapter",
    )
    experiment_cross_fold.add_argument(
        "--output",
        type=Path,
        required=True,
        help="destination for the generated cross-fold robustness result JSON",
    )
    experiment_cross_fold.add_argument(
        "--code-revision",
        required=True,
        help="full Git commit SHA for the exact execution code",
    )
    experiment_cross_fold.set_defaults(handler=_run_experiment_cross_fold)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)
    handler = args.handler
    return int(handler(args))


def _add_data_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=default_data_root(),
        help=f"raw data root (default: ${DATA_ROOT_ENV} or data/raw)",
    )


def _run_doctor(args: argparse.Namespace) -> int:
    del args
    print(f"industrial-phm {__version__}")
    print(f"data root: {default_data_root()}")
    print(f"registered datasets: {len(list_datasets())}")
    return 0


def _run_data_list(args: argparse.Namespace) -> int:
    del args
    for manifest in list_datasets():
        print(
            f"{manifest.dataset_id}\t{manifest.provider}\t{manifest.version}\t"
            f"{manifest.license_name}\t{manifest.title}"
        )
    return 0


def _run_data_status(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    root = args.root
    print(f"dataset: {manifest.dataset_id}")
    print(f"title: {manifest.title}")
    print(f"version: {manifest.version}")
    print(f"provider: {manifest.provider}")
    print(f"source: {manifest.source_url}")
    print(f"license: {manifest.license_name}")
    if manifest.citation_doi is not None:
        print(f"citation DOI: {manifest.citation_doi}")

    path = dataset_archive_path(manifest, root)
    if path is None:
        print("local state: manual source; no framework-managed archive path")
        return 0

    print(f"archive: {path}")
    print(f"local state: {'present' if path.is_file() else 'missing'}")
    checksum_policy = "manifest SHA-256" if manifest.sha256 is not None else "local SHA-256"
    print(f"checksum policy: {checksum_policy}")
    return 0


def _run_data_fetch(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
        result = fetch_dataset(manifest, args.root)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2
    except ManualAcquisitionRequired as error:
        print(str(error), file=sys.stderr)
        print(
            "download from the official source and preserve provenance before import",
            file=sys.stderr,
        )
        return 2
    except (OSError, DatasetIntegrityError, ValueError) as error:
        print(f"dataset fetch failed: {error}", file=sys.stderr)
        return 1

    print(f"fetched: {result.path}")
    print(f"bytes: {result.integrity.size_bytes}")
    print(f"sha256: {result.integrity.sha256}")
    if not result.checksum_pinned:
        print("integrity basis: local SHA-256 provenance")
    return 0


def _run_data_verify(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    path = dataset_archive_path(manifest, root=args.root)
    if path is None:
        print(
            f"{manifest.dataset_id} is a manual source without a framework-managed archive",
            file=sys.stderr,
        )
        print(f"official source: {manifest.source_url}", file=sys.stderr)
        return 2

    try:
        if manifest.sha256 is None:
            integrity = inspect_file(path)
        else:
            integrity = verify_sha256(path, manifest.sha256)
    except DatasetIntegrityError as error:
        print(str(error), file=sys.stderr)
        return 1

    if manifest.sha256 is None:
        print(f"local file inspected: {integrity.path}")
    else:
        print(f"verified local file: {integrity.path}")
    print(f"bytes: {integrity.size_bytes}")
    print(f"sha256: {integrity.sha256}")
    if manifest.sha256 is None:
        print("integrity basis: local SHA-256 provenance; no publisher checksum pinned")
    return 0


def _run_data_inspect(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
        inspection = inspect_source(args.source)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2
    except (OSError, DatasetIntegrityError) as error:
        print(f"dataset inspection failed: {error}", file=sys.stderr)
        return 1

    print(f"dataset: {manifest.dataset_id}")
    print(f"title: {manifest.title}")
    print(f"provider: {manifest.provider}")
    print(f"official source: {manifest.source_url}")
    print(f"local source: {inspection.path}")
    print(f"source kind: {inspection.kind}")
    print(f"files: {inspection.file_count}")
    print(f"bytes: {inspection.source_bytes}")
    if inspection.kind == "zip":
        print(f"uncompressed bytes: {inspection.total_bytes}")
    print(f"max path depth: {inspection.max_depth}")

    for summary in inspection.extension_summaries:
        extension = summary.extension or "<none>"
        print(
            f"extension {extension}: {summary.file_count} file(s), "
            f"{summary.total_bytes} payload byte(s)"
        )

    if args.details:
        for entry in inspection.top_level_entries:
            print(f"top-level sample: {entry}")
        for path_sample in inspection.representative_files:
            print(f"representative file: {path_sample}")

    if inspection.file_count == 0:
        print(
            "inspection state: empty local source; add dataset files before continuing",
            file=sys.stderr,
        )
        return 1

    nested_archive_extensions = {".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".zip"}
    nested_archives_observed = inspection.kind == "zip" and any(
        summary.extension in nested_archive_extensions for summary in inspection.extension_summaries
    )
    print("inspection scope: structural inventory")
    print("inspection state: completed")
    if nested_archives_observed:
        print("prepared source state: nested archive extraction required")
        print(
            f"validation command: industrial-phm data validate {manifest.dataset_id} "
            "--source <prepared-source>"
        )
    return 0


def _run_data_validate(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    if manifest.dataset_id == "xjtu-sy":
        return _run_xjtu_data_validate(args, manifest.title)
    if manifest.dataset_id == "ims-bearings":
        return _run_ims_data_validate(args, manifest.title)

    print(
        f"dataset-specific validation is not implemented for {manifest.dataset_id}",
        file=sys.stderr,
    )
    return 2


def _run_xjtu_data_validate(args: argparse.Namespace, title: str) -> int:

    try:
        report = validate_xjtu_source(args.source, full=args.full)
    except (OSError, XjtuSySourceError) as error:
        print(f"dataset validation failed: {error}", file=sys.stderr)
        return 1

    print("dataset: xjtu-sy")
    print(f"title: {title}")
    print(f"local source: {report.source}")
    print(f"validation mode: {'full' if report.full else 'sampled'}")
    print(f"operating conditions: {report.operating_condition_count}")
    print(f"bearing runs: {report.bearing_run_count}")
    print(f"acquisitions: {report.acquisition_count}")
    print(f"waveform acquisitions checked: {report.checked_acquisition_count}")
    print(f"samples per acquisition: {report.samples_per_acquisition}")
    print(f"channels: {', '.join(report.channels)}")
    print(f"sampling rate hz: {report.sampling_rate_hz:g}")
    print(f"waveform compatibility: PASS ({'full' if report.full else 'sampled'})")

    if not report.profile_matches:
        print("profile compatibility: FAIL")
        for issue in report.profile_issues:
            print(f"profile issue: {issue}", file=sys.stderr)
        return 1

    print("profile compatibility: PASS")
    return 0


def _run_ims_data_validate(args: argparse.Namespace, title: str) -> int:
    try:
        report = validate_ims_source(args.source, full=args.full)
    except (OSError, ImsBearingSourceError) as error:
        print(f"dataset validation failed: {error}", file=sys.stderr)
        return 1

    print("dataset: ims-bearings")
    print(f"title: {title}")
    print(f"local source: {report.source}")
    print(f"validation mode: {'full' if report.full else 'sampled'}")
    print(f"tests: {len(report.tests)}")
    print(f"acquisitions: {report.acquisition_count}")
    print(f"waveform acquisitions checked: {report.checked_acquisition_count}")
    print(f"samples per acquisition: {report.samples_per_acquisition}")
    print(f"sampling rate hz: {report.sampling_rate_hz:g}")
    for summary in report.tests:
        print(
            f"test {summary.test_id}: source={summary.source_directory}, "
            f"acquisitions={summary.acquisition_count}, channels={summary.channel_count}, "
            f"range={summary.first_acquisition_at.isoformat()}.."
            f"{summary.last_acquisition_at.isoformat()}"
        )
        if summary.archive_extension_acquisition_count:
            print(
                f"test {summary.test_id} archive extension: "
                f"{summary.archive_extension_acquisition_count} acquisition(s); "
                f"README scope={summary.readme_acquisition_count} acquisition(s)"
            )
    print(f"waveform compatibility: PASS ({'full' if report.full else 'sampled'})")

    if not report.profile_matches:
        print("profile compatibility: FAIL")
        for issue in report.profile_issues:
            print(f"profile issue: {issue}", file=sys.stderr)
        return 1

    print("profile compatibility: PASS")
    return 0


def _run_feature_characterize(args: argparse.Namespace) -> int:
    try:
        manifest = get_dataset(args.dataset_id)
    except UnknownDatasetError as error:
        print(str(error), file=sys.stderr)
        return 2

    if manifest.dataset_id != "xjtu-sy":
        print(
            f"feature characterization is not implemented for {manifest.dataset_id}",
            file=sys.stderr,
        )
        return 2

    try:
        artifacts = characterize_xjtu_source(
            args.source,
            args.output_dir,
            fold_id=args.fold_id,
            partition=args.partition,
        )
    except (
        OSError,
        XjtuSySourceError,
        XjtuFeatureCharacterizationError,
        VibrationFeatureError,
    ) as error:
        print(f"feature characterization failed: {error}", file=sys.stderr)
        return 1

    print(f"dataset: {manifest.dataset_id}")
    print(f"feature_set_id: {artifacts.feature_set_id}")
    print(f"split_id: {artifacts.split_id}")
    print(f"fold_id: {artifacts.fold_id}")
    print(f"partition: {artifacts.partition}")
    print(f"acquisitions: {artifacts.acquisition_count}")
    print(f"bearing_runs: {artifacts.bearing_run_count}")
    print(f"operating_conditions: {artifacts.operating_condition_count}")
    print(f"feature_table: {artifacts.feature_table_path}")
    print(f"summary: {artifacts.summary_path}")
    return 0


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
