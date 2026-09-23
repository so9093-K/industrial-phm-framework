from datetime import datetime

import pytest

from industrial_phm.application import (
    SourceFreshnessPolicy,
    SourceFreshnessState,
    SourceReceiptEvidence,
    assess_source_freshness,
)


def _receipt(
    *,
    source_id: str = "source-a",
    observed_at: str | None = "2026-09-23T10:00:00+09:00",
    received_at: str = "2026-09-23T10:00:05+09:00",
) -> SourceReceiptEvidence:
    return SourceReceiptEvidence(
        source_id=source_id,
        observed_at=None if observed_at is None else datetime.fromisoformat(observed_at),
        received_at=datetime.fromisoformat(received_at),
    )


def _policy(
    *,
    source_id: str = "source-a",
    max_age_seconds: float = 10.0,
) -> SourceFreshnessPolicy:
    return SourceFreshnessPolicy(
        source_id=source_id,
        max_observation_age_seconds=max_age_seconds,
        changed_at=datetime.fromisoformat("2026-09-23T09:00:00+09:00"),
    )


def _as_of(value: str = "2026-09-23T10:00:08+09:00") -> datetime:
    return datetime.fromisoformat(value)


def test_freshness_policy_requires_positive_finite_age() -> None:
    with pytest.raises(ValueError, match="positive finite"):
        _policy(max_age_seconds=0.0)


def test_freshness_policy_requires_timezone_aware_change_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SourceFreshnessPolicy(
            source_id="source-a",
            max_observation_age_seconds=10.0,
            changed_at=datetime.fromisoformat("2026-09-23T09:00:00"),
        )


def test_freshness_requires_timezone_aware_assessment_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        assess_source_freshness(
            _receipt(),
            _policy(),
            as_of=datetime.fromisoformat("2026-09-23T10:00:08"),
        )


def test_freshness_is_not_configured_without_source_policy() -> None:
    assessment = assess_source_freshness(_receipt(), None, as_of=_as_of())

    assert assessment.state == SourceFreshnessState.NOT_CONFIGURED
    assert assessment.delivery_lag_seconds == 5.0
    assert assessment.observation_age_seconds == 8.0
    assert assessment.max_observation_age_seconds is None
    assert assessment.reason == "source-specific freshness policy is not configured"


def test_freshness_uses_assessment_age_not_delivery_lag() -> None:
    receipt = _receipt(received_at="2026-09-23T10:00:01+09:00")

    assessment = assess_source_freshness(
        receipt,
        _policy(max_age_seconds=10.0),
        as_of=_as_of("2026-09-23T10:00:11+09:00"),
    )

    assert assessment.delivery_lag_seconds == 1.0
    assert assessment.observation_age_seconds == 11.0
    assert assessment.state == SourceFreshnessState.STALE


def test_freshness_is_fresh_at_or_below_threshold() -> None:
    fresh = assess_source_freshness(
        _receipt(),
        _policy(max_age_seconds=10.0),
        as_of=_as_of("2026-09-23T10:00:08+09:00"),
    )
    boundary = assess_source_freshness(
        _receipt(),
        _policy(max_age_seconds=10.0),
        as_of=_as_of("2026-09-23T10:00:10+09:00"),
    )

    assert fresh.state == SourceFreshnessState.FRESH
    assert fresh.reason is None
    assert boundary.state == SourceFreshnessState.FRESH


def test_freshness_is_stale_above_threshold() -> None:
    assessment = assess_source_freshness(
        _receipt(),
        _policy(max_age_seconds=10.0),
        as_of=_as_of("2026-09-23T10:00:11+09:00"),
    )

    assert assessment.state == SourceFreshnessState.STALE
    assert assessment.observation_age_seconds == 11.0
    assert assessment.max_observation_age_seconds == 10.0


def test_freshness_is_unavailable_for_naive_source_time() -> None:
    assessment = assess_source_freshness(
        _receipt(observed_at="2026-09-23T10:00:00"),
        _policy(),
        as_of=_as_of(),
    )

    assert assessment.state == SourceFreshnessState.UNAVAILABLE
    assert assessment.delivery_lag_seconds is None
    assert assessment.observation_age_seconds is None
    assert assessment.reason == "source observation timezone is unavailable"


def test_freshness_is_unavailable_for_missing_source_time() -> None:
    assessment = assess_source_freshness(
        _receipt(observed_at=None),
        _policy(),
        as_of=_as_of(),
    )

    assert assessment.state == SourceFreshnessState.UNAVAILABLE
    assert assessment.observation_age_seconds is None
    assert assessment.reason == "source observation time is unavailable"


def test_freshness_is_unavailable_for_future_observation_time() -> None:
    assessment = assess_source_freshness(
        _receipt(
            observed_at="2026-09-23T10:00:10+09:00",
            received_at="2026-09-23T10:00:05+09:00",
        ),
        _policy(),
        as_of=_as_of("2026-09-23T10:00:08+09:00"),
    )

    assert assessment.state == SourceFreshnessState.UNAVAILABLE
    assert assessment.delivery_lag_seconds == -5.0
    assert assessment.observation_age_seconds == -2.0
    assert assessment.reason is not None
    assert "assessment time" in assessment.reason


def test_freshness_rejects_policy_for_different_source() -> None:
    with pytest.raises(ValueError, match="share one source_id"):
        assess_source_freshness(
            _receipt(),
            _policy(source_id="source-b"),
            as_of=_as_of(),
        )
