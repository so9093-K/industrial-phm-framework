"""Source-specific freshness policy and assessment contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite
from numbers import Real
from typing import Protocol, runtime_checkable

from industrial_phm.application.source_receipt import SourceReceiptEvidence


class SourceFreshnessState(StrEnum):
    """Freshness state derived only when policy and comparable timing evidence exist."""

    NOT_CONFIGURED = "not-configured"
    FRESH = "fresh"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class SourceFreshnessPolicy:
    """Persisted max observation-age policy for one registered source."""

    source_id: str
    max_observation_age_seconds: float
    changed_at: datetime

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        if (
            isinstance(self.max_observation_age_seconds, bool)
            or not isinstance(self.max_observation_age_seconds, Real)
            or not isfinite(self.max_observation_age_seconds)
            or self.max_observation_age_seconds <= 0
        ):
            raise ValueError("max_observation_age_seconds must be a positive finite number")
        if not isinstance(self.changed_at, datetime):
            raise ValueError("changed_at must be a datetime")
        if self.changed_at.utcoffset() is None:
            raise ValueError("changed_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SourceFreshnessAssessment:
    """Freshness result derived from explicit receipt evidence and optional policy."""

    source_id: str
    state: SourceFreshnessState
    observed_at: datetime | None
    received_at: datetime
    lag_seconds: float | None
    max_observation_age_seconds: float | None
    reason: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        if not isinstance(self.state, SourceFreshnessState):
            raise ValueError("state must be a SourceFreshnessState")
        if not isinstance(self.received_at, datetime) or self.received_at.utcoffset() is None:
            raise ValueError("received_at must be a timezone-aware datetime")
        if self.observed_at is not None and not isinstance(self.observed_at, datetime):
            raise ValueError("observed_at must be a datetime when provided")
        if self.lag_seconds is not None and (
            isinstance(self.lag_seconds, bool)
            or not isinstance(self.lag_seconds, Real)
            or not isfinite(self.lag_seconds)
        ):
            raise ValueError("lag_seconds must be a finite number when provided")
        if self.max_observation_age_seconds is not None and (
            isinstance(self.max_observation_age_seconds, bool)
            or not isinstance(self.max_observation_age_seconds, Real)
            or not isfinite(self.max_observation_age_seconds)
            or self.max_observation_age_seconds <= 0
        ):
            raise ValueError(
                "max_observation_age_seconds must be a positive finite number when provided"
            )

        if self.state in {SourceFreshnessState.FRESH, SourceFreshnessState.STALE}:
            if self.lag_seconds is None or self.max_observation_age_seconds is None:
                raise ValueError("fresh/stale assessment requires lag and configured policy")
            if self.lag_seconds < 0:
                raise ValueError("fresh/stale assessment requires non-negative lag")
            if self.reason is not None:
                raise ValueError("fresh/stale assessment must not carry an unavailable reason")
        else:
            if self.reason is None:
                raise ValueError("non-decision freshness state requires a reason")


@runtime_checkable
class SourceFreshnessPolicyRepository(Protocol):
    """Persistence boundary for optional source-specific freshness policies."""

    def get_freshness_policy(self, source_id: str) -> SourceFreshnessPolicy | None:
        """Return the configured source policy, or None when not configured."""
        ...

    def set_freshness_policy(self, policy: SourceFreshnessPolicy) -> None:
        """Persist one source-specific freshness policy."""
        ...

    def clear_freshness_policy(self, source_id: str) -> None:
        """Remove the configured freshness policy for one registered source."""
        ...


def assess_source_freshness(
    receipt: SourceReceiptEvidence,
    policy: SourceFreshnessPolicy | None,
) -> SourceFreshnessAssessment:
    """Derive freshness without inventing missing timestamp or policy semantics."""
    if not isinstance(receipt, SourceReceiptEvidence):
        raise ValueError("receipt must be SourceReceiptEvidence")

    if policy is None:
        return SourceFreshnessAssessment(
            source_id=receipt.source_id,
            state=SourceFreshnessState.NOT_CONFIGURED,
            observed_at=receipt.observed_at,
            received_at=receipt.received_at,
            lag_seconds=receipt.lag_seconds,
            max_observation_age_seconds=None,
            reason="source-specific freshness policy is not configured",
        )

    if not isinstance(policy, SourceFreshnessPolicy):
        raise ValueError("policy must be SourceFreshnessPolicy when provided")
    if policy.source_id != receipt.source_id:
        raise ValueError("receipt and freshness policy must share one source_id")

    lag = receipt.lag_seconds
    if lag is None:
        return SourceFreshnessAssessment(
            source_id=receipt.source_id,
            state=SourceFreshnessState.UNAVAILABLE,
            observed_at=receipt.observed_at,
            received_at=receipt.received_at,
            lag_seconds=None,
            max_observation_age_seconds=policy.max_observation_age_seconds,
            reason=receipt.lag_unavailable_reason or "receipt lag is unavailable",
        )

    if lag < 0:
        return SourceFreshnessAssessment(
            source_id=receipt.source_id,
            state=SourceFreshnessState.UNAVAILABLE,
            observed_at=receipt.observed_at,
            received_at=receipt.received_at,
            lag_seconds=lag,
            max_observation_age_seconds=policy.max_observation_age_seconds,
            reason=(
                "observed_at is after received_at; timestamp alignment must be resolved "
                "before freshness can be classified"
            ),
        )

    state = (
        SourceFreshnessState.FRESH
        if lag <= policy.max_observation_age_seconds
        else SourceFreshnessState.STALE
    )
    return SourceFreshnessAssessment(
        source_id=receipt.source_id,
        state=state,
        observed_at=receipt.observed_at,
        received_at=receipt.received_at,
        lag_seconds=lag,
        max_observation_age_seconds=policy.max_observation_age_seconds,
    )


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
