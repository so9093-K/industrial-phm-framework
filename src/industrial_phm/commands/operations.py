"""Operational source-runtime command handlers."""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from industrial_phm.application import (
    AlignmentPolicyKind,
    CollectionDesiredState,
    JsonSourceRepository,
    JsonSourceRuntimeRepository,
    JsonWindowAnalysisRuntimeRepository,
    ObservationWindowCoordinatorPolicy,
    PhaseUnbalanceConfig,
    SourcePollingPolicy,
    SourceRuntimeCycleState,
    SqliteObservationWindowRepository,
    SqlitePhaseUnbalanceRepository,
    SqliteWindowAnalysisLedger,
    TemporalAlignmentPolicy,
    analyze_finalized_windows_incremental,
    backfill_registered_file_source,
    poll_registered_source,
    request_collection_state,
    validate_distinct_source_state_paths,
)
from industrial_phm.application.opcua_persistent import OpcUaPersistentSessionPolicy
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime import (
    CollectionServicePolicy,
    OperationsComponentKind,
    OperationsProcessEvidence,
    OperationsSupervisorStateKind,
    OperationsWorkspace,
    SqliteAcquisitionSpool,
    SqliteAcquisitionSpoolConfig,
    SqliteAcquisitionTelemetryRepository,
    SqliteCollectionControlRepository,
    build_operations_runtime_plan,
    create_operations_backup,
    initialize_operations_workspace,
    inspect_operations_deployment,
    inspect_operations_runtime_status,
    load_operations_runtime_config,
    request_operations_supervisor_stop,
    restore_operations_backup,
    run_collection_service,
    run_operations_supervisor,
    tail_operations_component_log,
)
from industrial_phm.runtime.operations_retention import apply_operations_retention
from industrial_phm.runtime.pipeline_metrics import PipelineMetrics


def _run_operations_init(args: argparse.Namespace) -> int:
    """Initialize or validate one local Operations workspace."""
    workspace = OperationsWorkspace(args.workspace)
    try:
        result = initialize_operations_workspace(workspace)
    except (OSError, ValueError) as error:
        print(f"Operations workspace initialization failed: {error}", file=sys.stderr)
        return 1

    state = "created" if result.created else "existing"
    print(
        f"workspace={result.workspace.root} config={result.workspace.config_path} "
        f"schema={result.config.schema} state={state}"
    )
    return 0


def _run_operations_backup(args: argparse.Namespace) -> int:
    """Create one integrity-checked offline backup of a stopped workspace."""
    workspace = OperationsWorkspace(args.workspace)
    try:
        result = create_operations_backup(workspace, args.destination)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Operations backup failed: {error}", file=sys.stderr)
        return 1

    print(
        f"workspace={workspace.root} backup={result.backup_path} "
        f"files={len(result.manifest.files)} bytes={result.manifest.total_bytes} "
        f"schema={result.manifest.schema}"
    )
    return 0


def _run_operations_preflight(args: argparse.Namespace) -> int:
    """Validate service-manager startup preconditions as the current service user."""
    workspace = OperationsWorkspace(args.workspace)
    report = inspect_operations_deployment(workspace)

    print(f"workspace={workspace.root} deployment_ready={'yes' if report.ready else 'no'}")
    for check in report.checks:
        print(f"{check.state.value.upper()} {check.name}: {check.detail}")
    return 0 if report.ready else 1


def _run_operations_restore(args: argparse.Namespace) -> int:
    """Restore one verified backup into a new workspace root."""
    workspace = OperationsWorkspace(args.workspace)
    try:
        result = restore_operations_backup(args.backup, workspace)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Operations restore failed: {error}", file=sys.stderr)
        return 1

    print(
        f"workspace={workspace.root} backup={result.backup_path} "
        f"state=restored files={len(result.manifest.files)} "
        f"bytes={result.manifest.total_bytes}"
    )
    return 0


def _run_operations_start(args: argparse.Namespace) -> int:
    """Run the workspace-owned local node lifecycle in the foreground."""
    workspace = OperationsWorkspace(args.workspace)
    try:
        config = load_operations_runtime_config(workspace.config_path)
        plan = build_operations_runtime_plan(workspace, config)
        print(
            f"workspace={workspace.root} operations_url={plan.ui_url} mode=foreground",
            flush=True,
        )
        result = run_operations_supervisor(plan)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Operations runtime start failed: {error}", file=sys.stderr)
        return 1

    if result.state.failure is not None:
        print(f"Operations runtime failed: {result.state.failure}", file=sys.stderr)
    if result.state.state == OperationsSupervisorStateKind.STOPPED:
        return 0
    return result.exit_code


