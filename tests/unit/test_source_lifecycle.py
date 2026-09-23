from datetime import datetime

import pytest

from industrial_phm.application import (
    SourceLifecycleRecord,
    SourceLifecycleRepository,
    SourceLifecycleState,
    transition_source_lifecycle,
)


class _LifecycleRepository:
    def __init__(self, record: SourceLifecycleRecord) -> None:
        self.record = record

    def get_lifecycle(self, source_id: str) -> SourceLifecycleRecord:
        if source_id != self.record.source_id:
            raise LookupError(source_id)
        return self.record

    def set_lifecycle(self, record: SourceLifecycleRecord) -> None:
        self.record = record


def _record(
    *,
    state: SourceLifecycleState = SourceLifecycleState.REGISTERED,
) -> SourceLifecycleRecord:
    return SourceLifecycleRecord(
        source_id="source-a",
        state=state,
        changed_at=datetime.fromisoformat("2026-09-23T10:00:00+09:00"),
    )


def test_source_lifecycle_record_requires_timezone_aware_change_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SourceLifecycleRecord(
            source_id="source-a",
            state=SourceLifecycleState.REGISTERED,
            changed_at=datetime.fromisoformat("2026-09-23T10:00:00"),
        )


def test_source_lifecycle_active_does_not_claim_runtime_health() -> None:
    record = _record().transition_to(
        SourceLifecycleState.ACTIVE,
        changed_at=datetime.fromisoformat("2026-09-23T10:05:00+09:00"),
    )

    assert record.state == SourceLifecycleState.ACTIVE
    assert not hasattr(record, "connected")
    assert not hasattr(record, "healthy")
    assert not hasattr(record, "last_received_at")


def test_source_lifecycle_rejects_same_state_and_backward_time() -> None:
    record = _record()

    with pytest.raises(ValueError, match="already registered"):
        record.transition_to(
            SourceLifecycleState.REGISTERED,
            changed_at=datetime.fromisoformat("2026-09-23T10:05:00+09:00"),
        )

    with pytest.raises(ValueError, match="must not move backwards"):
        record.transition_to(
            SourceLifecycleState.ACTIVE,
            changed_at=datetime.fromisoformat("2026-09-23T09:59:59+09:00"),
        )


def test_source_lifecycle_error_requires_detail_and_detail_is_error_only() -> None:
    active = _record().transition_to(
        SourceLifecycleState.ACTIVE,
        changed_at=datetime.fromisoformat("2026-09-23T10:05:00+09:00"),
    )

    with pytest.raises(ValueError, match="requires detail"):
        active.transition_to(
            SourceLifecycleState.ERROR,
            changed_at=datetime.fromisoformat("2026-09-23T10:06:00+09:00"),
        )

    with pytest.raises(ValueError, match="only supported for error"):
        active.transition_to(
            SourceLifecycleState.PAUSED,
            changed_at=datetime.fromisoformat("2026-09-23T10:06:00+09:00"),
            detail="manual pause",
        )


def test_source_lifecycle_transition_graph_is_explicit() -> None:
    registered = _record()
    paused = registered.transition_to(
        SourceLifecycleState.PAUSED,
        changed_at=datetime.fromisoformat("2026-09-23T10:05:00+09:00"),
    )
    active = paused.transition_to(
        SourceLifecycleState.ACTIVE,
        changed_at=datetime.fromisoformat("2026-09-23T10:06:00+09:00"),
    )
    error = active.transition_to(
        SourceLifecycleState.ERROR,
        changed_at=datetime.fromisoformat("2026-09-23T10:07:00+09:00"),
        detail="runtime read failed",
    )
    recovered = error.transition_to(
        SourceLifecycleState.ACTIVE,
        changed_at=datetime.fromisoformat("2026-09-23T10:08:00+09:00"),
    )

    assert paused.state == SourceLifecycleState.PAUSED
    assert error.detail == "runtime read failed"
    assert recovered.state == SourceLifecycleState.ACTIVE
    assert recovered.detail is None


def test_transition_source_lifecycle_uses_repository_boundary() -> None:
    repository = _LifecycleRepository(_record())

    assert isinstance(repository, SourceLifecycleRepository)

    transitioned = transition_source_lifecycle(
        repository,
        "source-a",
        SourceLifecycleState.ACTIVE,
        changed_at=datetime.fromisoformat("2026-09-23T10:05:00+09:00"),
    )

    assert transitioned == repository.record
    assert transitioned.state == SourceLifecycleState.ACTIVE
