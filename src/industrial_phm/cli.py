"""Command-line interface for explicit industrial PHM workflows."""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from industrial_phm import __version__
from industrial_phm.commands.analysis import _run_analysis_report
from industrial_phm.commands.data import (
    _run_data_fetch,
    _run_data_inspect,
    _run_data_list,
    _run_data_status,
    _run_data_validate,
    _run_data_validate_csv,
    _run_data_verify,
)
from industrial_phm.commands.experiment import (
    _run_experiment_cross_fold,
    _run_experiment_cross_test,
    _run_experiment_holdout,
    _run_experiment_inspect,
    _run_experiment_lstm_development,
    _run_experiment_mimii_development,
    _run_experiment_mimii_external_evaluate,
    _run_experiment_mimii_external_score,
    _run_experiment_reference_compare,
    _run_experiment_rul_baseline_validation,
    _run_experiment_rul_benchmark,
    _run_experiment_rul_validation,
    _run_experiment_validate,
)
from industrial_phm.commands.feature import _run_feature_characterize
from industrial_phm.commands.operations import (
    _run_operations_backfill_source,
    _run_operations_collection_service,
    _run_operations_compact_history,
    _run_operations_flush_history,
    _run_operations_init,
    _run_operations_migrate_phase_unbalance_results,
    _run_operations_poll_source,
    _run_operations_request_collection,
    _run_operations_start,
    _run_operations_status,
    _run_operations_stop,
    _run_operations_window_analysis,
)
from industrial_phm.data.registry import list_datasets

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

    analysis = subcommands.add_parser(
        "analysis",
        help="render and export validated user-facing analysis evidence",
    )
    analysis_commands = analysis.add_subparsers(dest="analysis_command", required=True)
    analysis_report = analysis_commands.add_parser(
        "report",
        help="write a deterministic Markdown report from validated analysis artifacts",
    )
    analysis_report.add_argument(
        "--anomaly",
        type=Path,
        required=True,
        help="validated XJTU LSTM anomaly evidence artifact",
    )
    analysis_report.add_argument(
        "--asset",
        required=True,
        help="asset identity to render",
    )
    analysis_report.add_argument(
        "--prognostics",
        type=Path,
        default=None,
        help="optional compatible prognostics evidence artifact",
    )
    analysis_report.add_argument(
        "--output",
        type=Path,
        required=True,
        help="destination Markdown report path",
    )
    analysis_report.set_defaults(handler=_run_analysis_report)

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
        help="check every waveform instead of representative samples",
    )
    data_validate.set_defaults(handler=_run_data_validate)

    data_validate_csv = data_commands.add_parser(
        "validate-csv",
        help="validate a prepared single-asset field CSV export",
    )
    data_validate_csv.add_argument(
        "--source",
        type=Path,
        required=True,
        help="prepared CSV sensor export",
    )
    data_validate_csv.add_argument(
        "--asset-id",
        required=True,
        help="canonical asset identity for this CSV segment",
    )
    data_validate_csv.add_argument(
        "--channel",
        dest="channels",
        action="append",
        required=True,
        help="sensor value column; repeat for multiple channels",
    )
    data_validate_csv.add_argument(
        "--timestamp-column",
        default=None,
        help="optional ISO 8601 timestamp column",
    )
    data_validate_csv.add_argument(
        "--sampling-rate-hz",
        type=float,
        default=None,
        help="optional declared regular sampling rate in Hz",
    )
    data_validate_csv.add_argument(
        "--sampling-rate-tolerance-ratio",
        type=float,
        default=None,
        help=("optional maximum relative timestamp-interval deviation from declared sampling rate"),
    )
    data_validate_csv.add_argument(
        "--minimum-sample-count",
        type=int,
        default=1,
        help="minimum accepted data-row count",
    )
    data_validate_csv.add_argument(
        "--delimiter",
        default=",",
        help="single-character CSV delimiter",
    )
    data_validate_csv.set_defaults(handler=_run_data_validate_csv)

    operations = subcommands.add_parser(
        "operations",
        help="run explicit operational source-runtime workflows",
    )
    operations_commands = operations.add_subparsers(
        dest="operations_command",
        required=True,
    )
    operations_init = operations_commands.add_parser(
        "init",
        help="initialize or validate one local Operations workspace",
    )
    operations_init.add_argument(
        "workspace",
        type=Path,
        help="local Operations workspace root",
    )
    operations_init.set_defaults(handler=_run_operations_init)

    operations_start = operations_commands.add_parser(
        "start",
        help="run the local Operations service lifecycle in the foreground",
    )
    operations_start.add_argument(
        "workspace",
        type=Path,
        help="initialized local Operations workspace root",
    )
    operations_start.set_defaults(handler=_run_operations_start)

    operations_stop = operations_commands.add_parser(
        "stop",
        help="request graceful shutdown of the live local Operations supervisor",
    )
    operations_stop.add_argument(
        "workspace",
        type=Path,
        help="initialized local Operations workspace root",
    )
    operations_stop.set_defaults(handler=_run_operations_stop)

    operations_status = operations_commands.add_parser(
        "status",
        help="show local supervisor process identity and component runtime readiness",
    )
    operations_status.add_argument(
        "workspace",
        type=Path,
        help="initialized local Operations workspace root",
    )
    operations_status.set_defaults(handler=_run_operations_status)

    operations_poll_source = operations_commands.add_parser(
        "poll-source",
        help="poll one ACTIVE registered FILE or OPC UA source until stopped",
    )
    operations_poll_source.add_argument(
        "--registry",
        type=Path,
        required=True,
        help="persistent registered-source control-plane JSON path",
    )
    operations_poll_source.add_argument(
        "--runtime-state",
        type=Path,
        required=True,
        help="separate persistent latest runtime-evidence JSON path",
    )
    operations_poll_source.add_argument(
        "--source-id",
        required=True,
        help="registered source ID to poll",
    )
    operations_poll_source.add_argument(
        "--interval-seconds",
        type=float,
        default=5.0,
        help="positive polling interval in seconds (default: 5)",
    )
    operations_poll_source.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="optional positive cycle limit; omit to run until stop/failure/Ctrl+C",
    )
    operations_poll_source.set_defaults(handler=_run_operations_poll_source)

    operations_backfill_source = operations_commands.add_parser(
        "backfill-source",
        help="backfill one registered timestamped FILE source into DuckLake Asset History",
    )
    operations_backfill_source.add_argument(
        "--registry",
        type=Path,
        required=True,
        help="persistent registered-source control-plane JSON path",
    )
    operations_backfill_source.add_argument(
        "--source-id",
        required=True,
        help="registered FILE source ID",
    )
    operations_backfill_source.add_argument(
        "--ducklake-catalog",
        type=Path,
        required=True,
        help="DuckLake SQLite catalog path",
    )
    operations_backfill_source.add_argument(
        "--ducklake-data",
        type=Path,
        required=True,
        help="DuckLake managed Parquet data directory",
    )
    operations_backfill_source.set_defaults(handler=_run_operations_backfill_source)

    operations_compact_history = operations_commands.add_parser(
        "compact-history",
        help="merge active small DuckLake Parquet files without expiring snapshots",
    )
    operations_compact_history.add_argument(
        "--ducklake-catalog",
        type=Path,
        required=True,
        help="DuckLake SQLite catalog path",
    )
    operations_compact_history.add_argument(
        "--ducklake-data",
        type=Path,
        required=True,
        help="DuckLake managed Parquet data directory",
    )
    operations_compact_history.add_argument(
        "--target-file-size-bytes",
        type=int,
        required=True,
        help="persistent DuckLake target_file_size for compaction outputs and future writes",
    )
    operations_compact_history.add_argument(
        "--max-compacted-files",
        type=int,
        required=True,
        help="maximum DuckLake compaction output operations per table; not an input-file limit",
    )
    operations_compact_history.add_argument(
        "--min-file-size-bytes",
        type=int,
        default=None,
        help="optional minimum active data-file size eligible for compaction",
    )
    operations_compact_history.add_argument(
        "--max-file-size-bytes",
        type=int,
        default=None,
        help="optional maximum active data-file size eligible for compaction",
    )
    operations_compact_history.set_defaults(handler=_run_operations_compact_history)

    operations_flush_history = operations_commands.add_parser(
        "flush-history",
        help="move catalog-inlined DuckLake Asset History rows to Parquet",
    )
    operations_flush_history.add_argument(
        "--ducklake-catalog",
        type=Path,
        required=True,
        help="DuckLake SQLite catalog path",
    )
    operations_flush_history.add_argument(
        "--ducklake-data",
        type=Path,
        required=True,
        help="DuckLake managed Parquet data directory",
    )
    operations_flush_history.set_defaults(handler=_run_operations_flush_history)

    operations_migrate_phase_results = operations_commands.add_parser(
        "migrate-phase-unbalance-results",
        help="copy legacy phase-unbalance JSON evidence into the SQLite result store",
    )
    operations_migrate_phase_results.add_argument(
        "--from-json",
        type=Path,
        required=True,
        help="legacy phase-unbalance JSON result path; never modified",
    )
    operations_migrate_phase_results.add_argument(
        "--to-sqlite",
        type=Path,
        required=True,
        help="SQLite result path used by the live runner and Operations",
    )
    operations_migrate_phase_results.set_defaults(
        handler=_run_operations_migrate_phase_unbalance_results
    )

    operations_request_collection = operations_commands.add_parser(
        "request-collection",
        help="request desired continuous collection state without owning the runtime loop",
    )
    operations_request_collection.add_argument(
        "--workspace",
        type=Path,
        help="Operations workspace root; replaces --registry and --control-state",
    )
    operations_request_collection.add_argument(
        "--registry",
        type=Path,
        help="explicit registered-source JSON path (compatibility/internal mode)",
    )
    operations_request_collection.add_argument(
        "--control-state",
        type=Path,
        help="explicit desired collection-state SQLite path (compatibility/internal mode)",
    )
    operations_request_collection.add_argument(
        "--source-id",
        required=True,
        help="registered OPC UA source ID",
    )
    operations_request_collection.add_argument(
        "--state",
        choices=("running", "stopped"),
        required=True,
        help="desired continuous collection state",
    )
    operations_request_collection.set_defaults(handler=_run_operations_request_collection)

    operations_collection_service = operations_commands.add_parser(
        "run-collection-service",
        help="run the independent continuous OPC UA collection service",
    )
    operations_collection_service.add_argument(
        "--workspace",
        type=Path,
        help="Operations workspace root; replaces individual state/history path flags",
    )
    operations_collection_service.add_argument("--registry", type=Path)
    operations_collection_service.add_argument("--control-state", type=Path)
    operations_collection_service.add_argument("--spool-state", type=Path)
    operations_collection_service.add_argument("--telemetry-state", type=Path)
    operations_collection_service.add_argument("--window-state", type=Path)
    operations_collection_service.add_argument("--ducklake-catalog", type=Path)
    operations_collection_service.add_argument("--ducklake-data", type=Path)
    operations_collection_service.add_argument(
        "--reconcile-interval-seconds",
        type=float,
        default=0.5,
        help="positive desired-state reconciliation interval in seconds (default: 0.5)",
    )
    operations_collection_service.add_argument(
        "--window-duration-seconds",
        type=float,
        default=60.0,
        help="fixed aligned observation-window length in seconds (default: 60)",
    )
    operations_collection_service.add_argument(
        "--allowed-lateness-seconds",
        type=float,
        default=5.0,
        help="watermark lateness before a window finalizes, in seconds (default: 5)",
    )
    operations_collection_service.set_defaults(handler=_run_operations_collection_service)

    operations_collection_service.add_argument(
        "--subscription-queue-maxsize",
        type=int,
        help=(
            "per-subscription notification queue size (default 4096); smaller values are "
            "for fault-harness overflow scenarios"
        ),
    )
    operations_collection_service.add_argument(
        "--pipeline-metrics",
        type=Path,
        help=(
            "opt-in diagnostics: append per-10s JSON lines of queue depth, arrival/dequeue "
            "lag, spool/telemetry/commit latency and event-loop lag to this path"
        ),
    )
    operations_window_analysis = operations_commands.add_parser(
        "run-window-analysis",
        help="analyze each finalized live observation window once (three-phase unbalance)",
    )
    operations_window_analysis.add_argument(
        "--workspace",
        type=Path,
        help="Operations workspace root; replaces window/analysis/ledger/runtime state paths",
    )
    operations_window_analysis.add_argument(
        "--window-state", type=Path, help="explicit finalized window SQLite path"
    )
    operations_window_analysis.add_argument(
        "--analysis-state",
        type=Path,
        help="explicit phase unbalance result SQLite path (shared with Operations)",
    )
    operations_window_analysis.add_argument(
        "--ledger-state",
        type=Path,
        help="explicit SQLite skip ledger and incremental analysis cursor path",
    )
    operations_window_analysis.add_argument(
        "--runtime-status",
        type=Path,
        default=None,
        help=(
            "explicit analysis-runner runtime telemetry JSON path; defaults from --workspace "
            "or beside --analysis-state as <stem>-runtime.json"
        ),
    )
    operations_window_analysis.add_argument(
        "--interval-seconds", type=float, default=5.0, help="poll interval (default: 5)"
    )
    operations_window_analysis.add_argument(
        "--once", action="store_true", help="analyze pending windows once and exit"
    )
    operations_window_analysis.add_argument(
        "--alignment",
        choices=("strict", "bounded-previous"),
        default="strict",
        help="temporal alignment policy (ADR-0009); default strict",
    )
    operations_window_analysis.add_argument(
        "--max-carry-age-seconds",
        type=float,
        help="bounded-previous only: oldest earlier value that may be carried",
    )
    operations_window_analysis.add_argument(
        "--alignment-basis",
        help="bounded-previous only: device/measurement fact justifying the carry age",
    )
    operations_window_analysis.set_defaults(handler=_run_operations_window_analysis)

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
    experiment_inspect = experiment_commands.add_parser(
        "inspect",
        help="show a read-only pipeline summary for a supported result artifact",
    )
    experiment_inspect.add_argument(
        "result",
        type=Path,
        help="existing XJTU holdout or IMS cross-test result JSON",
    )
    experiment_inspect.set_defaults(handler=_run_experiment_inspect)

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

    experiment_cross_test = experiment_commands.add_parser(
        "cross-test",
        help="run the fixed IMS Set 2 to Set 3 one-time cross-test evaluation",
    )
    experiment_cross_test.add_argument("dataset_id")
    experiment_cross_test.add_argument(
        "--source",
        type=Path,
        required=True,
        help="prepared local dataset root consumed by the IMS Domain Adapter",
    )
    experiment_cross_test.add_argument(
        "--output",
        type=Path,
        required=True,
        help="destination for the generated IMS cross-test result JSON",
    )
    experiment_cross_test.add_argument(
        "--code-revision",
        required=True,
        help="full Git commit SHA for the exact execution code",
    )
    experiment_cross_test.set_defaults(handler=_run_experiment_cross_test)

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

    experiment_lstm_development = experiment_commands.add_parser(
        "lstm-development",
        help="run the frozen XJTU LSTM retrospective development evaluation",
    )
    experiment_lstm_development.add_argument("dataset_id")
    experiment_lstm_development.add_argument(
        "--source",
        type=Path,
        required=True,
        help="prepared local XJTU-SY source consumed by the Domain Adapter",
    )
    experiment_lstm_development.add_argument(
        "--output",
        type=Path,
        required=True,
        help="destination for the generated LSTM development result JSON",
    )
    experiment_lstm_development.add_argument(
        "--code-revision",
        required=True,
        help="full Git commit SHA for the exact execution code",
    )
    experiment_lstm_development.set_defaults(handler=_run_experiment_lstm_development)

    experiment_rul_baseline_validation = experiment_commands.add_parser(
        "rul-baseline-validation",
        help="run frozen XJTU age-only and feature-Ridge RUL validation baselines",
    )
    experiment_rul_baseline_validation.add_argument("dataset_id")
    experiment_rul_baseline_validation.add_argument(
        "--source",
        type=Path,
        required=True,
        help="prepared local XJTU-SY source consumed by the Domain Adapter",
    )
    experiment_rul_baseline_validation.add_argument(
        "--output",
        type=Path,
        required=True,
        help="destination for the generated RUL baseline validation result JSON",
    )
    experiment_rul_baseline_validation.add_argument(
        "--code-revision",
        required=True,
        help="full Git commit SHA; must match current clean tracked Git checkout HEAD",
    )
    experiment_rul_baseline_validation.set_defaults(handler=_run_experiment_rul_baseline_validation)

    experiment_rul_validation = experiment_commands.add_parser(
        "rul-validation",
        help="run frozen XJTU age, Ridge, and temporal-LSTM RUL validation comparison",
    )
    experiment_rul_validation.add_argument("dataset_id")
    experiment_rul_validation.add_argument(
        "--source",
        type=Path,
        required=True,
        help="prepared local XJTU-SY source consumed by the Domain Adapter",
    )
    experiment_rul_validation.add_argument(
        "--output",
        type=Path,
        required=True,
        help="destination for the generated three-model RUL validation result JSON",
    )
    experiment_rul_validation.add_argument(
        "--code-revision",
        required=True,
        help="full Git commit SHA; must match current clean tracked Git checkout HEAD",
    )
    experiment_rul_validation.set_defaults(handler=_run_experiment_rul_validation)

    experiment_rul_benchmark = experiment_commands.add_parser(
        "rul-benchmark",
        help="run frozen validation-selected XJTU LSTM on the fold-1 held-out benchmark",
    )
    experiment_rul_benchmark.add_argument("dataset_id")
    experiment_rul_benchmark.add_argument(
        "--source",
        type=Path,
        required=True,
        help="prepared local XJTU-SY source consumed by the Domain Adapter",
    )
    experiment_rul_benchmark.add_argument(
        "--output",
        type=Path,
        required=True,
        help="destination for the generated frozen RUL benchmark result JSON",
    )
    experiment_rul_benchmark.add_argument(
        "--code-revision",
        required=True,
        help="full Git commit SHA; must match current clean tracked Git checkout HEAD",
    )
    experiment_rul_benchmark.set_defaults(handler=_run_experiment_rul_benchmark)

    experiment_mimii_development = experiment_commands.add_parser(
        "mimii-development",
        help="run the frozen MIMII DUE sections 00-02 development evaluation",
    )
    experiment_mimii_development.add_argument("dataset_id")
    experiment_mimii_development.add_argument(
        "--source",
        type=Path,
        required=True,
        help="prepared local MIMII DUE source consumed by the Domain Adapter",
    )
    experiment_mimii_development.add_argument(
        "--output",
        type=Path,
        required=True,
        help="destination for the generated MIMII development result JSON",
    )
    experiment_mimii_development.add_argument(
        "--code-revision",
        required=True,
        help="full Git commit SHA; must match current clean tracked Git checkout HEAD",
    )
    experiment_mimii_development.set_defaults(handler=_run_experiment_mimii_development)

    experiment_mimii_external = experiment_commands.add_parser(
        "mimii-external-score",
        help="score MIMII DUE evaluation sections 03-05 without reading any condition label",
    )
    experiment_mimii_external.add_argument("dataset_id")
    experiment_mimii_external.add_argument(
        "--source",
        type=Path,
        required=True,
        help="prepared local MIMII DUE source that provides sections 03-05 normal train",
    )
    experiment_mimii_external.add_argument(
        "--evaluation-source",
        type=Path,
        required=True,
        help="prepared local MIMII DUE evaluation-test audio root (label-free filenames)",
    )
    experiment_mimii_external.add_argument(
        "--output",
        type=Path,
        required=True,
        help="destination for the immutable label-blind score artifact JSON",
    )
    experiment_mimii_external.add_argument(
        "--code-revision",
        required=True,
        help="full Git commit SHA; must match current clean tracked Git checkout HEAD",
    )
    experiment_mimii_external.set_defaults(handler=_run_experiment_mimii_external_score)

    experiment_mimii_evaluate = experiment_commands.add_parser(
        "mimii-external-evaluate",
        help="join ground truth with a fixed MIMII score artifact and compute external evidence",
    )
    experiment_mimii_evaluate.add_argument("dataset_id")
    experiment_mimii_evaluate.add_argument(
        "--score-artifact",
        type=Path,
        required=True,
        help="immutable label-blind score artifact produced by mimii-external-score",
    )
    experiment_mimii_evaluate.add_argument(
        "--ground-truth-dir",
        type=Path,
        required=True,
        help="local directory holding the evaluation ground-truth CSV files",
    )
    experiment_mimii_evaluate.add_argument(
        "--output",
        type=Path,
        required=True,
        help="destination for the generated external evaluation result JSON",
    )
    experiment_mimii_evaluate.add_argument(
        "--code-revision",
        required=True,
        help="full Git commit SHA; must match current clean tracked Git checkout HEAD",
    )
    experiment_mimii_evaluate.set_defaults(handler=_run_experiment_mimii_external_evaluate)

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
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    python_supported = sys.version_info[:2] == (3, 14)
    data_root = default_data_root()
    checkout_detected = (
        Path("pyproject.toml").is_file() and Path("apps/analysis_explorer.py").is_file()
    )
    research_ui_installed = importlib.util.find_spec("marimo") is not None
    deep_learning_installed = importlib.util.find_spec("torch") is not None

    print(f"industrial-phm {__version__}")
    print(f"python: {python_version} ({'supported' if python_supported else 'unsupported'})")
    print(f"project checkout: {'detected' if checkout_detected else 'not detected'}")
    print(f"data root: {data_root} ({'present' if data_root.exists() else 'not created'})")
    print(f"registered datasets: {len(list_datasets())}")
    print(f"research UI runtime: {'installed' if research_ui_installed else 'not installed'}")
    print(f"deep-learning runtime: {'installed' if deep_learning_installed else 'not installed'}")
    print("next:")
    if checkout_detected:
        print(
            "  open recorded example: "
            "uv run --locked --group research marimo run apps/analysis_explorer.py"
        )
    else:
        print("  run this command from an industrial-phm-framework repository checkout")
    return 0
