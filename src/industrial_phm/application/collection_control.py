"""Desired continuous-collection control-plane contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from industrial_phm.application.source_lifecycle import SourceLifecycleState
from industrial_phm.application.source_registration import (
    OpcUaSourceConfig,
    SourceRepository,
)


class CollectionDesiredState(StrEnum):
    STOPPED = "stopped"
    RUNNING = "running"


@dataclass(frozen=True, slots=True)
class CollectionControlRecord:
    """Durable desired collection state, separate from lifecycle and observed runtime."""

    source_id: str
    desired_state: CollectionDesiredState
    generation: int
    requested_at: datetime

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        if not isinstance(self.desired_state, CollectionDesiredState):
            raise ValueError("desired_state must be CollectionDesiredState")
        _validate_positive_int(self.generation, "generation")
        _validate_aware_datetime(self.requested_at, "requested_at")


@runtime_checkable
class CollectionControlRepository(Protocol):
    def get(self, source_id: str) -> CollectionControlRecord | None: ...

    def list_records(self) -> tuple[CollectionControlRecord, ...]: ...

    def request_state(
        self,
        source_id: str,
        desired_state: CollectionDesiredState,
        *,
        requested_at: datetime,
    ) -> CollectionControlRecord: ...


def request_collection_state(
    source_repository: SourceRepository,
    control_repository: CollectionControlRepository,
    source_id: str,
    desired_state: CollectionDesiredState,
    *,
    requested_at: datetime,
) -> CollectionControlRecord:
    """Validate one UI/CLI command without starting or owning a collector loop."""
    if not isinstance(desired_state, CollectionDesiredState):
        raise ValueError("desired_state must be CollectionDesiredState")
    _validate_aware_datetime(requested_at, "requested_at")

    source = source_repository.get(source_id)
    if not isinstance(source.config, OpcUaSourceConfig):
        raise ValueError("continuous collection currently supports OPC UA sources only")

    if desired_state == CollectionDesiredState.RUNNING:
        lifecycle = source_repository.get_lifecycle(source_id)
        if lifecycle.state != SourceLifecycleState.ACTIVE:
            raise ValueError(
                "Start Collection requires source lifecycle ACTIVE; "
                f"current={lifecycle.state.value}"
            )

    return control_repository.request_state(
        source_id,
        desired_state,
        requested_at=requested_at,
    )


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")


def _validate_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be at least 1")
