from datetime import datetime

import pytest

from industrial_phm.application import (
    SourceConnectionAttemptEvidence,
    SourceConnectionAttemptOperation,
    SourceConnectionAttemptOutcome,
    SourceConnectionState,
    SourceDataFlowState,
    SourceFreshnessPolicy,
    SourceHealthAssessment,
    SourceLifecycleRecord,
    SourceLifecycleState,
    SourceReceiptEvidence,
    assess_source_health,
)


def _lifecycle(
    state: SourceLifecycleState,
    *,
    detail: str | None = None,
) -> SourceLifecycleRecord:
    return SourceLifecycleRecord(
        source_id="source-a",
        state=state,
        changed_at=datetime.fromisoformat("2026-09-23T10:00:00+09:00"),
        detail=detail,
    )


def _receipt(
    *,
    observed_at: str | None = "2026-09-23T10:04:00+09:00",
    received_at: str = "2026-09-23T10:04:05+09:00",
) -> SourceReceiptEvidence:
    return SourceReceiptEvidence(
        source_id="source-a",
        observed_at=None if observed_at is None else datetime.fromisoformat(observed_at),
        received_at=datetime.fromisoformat(received_at),
    )


def _attempt(
    *,
    source_id: str = "source-a",
    outcome: SourceConnectionAttemptOutcome = SourceConnectionAttemptOutcome.SUCCEEDED,
) -> SourceConnectionAttemptEvidence:
    return SourceConnectionAttemptEvidence(
        source_id=source_id,
        operation=SourceConnectionAttemptOperation.OPCUA_READ,
        outcome=outcome,
        attempted_at=datetime.fromisoformat("2026-09-23T10:03:58+09:00"),
        connected_at=(
            datetime.fromisoformat("2026-09-23T10:03:59+09:00")
            if outcome == SourceConnectionAttemptOutcome.SUCCEEDED
            else None
        ),
        completed_at=datetime.fromisoformat("2026-09-23T10:04:00+09:00"),
        detail=(
            None if outcome == SourceConnectionAttemptOutcome.SUCCEEDED else "connection refused"
        ),
    )


def _policy(max_age: float = 120.0) -> SourceFreshnessPolicy:
    return SourceFreshnessPolicy(
        source_id="source-a",
        max_observation_age_seconds=max_age,
        changed_at=datetime.fromisoformat("2026-09-23T09:00:00+09:00"),
    )


def _as_of(value: str = "2026-09-23T10:05:00+09:00") -> datetime:
    return datetime.fromisoformat(value)


def test_source_health_preserves_latest_attempt_without_claiming_current_connection() -> None:
    attempt = _attempt()
    assessment = assess_source_health(
        _lifecycle(SourceLifecycleState.ACTIVE),
        _receipt(),
        _policy(),
        connection_attempt=attempt,
        as_of=_as_of(),
    )

    assert assessment.connection_attempt == attempt
    assert assessment.connection_state == SourceConnectionState.NOT_INSTRUMENTED
    assert not hasattr(assessment, "connected")


def test_source_health_has_no_boolean_healthy_claim() -> None:
    assessment = assess_source_health(
        _lifecycle(SourceLifecycleState.ACTIVE),
        _receipt(),
        _policy(),
        as_of=_as_of(),
    )

    assert isinstance(assessment, SourceHealthAssessment)
    assert not hasattr(assessment, "healthy")
    assert assessment.connection_state == SourceConnectionState.NOT_INSTRUMENTED


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (SourceLifecycleState.REGISTERED, SourceDataFlowState.INACTIVE),
        (SourceLifecycleState.PAUSED, SourceDataFlowState.INACTIVE),
    ],
)
def test_non_active_source_is_inactive_without_inventing_connection_state(
    state: SourceLifecycleState,
    expected: SourceDataFlowState,
) -> None:
    assessment = assess_source_health(
        _lifecycle(state),
        _receipt(),
        _policy(),
        as_of=_as_of(),
    )

    assert assessment.data_flow_state == expected
    assert assessment.connection_state == SourceConnectionState.NOT_INSTRUMENTED
    assert assessment.freshness is None


def test_source_error_comes_from_lifecycle_failure_evidence() -> None:
    assessment = assess_source_health(
        _lifecycle(SourceLifecycleState.ERROR, detail="ValueError: invalid sensor value"),
        _receipt(),
        _policy(),
        as_of=_as_of(),
    )

    assert assessment.data_flow_state == SourceDataFlowState.SOURCE_ERROR
    assert assessment.reason == "ValueError: invalid sensor value"
    assert assessment.connection_state == SourceConnectionState.NOT_INSTRUMENTED


