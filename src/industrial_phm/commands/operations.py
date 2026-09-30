"""Operational source-runtime command handlers."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from industrial_phm.application import (
    AlignmentPolicyKind,
    CollectionDesiredState,
    JsonObservationWindowRepository,
    JsonPhaseUnbalanceRepository,
    JsonSourceRepository,
    JsonSourceRuntimeRepository,
    JsonWindowAnalysisLedger,
    JsonWindowAnalysisRuntimeRepository,
    ObservationWindowCoordinatorPolicy,
    PhaseUnbalanceConfig,
    SourcePollingPolicy,
    SourceRuntimeCycleState,
    TemporalAlignmentPolicy,
    analyze_finalized_windows,
    backfill_registered_file_source,
    poll_registered_source,
    request_collection_state,
    validate_distinct_source_state_paths,
)
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime import (
    CollectionServicePolicy,
    SqliteAcquisitionSpool,
    SqliteAcquisitionSpoolConfig,
    SqliteAcquisitionTelemetryRepository,
    SqliteCollectionControlRepository,
    run_collection_service,
)


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
    runtime_path = args.runtime_status or args.analysis_state.with_name(
        f"{args.analysis_state.stem}-runtime.json"
    )
    runtime = JsonWindowAnalysisRuntimeRepository(runtime_path)
    _try_record_window_analysis_runtime(runtime.record_start, datetime.now(UTC))
    try:
        if args.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        windows = JsonObservationWindowRepository(args.window_state)
        results = JsonPhaseUnbalanceRepository(args.analysis_state)
        ledger = JsonWindowAnalysisLedger(args.ledger_state)
        config = PhaseUnbalanceConfig(alignment=_alignment_policy(args))
        while True:
            outcomes = analyze_finalized_windows(windows, results, ledger, config=config)
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
        source_repository = JsonSourceRepository(args.registry)
        control_repository = SqliteCollectionControlRepository(args.control_state)
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
        _validate_collection_service_paths(args)
        source_repository = JsonSourceRepository(args.registry)
        control_repository = SqliteCollectionControlRepository(args.control_state)
        spool = SqliteAcquisitionSpool(SqliteAcquisitionSpoolConfig(path=args.spool_state))
        telemetry = SqliteAcquisitionTelemetryRepository(args.telemetry_state)
        history = DuckLakeAssetHistory(
            DuckLakeAssetHistoryConfig(
                catalog_path=args.ducklake_catalog,
                data_path=args.ducklake_data,
            )
        )
        window_repository = JsonObservationWindowRepository(args.window_state)
        policy = CollectionServicePolicy(
            reconcile_interval_seconds=args.reconcile_interval_seconds,
            window_policy=ObservationWindowCoordinatorPolicy(
                window_duration_seconds=args.window_duration_seconds,
                allowed_lateness_seconds=args.allowed_lateness_seconds,
            ),
        )

        async def _run() -> None:
            stop_event = asyncio.Event()
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
                policy=policy,
            )

        asyncio.run(_run())
    except KeyboardInterrupt:
        print("collection service interrupted by user", file=sys.stderr)
        return 130
    except (LookupError, OSError, RuntimeError, ValueError) as error:
        print(f"collection service failed: {error}", file=sys.stderr)
        return 1
    return 0


def _validate_collection_service_paths(args: argparse.Namespace) -> None:
    file_paths = {
        "registry": args.registry,
        "control-state": args.control_state,
        "spool-state": args.spool_state,
        "telemetry-state": args.telemetry_state,
        "window-state": args.window_state,
        "ducklake-catalog": args.ducklake_catalog,
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

    ducklake_data = args.ducklake_data.expanduser().resolve(strict=False)
    if ducklake_data in resolved.values():
        raise ValueError(
            "ducklake-data directory must be distinct from collection service state files"
        )