def _run_operations_logs(args: argparse.Namespace) -> int:
    """Print bounded tails from workspace-owned component logs."""
    workspace = OperationsWorkspace(args.workspace)
    if isinstance(args.lines, bool) or not 1 <= args.lines <= 10_000:
        print("Operations logs failed: --lines must be between 1 and 10000", file=sys.stderr)
        return 1
    try:
        config = load_operations_runtime_config(workspace.config_path)
        plan = build_operations_runtime_plan(workspace, config)
        kinds = (
            (OperationsComponentKind(args.component),)
            if args.component is not None
            else tuple(OperationsComponentKind)
        )
    except (OSError, ValueError) as error:
        print(f"Operations logs failed: {error}", file=sys.stderr)
        return 1

    available = 0
    for index, kind in enumerate(kinds):
        if index:
            print()
        print(f"== {kind.value} ==")
        try:
            lines = tail_operations_component_log(plan, kind, lines=args.lines)
        except FileNotFoundError:
            print("[log unavailable: component has not written a log yet]")
            continue
        except (LookupError, OSError, ValueError) as error:
            print(f"[log read failed: {error}]", file=sys.stderr)
            continue
        available += 1
        if not lines:
            print("[log is empty]")
            continue
        for line in lines:
            print(line)

    return 0 if available else 2


def _run_operations_stop(args: argparse.Namespace) -> int:
    """Request graceful shutdown of the live workspace supervisor."""
    workspace = OperationsWorkspace(args.workspace)
    try:
        pid = request_operations_supervisor_stop(workspace)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Operations runtime stop failed: {error}", file=sys.stderr)
        return 1

    print(f"workspace={workspace.root} stop=requested supervisor_pid={pid}")
    return 0


def _run_operations_status(args: argparse.Namespace) -> int:
    """Report process identity and component-owned runtime readiness separately."""
    workspace = OperationsWorkspace(args.workspace)
    try:
        status = inspect_operations_runtime_status(workspace)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Operations runtime status failed: {error}", file=sys.stderr)
        return 1

    print(f"workspace={workspace.root} ready={'yes' if status.ready else 'no'}")
    supervisor = status.supervisor
    print(
        "supervisor "
        f"condition={supervisor.condition.value} "
        f"process={_operations_process_value(supervisor.process)} "
        f"heartbeat={_operations_time_value(supervisor.heartbeat_at)} "
        f"detail={supervisor.detail}"
    )
    for component in status.components:
        print(
            f"{component.kind.value} "
            f"condition={component.condition.value} "
            f"process={_operations_process_value(component.process)} "
            f"runtime={component.runtime_state or 'unavailable'} "
            f"heartbeat={_operations_time_value(component.heartbeat_at)} "
            f"detail={component.detail}"
        )
    return 0 if status.ready else 2


def _operations_process_value(process: OperationsProcessEvidence | None) -> str:
    if process is None:
        return "unavailable"
    return_code = "none" if process.return_code is None else str(process.return_code)
    return f"pid:{process.pid},alive:{'yes' if process.alive else 'no'},return_code:{return_code}"


def _operations_time_value(value: datetime | None) -> str:
    return "unavailable" if value is None else value.isoformat()


