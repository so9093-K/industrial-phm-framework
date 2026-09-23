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
    """Persisted maximum latest-observation age for one registered source."""

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
    """Freshness result derived from explicit timing evidence and optional policy."""

    source_id: str
    state: SourceFreshnessState
    observed_at: datetime | None
    received_at: datetime
    assessed_at: datetime
    delivery_lag_seconds: float | None
    observation_age_seconds: float | None
    max_observation_age_seconds: float | None
    reason: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        if not isinstance(self.state, SourceFreshnessState):
            raise ValueError("state must be a SourceFreshnessState")
        if not isinstance(self.received_at, datetime) or self.received_at.utcoffset() is None:
            raise ValueError("received_at must be a timezone-aware datetime")
        if not isinstance(self.assessed_at, datetime) or self.assessed_at.utcoffset() is None:
            raise ValueError("assessed_at must be a timezone-aware datetime")
        if self.observed_at is not None and not isinstance(self.observed_at, datetime):
            raise ValueError("observed_at must be a datetime when provided")
        _validate_optional_finite_number(self.delivery_lag_seconds, "delivery_lag_seconds")
        _validate_optional_finite_number(self.observation_age_seconds, "observation_age_seconds")
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
            if self.observation_age_seconds is None or self.max_observation_age_seconds is None:
                raise ValueError(
                    "fresh/stale assessment requires observation age and configured policy"
                )
            if self.observation_age_seconds < 0:
                raise ValueError("fresh/stale assessment requires non-negative observation age")
            if self.reason is not None:
                raise ValueError("fresh/stale assessment must not carry an unavailable reason")
        elif self.reason is None:
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
    *,
    as_of: datetime,
) -> SourceFreshnessAssessment:
    """Assess latest-observation freshness at an explicit evaluation time.

    Delivery lag and freshness age are different facts:
    - delivery lag = received_at - observed_at
    - observation age = as_of - observed_at

    Fresh/stale classification uses observation age only. No decision is produced
    when the source observation timestamp is missing, timezone-naive, in the future,
    or when no source-specific policy is configured.
    """
    if not isinstance(receipt, SourceReceiptEvidence):
        raise ValueError("receipt must be SourceReceiptEvidence")
    if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
        raise ValueError("as_of must be a timezone-aware datetime")

    delivery_lag = receipt.lag_seconds

    if policy is None:
        return SourceFreshnessAssessment(
            source_id=receipt.source_id,
            state=SourceFreshnessState.NOT_CONFIGURED,
            observed_at=receipt.observed_at,
            received_at=receipt.received_at,
            assessed_at=as_of,
            delivery_lag_seconds=delivery_lag,
            observation_age_seconds=_observation_age_seconds(receipt, as_of),
            max_observation_age_seconds=None,
            reason="source-specific freshness policy is not configured",
        )

    if not isinstance(policy, SourceFreshnessPolicy):
        raise ValueError("policy must be SourceFreshnessPolicy when provided")
    if policy.source_id != receipt.source_id:
        raise ValueError("receipt and freshness policy must share one source_id")

    if receipt.observed_at is None:
        return _unavailable_assessment(
            receipt,
            policy,
            as_of=as_of,
            delivery_lag=delivery_lag,
            observation_age=None,
            reason="source observation time is unavailable",
        )
    if receipt.observed_at.utcoffset() is None:
        return _unavailable_assessment(
            receipt,
            policy,
            as_of=as_of,
            delivery_lag=None,
            observation_age=None,
            reason="source observation timezone is unavailable",
        )

    age = (as_of - receipt.observed_at).total_seconds()
    if age < 0:
        return _unavailable_assessment(
            receipt,
            policy,
            as_of=as_of,
            delivery_lag=delivery_lag,
            observation_age=age,
            reason=(
                "observed_at is after freshness assessment time; timestamp alignment "
                "must be resolved before freshness can be classified"
            ),
        )

    state = (
        SourceFreshnessState.FRESH
        if age <= policy.max_observation_age_seconds
        else SourceFreshnessState.STALE
    )
    return SourceFreshnessAssessment(
        source_id=receipt.source_id,
        state=state,
        observed_at=receipt.observed_at,
        received_at=receipt.received_at,
        assessed_at=as_of,
        delivery_lag_seconds=delivery_lag,
        observation_age_seconds=age,
        max_observation_age_seconds=policy.max_observation_age_seconds,
    )


def _unavailable_assessment(
    receipt: SourceReceiptEvidence,
    policy: SourceFreshnessPolicy,
    *,
    as_of: datetime,
    delivery_lag: float | None,
    observation_age: float | None,
    reason: str,
) -> SourceFreshnessAssessment:
    return SourceFreshnessAssessment(
        source_id=receipt.source_id,
        state=SourceFreshnessState.UNAVAILABLE,
        observed_at=receipt.observed_at,
        received_at=receipt.received_at,
        assessed_at=as_of,
        delivery_lag_seconds=delivery_lag,
        observation_age_seconds=observation_age,
        max_observation_age_seconds=policy.max_observation_age_seconds,
        reason=reason,
    )


def _observation_age_seconds(
    receipt: SourceReceiptEvidence,
    as_of: datetime,
) -> float | None:
    if receipt.observed_at is None or receipt.observed_at.utcoffset() is None:
        return None
    return (as_of - receipt.observed_at).total_seconds()


def _validate_optional_finite_number(value: float | None, field_name: str) -> None:
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value)
    ):
        raise ValueError(f"{field_name} must be a finite number when provided")


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
