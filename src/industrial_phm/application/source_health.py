"""Multidimensional source-health read model without invented connectivity evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from industrial_phm.application.source_freshness import (
    SourceFreshnessAssessment,
    SourceFreshnessPolicy,
    SourceFreshnessState,
    assess_source_freshness,
)
from industrial_phm.application.source_lifecycle import (
    SourceLifecycleRecord,
    SourceLifecycleState,
)
from industrial_phm.application.source_receipt import SourceReceiptEvidence


class SourceConnectionState(StrEnum):
    """Connection evidence state currently supported by the prepared-file runtime."""

    NOT_INSTRUMENTED = "not-instrumented"


class SourceDataFlowState(StrEnum):
    """Observed data-flow state derived without claiming connector health."""

    INACTIVE = "inactive"
    SOURCE_ERROR = "source-error"
    NO_RECEIPT = "no-receipt"
    FRESHNESS_NOT_CONFIGURED = "freshness-not-configured"
    FRESH = "fresh"
    STALE = "stale"
    TIMING_UNAVAILABLE = "timing-unavailable"


@dataclass(frozen=True, slots=True)
class SourceHealthAssessment:
    """Read model combining control-plane and measured timing evidence.

    This model intentionally has no boolean healthy flag. Connection state remains
    NOT_INSTRUMENTED until a connector runtime supplies actual connection telemetry.
    """

    source_id: str
    assessed_at: datetime
    lifecycle: SourceLifecycleRecord
    connection_state: SourceConnectionState
    data_flow_state: SourceDataFlowState
    receipt: SourceReceiptEvidence | None = None
    freshness: SourceFreshnessAssessment | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        if not isinstance(self.assessed_at, datetime) or self.assessed_at.utcoffset() is None:
            raise ValueError("assessed_at must be a timezone-aware datetime")
        if not isinstance(self.lifecycle, SourceLifecycleRecord):
            raise ValueError("lifecycle must be a SourceLifecycleRecord")
        if self.lifecycle.source_id != self.source_id:
            raise ValueError("lifecycle must match source_id")
        if not isinstance(self.connection_state, SourceConnectionState):
            raise ValueError("connection_state must be a SourceConnectionState")
        if not isinstance(self.data_flow_state, SourceDataFlowState):
            raise ValueError("data_flow_state must be a SourceDataFlowState")
        if self.receipt is not None:
            if not isinstance(self.receipt, SourceReceiptEvidence):
                raise ValueError("receipt must be SourceReceiptEvidence when provided")
            if self.receipt.source_id != self.source_id:
                raise ValueError("receipt must match source_id")
        if self.freshness is not None:
            if not isinstance(self.freshness, SourceFreshnessAssessment):
                raise ValueError("freshness must be SourceFreshnessAssessment when provided")
            if self.freshness.source_id != self.source_id:
                raise ValueError("freshness must match source_id")

        if self.data_flow_state in {
            SourceDataFlowState.FRESHNESS_NOT_CONFIGURED,
            SourceDataFlowState.FRESH,
            SourceDataFlowState.STALE,
            SourceDataFlowState.TIMING_UNAVAILABLE,
        } and self.receipt is None:
            raise ValueError("timing-derived data-flow state requires receipt evidence")

        if self.data_flow_state in {
            SourceDataFlowState.FRESHNESS_NOT_CONFIGURED,
            SourceDataFlowState.FRESH,
            SourceDataFlowState.STALE,
            SourceDataFlowState.TIMING_UNAVAILABLE,
        } and self.freshness is None:
            raise ValueError("timing-derived data-flow state requires freshness assessment")

    @property
    def latest_received_at(self) -> datetime | None:
        """Return the latest accepted receipt time when evidence exists."""
        return None if self.receipt is None else self.receipt.received_at

    @property
    def latest_observed_at(self) -> datetime | None:
        """Return the latest source observation time when evidence exists."""
        return None if self.receipt is None else self.receipt.observed_at

    @property
    def delivery_lag_seconds(self) -> float | None:
        """Return observed-to-received delivery lag when timestamps are comparable."""
        return None if self.receipt is None else self.receipt.lag_seconds


def assess_source_health(
    lifecycle: SourceLifecycleRecord,
    receipt: SourceReceiptEvidence | None,
    freshness_policy: SourceFreshnessPolicy | None,
    *,
    as_of: datetime,
) -> SourceHealthAssessment:
    """Combine explicit lifecycle and timing facts into a source-health read model.

    No connection success is inferred from file readability, receipt existence, or
    freshness. The prepared-file runtime has no connector telemetry, so connection state
    remains NOT_INSTRUMENTED.
    """
    if not isinstance(lifecycle, SourceLifecycleRecord):
        raise ValueError("lifecycle must be a SourceLifecycleRecord")
    if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
        raise ValueError("as_of must be a timezone-aware datetime")
    if receipt is not None:
        if not isinstance(receipt, SourceReceiptEvidence):
            raise ValueError("receipt must be SourceReceiptEvidence when provided")
        if receipt.source_id != lifecycle.source_id:
            raise ValueError("lifecycle and receipt must share one source_id")
    if freshness_policy is not None:
        if not isinstance(freshness_policy, SourceFreshnessPolicy):
            raise ValueError("freshness_policy must be SourceFreshnessPolicy when provided")
        if freshness_policy.source_id != lifecycle.source_id:
            raise ValueError("lifecycle and freshness policy must share one source_id")

    connection_state = SourceConnectionState.NOT_INSTRUMENTED

    if lifecycle.state == SourceLifecycleState.ERROR:
        return SourceHealthAssessment(
            source_id=lifecycle.source_id,
            assessed_at=as_of,
            lifecycle=lifecycle,
            connection_state=connection_state,
            data_flow_state=SourceDataFlowState.SOURCE_ERROR,
            receipt=receipt,
            reason=lifecycle.detail,
        )

    if lifecycle.state != SourceLifecycleState.ACTIVE:
        return SourceHealthAssessment(
            source_id=lifecycle.source_id,
            assessed_at=as_of,
            lifecycle=lifecycle,
            connection_state=connection_state,
            data_flow_state=SourceDataFlowState.INACTIVE,
            receipt=receipt,
            reason=f"source lifecycle is {lifecycle.state.value}",
        )

    if receipt is None:
        return SourceHealthAssessment(
            source_id=lifecycle.source_id,
            assessed_at=as_of,
            lifecycle=lifecycle,
            connection_state=connection_state,
            data_flow_state=SourceDataFlowState.NO_RECEIPT,
            reason="active source has no accepted receipt evidence",
        )

    if receipt.received_at < lifecycle.changed_at:
        return SourceHealthAssessment(
            source_id=lifecycle.source_id,
            assessed_at=as_of,
            lifecycle=lifecycle,
            connection_state=connection_state,
            data_flow_state=SourceDataFlowState.NO_RECEIPT,
            receipt=receipt,
            reason=(
                "latest receipt predates the current active lifecycle transition; "
                "current activation has no accepted receipt evidence"
            ),
        )

    freshness = assess_source_freshness(
        receipt,
        freshness_policy,
        as_of=as_of,
    )
    data_flow_state = _data_flow_state_from_freshness(freshness.state)
    return SourceHealthAssessment(
        source_id=lifecycle.source_id,
        assessed_at=as_of,
        lifecycle=lifecycle,
        connection_state=connection_state,
        data_flow_state=data_flow_state,
        receipt=receipt,
        freshness=freshness,
        reason=freshness.reason,
    )


def _data_flow_state_from_freshness(state: SourceFreshnessState) -> SourceDataFlowState:
    if state == SourceFreshnessState.FRESH:
        return SourceDataFlowState.FRESH
    if state == SourceFreshnessState.STALE:
        return SourceDataFlowState.STALE
    if state == SourceFreshnessState.NOT_CONFIGURED:
        return SourceDataFlowState.FRESHNESS_NOT_CONFIGURED
    return SourceDataFlowState.TIMING_UNAVAILABLE


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