def _run_operations_poll_source(args: argparse.Namespace) -> int:
    registry_path = args.registry
    runtime_path = args.runtime_state

    try:
        validate_distinct_source_state_paths(registry_path, runtime_path)
        source_repository = JsonSourceRepository(registry_path)
        runtime_repository = JsonSourceRuntimeRepository(runtime_path)
        policy = SourcePollingPolicy(
            interval_seconds=args.interval_seconds,
            max_cycles=args.max_cycles,
        )
        results = poll_registered_source(
            source_repository,
            source_repository,
            runtime_repository,
            args.source_id,
            policy,
        )

        last_state: SourceRuntimeCycleState | None = None
        for cycle_number, result in enumerate(results, start=1):
            last_state = result.state
            if result.state == SourceRuntimeCycleState.SUCCEEDED:
                received = result.received
                if received is None:
                    print(
                        "runtime polling invariant violation: succeeded cycle has no receipt",
                        file=sys.stderr,
                    )
                    return 1
                print(
                    f"cycle {cycle_number}: succeeded "
                    f"received_at={received.receipt.received_at.isoformat()}"
                )
            elif result.state == SourceRuntimeCycleState.SKIPPED:
                print(
                    f"cycle {cycle_number}: skipped "
                    f"reason={result.message or 'source is not active'}",
                    file=sys.stderr,
                )
            else:
                scope = "unknown" if result.failure_scope is None else result.failure_scope.value
                print(
                    f"cycle {cycle_number}: failed scope={scope} "
                    f"reason={result.message or 'runtime cycle failed'}",
                    file=sys.stderr,
                )
    except KeyboardInterrupt:
        print("source polling interrupted by user", file=sys.stderr)
        return 130
    except (LookupError, OSError, ValueError) as error:
        print(f"source polling failed: {error}", file=sys.stderr)
        return 1

    if last_state is None:
        print("source polling produced no runtime cycle", file=sys.stderr)
        return 1
    if last_state == SourceRuntimeCycleState.SUCCEEDED:
        return 0
    if last_state == SourceRuntimeCycleState.SKIPPED:
        return 2
    return 1


def _run_operations_backfill_source(args: argparse.Namespace) -> int:
    try:
        source_repository = JsonSourceRepository(args.registry)
        history = DuckLakeAssetHistory(
            DuckLakeAssetHistoryConfig(
                catalog_path=args.ducklake_catalog,
                data_path=args.ducklake_data,
            )
        )
        result = backfill_registered_file_source(
            source_repository,
            history,
            args.source_id,
        )
    except (LookupError, OSError, RuntimeError, ValueError) as error:
        print(f"historical backfill failed: {error}", file=sys.stderr)
        return 1

    for segment in result.segments:
        disposition = "recovered" if segment.recovered_existing_commit else "committed"
        print(
            f"segment={segment.source_file} batch={segment.batch_id} "
            f"events={segment.event_count} snapshot={segment.commit.snapshot_id} "
            f"state={disposition}"
        )
    print(
        f"source={result.source_id} asset={result.asset_id} events={result.event_count} "
        f"history_snapshot={result.history_snapshot_id} "
        f"input_start={result.input_reference.start_at.isoformat()} "
        f"input_end={result.input_reference.end_at.isoformat()}"
    )
    return 0


def _run_operations_retain_history(args: argparse.Namespace) -> int:
    """Apply the live-evidence retention policy to one workspace."""
    workspace = OperationsWorkspace(args.workspace)
    if isinstance(args.retention_days, bool) or args.retention_days < 1:
        print("history retention failed: --retention-days must be at least 1", file=sys.stderr)
        return 1
    try:
        result = apply_operations_retention(
            workspace,
            now=datetime.now(UTC),
            retention=timedelta(days=args.retention_days),
            dry_run=args.dry_run,
        )
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        print(f"history retention failed: {error}", file=sys.stderr)
        return 1

    protection = result.protection
    print(
        f"workspace={workspace.root} cutoff={result.cutoff.isoformat()} "
        f"dry_run={'yes' if result.dry_run else 'no'} "
        f"protected_ranges={len(protection.ranges)} "
        f"protected_windows={len(protection.window_ids)} "
        f"protected_snapshots={len(protection.snapshot_ids)}"
    )
    windows = result.windows
    if windows is not None:
        print(
            f"windows_deleted={windows.deleted_window_count} "
            f"skipped_outcomes_deleted={windows.deleted_skipped_outcome_count} "
            f"windows_kept_protected={windows.protected_window_count} "
            f"windows_kept_unanalyzed={windows.unanalyzed_window_count}"
        )
    history = result.history
    if history is not None:
        before, after = history.storage_before, history.storage_after
        print(
            f"observations_deleted={history.deleted_observation_count} "
            f"measurements_deleted={history.deleted_measurement_count} "
            f"batches_deleted={history.deleted_batch_count} "
            f"observations_kept_protected={history.protected_observation_count} "
            f"snapshots_expired={history.expired_snapshot_count} "
            f"protected_snapshots_missing={len(history.missing_protected_snapshot_ids)} "
            f"files_removed={history.removed_file_count}"
        )
        print(
            f"physical_files_before={before.physical_parquet_file_count} "
            f"physical_files_after={after.physical_parquet_file_count} "
            f"physical_bytes_before={before.physical_parquet_bytes} "
            f"physical_bytes_after={after.physical_parquet_bytes}"
        )
    return 0


