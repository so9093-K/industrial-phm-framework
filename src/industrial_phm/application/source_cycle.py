"""Single-iteration runtime execution for active registered file sources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from industrial_phm.application.source_lifecycle import (
    SourceLifecycleRecord,
    SourceLifecycleRepository,
    SourceLifecycleState,
    transition_source_lifecycle,
)
from industrial_phm.application.source_receipt import (
    ReceivedRegisteredFileObservation,
    receive_registered_file_source_observation,
)
from industrial_phm.application.source_registration import SourceRepository
from industrial_phm.application.source_runtime import SourceRuntimeRepository


class SourceRuntimeCycleState(StrEnum):
    """Outcome of one explicit source-runtime execution cycle."""

    SKIPPED = "skipped"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SourceRuntimeCycleFailureScope(StrEnum):
    """Scope owning a failed runtime cycle."""

    SOURCE = "source"
    PLATFORM = "platform"


@dataclass(frozen=True, slots=True)
class SourceRuntimeCycleResult:
    """Result of one runtime attempt against a registered file source."""

    source_id: str
    state: SourceRuntimeCycleState
    executed_at: datetime
    lifecycle_before: SourceLifecycleRecord
    lifecycle_after: SourceLifecycleRecord
    received: ReceivedRegisteredFileObservation | None = None
    failure_scope: SourceRuntimeCycleFailureScope | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        if self.source_id != self.source_id.strip():
            raise ValueError("source_id must not contain surrounding whitespace")
        if not isinstance(self.state, SourceRuntimeCycleState):
            raise ValueError("state must be a SourceRuntimeCycleState")
        if not isinstance(self.executed_at, datetime) or self.executed_at.utcoffset() is None:
            raise ValueError("executed_at must be a timezone-aware datetime")
        if self.lifecycle_before.source_id != self.source_id:
            raise ValueError("lifecycle_before must match source_id")
        if self.lifecycle_after.source_id != self.source_id:
            raise ValueError("lifecycle_after must match source_id")

        if self.state == SourceRuntimeCycleState.SUCCEEDED:
            if self.received is None:
                raise ValueError("succeeded runtime cycle requires received observation")
            if self.failure_scope is not None:
                raise ValueError("succeeded runtime cycle must not carry failure_scope")
            if self.message is not None:
                raise ValueError("succeeded runtime cycle must not carry a message")
            if self.lifecycle_after.state != SourceLifecycleState.ACTIVE:
                raise ValueError("succeeded runtime cycle must remain active")
        else:
            if self.message is None or not self.message.strip():
                raise ValueError("non-success runtime cycle requires a message")

        if self.state == SourceRuntimeCycleState.SKIPPED:
            if self.received is not None:
                raise ValueError("skipped runtime cycle must not carry received observation")
            if self.failure_scope is not None:
                raise ValueError("skipped runtime cycle must not carry failure_scope")
            if self.lifecycle_after != self.lifecycle_before:
                raise ValueError("skipped runtime cycle must not change lifecycle")
        elif self.state == SourceRuntimeCycleState.FAILED:
            if self.failure_scope is None:
                raise ValueError("failed runtime cycle requires failure_scope")
            if self.failure_scope == SourceRuntimeCycleFailureScope.SOURCE:
                if self.lifecycle_after.state != SourceLifecycleState.ERROR:
                    raise ValueError("source failure must transition lifecycle to error")
            elif self.lifecycle_after != self.lifecycle_before:
                raise ValueError("platform failure must not change source lifecycle")


def run_registered_file_source_cycle(
    source_repository: SourceRepository,
    lifecycle_repository: SourceLifecycleRepository,
    runtime_repository: SourceRuntimeRepository,
    source_id: str,
    *,
    executed_at: datetime | None = None,
    received_at: datetime | None = None,
) -> SourceRuntimeCycleResult:
    """Run one ACTIVE registered-file source cycle.

    REGISTERED, PAUSED, or ERROR sources are skipped without source I/O. ACTIVE sources
    re-validate the current source bytes, create receipt evidence, and persist the latest
    receipt. Source validation/I/O failures transition lifecycle ACTIVE -> ERROR with the
    concrete failure detail. Platform runtime-state failures fail the cycle without changing
    source lifecycle. This is one explicit iteration, not a scheduler or background poller.
    """
    source = source_repository.get(source_id)
    lifecycle_before = lifecycle_repository.get_lifecycle(source_id)
    cycle_time = datetime.now(UTC) if executed_at is None else executed_at
    _validate_cycle_time(cycle_time, lifecycle_before)

    if lifecycle_before.state != SourceLifecycleState.ACTIVE:
        return SourceRuntimeCycleResult(
            source_id=source_id,
            state=SourceRuntimeCycleState.SKIPPED,
            executed_at=cycle_time,
            lifecycle_before=lifecycle_before,
            lifecycle_after=lifecycle_before,
            message=(
                f"source lifecycle is {lifecycle_before.state.value}; "
                "runtime cycle requires active"
            ),
        )

    if received_at is not None and (
        not isinstance(received_at, datetime) or received_at.utcoffset() is None
    ):
        raise ValueError("received_at override must be a timezone-aware datetime")

    persisted_receipt = None
    if received_at is not None:
        try:
            persisted_receipt = runtime_repository.get_latest_receipt(source_id)
        except (OSError, ValueError) as error:
            return _failed_cycle(
                lifecycle_repository,
                source_id,
                lifecycle_before,
                cycle_time,
                error,
                failure_scope=SourceRuntimeCycleFailureScope.PLATFORM,
            )
        if persisted_receipt is not None and received_at < persisted_receipt.received_at:
            raise ValueError("received_at override must not move backwards")

    try:
        received = receive_registered_file_source_observation(
            source,
            received_at=received_at,
        )
    except (OSError, ValueError) as error:
        return _failed_cycle(
            lifecycle_repository,
            source_id,
            lifecycle_before,
            cycle_time,
            error,
            failure_scope=SourceRuntimeCycleFailureScope.SOURCE,
        )

    if (
        received_at is not None
        and persisted_receipt is not None
        and received_at == persisted_receipt.received_at
        and received.receipt != persisted_receipt
    ):
        raise ValueError(
            "received_at override matching persisted time must reproduce persisted evidence"
        )

    try:
        runtime_repository.record_receipt(received.receipt)
    except (OSError, ValueError) as error:
        return _failed_cycle(
            lifecycle_repository,
            source_id,
            lifecycle_before,
            cycle_time,
            error,
            failure_scope=SourceRuntimeCycleFailureScope.PLATFORM,
            received=received,
        )

    return SourceRuntimeCycleResult(
        source_id=source_id,
        state=SourceRuntimeCycleState.SUCCEEDED,
        executed_at=cycle_time,
        lifecycle_before=lifecycle_before,
        lifecycle_after=lifecycle_before,
        received=received,
    )


def _failed_cycle(
    lifecycle_repository: SourceLifecycleRepository,
    source_id: str,
    lifecycle_before: SourceLifecycleRecord,
    cycle_time: datetime,
    error: Exception,
    *,
    failure_scope: SourceRuntimeCycleFailureScope,
    received: ReceivedRegisteredFileObservation | None = None,
) -> SourceRuntimeCycleResult:
    detail = _failure_detail(error)
    lifecycle_after = lifecycle_before
    if failure_scope == SourceRuntimeCycleFailureScope.SOURCE:
        lifecycle_after = transition_source_lifecycle(
            lifecycle_repository,
            source_id,
            SourceLifecycleState.ERROR,
            changed_at=cycle_time,
            detail=detail,
        )
    return SourceRuntimeCycleResult(
        source_id=source_id,
        state=SourceRuntimeCycleState.FAILED,
        executed_at=cycle_time,
        lifecycle_before=lifecycle_before,
        lifecycle_after=lifecycle_after,
        received=received,
        failure_scope=failure_scope,
        message=detail,
    )


def _validate_cycle_time(
    executed_at: datetime,
    lifecycle: SourceLifecycleRecord,
) -> None:
    if not isinstance(executed_at, datetime) or executed_at.utcoffset() is None:
        raise ValueError("executed_at must be a timezone-aware datetime")
    if executed_at < lifecycle.changed_at:
        raise ValueError("executed_at must not be before the current lifecycle change")


def _failure_detail(error: Exception) -> str:
    message = str(error).strip()
    if message:
        return f"{type(error).__name__}: {message}"
    return type(error).__name__
