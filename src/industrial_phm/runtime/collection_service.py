"""Independent continuous-collection service owned outside the Operations UI."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
from numbers import Real

from industrial_phm.application.acquisition_spool import AcquisitionSpool
from industrial_phm.application.acquisition_telemetry import (
    AcquisitionTelemetryRecorder,
    CollectionServiceRuntimeRecorder,
)
from industrial_phm.application.collection_control import (
    CollectionControlRepository,
    CollectionDesiredState,
)
from industrial_phm.application.history_writer import (
    OpcUaHistoricalBatchStore,
    SpoolToHistoryWriterPolicy,
)
from industrial_phm.application.observation_window import ObservationWindowRepository
from industrial_phm.application.opcua_acquisition import OpcUaPersistentSessionEvidenceSink
from industrial_phm.application.source_lifecycle import (
    SourceLifecycleRepository,
    SourceLifecycleState,
)
from industrial_phm.application.source_registration import (
    OpcUaSourceConfig,
    SourceRepository,
)
from industrial_phm.application.window_coordinator import (
    ObservationWindowCoordinatorPolicy,
    OpcUaHistoricalEventReader,
)
from industrial_phm.runtime.history_writer import run_spool_to_history_writer
from industrial_phm.runtime.opcua_acquisition import (
    run_registered_opcua_acquisition_worker,
)
from industrial_phm.runtime.window_coordinator import (
    run_continuous_registered_opcua_observation_windows,
)


@dataclass(frozen=True, slots=True)
class CollectionServicePolicy:
    reconcile_interval_seconds: float = 0.5
    history_writer_policy: SpoolToHistoryWriterPolicy = field(
        default_factory=SpoolToHistoryWriterPolicy
    )
    window_policy: ObservationWindowCoordinatorPolicy = field(
        default_factory=ObservationWindowCoordinatorPolicy
    )

    def __post_init__(self) -> None:
        _validate_positive_finite(
            self.reconcile_interval_seconds,
            "reconcile_interval_seconds",
        )
        if not isinstance(self.history_writer_policy, SpoolToHistoryWriterPolicy):
            raise ValueError("history_writer_policy must be SpoolToHistoryWriterPolicy")
        if not isinstance(self.window_policy, ObservationWindowCoordinatorPolicy):
            raise ValueError("window_policy must be ObservationWindowCoordinatorPolicy")


@dataclass(frozen=True, slots=True)
class CollectionServiceResult:
    started_at: datetime
    stopped_at: datetime
    reconcile_count: int
    source_start_count: int
    source_stop_count: int
    source_restart_count: int

    def __post_init__(self) -> None:
        _validate_aware_datetime(self.started_at, "started_at")
        _validate_aware_datetime(self.stopped_at, "stopped_at")
        if self.stopped_at < self.started_at:
            raise ValueError("stopped_at must not be before started_at")
        for field_name in (
            "reconcile_count",
            "source_start_count",
            "source_stop_count",
            "source_restart_count",
        ):
            _validate_non_negative_int(getattr(self, field_name), field_name)


@dataclass(slots=True)
class _OwnedSourceRuntime:
    stop_event: asyncio.Event
    worker_task: asyncio.Task[object]
    window_task: asyncio.Task[object]


async def run_collection_service(
    source_repository: SourceRepository,
    lifecycle_repository: SourceLifecycleRepository,
    control_repository: CollectionControlRepository,
    spool: AcquisitionSpool,
    history: OpcUaHistoricalBatchStore,
    history_reader: OpcUaHistoricalEventReader,
    window_repository: ObservationWindowRepository,
    session_evidence_sink: OpcUaPersistentSessionEvidenceSink,
    *,
    stop_event: asyncio.Event,
    telemetry_recorder: AcquisitionTelemetryRecorder | None = None,
    service_runtime_recorder: CollectionServiceRuntimeRecorder | None = None,
    policy: CollectionServicePolicy | None = None,
) -> CollectionServiceResult:
    """Reconcile durable desired state into independently owned runtime tasks."""
    if not isinstance(stop_event, asyncio.Event):
        raise ValueError("stop_event must be an asyncio.Event")
    effective_policy = CollectionServicePolicy() if policy is None else policy
    if not isinstance(effective_policy, CollectionServicePolicy):
        raise ValueError("policy must be CollectionServicePolicy")

    started_at = datetime.now(UTC)
    if service_runtime_recorder is not None:
        _record_service_runtime_best_effort(
            service_runtime_recorder.record_collection_service_start,
            started_at=started_at,
        )
    reconcile_count = 0
    source_start_count = 0
    source_stop_count = 0
    source_restart_count = 0
    owned: dict[str, _OwnedSourceRuntime] = {}
    previously_started: set[str] = set()

    writer_stop = asyncio.Event()
    writer_task = asyncio.create_task(
        run_spool_to_history_writer(
            spool,
            history,
            stop_event=writer_stop,
            policy=effective_policy.history_writer_policy,
            telemetry_recorder=telemetry_recorder,
        )
    )

    async def _stop_source(source_id: str) -> None:
        nonlocal source_stop_count
        runtime = owned.pop(source_id, None)
        if runtime is None:
            return
        runtime.stop_event.set()
        await asyncio.gather(
            runtime.worker_task,
            runtime.window_task,
            return_exceptions=True,
        )
        source_stop_count += 1

    def _start_source(source_id: str) -> None:
        nonlocal source_start_count, source_restart_count
        source_stop = asyncio.Event()
        worker_task = asyncio.create_task(
            run_registered_opcua_acquisition_worker(
                source_repository,
                lifecycle_repository,
                spool,
                session_evidence_sink,
                source_id,
                stop_event=source_stop,
                telemetry_recorder=telemetry_recorder,
            )
        )
        window_task = asyncio.create_task(
            run_continuous_registered_opcua_observation_windows(
                source_repository,
                history_reader,
                window_repository,
                source_id,
                stop_event=source_stop,
                policy=effective_policy.window_policy,
                telemetry_recorder=telemetry_recorder,
            )
        )
        owned[source_id] = _OwnedSourceRuntime(
            stop_event=source_stop,
            worker_task=worker_task,
            window_task=window_task,
        )
        source_start_count += 1
        if source_id in previously_started:
            source_restart_count += 1
        previously_started.add(source_id)

    try:
        while not stop_event.is_set():
            reconcile_count += 1

            completed_ids = tuple(
                source_id
                for source_id, runtime in owned.items()
                if runtime.worker_task.done() or runtime.window_task.done()
            )
            for source_id in completed_ids:
                await _stop_source(source_id)

            records = {record.source_id: record for record in control_repository.list_records()}
            sources = {source.source_id: source for source in source_repository.list_sources()}

            should_run: set[str] = set()
            for source_id, record in records.items():
                if record.desired_state != CollectionDesiredState.RUNNING:
                    continue
                source = sources.get(source_id)
                if source is None or not isinstance(source.config, OpcUaSourceConfig):
                    continue
                try:
                    lifecycle = lifecycle_repository.get_lifecycle(source_id)
                except LookupError:
                    continue
                if lifecycle.state == SourceLifecycleState.ACTIVE:
                    should_run.add(source_id)

            for source_id in tuple(owned):
                if source_id not in should_run:
                    await _stop_source(source_id)

            for source_id in sorted(should_run):
                if source_id not in owned and source_id not in completed_ids:
                    _start_source(source_id)

            if writer_task.done():
                writer_error = writer_task.exception()
                if writer_error is not None:
                    raise writer_error
                raise RuntimeError("history writer stopped while collection service is running")

            if service_runtime_recorder is not None:
                _record_service_runtime_best_effort(
                    service_runtime_recorder.record_collection_service_heartbeat,
                    heartbeat_at=datetime.now(UTC),
                    reconcile_count=reconcile_count,
                    owned_source_count=len(owned),
                )

            with suppress(TimeoutError):
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=effective_policy.reconcile_interval_seconds,
                )
    except Exception as error:
        if service_runtime_recorder is not None:
            _record_service_runtime_best_effort(
                service_runtime_recorder.record_collection_service_failure,
                _failure_detail(error),
                occurred_at=datetime.now(UTC),
            )
        raise
    finally:
        for source_id in tuple(owned):
            await _stop_source(source_id)
        writer_stop.set()
        await asyncio.gather(writer_task, return_exceptions=True)

    stopped_at = datetime.now(UTC)
    if service_runtime_recorder is not None:
        _record_service_runtime_best_effort(
            service_runtime_recorder.record_collection_service_stop,
            stopped_at=stopped_at,
            reconcile_count=reconcile_count,
        )

    return CollectionServiceResult(
        started_at=started_at,
        stopped_at=stopped_at,
        reconcile_count=reconcile_count,
        source_start_count=source_start_count,
        source_stop_count=source_stop_count,
        source_restart_count=source_restart_count,
    )


def _record_service_runtime_best_effort(
    callback: Callable[..., object],
    *args: object,
    **kwargs: object,
) -> None:
    try:
        callback(*args, **kwargs)
    except (OSError, ValueError):
        return


def _failure_detail(error: Exception) -> str:
    detail = str(error).strip()
    return type(error).__name__ if not detail else f"{type(error).__name__}: {detail}"


def _validate_positive_finite(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value):
        raise ValueError(f"{field_name} must be a finite number")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")


def _validate_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
