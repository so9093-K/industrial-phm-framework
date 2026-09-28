"""Long-lived registered OPC UA acquisition worker.

The worker owns application session semantics and durable spool acceptance. asyncua owns
transport/session/subscription recovery through the concrete connector.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from industrial_phm.application.acquisition_spool import AcquisitionSpool
from industrial_phm.application.acquisition_telemetry import (
    AcquisitionFailureComponent,
    AcquisitionFailureTelemetry,
    AcquisitionTelemetryRecorder,
)
from industrial_phm.application.opcua_acquisition import (
    OpcUaAcquisitionWorkerResult,
    OpcUaPersistentSessionEvidenceSink,
)
from industrial_phm.application.opcua_persistent import (
    OpcUaEventTimePolicy,
    OpcUaPersistentSessionEvidence,
    OpcUaPersistentSessionPolicy,
    OpcUaPersistentSessionState,
    validate_opcua_persistent_session_transition,
)
from industrial_phm.application.source_lifecycle import (
    SourceLifecycleRepository,
    SourceLifecycleState,
)
from industrial_phm.application.source_registration import (
    OpcUaSourceConfig,
    SourceRepository,
)
from industrial_phm.application.source_subscription import RegisteredOpcUaDataChangeEvent
from industrial_phm.connectors import OpcUaSubscriptionNotification
from industrial_phm.connectors.opcua_persistent import (
    OpcUaConnectorConnectionState,
    OpcUaConnectorQueueOverflow,
    OpcUaConnectorStateEvent,
    OpcUaPersistentConnectorConfig,
    OpcUaPersistentSubscription,
)


class _PersistentConnector(Protocol):
    async def start(self) -> None: ...

    async def next_state(self, timeout: float | None = None) -> OpcUaConnectorStateEvent: ...

    async def next_notification(
        self,
        timeout: float | None = None,
    ) -> OpcUaSubscriptionNotification | None: ...

    async def next_queue_overflow(self) -> OpcUaConnectorQueueOverflow: ...

    async def close(self) -> None: ...


ConnectorFactory = Callable[[OpcUaPersistentConnectorConfig], _PersistentConnector]
NowFunction = Callable[[], datetime]
_LOGGER = logging.getLogger(__name__)


async def run_registered_opcua_acquisition_worker(
    source_repository: SourceRepository,
    lifecycle_repository: SourceLifecycleRepository,
    spool: AcquisitionSpool,
    session_evidence_sink: OpcUaPersistentSessionEvidenceSink,
    source_id: str,
    *,
    stop_event: asyncio.Event,
    session_policy: OpcUaPersistentSessionPolicy | None = None,
    event_time_policy: OpcUaEventTimePolicy | None = None,
    connector_factory: ConnectorFactory = OpcUaPersistentSubscription,
    telemetry_recorder: AcquisitionTelemetryRecorder | None = None,
    now_fn: NowFunction = lambda: datetime.now(UTC),
) -> OpcUaAcquisitionWorkerResult:
    """Run one ACTIVE registered OPC UA source until explicit stop or failure.

    asyncua 2.0.1 exposes the reconnect delay cap but fixes the initial delay and
    exponential multiplier to 1 second and 2x. v1 therefore fails fast when the
    application policy requests different values instead of silently ignoring them.
    """
    if not isinstance(stop_event, asyncio.Event):
        raise ValueError("stop_event must be an asyncio.Event")

    source = source_repository.get(source_id)
    lifecycle = lifecycle_repository.get_lifecycle(source_id)
    if lifecycle.state != SourceLifecycleState.ACTIVE:
        raise ValueError("persistent OPC UA acquisition requires an active source lifecycle")
    config = source.config
    if not isinstance(config, OpcUaSourceConfig):
        raise ValueError("persistent OPC UA acquisition requires OpcUaSourceConfig")

    effective_session_policy = (
        OpcUaPersistentSessionPolicy() if session_policy is None else session_policy
    )
    if not isinstance(effective_session_policy, OpcUaPersistentSessionPolicy):
        raise ValueError("session_policy must be OpcUaPersistentSessionPolicy")
    effective_event_time_policy = (
        OpcUaEventTimePolicy() if event_time_policy is None else event_time_policy
    )
    if not isinstance(effective_event_time_policy, OpcUaEventTimePolicy):
        raise ValueError("event_time_policy must be OpcUaEventTimePolicy")
    _validate_asyncua_reconnect_policy(effective_session_policy)

    started_at = _now(now_fn)
    baseline_epoch = await asyncio.to_thread(
        spool.get_last_connection_epoch,
        source_id,
    )
    current = OpcUaPersistentSessionEvidence(
        source_id=source_id,
        state=OpcUaPersistentSessionState.DISCONNECTED,
        changed_at=started_at,
        connection_epoch=baseline_epoch,
    )
    if telemetry_recorder is not None:
        _record_telemetry_best_effort(
            lambda: telemetry_recorder.record_session_configuration(
                source_id,
                callback_queue_maxsize=effective_session_policy.queue_maxsize,
                recorded_at=started_at,
            ),
            label="session configuration",
        )
    _record_session_evidence(
        session_evidence_sink,
        telemetry_recorder,
        current,
    )

    connector = connector_factory(
        OpcUaPersistentConnectorConfig(
            endpoint_url=config.endpoint_url,
            node_mappings=tuple(config.node_mappings),
            publishing_interval_ms=effective_session_policy.publishing_interval_ms,
            queue_maxsize=effective_session_policy.queue_maxsize,
            timeout_seconds=config.timeout_seconds,
            reconnect_max_delay_seconds=effective_session_policy.reconnect_max_delay_seconds,
        )
    )

    accepted_event_count = 0
    replayed_event_count = 0
    queue_overflow_count = 0
    next_event_index = 0
    overflow_pending = False
    state_task: asyncio.Task[OpcUaConnectorStateEvent] | None = None
    notification_task: asyncio.Task[OpcUaSubscriptionNotification | None] | None = None
    overflow_task: asyncio.Task[OpcUaConnectorQueueOverflow] | None = None
    stop_task: asyncio.Task[bool] | None = None
    stop_detail = "stop-requested"

    async def _transition(
        state: OpcUaPersistentSessionState,
        *,
        changed_at: datetime,
        detail: str | None = None,
    ) -> None:
        nonlocal current, next_event_index
        epoch = current.connection_epoch
        reconnect_attempt = current.reconnect_attempt_index
        if (
            current.state == OpcUaPersistentSessionState.CONNECTING
            and state == OpcUaPersistentSessionState.CONNECTED
        ):
            epoch = await asyncio.to_thread(
                spool.reserve_next_connection_epoch,
                source_id,
                expected_previous_epoch=current.connection_epoch,
            )
            next_event_index = 0
        if (
            current.state == OpcUaPersistentSessionState.RECONNECT_WAIT
            and state == OpcUaPersistentSessionState.CONNECTING
        ):
            reconnect_attempt += 1
        candidate = OpcUaPersistentSessionEvidence(
            source_id=source_id,
            state=state,
            changed_at=changed_at,
            connection_epoch=epoch,
            reconnect_attempt_index=reconnect_attempt,
            detail=detail,
        )
        validate_opcua_persistent_session_transition(current, candidate)
        _record_session_evidence(
            session_evidence_sink,
            telemetry_recorder,
            candidate,
        )
        current = candidate

    async def _process_state(event: OpcUaConnectorStateEvent) -> None:
        nonlocal overflow_pending
        if event.state == OpcUaConnectorConnectionState.RECONNECTING:
            if current.state in {
                OpcUaPersistentSessionState.CONNECTED,
                OpcUaPersistentSessionState.CONNECTING,
            }:
                detail = (
                    "subscription-queue-overflow" if overflow_pending else "asyncua-reconnecting"
                )
                overflow_pending = False
                await _transition(
                    OpcUaPersistentSessionState.RECONNECT_WAIT,
                    changed_at=event.occurred_at,
                    detail=detail,
                )
            return
        if event.state == OpcUaConnectorConnectionState.CONNECTING:
            if current.state == OpcUaPersistentSessionState.RECONNECT_WAIT:
                await _transition(
                    OpcUaPersistentSessionState.CONNECTING,
                    changed_at=event.occurred_at,
                )
            return
        if (
            event.state == OpcUaConnectorConnectionState.CONNECTED
            and current.state == OpcUaPersistentSessionState.CONNECTING
        ):
            await _transition(
                OpcUaPersistentSessionState.CONNECTED,
                changed_at=event.occurred_at,
            )

    try:
        await _transition(
            OpcUaPersistentSessionState.CONNECTING,
            changed_at=_now(now_fn),
        )
        await connector.start()
        await _transition(
            OpcUaPersistentSessionState.CONNECTED,
            changed_at=_now(now_fn),
        )

        state_task = asyncio.create_task(connector.next_state())
        notification_task = asyncio.create_task(connector.next_notification())
        overflow_task = asyncio.create_task(connector.next_queue_overflow())
        stop_task = asyncio.create_task(stop_event.wait())

        while True:
            wait_set: set[asyncio.Task[object]] = {
                state_task,
                notification_task,
                overflow_task,
                stop_task,
            }
            done, _ = await asyncio.wait(
                wait_set,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if stop_task in done:
                break

            if overflow_task in done:
                overflow = overflow_task.result()
                queue_overflow_count += 1
                overflow_pending = True
                if telemetry_recorder is not None:
                    _record_telemetry_best_effort(
                        lambda overflow=overflow: telemetry_recorder.record_callback_queue_overflow(
                            source_id,
                            occurred_at=overflow.occurred_at,
                        ),
                        label="callback queue overflow",
                    )
                overflow_task = asyncio.create_task(connector.next_queue_overflow())

            if state_task in done:
                while state_task.done():
                    await _process_state(state_task.result())
                    state_task = asyncio.create_task(connector.next_state())
                    await asyncio.sleep(0)

            if notification_task in done:
                # Give an already-buffered reconnect state transition priority over
                # data so replay/new notifications use the new connection epoch.
                await asyncio.sleep(0)
                if state_task.done():
                    while state_task.done():
                        await _process_state(state_task.result())
                        state_task = asyncio.create_task(connector.next_state())
                        await asyncio.sleep(0)

                notification = notification_task.result()
                notification_task = asyncio.create_task(connector.next_notification())
                if notification is None:
                    continue
                if current.state != OpcUaPersistentSessionState.CONNECTED:
                    raise RuntimeError(
                        "OPC UA DataChange arrived while application session is not CONNECTED"
                    )

                registered = RegisteredOpcUaDataChangeEvent(
                    source_id=source_id,
                    asset_id=source.asset_id,
                    endpoint_url=config.endpoint_url,
                    measurement_point_id=source.measurement_point_id,
                    collection_index=next_event_index,
                    notification=notification,
                )
                persistent_event = await asyncio.to_thread(
                    spool.accept_opcua_event,
                    registered,
                    connection_epoch=current.connection_epoch,
                    event_index=next_event_index,
                    accepted_at=_now(now_fn),
                    event_time_policy=effective_event_time_policy,
                )
                if telemetry_recorder is not None:
                    _record_telemetry_best_effort(
                        lambda persistent_event=persistent_event: telemetry_recorder.record_opcua_event(
                            persistent_event
                        ),
                        label="OPC UA flow event",
                    )
                accepted_event_count += 1
                if notification.replayed:
                    replayed_event_count += 1
                next_event_index += 1

    except BaseException as error:
        stop_detail = f"worker-error:{type(error).__name__}"
        if telemetry_recorder is not None and isinstance(error, Exception):
            failure_at = _now(now_fn)
            failure_detail = _failure_detail(error)
            _record_telemetry_best_effort(
                lambda failure_at=failure_at, failure_detail=failure_detail: telemetry_recorder.record_failure(
                    AcquisitionFailureTelemetry(
                        source_id=source_id,
                        component=AcquisitionFailureComponent.OPCUA_WORKER,
                        occurred_at=failure_at,
                        detail=failure_detail,
                    )
                ),
                label="OPC UA worker failure",
            )
        raise
    finally:
        for task in (
            state_task,
            notification_task,
            overflow_task,
            stop_task,
        ):
            if task is not None and not task.done():
                task.cancel()
        pending_tasks = tuple(
            task
            for task in (
                state_task,
                notification_task,
                overflow_task,
                stop_task,
            )
            if task is not None
        )
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)

        await connector.close()
        if current.state != OpcUaPersistentSessionState.STOPPED:
            await _transition(
                OpcUaPersistentSessionState.STOPPED,
                changed_at=_now(now_fn),
                detail=stop_detail,
            )

    stopped_at = current.changed_at
    return OpcUaAcquisitionWorkerResult(
        source_id=source_id,
        started_at=started_at,
        stopped_at=stopped_at,
        accepted_event_count=accepted_event_count,
        replayed_event_count=replayed_event_count,
        queue_overflow_count=queue_overflow_count,
    )


def _record_session_evidence(
    session_evidence_sink: OpcUaPersistentSessionEvidenceSink,
    telemetry_recorder: AcquisitionTelemetryRecorder | None,
    evidence: OpcUaPersistentSessionEvidence,
) -> None:
    session_evidence_sink.record_session_evidence(evidence)
    if telemetry_recorder is not None and telemetry_recorder is not session_evidence_sink:
        _record_telemetry_best_effort(
            lambda: telemetry_recorder.record_session_evidence(evidence),
            label="session evidence",
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


def _validate_asyncua_reconnect_policy(policy: OpcUaPersistentSessionPolicy) -> None:
    if policy.reconnect_initial_delay_seconds != 1.0:
        raise ValueError(
            "asyncua 2.0.1 persistent worker requires reconnect_initial_delay_seconds == 1.0"
        )
    if policy.reconnect_backoff_multiplier != 2.0:
        raise ValueError(
            "asyncua 2.0.1 persistent worker requires reconnect_backoff_multiplier == 2.0"
        )


def _now(now_fn: NowFunction) -> datetime:
    value = now_fn()
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("now_fn must return a timezone-aware datetime")
    return value
