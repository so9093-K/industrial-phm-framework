"""Drain the durable acquisition spool into historical Asset History."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, datetime
from functools import partial
from uuid import uuid4

from industrial_phm.application.acquisition_spool import (
    AcquisitionSpool,
    AcquisitionSpoolPendingStats,
    AcquisitionSpoolStateError,
)
from industrial_phm.application.acquisition_telemetry import (
    AcquisitionFailureComponent,
    AcquisitionFailureTelemetry,
    AcquisitionTelemetryRecorder,
)
from industrial_phm.application.asset_history import HistoryIngestionMode
from industrial_phm.application.history_writer import (
    OpcUaHistoricalBatchStore,
    SpoolHistoryBatchWriteResult,
    SpoolHistoryWriterResult,
    SpoolToHistoryWriterPolicy,
)

BatchIdFactory = Callable[[], str]
NowFunction = Callable[[], datetime]
_LOGGER = logging.getLogger(__name__)


def write_next_spool_batch(
    spool: AcquisitionSpool,
    history: OpcUaHistoricalBatchStore,
    *,
    policy: SpoolToHistoryWriterPolicy | None = None,
    batch_id_factory: BatchIdFactory = lambda: f"live-{uuid4()}",
    now_fn: NowFunction = lambda: datetime.now(UTC),
    telemetry_recorder: AcquisitionTelemetryRecorder | None = None,
    force: bool = False,
) -> SpoolHistoryBatchWriteResult | None:
    """Commit and acknowledge one due/active spool batch.

    The downstream commit always happens before spool acknowledgement. If a process dies
    in that gap, the stable active batch remains in the spool; the next invocation resolves
    the identical DuckLake commit and only then acknowledges the batch.
    """
    effective_policy = SpoolToHistoryWriterPolicy() if policy is None else policy
    if not isinstance(effective_policy, SpoolToHistoryWriterPolicy):
        raise ValueError("policy must be SpoolToHistoryWriterPolicy")
    if not isinstance(force, bool):
        raise ValueError("force must be boolean")

    write_started_at = _now(now_fn)
    batch = spool.get_active_batch()
    if batch is None:
        stats = spool.pending_unassigned_stats()
        if stats.event_count == 0:
            return None
        if not force and not _flush_due(
            stats,
            now=write_started_at,
            policy=effective_policy,
        ):
            return None

        batch_id = batch_id_factory()
        _validate_identifier(batch_id, "batch_id")
        batch = spool.assign_next_batch(
            batch_id=batch_id,
            max_events=effective_policy.max_events,
            max_bytes=effective_policy.max_bytes,
            created_at=write_started_at,
        )
        if batch is None:
            raise AcquisitionSpoolStateError(
                "pending spool events disappeared before batch assignment"
            )

    try:
        existing = history.get_opcua_batch_commit(
            batch.events,
            batch_id=batch.batch_id,
            ingestion_mode=HistoryIngestionMode.LIVE,
        )
        recovered_existing_commit = existing is not None
        commit = (
            existing
            if existing is not None
            else history.append_opcua_batch(
                batch.events,
                batch_id=batch.batch_id,
                ingestion_mode=HistoryIngestionMode.LIVE,
            )
        )

        if commit.batch_id != batch.batch_id:
            raise AcquisitionSpoolStateError(
                "historical commit batch_id does not match the active spool batch"
            )
        if commit.event_count != batch.event_count:
            raise AcquisitionSpoolStateError(
                "historical commit event_count does not match the active spool batch"
            )

        acknowledged_at = _now(now_fn)
        acknowledged_count = spool.acknowledge_batch(
            batch.batch_id,
            acknowledged_at=acknowledged_at,
        )
        if acknowledged_count != batch.event_count:
            raise AcquisitionSpoolStateError(
                "spool acknowledgement count does not match the committed batch"
            )
    except Exception as error:
        if telemetry_recorder is not None:
            failure_at = _now(now_fn)
            failure_detail = _failure_detail(error)
            for source_id in sorted({event.source_id for event in batch.events}):
                _record_telemetry_best_effort(
                    partial(
                        telemetry_recorder.record_failure,
                        AcquisitionFailureTelemetry(
                            source_id=source_id,
                            component=AcquisitionFailureComponent.HISTORY_WRITER,
                            occurred_at=failure_at,
                            detail=failure_detail,
                        ),
                    ),
                    label="history writer failure",
                )
        raise

    result = SpoolHistoryBatchWriteResult(
        commit=commit,
        payload_bytes=batch.payload_bytes,
        write_started_at=write_started_at,
        acknowledged_at=acknowledged_at,
        recovered_existing_commit=recovered_existing_commit,
    )
    if telemetry_recorder is not None:
        source_counts = Counter(event.source_id for event in batch.events)
        source_event_counts = dict(source_counts)
        _record_telemetry_best_effort(
            partial(
                telemetry_recorder.record_history_batch,
                result,
                source_event_counts=source_event_counts,
            ),
            label="history batch",
        )
    return result


async def run_spool_to_history_writer(
    spool: AcquisitionSpool,
    history: OpcUaHistoricalBatchStore,
    *,
    stop_event: asyncio.Event,
    policy: SpoolToHistoryWriterPolicy | None = None,
    batch_id_factory: BatchIdFactory = lambda: f"live-{uuid4()}",
    telemetry_recorder: AcquisitionTelemetryRecorder | None = None,
    now_fn: NowFunction = lambda: datetime.now(UTC),
) -> SpoolHistoryWriterResult:
    """Continuously flush due micro-batches until an explicit stop request.

    A stop does not discard or force-flush sub-threshold events. They remain durable in the
    spool for the next writer process, which keeps graceful shutdown separate from data loss.

    Transient downstream exceptions are retried using the same durable active batch after the
    normal poll delay. Value/identity conflicts and spool invariant failures remain fail-fast.
    """
    if not isinstance(stop_event, asyncio.Event):
        raise ValueError("stop_event must be an asyncio.Event")
    effective_policy = SpoolToHistoryWriterPolicy() if policy is None else policy
    if not isinstance(effective_policy, SpoolToHistoryWriterPolicy):
        raise ValueError("policy must be SpoolToHistoryWriterPolicy")

    started_at = _now(now_fn)
    batch_count = 0
    event_count = 0
    recovered_batch_count = 0

    while not stop_event.is_set():
        try:
            result = await asyncio.to_thread(
                write_next_spool_batch,
                spool,
                history,
                policy=effective_policy,
                batch_id_factory=batch_id_factory,
                now_fn=now_fn,
                telemetry_recorder=telemetry_recorder,
            )
        except AcquisitionSpoolStateError, ValueError:
            # Stable-identity conflicts and spool invariants are contract failures,
            # not transient downstream outages. Fail fast instead of retrying forever.
            raise
        except Exception:
            # The active batch remains durable and unacknowledged. Retry the exact
            # same batch after the normal writer poll delay; telemetry was already
            # recorded by write_next_spool_batch.
            _LOGGER.exception("Transient history writer failure; retrying stable active batch")
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=effective_policy.poll_interval_seconds,
                )
            continue

        if result is not None:
            batch_count += 1
            event_count += result.event_count
            if result.recovered_existing_commit:
                recovered_batch_count += 1
            continue

        with suppress(TimeoutError):
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=effective_policy.poll_interval_seconds,
            )

    return SpoolHistoryWriterResult(
        started_at=started_at,
        stopped_at=_now(now_fn),
        batch_count=batch_count,
        event_count=event_count,
        recovered_batch_count=recovered_batch_count,
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


def _flush_due(
    stats: AcquisitionSpoolPendingStats,
    *,
    now: datetime,
    policy: SpoolToHistoryWriterPolicy,
) -> bool:
    if stats.event_count >= policy.max_events:
        return True
    if stats.payload_bytes >= policy.max_bytes:
        return True
    oldest = stats.oldest_accepted_at
    if oldest is None or now < oldest:
        return False
    return (now - oldest).total_seconds() >= policy.max_interval_seconds


def _now(now_fn: NowFunction) -> datetime:
    value = now_fn()
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("now_fn must return a timezone-aware datetime")
    return value


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
