"""Operational CLI taxonomy by user responsibility."""

from __future__ import annotations

import argparse
from pathlib import Path

from industrial_phm.application.history_retention import DEFAULT_LIVE_RETENTION
from industrial_phm.commands.operations import (
    _run_operations_backfill_source,
    _run_operations_backup,
    _run_operations_collection_service,
    _run_operations_compact_history,
    _run_operations_flush_history,
    _run_operations_init,
    _run_operations_logs,
    _run_operations_poll_source,
    _run_operations_preflight,
    _run_operations_request_collection,
    _run_operations_restore,
    _run_operations_retain_history,
    _run_operations_start,
    _run_operations_status,
    _run_operations_stop,
    _run_operations_up,
    _run_operations_window_analysis,
)


def add_operational_command_groups(
    subcommands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Add user, maintenance, validation, and internal operational surfaces."""
    _add_operations_commands(subcommands)
    _add_maintenance_commands(subcommands)
    _add_validate_commands(subcommands)
    _add_internal_commands(subcommands)


def _add_operations_commands(
    subcommands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    operations = subcommands.add_parser(
        "operations",
        help="operate one local PHM node without internal storage/process wiring",
    )
    commands = operations.add_subparsers(dest="operations_command", required=True)

    up = commands.add_parser(
        "up",
        help="prepare or reopen one local Operations workspace and run it",
    )
    up.add_argument("workspace", type=Path, help="local Operations workspace root")
    up.set_defaults(handler=_run_operations_up)

    init = commands.add_parser(
        "init",
        help="initialize or validate one local Operations workspace",
    )
    init.add_argument("workspace", type=Path, help="local Operations workspace root")
    init.set_defaults(handler=_run_operations_init)

    start = commands.add_parser(
        "start",
        help="run the local Operations service lifecycle in the foreground",
    )
    start.add_argument(
        "workspace",
        type=Path,
        help="initialized local Operations workspace root",
    )
    start.set_defaults(handler=_run_operations_start)

    status = commands.add_parser(
        "status",
        help="show local supervisor identity and component readiness",
    )
    status.add_argument(
        "workspace",
        type=Path,
        help="initialized local Operations workspace root",
    )
    status.set_defaults(handler=_run_operations_status)

    logs = commands.add_parser(
        "logs",
        help="show bounded tails from local Operations component logs",
    )
    logs.add_argument(
        "workspace",
        type=Path,
        help="initialized local Operations workspace root",
    )
    logs.add_argument(
        "--component",
        choices=("collection", "analysis", "ui"),
        help="optional single component; default shows all managed components",
    )
    logs.add_argument(
        "--lines",
        type=int,
        default=100,
        help="lines per component to show, between 1 and 10000 (default: 100)",
    )
    logs.set_defaults(handler=_run_operations_logs)

    stop = commands.add_parser(
        "stop",
        help="request graceful shutdown of the live local Operations supervisor",
    )
    stop.add_argument(
        "workspace",
        type=Path,
        help="initialized local Operations workspace root",
    )
    stop.set_defaults(handler=_run_operations_stop)


def _add_maintenance_commands(
    subcommands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    maintenance = subcommands.add_parser(
        "maintenance",
        help="perform explicit offline/recovery/history maintenance",
    )
    commands = maintenance.add_subparsers(dest="maintenance_command", required=True)

    backup = commands.add_parser(
        "backup",
        help="create an integrity-checked offline backup of a stopped workspace",
    )
    backup.add_argument(
        "workspace",
        type=Path,
        help="initialized local Operations workspace root",
    )
    backup.add_argument(
        "destination",
        type=Path,
        help="new backup directory; must not already exist or be inside the workspace",
    )
    backup.set_defaults(handler=_run_operations_backup)

    restore = commands.add_parser(
        "restore",
        help="restore a verified backup into a new workspace root",
    )
    restore.add_argument(
        "backup",
        type=Path,
        help="Operations backup directory containing manifest.json and payload/",
    )
    restore.add_argument(
        "workspace",
        type=Path,
        help="new Operations workspace root; must not already exist",
    )
    restore.set_defaults(handler=_run_operations_restore)

    history = commands.add_parser(
        "history",
        help="perform explicit Asset History backfill/flush/compaction maintenance",
    )
    history_commands = history.add_subparsers(dest="history_command", required=True)

    backfill = history_commands.add_parser(
        "backfill",
        help="backfill one registered timestamped FILE source into DuckLake Asset History",
    )
    backfill.add_argument(
        "--registry",
        type=Path,
        required=True,
        help="persistent registered-source control-plane JSON path",
    )
    backfill.add_argument(
        "--source-id",
        required=True,
        help="registered FILE source ID",
    )
    backfill.add_argument(
        "--ducklake-catalog",
        type=Path,
        required=True,
        help="DuckLake SQLite catalog path",
    )
    backfill.add_argument(
        "--ducklake-data",
        type=Path,
        required=True,
        help="DuckLake managed Parquet data directory",
    )
    backfill.set_defaults(handler=_run_operations_backfill_source)

    flush = history_commands.add_parser(
        "flush",
        help="move catalog-inlined DuckLake Asset History rows to Parquet",
    )
    flush.add_argument(
        "--ducklake-catalog",
        type=Path,
        required=True,
        help="DuckLake SQLite catalog path",
    )
    flush.add_argument(
        "--ducklake-data",
        type=Path,
        required=True,
        help="DuckLake managed Parquet data directory",
    )
    flush.set_defaults(handler=_run_operations_flush_history)

    compact = history_commands.add_parser(
        "compact",
        help="merge active small DuckLake Parquet files without expiring snapshots",
    )
    compact.add_argument(
        "--ducklake-catalog",
        type=Path,
        required=True,
        help="DuckLake SQLite catalog path",
    )
    compact.add_argument(
        "--ducklake-data",
        type=Path,
        required=True,
        help="DuckLake managed Parquet data directory",
    )
    compact.add_argument(
        "--target-file-size-bytes",
        type=int,
        required=True,
        help="persistent DuckLake target_file_size for outputs and future writes",
    )
    compact.add_argument(
        "--max-compacted-files",
        type=int,
        required=True,
        help="maximum DuckLake compaction output operations per table",
    )
    compact.add_argument(
        "--min-file-size-bytes",
        type=int,
        default=None,
        help="optional minimum active data-file size eligible for compaction",
    )
    compact.add_argument(
        "--max-file-size-bytes",
        type=int,
        default=None,
        help="optional maximum active data-file size eligible for compaction",
    )
    compact.set_defaults(handler=_run_operations_compact_history)

    retain = history_commands.add_parser(
        "retain",
        help=(
            "delete live OPC UA evidence and finalized windows older than the retention "
            "period, except open-review evidence, and reclaim their storage"
        ),
    )
    retain.add_argument(
        "workspace",
        type=Path,
        help="initialized local Operations workspace root",
    )
    retain.add_argument(
        "--retention-days",
        type=int,
        default=DEFAULT_LIVE_RETENTION.days,
        help="keep live evidence whose event time is within this many days (default: %(default)s)",
    )
    retain.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would be deleted without changing anything",
    )
    retain.set_defaults(handler=_run_operations_retain_history)


def _add_validate_commands(
    subcommands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    validate = subcommands.add_parser(
        "validate",
        help="run explicit operational/deployment validation gates",
    )
    commands = validate.add_subparsers(dest="validate_command", required=True)

    deployment = commands.add_parser(
        "deployment",
        help="validate service-manager startup requirements as the current service user",
    )
    deployment.add_argument(
        "workspace",
        type=Path,
        help="absolute initialized Operations workspace root for long-running deployment",
    )
    deployment.set_defaults(handler=_run_operations_preflight)


def _add_internal_commands(
    subcommands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    internal = subcommands.add_parser(
        "internal",
        help="internal service/source plumbing; not the normal user lifecycle",
    )
    commands = internal.add_subparsers(dest="internal_command", required=True)

    poll_source = commands.add_parser(
        "poll-source",
        help="poll one ACTIVE registered FILE or OPC UA source until stopped",
    )
    poll_source.add_argument(
        "--registry",
        type=Path,
        required=True,
        help="persistent registered-source control-plane JSON path",
    )
    poll_source.add_argument(
        "--runtime-state",
        type=Path,
        required=True,
        help="separate persistent latest runtime-evidence JSON path",
    )
    poll_source.add_argument("--source-id", required=True, help="registered source ID to poll")
    poll_source.add_argument(
        "--interval-seconds",
        type=float,
        default=5.0,
        help="positive polling interval in seconds (default: 5)",
    )
    poll_source.add_argument(
        "--max-cycles",
        type=int,
        default=None,
        help="optional positive cycle limit; omit to run until stop/failure/Ctrl+C",
    )
    poll_source.set_defaults(handler=_run_operations_poll_source)

    request_collection = commands.add_parser(
        "request-collection",
        help="request desired collection state without owning the runtime loop",
    )
    request_collection.add_argument(
        "--workspace",
        type=Path,
        help="Operations workspace root; replaces --registry and --control-state",
    )
    request_collection.add_argument(
        "--registry",
        type=Path,
        help="explicit registered-source JSON path (internal/diagnostic mode)",
    )
    request_collection.add_argument(
        "--control-state",
        type=Path,
        help="explicit desired collection-state SQLite path (internal/diagnostic mode)",
    )
    request_collection.add_argument(
        "--source-id",
        required=True,
        help="registered OPC UA source ID",
    )
    request_collection.add_argument(
        "--state",
        choices=("running", "stopped"),
        required=True,
        help="desired continuous collection state",
    )
    request_collection.set_defaults(handler=_run_operations_request_collection)

    collection_service = commands.add_parser(
        "collection-service",
        help="run the independent continuous OPC UA collection service",
    )
    collection_service.add_argument(
        "--workspace",
        type=Path,
        help="Operations workspace root; replaces individual state/history path flags",
    )
    collection_service.add_argument("--registry", type=Path)
    collection_service.add_argument("--control-state", type=Path)
    collection_service.add_argument("--spool-state", type=Path)
    collection_service.add_argument("--telemetry-state", type=Path)
    collection_service.add_argument("--window-state", type=Path)
    collection_service.add_argument("--ducklake-catalog", type=Path)
    collection_service.add_argument("--ducklake-data", type=Path)
    collection_service.add_argument(
        "--reconcile-interval-seconds",
        type=float,
        default=0.5,
        help="positive desired-state reconciliation interval in seconds (default: 0.5)",
    )
    collection_service.add_argument(
        "--window-duration-seconds",
        type=float,
        default=60.0,
        help="fixed aligned observation-window length in seconds (default: 60)",
    )
    collection_service.add_argument(
        "--allowed-lateness-seconds",
        type=float,
        default=5.0,
        help="watermark lateness before a window finalizes, in seconds (default: 5)",
    )
    collection_service.add_argument(
        "--subscription-queue-maxsize",
        type=int,
        help=(
            "per-subscription notification queue size (default 4096); smaller values are "
            "for fault-harness overflow scenarios"
        ),
    )
    collection_service.add_argument(
        "--pipeline-metrics",
        type=Path,
        help=(
            "opt-in diagnostics: append per-10s JSON lines of queue depth, arrival/dequeue "
            "lag, spool/telemetry/commit latency and event-loop lag to this path"
        ),
    )
    collection_service.set_defaults(handler=_run_operations_collection_service)

    window_analysis = commands.add_parser(
        "window-analysis",
        help="analyze each finalized live observation window once (three-phase unbalance)",
    )
    window_analysis.add_argument(
        "--workspace",
        type=Path,
        help="Operations workspace root; replaces window/analysis/ledger/runtime state paths",
    )
    window_analysis.add_argument(
        "--window-state",
        type=Path,
        help="explicit finalized window SQLite path",
    )
    window_analysis.add_argument(
        "--analysis-state",
        type=Path,
        help="explicit phase unbalance result SQLite path (shared with Operations)",
    )
    window_analysis.add_argument(
        "--ledger-state",
        type=Path,
        help="explicit SQLite skip ledger and incremental analysis cursor path",
    )
    window_analysis.add_argument(
        "--runtime-status",
        type=Path,
        default=None,
        help=(
            "explicit analysis-runner runtime telemetry JSON path; defaults from --workspace "
            "or beside --analysis-state as <stem>-runtime.json"
        ),
    )
    window_analysis.add_argument(
        "--interval-seconds",
        type=float,
        default=5.0,
        help="poll interval (default: 5)",
    )
    window_analysis.add_argument(
        "--once",
        action="store_true",
        help="analyze pending windows once and exit",
    )
    window_analysis.add_argument(
        "--alignment",
        choices=("strict", "bounded-previous"),
        default="strict",
        help="temporal alignment policy (ADR-0009); default strict",
    )
    window_analysis.add_argument(
        "--max-carry-age-seconds",
        type=float,
        help="bounded-previous only: oldest earlier value that may be carried",
    )
    window_analysis.add_argument(
        "--alignment-basis",
        help="bounded-previous only: device/measurement fact justifying the carry age",
    )
    window_analysis.set_defaults(handler=_run_operations_window_analysis)
