"""Receipt-time evidence for validated registered-source observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from industrial_phm.application.file_source_registration import (
    RegisteredFileObservation,
    load_registered_file_source_observation,
)
from industrial_phm.application.source_registration import RegisteredSource


@dataclass(frozen=True, slots=True)
class SourceReceiptEvidence:
    """Timing evidence for one source load accepted by the application boundary.

    received_at is the platform acceptance time for this validated load. For prepared
    files it is not a reconstruction of when the original sensor transport delivered
    each sample.
    """

    source_id: str
    received_at: datetime
    observed_at: datetime | None

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        if self.source_id != self.source_id.strip():
            raise ValueError("source_id must not contain surrounding whitespace")
        if not isinstance(self.received_at, datetime):
            raise ValueError("received_at must be a datetime")
        if self.received_at.utcoffset() is None:
            raise ValueError("received_at must be timezone-aware")
        if self.observed_at is not None and not isinstance(self.observed_at, datetime):
            raise ValueError("observed_at must be a datetime when provided")

    @property
    def lag_seconds(self) -> float | None:
        """Return signed observed-to-received lag when timestamps are comparable."""
        if self.observed_at is None or self.observed_at.utcoffset() is None:
            return None
        return (self.received_at - self.observed_at).total_seconds()

    @property
    def lag_unavailable_reason(self) -> str | None:
        """Explain why lag cannot be computed without inventing timestamp semantics."""
        if self.observed_at is None:
            return "source observation time is unavailable"
        if self.observed_at.utcoffset() is None:
            return "source observation timezone is unavailable"
        return None


@dataclass(frozen=True, slots=True)
class ReceivedRegisteredFileObservation:
    """Validated registered-file observation plus platform receipt-time evidence."""

    observation: RegisteredFileObservation
    receipt: SourceReceiptEvidence

    def __post_init__(self) -> None:
        if not isinstance(self.observation, RegisteredFileObservation):
            raise ValueError("observation must be a RegisteredFileObservation")
        if not isinstance(self.receipt, SourceReceiptEvidence):
            raise ValueError("receipt must be SourceReceiptEvidence")
        if self.observation.latest.source_id != self.receipt.source_id:
            raise ValueError("observation and receipt must share one source_id")


def receive_registered_file_source_observation(
    source: RegisteredSource,
    *,
    received_at: datetime | None = None,
) -> ReceivedRegisteredFileObservation:
    """Validate current source bytes and record when the platform accepted this load.

    When received_at is omitted it is captured in UTC after source validation succeeds.
    Tests and other deterministic callers may inject an explicit timezone-aware value.
    """
    observation = load_registered_file_source_observation(source)
    acceptance_time = datetime.now(timezone.utc) if received_at is None else received_at
    receipt = SourceReceiptEvidence(
        source_id=source.source_id,
        received_at=acceptance_time,
        observed_at=observation.latest.observed_end_at,
    )
    return ReceivedRegisteredFileObservation(
        observation=observation,
        receipt=receipt,
    )
