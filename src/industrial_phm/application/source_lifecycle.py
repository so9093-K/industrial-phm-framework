"""Administrative lifecycle contracts for registered operational sources."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from industrial_phm.application.source_registration import UnknownRegisteredSourceError


class SourceLifecycleState(StrEnum):
    """Administrative source lifecycle.

    ACTIVE means the source is enabled for a runtime to consume. It does not prove
    connection, health, freshness, or active ingestion.
    """

    REGISTERED = "registered"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"


_ALLOWED_TRANSITIONS: dict[SourceLifecycleState, frozenset[SourceLifecycleState]] = {
    SourceLifecycleState.REGISTERED: frozenset(
        {
            SourceLifecycleState.ACTIVE,
            SourceLifecycleState.PAUSED,
        }
    ),
    SourceLifecycleState.ACTIVE: frozenset(
        {
            SourceLifecycleState.PAUSED,
            SourceLifecycleState.ERROR,
        }
    ),
    SourceLifecycleState.PAUSED: frozenset(
        {
            SourceLifecycleState.ACTIVE,
        }
    ),
    SourceLifecycleState.ERROR: frozenset(
        {
            SourceLifecycleState.ACTIVE,
            SourceLifecycleState.PAUSED,
        }
    ),
}


@dataclass(frozen=True, slots=True)
class SourceLifecycleRecord:
    """Persisted administrative lifecycle state for one registered source."""

    source_id: str
    state: SourceLifecycleState
    changed_at: datetime
    detail: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        if not isinstance(self.state, SourceLifecycleState):
            raise ValueError("state must be a SourceLifecycleState")
        if not isinstance(self.changed_at, datetime):
            raise ValueError("changed_at must be a datetime")
        if self.changed_at.utcoffset() is None:
            raise ValueError("changed_at must be timezone-aware")
        if self.detail is not None:
            _validate_identifier(self.detail, "detail")
        if self.state == SourceLifecycleState.ERROR and self.detail is None:
            raise ValueError("error lifecycle state requires detail")
        if self.state != SourceLifecycleState.ERROR and self.detail is not None:
            raise ValueError("detail is only supported for error lifecycle state")

    def transition_to(
        self,
        state: SourceLifecycleState,
        *,
        changed_at: datetime,
        detail: str | None = None,
    ) -> SourceLifecycleRecord:
        """Return the next lifecycle record after validating the state transition."""
        if not isinstance(state, SourceLifecycleState):
            raise ValueError("state must be a SourceLifecycleState")
        if not isinstance(changed_at, datetime):
            raise ValueError("changed_at must be a datetime")
        if changed_at.utcoffset() is None:
            raise ValueError("changed_at must be timezone-aware")
        if changed_at < self.changed_at:
            raise ValueError("lifecycle changed_at must not move backwards")
        if state == self.state:
            raise ValueError(f"source lifecycle is already {state.value}")
        if state not in _ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(
                f"invalid source lifecycle transition: {self.state.value} -> {state.value}"
            )
        if state == SourceLifecycleState.ERROR and detail is None:
            raise ValueError("error lifecycle state requires detail")
        if state != SourceLifecycleState.ERROR and detail is not None:
            raise ValueError("detail is only supported for error lifecycle state")
        return replace(self, state=state, changed_at=changed_at, detail=detail)


@runtime_checkable
class SourceLifecycleRepository(Protocol):
    """Persistence boundary for source lifecycle state."""

    def get_lifecycle(self, source_id: str) -> SourceLifecycleRecord:
        """Resolve lifecycle state for a registered source."""
        ...

    def set_lifecycle(self, record: SourceLifecycleRecord) -> None:
        """Persist an already validated lifecycle record."""
        ...


def transition_source_lifecycle(
    repository: SourceLifecycleRepository,
    source_id: str,
    state: SourceLifecycleState,
    *,
    changed_at: datetime,
    detail: str | None = None,
) -> SourceLifecycleRecord:
    """Validate and persist one source lifecycle transition."""
    try:
        current = repository.get_lifecycle(source_id)
    except UnknownRegisteredSourceError:
        raise
    next_record = current.transition_to(
        state,
        changed_at=changed_at,
        detail=detail,
    )
    repository.set_lifecycle(next_record)
    return next_record


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
