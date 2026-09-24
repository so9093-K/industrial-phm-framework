"""Bounded OPC UA subscription collection for registered operational sources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from industrial_phm.application.source_cycle import (
    SourceRuntimeCycleFailureScope,
    SourceRuntimeCycleState,
)
from industrial_phm.application.source_lifecycle import (
    SourceLifecycleRecord,
    SourceLifecycleRepository,
    SourceLifecycleState,
    transition_source_lifecycle,
)
from industrial_phm.application.source_registration import (
    OpcUaSourceConfig,
    SourceRepository,
)
from industrial_phm.application.source_runtime import (
    SourceConnectionAttemptEvidence,
    SourceConnectionAttemptOperation,
    SourceConnectionAttemptOutcome,
    SourceRuntimeRepository,
)
from industrial_phm.connectors import (
    OpcUaNodeMapping,
    OpcUaRuntimeUnavailableError,
    OpcUaSourceError,
    OpcUaSubscriptionConfig,
    OpcUaSubscriptionNotification,
    OpcUaSubscriptionResult,
    collect_opcua_subscription_notifications,
)


@dataclass(frozen=True, slots=True)
class RegisteredOpcUaDataChangeEvent:
    """One registered-source DataChange event with application identity.

    collection_index is the zero-based order in this bounded collection result. It is
    not an OPC UA server sequence number and does not prove gap-free delivery.
    """

    source_id: str
    asset_id: str
    endpoint_url: str
    collection_index: int
    notification: OpcUaSubscriptionNotification
    measurement_point_id: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        _validate_identifier(self.asset_id, "asset_id")
        _validate_identifier(self.endpoint_url, "endpoint_url")
        if self.measurement_point_id is not None:
            _validate_identifier(self.measurement_point_id, "measurement_point_id")
        if isinstance(self.collection_index, bool) or not isinstance(self.collection_index, int):
            raise ValueError("collection_index must be an integer")
        if self.collection_index < 0:
            raise ValueError("collection_index must not be negative")
        if not isinstance(self.notification, OpcUaSubscriptionNotification):
            raise ValueError("notification must be an OpcUaSubscriptionNotification")

    @property
    def channel_id(self) -> str:
        """Return the registered channel carried by this event."""
        return self.notification.observation.channel_id

    @property
    def node_id(self) -> str:
        """Return the OPC UA NodeId carried by this event."""
        return self.notification.observation.node_id


@dataclass(frozen=True, slots=True)
class RegisteredOpcUaSubscriptionCoverage:
    """Configured-channel coverage within one bounded subscription result.

    Full channel coverage means every registered channel appeared at least once in this
    bounded collection. It does not imply timestamp alignment, a synchronized snapshot,
    gap-free delivery, or an analysis-ready observation window.
    """

    configured_channel_ids: tuple[str, ...]
    observed_channel_ids: tuple[str, ...]
    missing_channel_ids: tuple[str, ...]
    notification_count: int
    has_full_channel_coverage: bool

    def __post_init__(self) -> None:
        _validate_channel_id_tuple(self.configured_channel_ids, "configured_channel_ids")
        _validate_channel_id_tuple(self.observed_channel_ids, "observed_channel_ids")
        _validate_channel_id_tuple(self.missing_channel_ids, "missing_channel_ids")
        if not self.configured_channel_ids:
            raise ValueError("configured_channel_ids must not be empty")
        if not isinstance(self.has_full_channel_coverage, bool):
            raise ValueError("has_full_channel_coverage must be boolean")
        if isinstance(self.notification_count, bool) or not isinstance(
            self.notification_count, int
        ):
            raise ValueError("notification_count must be an integer")
        if self.notification_count < 0:
            raise ValueError("notification_count must not be negative")
        if self.notification_count < len(self.observed_channel_ids):
            raise ValueError("notification_count must cover every observed channel at least once")

        configured = set(self.configured_channel_ids)
        observed = set(self.observed_channel_ids)
        missing = set(self.missing_channel_ids)
        if not observed <= configured:
            raise ValueError("observed_channel_ids must be configured channels")
        if missing != configured - observed:
            raise ValueError("missing_channel_ids must match configured minus observed channels")
        expected_observed = tuple(
            channel_id for channel_id in self.configured_channel_ids if channel_id in observed
        )
        expected_missing = tuple(
            channel_id for channel_id in self.configured_channel_ids if channel_id in missing
        )
        if self.observed_channel_ids != expected_observed:
            raise ValueError("observed_channel_ids must preserve configured channel order")
        if self.missing_channel_ids != expected_missing:
            raise ValueError("missing_channel_ids must preserve configured channel order")
        if self.has_full_channel_coverage != (not missing):
            raise ValueError(
                "has_full_channel_coverage must match whether missing_channel_ids is empty"
            )


@dataclass(frozen=True, slots=True)
class RegisteredOpcUaSubscription:
    """One bounded subscription result tied to registered source identity and mapping.

    The notification sequence is event-level evidence. Its length does not imply that
    every configured channel produced a notification or that a complete observation
    snapshot/window exists.
    """

    source_id: str
    asset_id: str
    endpoint_url: str
    node_mappings: tuple[OpcUaNodeMapping, ...]
    subscription: OpcUaSubscriptionResult
    measurement_point_id: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        _validate_identifier(self.asset_id, "asset_id")
        _validate_identifier(self.endpoint_url, "endpoint_url")
        if self.measurement_point_id is not None:
            _validate_identifier(self.measurement_point_id, "measurement_point_id")
        if not self.node_mappings:
            raise ValueError("node_mappings must not be empty")
        if not all(isinstance(mapping, OpcUaNodeMapping) for mapping in self.node_mappings):
            raise ValueError("node_mappings must contain OpcUaNodeMapping values")
        if not isinstance(self.subscription, OpcUaSubscriptionResult):
            raise ValueError("subscription must be an OpcUaSubscriptionResult")
        if self.subscription.endpoint_url != self.endpoint_url:
            raise ValueError("subscription endpoint_url must match the registered OPC UA endpoint")

        mapping_pairs = {(mapping.channel_id, mapping.node_id) for mapping in self.node_mappings}
        for notification in self.subscription.notifications:
            observation = notification.observation
            if (observation.channel_id, observation.node_id) not in mapping_pairs:
                raise ValueError(
                    "subscription notification must match the registered OPC UA mapping"
                )

    @property
    def events(self) -> tuple[RegisteredOpcUaDataChangeEvent, ...]:
        """Return event-level application identity without inventing stream completeness."""
        return tuple(
            RegisteredOpcUaDataChangeEvent(
                source_id=self.source_id,
                asset_id=self.asset_id,
                endpoint_url=self.endpoint_url,
                measurement_point_id=self.measurement_point_id,
                collection_index=index,
                notification=notification,
            )
            for index, notification in enumerate(self.subscription.notifications)
        )

    @property
    def coverage(self) -> RegisteredOpcUaSubscriptionCoverage:
        """Summarize registered-channel coverage for this bounded collection."""
        configured = tuple(mapping.channel_id for mapping in self.node_mappings)
        observed_set = {event.channel_id for event in self.events}
        observed = tuple(channel_id for channel_id in configured if channel_id in observed_set)
        missing = tuple(channel_id for channel_id in configured if channel_id not in observed_set)
        return RegisteredOpcUaSubscriptionCoverage(
            configured_channel_ids=configured,
            observed_channel_ids=observed,
            missing_channel_ids=missing,
            notification_count=len(self.subscription.notifications),
            has_full_channel_coverage=not missing,
        )


@dataclass(frozen=True, slots=True)
class RegisteredOpcUaSubscriptionCycleResult:
    """Result of one lifecycle-aware bounded registered OPC UA subscription cycle."""

    source_id: str
    state: SourceRuntimeCycleState
    executed_at: datetime
    lifecycle_before: SourceLifecycleRecord
    lifecycle_after: SourceLifecycleRecord
    subscription: RegisteredOpcUaSubscription | None = None
    failure_scope: SourceRuntimeCycleFailureScope | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        if not isinstance(self.state, SourceRuntimeCycleState):
            raise ValueError("state must be a SourceRuntimeCycleState")
        if self.failure_scope is not None and not isinstance(
            self.failure_scope,
            SourceRuntimeCycleFailureScope,
        ):
            raise ValueError("failure_scope must be a SourceRuntimeCycleFailureScope when provided")
        _validate_aware_datetime(self.executed_at, "executed_at")
        if self.lifecycle_before.source_id != self.source_id:
            raise ValueError("lifecycle_before must match source_id")
        if self.lifecycle_after.source_id != self.source_id:
            raise ValueError("lifecycle_after must match source_id")

        if self.state == SourceRuntimeCycleState.SUCCEEDED:
            if self.subscription is None:
                raise ValueError("succeeded subscription cycle requires subscription result")
            if self.failure_scope is not None:
                raise ValueError("succeeded subscription cycle must not carry failure_scope")
            if self.message is not None:
                raise ValueError("succeeded subscription cycle must not carry a message")
            if self.lifecycle_after.state != SourceLifecycleState.ACTIVE:
                raise ValueError("succeeded subscription cycle must remain active")
        else:
            if self.message is None or not self.message.strip():
                raise ValueError("non-success subscription cycle requires a message")

        if self.state == SourceRuntimeCycleState.SKIPPED:
            if self.subscription is not None:
                raise ValueError("skipped subscription cycle must not carry subscription result")
            if self.failure_scope is not None:
                raise ValueError("skipped subscription cycle must not carry failure_scope")
            if self.lifecycle_after != self.lifecycle_before:
                raise ValueError("skipped subscription cycle must not change lifecycle")
        elif self.state == SourceRuntimeCycleState.FAILED:
            if self.failure_scope is None:
                raise ValueError("failed subscription cycle requires failure_scope")
            if self.failure_scope == SourceRuntimeCycleFailureScope.SOURCE:
                if self.lifecycle_before.state != SourceLifecycleState.ACTIVE:
                    raise ValueError("source failure requires an active lifecycle_before")
                if (
                    self.lifecycle_after != self.lifecycle_before
                    and self.lifecycle_after.state != SourceLifecycleState.ERROR
                ):
                    raise ValueError(
                        "source failure may only preserve active lifecycle or transition to error"
                    )
            elif self.lifecycle_after != self.lifecycle_before:
                raise ValueError("platform failure must not change source lifecycle")


async def collect_registered_opcua_source_subscription(
    source_repository: SourceRepository,
    lifecycle_repository: SourceLifecycleRepository,
    source_id: str,
    *,
    publishing_interval_ms: float = 500.0,
    collection_timeout_seconds: float = 5.0,
    max_events: int = 1,
    queue_maxsize: int = 128,
) -> RegisteredOpcUaSubscription:
    """Collect one bounded subscription session for an ACTIVE registered OPC UA source.

    Endpoint, explicit NodeId mapping and request timeout always come from the registered
    source. Runtime collection bounds are supplied by this explicit call. The function
    does not persist notifications, mutate lifecycle, infer complete-channel observations,
    retry, reconnect, or create background execution.
    """
    source = source_repository.get(source_id)
    lifecycle = lifecycle_repository.get_lifecycle(source_id)
    if lifecycle.state != SourceLifecycleState.ACTIVE:
        raise ValueError(
            "registered OPC UA subscription collection requires an active source lifecycle"
        )

    config = source.config
    if not isinstance(config, OpcUaSourceConfig):
        raise ValueError("registered OPC UA subscription requires OpcUaSourceConfig")

    subscription_config = OpcUaSubscriptionConfig(
        endpoint_url=config.endpoint_url,
        node_mappings=tuple(config.node_mappings),
        publishing_interval_ms=publishing_interval_ms,
        collection_timeout_seconds=collection_timeout_seconds,
        max_events=max_events,
        queue_maxsize=queue_maxsize,
        timeout_seconds=config.timeout_seconds,
    )
    result = await collect_opcua_subscription_notifications(subscription_config)
    return RegisteredOpcUaSubscription(
        source_id=source.source_id,
        asset_id=config.asset_id,
        endpoint_url=config.endpoint_url,
        measurement_point_id=config.measurement_point_id,
        node_mappings=tuple(config.node_mappings),
        subscription=result,
    )


async def run_registered_opcua_subscription_cycle(
    source_repository: SourceRepository,
    lifecycle_repository: SourceLifecycleRepository,
    runtime_repository: SourceRuntimeRepository,
    source_id: str,
    *,
    executed_at: datetime | None = None,
    publishing_interval_ms: float = 500.0,
    collection_timeout_seconds: float = 5.0,
    max_events: int = 1,
    queue_maxsize: int = 128,
) -> RegisteredOpcUaSubscriptionCycleResult:
    """Run one lifecycle-aware bounded subscription cycle for an ACTIVE OPC UA source.

    The cycle persists latest connection-attempt evidence only. It does not create receipt
    evidence or freshness because bounded DataChange channel coverage is not a complete
    operational observation/window.
    """
    source = source_repository.get(source_id)
    lifecycle_before = lifecycle_repository.get_lifecycle(source_id)
    cycle_time = datetime.now(UTC) if executed_at is None else executed_at
    _validate_cycle_time(cycle_time, lifecycle_before)

    if lifecycle_before.state != SourceLifecycleState.ACTIVE:
        return RegisteredOpcUaSubscriptionCycleResult(
            source_id=source_id,
            state=SourceRuntimeCycleState.SKIPPED,
            executed_at=cycle_time,
            lifecycle_before=lifecycle_before,
            lifecycle_after=lifecycle_before,
            message=(
                f"source lifecycle is {lifecycle_before.state.value}; "
                "subscription cycle requires active"
            ),
        )

    if not isinstance(source.config, OpcUaSourceConfig):
        return RegisteredOpcUaSubscriptionCycleResult(
            source_id=source_id,
            state=SourceRuntimeCycleState.SKIPPED,
            executed_at=cycle_time,
            lifecycle_before=lifecycle_before,
            lifecycle_after=lifecycle_before,
            message=(
                f"registered source type is {source.source_type.value}; "
                "opcua subscription cycle requires opcua"
            ),
        )

    attempt_started_at = datetime.now(UTC)
    try:
        subscription = await collect_registered_opcua_source_subscription(
            source_repository,
            lifecycle_repository,
            source_id,
            publishing_interval_ms=publishing_interval_ms,
            collection_timeout_seconds=collection_timeout_seconds,
            max_events=max_events,
            queue_maxsize=queue_maxsize,
        )
    except OpcUaSourceError as error:
        detail = _record_failed_subscription_attempt(
            runtime_repository,
            source_id,
            attempt_started_at,
            error,
        )
        return _failed_subscription_cycle(
            lifecycle_repository,
            source_id,
            lifecycle_before,
            cycle_time,
            error,
            failure_scope=SourceRuntimeCycleFailureScope.SOURCE,
            detail_override=detail,
        )
    except OSError as error:
        detail = _record_failed_subscription_attempt(
            runtime_repository,
            source_id,
            attempt_started_at,
            error,
        )
        return _failed_subscription_cycle(
            lifecycle_repository,
            source_id,
            lifecycle_before,
            cycle_time,
            error,
            failure_scope=SourceRuntimeCycleFailureScope.SOURCE,
            detail_override=detail,
            transition_source_to_error=False,
        )
    except (OpcUaRuntimeUnavailableError, ValueError) as error:
        return _failed_subscription_cycle(
            lifecycle_repository,
            source_id,
            lifecycle_before,
            cycle_time,
            error,
            failure_scope=SourceRuntimeCycleFailureScope.PLATFORM,
        )
    except Exception as error:
        return _failed_subscription_cycle(
            lifecycle_repository,
            source_id,
            lifecycle_before,
            cycle_time,
            error,
            failure_scope=SourceRuntimeCycleFailureScope.PLATFORM,
        )

    connector_result = subscription.subscription
    attempt = SourceConnectionAttemptEvidence(
        source_id=source_id,
        operation=SourceConnectionAttemptOperation.OPCUA_SUBSCRIPTION,
        outcome=SourceConnectionAttemptOutcome.SUCCEEDED,
        attempted_at=min(attempt_started_at, connector_result.connected_at),
        connected_at=connector_result.connected_at,
        completed_at=connector_result.completed_at,
    )
    try:
        runtime_repository.record_connection_attempt(attempt)
    except (OSError, ValueError) as error:
        return _failed_subscription_cycle(
            lifecycle_repository,
            source_id,
            lifecycle_before,
            cycle_time,
            error,
            failure_scope=SourceRuntimeCycleFailureScope.PLATFORM,
            subscription=subscription,
        )

    return RegisteredOpcUaSubscriptionCycleResult(
        source_id=source_id,
        state=SourceRuntimeCycleState.SUCCEEDED,
        executed_at=cycle_time,
        lifecycle_before=lifecycle_before,
        lifecycle_after=lifecycle_before,
        subscription=subscription,
    )


def _record_failed_subscription_attempt(
    runtime_repository: SourceRuntimeRepository,
    source_id: str,
    attempted_at: datetime,
    error: Exception,
) -> str:
    completed_at = datetime.now(UTC)
    detail = _failure_detail(error)
    attempt = SourceConnectionAttemptEvidence(
        source_id=source_id,
        operation=SourceConnectionAttemptOperation.OPCUA_SUBSCRIPTION,
        outcome=SourceConnectionAttemptOutcome.FAILED,
        attempted_at=attempted_at,
        completed_at=completed_at,
        detail=detail,
    )
    try:
        runtime_repository.record_connection_attempt(attempt)
    except (OSError, ValueError) as persistence_error:
        detail = (
            f"{detail}; connection-attempt persistence failed: {_failure_detail(persistence_error)}"
        )
    return detail


def _failed_subscription_cycle(
    lifecycle_repository: SourceLifecycleRepository,
    source_id: str,
    lifecycle_before: SourceLifecycleRecord,
    cycle_time: datetime,
    error: Exception,
    *,
    failure_scope: SourceRuntimeCycleFailureScope,
    subscription: RegisteredOpcUaSubscription | None = None,
    detail_override: str | None = None,
    transition_source_to_error: bool = True,
) -> RegisteredOpcUaSubscriptionCycleResult:
    detail = _failure_detail(error) if detail_override is None else detail_override
    lifecycle_after = lifecycle_before
    if failure_scope == SourceRuntimeCycleFailureScope.SOURCE and transition_source_to_error:
        lifecycle_after = transition_source_lifecycle(
            lifecycle_repository,
            source_id,
            SourceLifecycleState.ERROR,
            changed_at=cycle_time,
            detail=detail,
        )
    return RegisteredOpcUaSubscriptionCycleResult(
        source_id=source_id,
        state=SourceRuntimeCycleState.FAILED,
        executed_at=cycle_time,
        lifecycle_before=lifecycle_before,
        lifecycle_after=lifecycle_after,
        subscription=subscription,
        failure_scope=failure_scope,
        message=detail,
    )


def _validate_cycle_time(
    executed_at: datetime,
    lifecycle: SourceLifecycleRecord,
) -> None:
    _validate_aware_datetime(executed_at, "executed_at")
    if executed_at < lifecycle.changed_at:
        raise ValueError("executed_at must not be before the current lifecycle change")


def _failure_detail(error: Exception) -> str:
    message = str(error).strip()
    if message:
        return f"{type(error).__name__}: {message}"
    return type(error).__name__


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")


def _validate_channel_id_tuple(values: tuple[str, ...], field_name: str) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{field_name} must be a tuple")
    if any(
        not isinstance(value, str) or not value.strip() or value != value.strip()
        for value in values
    ):
        raise ValueError(f"{field_name} must contain non-empty trimmed strings")
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must not contain duplicates")


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