def _run_operations_compact_history(args: argparse.Namespace) -> int:
    """Run explicit bounded DuckLake compaction without expiring snapshots."""
    try:
        history = DuckLakeAssetHistory(
            DuckLakeAssetHistoryConfig(
                catalog_path=args.ducklake_catalog,
                data_path=args.ducklake_data,
            )
        )
        fingerprint = history.runtime_fingerprint()
        result = history.compact_adjacent_files(
            max_compacted_files=args.max_compacted_files,
            target_file_size_bytes=args.target_file_size_bytes,
            min_file_size_bytes=args.min_file_size_bytes,
            max_file_size_bytes=args.max_file_size_bytes,
        )
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        print(f"history compaction failed: {error}", file=sys.stderr)
        return 1

    print(
        f"duckdb={fingerprint.duckdb_version} "
        f"ducklake={fingerprint.ducklake_extension_version or 'unknown'} "
        f"installed_from={fingerprint.ducklake_installed_from or 'unknown'}"
    )
    for table in result.tables:
        print(
            f"table={table.schema_name}.{table.table_name} "
            f"files_processed={table.files_processed} files_created={table.files_created}"
        )
    before = result.storage_before
    after = result.storage_after
    print(
        f"snapshot_before={result.snapshot_before} snapshot_after={result.snapshot_after} "
        f"active_files_before={before.active_data_file_count} "
        f"active_files_after={after.active_data_file_count} "
        f"scheduled_for_deletion_before={before.scheduled_for_deletion_count} "
        f"scheduled_for_deletion_after={after.scheduled_for_deletion_count} "
        f"physical_files_before={before.physical_parquet_file_count} "
        f"physical_files_after={after.physical_parquet_file_count} "
        f"target_file_size_bytes={result.target_file_size_bytes} "
        f"duration_seconds={result.duration_seconds:.6f}"
    )
    return 0


def _run_operations_flush_history(args: argparse.Namespace) -> int:
    try:
        history = DuckLakeAssetHistory(
            DuckLakeAssetHistoryConfig(
                catalog_path=args.ducklake_catalog,
                data_path=args.ducklake_data,
            )
        )
        result = history.flush_inlined_data()
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        print(f"history flush failed: {error}", file=sys.stderr)
        return 1

    for table, count in result.flushed_rows:
        print(f"table={table} flushed_rows={count}")
    print(f"flushed_rows={result.flushed_row_count} history_snapshot={result.snapshot_id}")
    return 0


def _run_operations_window_analysis(args: argparse.Namespace) -> int:
    """Analyze finalized live windows and publish independent runner runtime evidence."""
    try:
        workspace = _resolve_workspace_mode(
            args,
            required_explicit=("window_state", "analysis_state", "ledger_state"),
            all_explicit=("window_state", "analysis_state", "ledger_state", "runtime_status"),
        )
        if workspace is None:
            window_state = args.window_state
            analysis_state = args.analysis_state
            ledger_state = args.ledger_state
            runtime_path = args.runtime_status or analysis_state.with_name(
                f"{analysis_state.stem}-runtime.json"
            )
        else:
            window_state = workspace.window_state_path
            analysis_state = workspace.phase_unbalance_state_path
            ledger_state = workspace.analysis_ledger_path
            runtime_path = workspace.analysis_runtime_path
    except ValueError as error:
        print(f"window analysis failed: {error}", file=sys.stderr)
        return 1

    runtime = JsonWindowAnalysisRuntimeRepository(runtime_path)
    _try_record_window_analysis_runtime(runtime.record_start, datetime.now(UTC))
    try:
        if args.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        windows = SqliteObservationWindowRepository(window_state)
        results = SqlitePhaseUnbalanceRepository(analysis_state)
        ledger = SqliteWindowAnalysisLedger(ledger_state)
        config = PhaseUnbalanceConfig(alignment=_alignment_policy(args))
        while True:
            outcomes = analyze_finalized_windows_incremental(
                windows,
                results,
                ledger,
                config=config,
            )
            for outcome in outcomes:
                detail = outcome.analysis_run_id or outcome.reason
                print(
                    f"window={outcome.window_id} capability={outcome.capability_id} "
                    f"state={outcome.state.value} detail={detail}",
                    flush=True,
                )
            _try_record_window_analysis_runtime(
                runtime.record_cycle,
                outcomes,
                completed_at=datetime.now(UTC),
            )
            if args.once:
                _try_record_window_analysis_runtime(runtime.record_stop, datetime.now(UTC))
                return 0
            time.sleep(args.interval_seconds)
    except KeyboardInterrupt:
        _try_record_window_analysis_runtime(runtime.record_stop, datetime.now(UTC))
        print("window analysis interrupted by user", file=sys.stderr)
        return 130
    except (OSError, ValueError) as error:
        _try_record_window_analysis_runtime(
            runtime.record_failure,
            str(error),
            occurred_at=datetime.now(UTC),
        )
        print(f"window analysis failed: {error}", file=sys.stderr)
        return 1