def test_active_source_without_receipt_is_explicitly_no_receipt() -> None:
    attempt = _attempt(outcome=SourceConnectionAttemptOutcome.FAILED)
    assessment = assess_source_health(
        _lifecycle(SourceLifecycleState.ACTIVE),
        None,
        _policy(),
        connection_attempt=attempt,
        as_of=_as_of(),
    )

    assert assessment.data_flow_state == SourceDataFlowState.NO_RECEIPT
    assert assessment.connection_attempt == attempt
    assert assessment.latest_received_at is None
    assert assessment.reason == "active source has no accepted receipt evidence"


def test_reactivated_source_does_not_reuse_receipt_from_previous_active_epoch() -> None:
    lifecycle = SourceLifecycleRecord(
        source_id="source-a",
        state=SourceLifecycleState.ACTIVE,
        changed_at=datetime.fromisoformat("2026-09-23T10:05:10+09:00"),
    )
    receipt = _receipt(received_at="2026-09-23T10:04:05+09:00")

    assessment = assess_source_health(
        lifecycle,
        receipt,
        _policy(),
        as_of=_as_of("2026-09-23T10:06:00+09:00"),
    )

    assert assessment.data_flow_state == SourceDataFlowState.NO_RECEIPT
    assert assessment.latest_received_at == receipt.received_at
    assert assessment.freshness is None
    assert assessment.reason is not None
    assert "current active lifecycle transition" in assessment.reason


def test_active_source_without_freshness_policy_is_not_configured() -> None:
    assessment = assess_source_health(
        _lifecycle(SourceLifecycleState.ACTIVE),
        _receipt(),
        None,
        as_of=_as_of(),
    )

    assert assessment.data_flow_state == SourceDataFlowState.FRESHNESS_NOT_CONFIGURED
    assert assessment.freshness is not None
    assert assessment.freshness.state.value == "not-configured"


def test_active_source_with_fresh_observation_maps_to_fresh_data_flow() -> None:
    assessment = assess_source_health(
        _lifecycle(SourceLifecycleState.ACTIVE),
        _receipt(),
        _policy(max_age=120.0),
        as_of=_as_of(),
    )

    assert assessment.data_flow_state == SourceDataFlowState.FRESH
    assert assessment.latest_observed_at == datetime.fromisoformat("2026-09-23T10:04:00+09:00")
    assert assessment.latest_received_at == datetime.fromisoformat("2026-09-23T10:04:05+09:00")
    assert assessment.delivery_lag_seconds == 5.0


def test_active_source_with_old_observation_maps_to_stale_data_flow() -> None:
    assessment = assess_source_health(
        _lifecycle(SourceLifecycleState.ACTIVE),
        _receipt(observed_at="2026-09-23T09:55:00+09:00"),
        _policy(max_age=120.0),
        as_of=_as_of(),
    )

    assert assessment.data_flow_state == SourceDataFlowState.STALE
    assert assessment.freshness is not None
    assert assessment.freshness.observation_age_seconds == 600.0


@pytest.mark.parametrize(
    "observed_at",
    [None, "2026-09-23T10:04:00"],
)
def test_active_source_with_unusable_timing_maps_to_timing_unavailable(
    observed_at: str | None,
) -> None:
    assessment = assess_source_health(
        _lifecycle(SourceLifecycleState.ACTIVE),
        _receipt(observed_at=observed_at),
        _policy(),
        as_of=_as_of(),
    )

    assert assessment.data_flow_state == SourceDataFlowState.TIMING_UNAVAILABLE
    assert assessment.freshness is not None
    assert assessment.freshness.state.value == "unavailable"


def test_source_health_rejects_cross_source_evidence() -> None:
    receipt = SourceReceiptEvidence(
        source_id="source-b",
        observed_at=datetime.fromisoformat("2026-09-23T10:04:00+09:00"),
        received_at=datetime.fromisoformat("2026-09-23T10:04:05+09:00"),
    )

    with pytest.raises(ValueError, match="share one source_id"):
        assess_source_health(
            _lifecycle(SourceLifecycleState.ACTIVE),
            receipt,
            _policy(),
            as_of=_as_of(),
        )


def test_source_health_rejects_cross_source_connection_attempt() -> None:
    with pytest.raises(ValueError, match="connection attempt"):
        assess_source_health(
            _lifecycle(SourceLifecycleState.ACTIVE),
            _receipt(),
            _policy(),
            connection_attempt=_attempt(source_id="source-b"),
            as_of=_as_of(),
        )


def test_source_health_requires_timezone_aware_assessment_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        assess_source_health(
            _lifecycle(SourceLifecycleState.ACTIVE),
            _receipt(),
            _policy(),
            as_of=datetime.fromisoformat("2026-09-23T10:05:00"),
        )
