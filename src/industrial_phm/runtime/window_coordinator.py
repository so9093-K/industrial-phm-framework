"""Continuous observation-window coordination from durable OPC UA history."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from functools import partial

from industrial_phm.application.acquisition_telemetry import (
    AcquisitionFailureComponent,
    AcquisitionFailureTelemetry,
    AcquisitionTelemetryRecorder,
)
from industrial_phm.application.observation_window import (
    DurableObservationWindow,
    ObservationWindowBuffer,
    ObservationWindowEventDisposition,
    ObservationWindowIngestResult,
    ObservationWindowRepository,
)
from industrial_phm.application.opcua_persistent import OpcUaPersistentDataChangeEvent
from industrial_phm.application.source_registration import (
    OpcUaSourceConfig,
    SourceRepository,
)
from industrial_phm.application.window_coordinator import (
    ContinuousObservationWindowCoordinatorResult,
    IncrementalObservationWindowRepository,
    ObservationWindowCoordinatorCycleResult,
    ObservationWindowCoordinatorPolicy,
    ObservationWindowCoordinatorState,
    OpcUaHistoricalEventCursor,
    OpcUaHistoricalEventReader,
)
from industrial_phm.runtime.pipeline_metrics import PipelineMetrics

NowFunction = Callable[[], datetime]
_LOGGER = logging.getLogger(__name__)


def rebuild_registered_opcua_observation_windows(
    source_repository: SourceRepository,
    history: OpcUaHistoricalEventReader,
    window_repository: ObservationWindowRepository,
    source_id: str,
    *,
    policy: ObservationWindowCoordinatorPolicy | None = None,
) -> ObservationWindowCoordinatorCycleResult:
    """Replay durable history and idempotently persist every closed event-time window."""
    effective_policy = ObservationWindowCoordinatorPolicy() if policy is None else policy
    if not isinstance(effective_policy, ObservationWindowCoordinatorPolicy):
        raise ValueError("policy must be ObservationWindowCoordinatorPolicy")

    source = source_repository.get(source_id)
    config = source.config
    if not isinstance(config, OpcUaSourceConfig):
        raise ValueError("observation-window coordinator requires OpcUaSourceConfig")

    expected_channel_ids = tuple(mapping.channel_id for mapping in config.node_mappings)
    expected_channel_set = set(expected_channel_ids)
    events = history.query_opcua_events(source_id)

    duration = timedelta(seconds=effective_policy.window_duration_seconds)
    allowed_lateness = timedelta(seconds=effective_policy.allowed_lateness_seconds)
    buffers: dict[datetime, ObservationWindowBuffer] = {}
    finalized: list[DurableObservationWindow] = []
    event_results: list[ObservationWindowIngestResult] = []
    watermark: datetime | None = None
    max_valid_event_at: datetime | None = None

    def _advance_and_finalize(
        next_watermark: datetime,
        *,
        finalized_at: datetime,
    ) -> None:
        nonlocal watermark
        if watermark is not None and next_watermark < watermark:
            raise RuntimeError("derived observation watermark must not move backwards")
        watermark = next_watermark

        for buffer in buffers.values():
            buffer.advance_watermark(next_watermark)

        due_starts = tuple(
            sorted(
                window_start
                for window_start in buffers
                if window_start + duration <= next_watermark
            )
        )
        for window_start in due_starts:
            buffer = buffers.pop(window_start)
            window = buffer.finalize(finalized_at=finalized_at)
            window_repository.record_window(window)
            finalized.append(window)

    for event in events:
        if event.source_id != source_id:
            raise RuntimeError("historical event source_id does not match requested source")
        if event.event.asset_id != source.asset_id:
            raise RuntimeError("historical event asset_id does not match registered source")
        if event.event.measurement_point_id != source.measurement_point_id:
            raise RuntimeError(
                "historical event measurement_point_id does not match registered source"
            )

        identity = event.local_delivery_identity
        event_at = event.event_time.event_at
        if event_at is None:
            event_results.append(
                ObservationWindowIngestResult(
                    disposition=ObservationWindowEventDisposition.TIMING_UNAVAILABLE,
                    local_delivery_identity=identity,
                    event_at=None,
                    watermark_at_ingest=watermark,
                )
            )
            continue

        future_skew_seconds = (event_at - event.event_time.ingested_at).total_seconds()
        if future_skew_seconds > effective_policy.max_future_skew_seconds:
            event_results.append(
                ObservationWindowIngestResult(
                    disposition=ObservationWindowEventDisposition.FUTURE_TIMESTAMP,
                    local_delivery_identity=identity,
                    event_at=event_at,
                    watermark_at_ingest=watermark,
                )
            )
            continue

        if event.channel_id not in expected_channel_set:
            window_start, _ = _aligned_window_bounds(
                event_at,
                policy=effective_policy,
            )
            buffer = buffers.get(window_start)
            if buffer is None:
                event_results.append(
                    ObservationWindowIngestResult(
                        disposition=ObservationWindowEventDisposition.UNEXPECTED_CHANNEL,
                        local_delivery_identity=identity,
                        event_at=event_at,
                        watermark_at_ingest=watermark,
                    )
                )
            else:
                event_results.append(buffer.ingest(event))
            continue

        if max_valid_event_at is None or event_at > max_valid_event_at:
            max_valid_event_at = event_at
        candidate_watermark = max_valid_event_at - allowed_lateness
        if watermark is None or candidate_watermark > watermark:
            _advance_and_finalize(
                candidate_watermark,
                finalized_at=event.event_time.ingested_at,
            )

        window_start, window_end = _aligned_window_bounds(
            event_at,
            policy=effective_policy,
        )
        if watermark is not None and window_end <= watermark:
            event_results.append(
                ObservationWindowIngestResult(
                    disposition=ObservationWindowEventDisposition.LATE,
                    local_delivery_identity=identity,
                    event_at=event_at,
                    watermark_at_ingest=watermark,
                )
            )
            continue

        buffer = buffers.get(window_start)
        if buffer is None:
            buffer = ObservationWindowBuffer(
                window_id=_window_id(
                    source_id=source_id,
                    asset_id=source.asset_id,
                    measurement_point_id=source.measurement_point_id,
                    window_start=window_start,
                    window_end=window_end,
                    expected_channel_ids=expected_channel_ids,
                ),
                source_id=source_id,
                asset_id=source.asset_id,
                measurement_point_id=source.measurement_point_id,
                expected_channel_ids=expected_channel_ids,
                window_start=window_start,
                window_end=window_end,
                max_buffered_events=effective_policy.max_buffered_events,
                max_future_skew_seconds=effective_policy.max_future_skew_seconds,
            )
            if watermark is not None:
                buffer.advance_watermark(watermark)
            buffers[window_start] = buffer

        event_results.append(buffer.ingest(event))

    return ObservationWindowCoordinatorCycleResult(
        source_id=source_id,
        finalized_windows=tuple(
            sorted(finalized, key=lambda item: (item.window_start, item.window_id))
        ),
        event_results=tuple(event_results),
        watermark=watermark,
        active_window_count=len(buffers),
    )


class IncrementalRegisteredOpcUaWindowCoordinator:
    """Restart-safe incremental assembler over durable OPC UA ingestion order."""

    def __init__(
        self,
        source_repository: SourceRepository,
        history: OpcUaHistoricalEventReader,
        window_repository: IncrementalObservationWindowRepository,
        source_id: str,
        *,
        policy: ObservationWindowCoordinatorPolicy | None = None,
    ) -> None:
        effective_policy = ObservationWindowCoordinatorPolicy() if policy is None else policy
        if not isinstance(effective_policy, ObservationWindowCoordinatorPolicy):
            raise ValueError("policy must be ObservationWindowCoordinatorPolicy")
        if not isinstance(window_repository, IncrementalObservationWindowRepository):
            raise ValueError(
                "continuous coordinator requires an incremental observation-window repository"
            )

        source = source_repository.get(source_id)
        config = source.config
        if not isinstance(config, OpcUaSourceConfig):
            raise ValueError("observation-window coordinator requires OpcUaSourceConfig")

        self._history = history
        self._windows = window_repository
        self._source_id = source_id
        self._asset_id = source.asset_id
        self._measurement_point_id = source.measurement_point_id
        self._expected_channel_ids = tuple(mapping.channel_id for mapping in config.node_mappings)
        self._expected_channel_set = set(self._expected_channel_ids)
        self._policy = effective_policy
        self._duration = timedelta(seconds=effective_policy.window_duration_seconds)
        self._allowed_lateness = timedelta(seconds=effective_policy.allowed_lateness_seconds)

        state = window_repository.load_coordinator_state(source_id)
        if state is None:
            self._cursor: OpcUaHistoricalEventCursor | None = None
            self._watermark: datetime | None = None
            self._max_valid_event_at: datetime | None = None
            self._buffers: dict[datetime, ObservationWindowBuffer] = {}
        else:
            self._cursor = state.cursor
            self._watermark = state.watermark
            self._max_valid_event_at = state.max_valid_event_at
            self._buffers = {}
            for snapshot in state.active_buffers:
                if snapshot.asset_id != self._asset_id:
                    raise RuntimeError("coordinator state asset_id no longer matches source")
                if snapshot.measurement_point_id != self._measurement_point_id:
                    raise RuntimeError(
                        "coordinator state measurement_point_id no longer matches source"
                    )
                if tuple(snapshot.expected_channel_ids) != self._expected_channel_ids:
                    raise RuntimeError("coordinator state channel mapping no longer matches source")
                self._buffers[snapshot.window_start] = ObservationWindowBuffer.from_snapshot(
                    snapshot
                )

    def run_cycle(self) -> ObservationWindowCoordinatorCycleResult:
        events = self._history.query_opcua_events_after(
            self._source_id,
            cursor=self._cursor,
            limit=self._policy.history_page_size,
        )
        finalized: list[DurableObservationWindow] = []
        event_results: list[ObservationWindowIngestResult] = []

        for event in events:
            self._process_event(event, finalized=finalized, event_results=event_results)
            self._cursor = OpcUaHistoricalEventCursor(
                ingested_at=event.event_time.ingested_at,
                connection_epoch=event.connection_epoch,
                event_index=event.event_index,
            )

        if events:
            state = ObservationWindowCoordinatorState(
                source_id=self._source_id,
                cursor=self._cursor,
                watermark=self._watermark,
                max_valid_event_at=self._max_valid_event_at,
                active_buffers=tuple(
                    self._buffers[start].snapshot() for start in sorted(self._buffers)
                ),
            )
            self._windows.record_coordinator_cycle(tuple(finalized), state)

        return ObservationWindowCoordinatorCycleResult(
            source_id=self._source_id,
            finalized_windows=tuple(
                sorted(finalized, key=lambda item: (item.window_start, item.window_id))
            ),
            event_results=tuple(event_results),
            watermark=self._watermark,
            active_window_count=len(self._buffers),
        )

    def _advance_and_finalize(
        self,
        next_watermark: datetime,
        *,
        finalized_at: datetime,
        finalized: list[DurableObservationWindow],
    ) -> None:
        if self._watermark is not None and next_watermark < self._watermark:
            raise RuntimeError("derived observation watermark must not move backwards")
        self._watermark = next_watermark

        for buffer in self._buffers.values():
            buffer.advance_watermark(next_watermark)

        due_starts = tuple(
            sorted(
                window_start
                for window_start in self._buffers
                if window_start + self._duration <= next_watermark
            )
        )
        for window_start in due_starts:
            buffer = self._buffers.pop(window_start)
            finalized.append(buffer.finalize(finalized_at=finalized_at))

    def _process_event(
        self,
        event: OpcUaPersistentDataChangeEvent,
        *,
        finalized: list[DurableObservationWindow],
        event_results: list[ObservationWindowIngestResult],
    ) -> None:
        if event.source_id != self._source_id:
            raise RuntimeError("historical event source_id does not match requested source")
        if event.event.asset_id != self._asset_id:
            raise RuntimeError("historical event asset_id does not match registered source")
        if event.event.measurement_point_id != self._measurement_point_id:
            raise RuntimeError(
                "historical event measurement_point_id does not match registered source"
            )

        identity = event.local_delivery_identity
        event_at = event.event_time.event_at
        if event_at is None:
            event_results.append(
                ObservationWindowIngestResult(
                    disposition=ObservationWindowEventDisposition.TIMING_UNAVAILABLE,
                    local_delivery_identity=identity,
                    event_at=None,
                    watermark_at_ingest=self._watermark,
                )
            )
            return

        future_skew_seconds = (event_at - event.event_time.ingested_at).total_seconds()
        if future_skew_seconds > self._policy.max_future_skew_seconds:
            event_results.append(
                ObservationWindowIngestResult(
                    disposition=ObservationWindowEventDisposition.FUTURE_TIMESTAMP,
                    local_delivery_identity=identity,
                    event_at=event_at,
                    watermark_at_ingest=self._watermark,
                )
            )
            return

        if event.channel_id not in self._expected_channel_set:
            window_start, _ = _aligned_window_bounds(event_at, policy=self._policy)
            buffer = self._buffers.get(window_start)
            if buffer is None:
                event_results.append(
                    ObservationWindowIngestResult(
                        disposition=ObservationWindowEventDisposition.UNEXPECTED_CHANNEL,
                        local_delivery_identity=identity,
                        event_at=event_at,
                        watermark_at_ingest=self._watermark,
                    )
                )
            else:
                event_results.append(buffer.ingest(event))
            return

        if self._max_valid_event_at is None or event_at > self._max_valid_event_at:
            self._max_valid_event_at = event_at
        candidate_watermark = self._max_valid_event_at - self._allowed_lateness
        if self._watermark is None or candidate_watermark > self._watermark:
            self._advance_and_finalize(
                candidate_watermark,
                finalized_at=event.event_time.ingested_at,
                finalized=finalized,
            )

        window_start, window_end = _aligned_window_bounds(event_at, policy=self._policy)
        if self._watermark is not None and window_end <= self._watermark:
            event_results.append(
                ObservationWindowIngestResult(
                    disposition=ObservationWindowEventDisposition.LATE,
                    local_delivery_identity=identity,
                    event_at=event_at,
                    watermark_at_ingest=self._watermark,
                )
            )
            return

        buffer = self._buffers.get(window_start)
        if buffer is None:
            buffer = ObservationWindowBuffer(
                window_id=_window_id(
                    source_id=self._source_id,
                    asset_id=self._asset_id,
                    measurement_point_id=self._measurement_point_id,
                    window_start=window_start,
                    window_end=window_end,
                    expected_channel_ids=self._expected_channel_ids,
                ),
                source_id=self._source_id,
                asset_id=self._asset_id,
                measurement_point_id=self._measurement_point_id,
                expected_channel_ids=self._expected_channel_ids,
                window_start=window_start,
                window_end=window_end,
                max_buffered_events=self._policy.max_buffered_events,
                max_future_skew_seconds=self._policy.max_future_skew_seconds,
            )
            if self._watermark is not None:
                buffer.advance_watermark(self._watermark)
            self._buffers[window_start] = buffer

        event_results.append(buffer.ingest(event))


async def run_continuous_registered_opcua_observation_windows(
    source_repository: SourceRepository,
    history: OpcUaHistoricalEventReader,
    window_repository: ObservationWindowRepository,
    source_id: str,
    *,
    stop_event: asyncio.Event,
    policy: ObservationWindowCoordinatorPolicy | None = None,
    telemetry_recorder: AcquisitionTelemetryRecorder | None = None,
    now_fn: NowFunction = lambda: datetime.now(UTC),
    metrics: PipelineMetrics | None = None,
) -> ContinuousObservationWindowCoordinatorResult:
    """Process only newly durable events and persist exact restart state each cycle."""
    if not isinstance(stop_event, asyncio.Event):
        raise ValueError("stop_event must be an asyncio.Event")
    effective_policy = ObservationWindowCoordinatorPolicy() if policy is None else policy
    if not isinstance(effective_policy, ObservationWindowCoordinatorPolicy):
        raise ValueError("policy must be ObservationWindowCoordinatorPolicy")
    if not isinstance(window_repository, IncrementalObservationWindowRepository):
        raise ValueError(
            "continuous coordinator requires an incremental observation-window repository"
        )

    coordinator = IncrementalRegisteredOpcUaWindowCoordinator(
        source_repository,
        history,
        window_repository,
        source_id,
        policy=effective_policy,
    )
    started_at = _now(now_fn)
    cycle_count = 0
    last_watermark: datetime | None = None

    while not stop_event.is_set():
        try:
            cycle_started = time.monotonic()
            cycle = await asyncio.to_thread(coordinator.run_cycle)
            if metrics is not None:
                metrics.observe("window_cycle", time.monotonic() - cycle_started)
                metrics.count("window_cycle_events", cycle.historical_event_count)
            cycle_count += 1
            if (
                last_watermark is not None
                and cycle.watermark is not None
                and cycle.watermark < last_watermark
            ):
                raise RuntimeError("continuous observation watermark moved backwards")
            if cycle.watermark is not None:
                last_watermark = cycle.watermark
            if telemetry_recorder is not None:
                recorded_at = _now(now_fn)
                telemetry_started = time.monotonic()
                _record_telemetry_best_effort(
                    partial(
                        telemetry_recorder.record_window_cycle,
                        cycle,
                        recorded_at=recorded_at,
                    ),
                    label="window cycle",
                )
                if metrics is not None:
                    metrics.observe(
                        "telemetry_window_in_loop", time.monotonic() - telemetry_started
                    )
        except Exception as error:
            if telemetry_recorder is not None:
                occurred_at = _now(now_fn)
                failure_detail = _failure_detail(error)
                _record_telemetry_best_effort(
                    partial(
                        telemetry_recorder.record_failure,
                        AcquisitionFailureTelemetry(
                            source_id=source_id,
                            component=AcquisitionFailureComponent.WINDOW_COORDINATOR,
                            occurred_at=occurred_at,
                            detail=failure_detail,
                        ),
                    ),
                    label="window coordinator failure",
                )
            raise

        with suppress(TimeoutError):
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=effective_policy.poll_interval_seconds,
            )

    return ContinuousObservationWindowCoordinatorResult(
        source_id=source_id,
        started_at=started_at,
        stopped_at=_now(now_fn),
        cycle_count=cycle_count,
        last_watermark=last_watermark,
    )


def _record_telemetry_best_effort(
    callback: Callable[[], None],
    *,
    label: str,
) -> None:
    try:
        callback()
    except Exception:
        _LOGGER.exception("Failed to record acquisition telemetry: %s", label)


def _failure_detail(error: Exception) -> str:
    detail = str(error).strip()
    return type(error).__name__ if not detail else f"{type(error).__name__}: {detail}"


def _aligned_window_bounds(
    event_at: datetime,
    *,
    policy: ObservationWindowCoordinatorPolicy,
) -> tuple[datetime, datetime]:
    duration = timedelta(seconds=policy.window_duration_seconds)
    elapsed = event_at - policy.alignment_origin
    window_index = elapsed // duration
    window_start = policy.alignment_origin + window_index * duration
    return window_start, window_start + duration


def _window_id(
    *,
    source_id: str,
    asset_id: str,
    measurement_point_id: str | None,
    window_start: datetime,
    window_end: datetime,
    expected_channel_ids: tuple[str, ...],
) -> str:
    payload = json.dumps(
        {
            "schema": "industrial-phm-observation-window-coordinate-v1",
            "source_id": source_id,
            "asset_id": asset_id,
            "measurement_point_id": measurement_point_id,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "expected_channel_ids": list(expected_channel_ids),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "opcua-window-" + hashlib.sha256(payload).hexdigest()[:24]


def _now(now_fn: NowFunction) -> datetime:
    value = now_fn()
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("now_fn must return a timezone-aware datetime")
    return value