def _try_record_window_analysis_runtime(
    callback: Callable[..., object],
    *args: object,
    **kwargs: object,
) -> None:
    """Keep telemetry failure separate from the analysis data-plane outcome."""
    try:
        callback(*args, **kwargs)
    except (OSError, ValueError) as error:
        print(f"window analysis runtime telemetry unavailable: {error}", file=sys.stderr)


def _alignment_policy(args: argparse.Namespace) -> TemporalAlignmentPolicy:
    if args.alignment == "strict":
        if args.max_carry_age_seconds is not None or args.alignment_basis is not None:
            raise ValueError("strict alignment takes no carry age or basis")
        return TemporalAlignmentPolicy()
    if args.max_carry_age_seconds is None:
        raise ValueError("bounded-previous alignment requires --max-carry-age-seconds")
    return TemporalAlignmentPolicy(
        AlignmentPolicyKind.BOUNDED_PREVIOUS,
        max_age=timedelta(seconds=args.max_carry_age_seconds),
        basis=args.alignment_basis,
    )


def _run_operations_request_collection(args: argparse.Namespace) -> int:
    try:
        workspace = _resolve_workspace_mode(
            args,
            required_explicit=("registry", "control_state"),
            all_explicit=("registry", "control_state"),
        )
        registry_path = args.registry if workspace is None else workspace.source_registry_path
        control_state_path = (
            args.control_state if workspace is None else workspace.collection_control_path
        )
        source_repository = JsonSourceRepository(registry_path)
        control_repository = SqliteCollectionControlRepository(control_state_path)
        desired_state = CollectionDesiredState(args.state)
        record = request_collection_state(
            source_repository,
            source_repository,
            control_repository,
            args.source_id,
            desired_state,
            requested_at=datetime.now(UTC),
        )
    except (LookupError, OSError, ValueError) as error:
        print(f"collection request failed: {error}", file=sys.stderr)
        return 1

    print(
        f"source={record.source_id} desired={record.desired_state.value} "
        f"generation={record.generation} requested_at={record.requested_at.isoformat()}"
    )
    return 0


def _run_operations_collection_service(args: argparse.Namespace) -> int:
    try:
        workspace = _resolve_workspace_mode(
            args,
            required_explicit=(
                "registry",
                "control_state",
                "spool_state",
                "telemetry_state",
                "window_state",
                "ducklake_catalog",
                "ducklake_data",
            ),
            all_explicit=(
                "registry",
                "control_state",
                "spool_state",
                "telemetry_state",
                "window_state",
                "ducklake_catalog",
                "ducklake_data",
            ),
        )
        if workspace is None:
            registry_path = args.registry
            control_state_path = args.control_state
            spool_state_path = args.spool_state
            telemetry_state_path = args.telemetry_state
            window_state_path = args.window_state
            ducklake_catalog_path = args.ducklake_catalog
            ducklake_data_path = args.ducklake_data
        else:
            registry_path = workspace.source_registry_path
            control_state_path = workspace.collection_control_path
            spool_state_path = workspace.acquisition_spool_path
            telemetry_state_path = workspace.acquisition_telemetry_path
            window_state_path = workspace.window_state_path
            ducklake_catalog_path = workspace.history_catalog_path
            ducklake_data_path = workspace.history_data_path

        _validate_collection_service_paths(
            registry=registry_path,
            control_state=control_state_path,
            spool_state=spool_state_path,
            telemetry_state=telemetry_state_path,
            window_state=window_state_path,
            ducklake_catalog=ducklake_catalog_path,
            ducklake_data=ducklake_data_path,
        )
        source_repository = JsonSourceRepository(registry_path)
        control_repository = SqliteCollectionControlRepository(control_state_path)
        spool = SqliteAcquisitionSpool(SqliteAcquisitionSpoolConfig(path=spool_state_path))
        telemetry = SqliteAcquisitionTelemetryRepository(telemetry_state_path)
        history = DuckLakeAssetHistory(
            DuckLakeAssetHistoryConfig(
                catalog_path=ducklake_catalog_path,
                data_path=ducklake_data_path,
            )
        )
        window_repository = SqliteObservationWindowRepository(window_state_path)
        policy = CollectionServicePolicy(
            reconcile_interval_seconds=args.reconcile_interval_seconds,
            window_policy=ObservationWindowCoordinatorPolicy(
                window_duration_seconds=args.window_duration_seconds,
                allowed_lateness_seconds=args.allowed_lateness_seconds,
            ),
            session_policy=(
                OpcUaPersistentSessionPolicy()
                if args.subscription_queue_maxsize is None
                else OpcUaPersistentSessionPolicy(queue_maxsize=args.subscription_queue_maxsize)
            ),
        )

        async def _run() -> None:
            stop_event = asyncio.Event()
            # SIGINT/SIGTERM take the graceful path: sources stop (persisting what was
            # already dequeued), the writer stops, diagnostics flush their last interval.
            loop = asyncio.get_running_loop()
            for signum in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(signum, stop_event.set)
            await run_collection_service(
                source_repository,
                source_repository,
                control_repository,
                spool,
                history,
                history,
                window_repository,
                telemetry,
                stop_event=stop_event,
                telemetry_recorder=telemetry,
                service_runtime_recorder=telemetry,
                policy=policy,
                metrics=None if args.pipeline_metrics is None else PipelineMetrics(),
                metrics_path=args.pipeline_metrics,
            )

        asyncio.run(_run())
    except KeyboardInterrupt:
        print("collection service interrupted by user", file=sys.stderr)
        return 130
    except (LookupError, OSError, RuntimeError, ValueError) as error:
        print(f"collection service failed: {error}", file=sys.stderr)
        return 1
    return 0


def _resolve_workspace_mode(
    args: argparse.Namespace,
    *,
    required_explicit: tuple[str, ...],
    all_explicit: tuple[str, ...],
) -> OperationsWorkspace | None:
    workspace_root = args.workspace
    explicit_values = tuple(getattr(args, name) for name in all_explicit)
    if workspace_root is not None:
        if any(value is not None for value in explicit_values):
            flags = ", ".join(f"--{name.replace('_', '-')}" for name in all_explicit)
            raise ValueError(f"--workspace cannot be combined with explicit path flags: {flags}")
        return OperationsWorkspace(workspace_root)

    missing = tuple(name for name in required_explicit if getattr(args, name) is None)
    if missing:
        flags = ", ".join(f"--{name.replace('_', '-')}" for name in required_explicit)
        raise ValueError(f"provide --workspace or all explicit path flags: {flags}")
    return None


def _validate_collection_service_paths(
    *,
    registry: Path,
    control_state: Path,
    spool_state: Path,
    telemetry_state: Path,
    window_state: Path,
    ducklake_catalog: Path,
    ducklake_data: Path,
) -> None:
    file_paths = {
        "registry": registry,
        "control-state": control_state,
        "spool-state": spool_state,
        "telemetry-state": telemetry_state,
        "window-state": window_state,
        "ducklake-catalog": ducklake_catalog,
    }
    resolved = {
        label: path.expanduser().resolve(strict=False) for label, path in file_paths.items()
    }
    labels = tuple(resolved)
    for index, left in enumerate(labels):
        for right in labels[index + 1 :]:
            if resolved[left] == resolved[right]:
                raise ValueError(
                    f"collection service state paths must be distinct: {left} == {right}"
                )

    resolved_data = ducklake_data.expanduser().resolve(strict=False)
    if resolved_data in resolved.values():
        raise ValueError(
            "ducklake-data directory must be distinct from collection service state files"
        )
