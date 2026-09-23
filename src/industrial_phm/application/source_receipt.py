"""Receipt-time evidence for validated registered-source observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from industrial_phm.application.file_source_registration import (
    RegisteredFileObservation,
    load_registered_file_source_observation,
)
from industrial_phm.application.observation import AssetObservationSummary
from industrial_phm.application.source_registration import (
    OpcUaSourceConfig,
    RegisteredSource,
)
from industrial_phm.connectors import OpcUaReadSnapshot, read_opcua_snapshot
from industrial_phm.contracts import (
    DataQualityAssessment,
    DataQualityIssue,
    DataQualitySeverity,
)


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
class RegisteredOpcUaObservation:
    """One registered OPC UA snapshot projected with asset/source identity."""

    source_id: str
    asset_id: str
    snapshot: OpcUaReadSnapshot
    measurement_point_id: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.source_id, "source_id")
        _validate_identifier(self.asset_id, "asset_id")
        if self.measurement_point_id is not None:
            _validate_identifier(self.measurement_point_id, "measurement_point_id")
        if not isinstance(self.snapshot, OpcUaReadSnapshot):
            raise ValueError("snapshot must be an OpcUaReadSnapshot")

    @property
    def channels(self) -> tuple[str, ...]:
        """Return mapped OPC UA channel identifiers in snapshot order."""
        return tuple(item.channel_id for item in self.snapshot.observations)

    @property
    def observed_at(self) -> datetime | None:
        """Return the complete-channel event-time watermark when timestamps are available.

        For a multi-node snapshot the source-level timestamp must not be newer than any
        mapped channel. The earliest SourceTimestamp is therefore used as the conservative
        watermark for freshness/lag assessment. If any mapped node lacks SourceTimestamp,
        source-level timing remains unavailable.
        """
        timestamps = tuple(item.source_timestamp for item in self.snapshot.observations)
        if any(value is None for value in timestamps):
            return None
        return min(value for value in timestamps if value is not None)


def project_registered_opcua_observation_summary(
    observation: RegisteredOpcUaObservation,
) -> AssetObservationSummary:
    """Project one registered OPC UA snapshot into the canonical observation summary.

    The projection keeps the protocol snapshot itself separate and does not invent a
    sampling rate, file snapshot identity, or validation policy. One read iteration is
    represented as one sample across the configured channel set. Source observation time
    is exposed only through the conservative complete-channel watermark already defined
    by RegisteredOpcUaObservation.
    """
    if not isinstance(observation, RegisteredOpcUaObservation):
        raise ValueError("observation must be a RegisteredOpcUaObservation")

    non_good = tuple(item for item in observation.snapshot.observations if not item.status_good)
    issues: tuple[DataQualityIssue, ...] = ()
    if non_good:
        detail = ", ".join(f"{item.channel_id}={item.status_text}" for item in non_good)
        issues = (
            DataQualityIssue(
                code="opcua-non-good-status",
                severity=DataQualitySeverity.ERROR,
                message=f"non-good OPC UA status observed: {detail}",
            ),
        )

    observed_at = observation.observed_at
    return AssetObservationSummary(
        asset_id=observation.asset_id,
        source_id=observation.source_id,
        measurement_point_id=observation.measurement_point_id,
        channels=observation.channels,
        sample_count=1,
        observed_start_at=observed_at,
        observed_end_at=observed_at,
        sampling_rate_hz=None,
        source_snapshot=None,
        validation_policy=None,
        data_quality=DataQualityAssessment(issues),
    )


@dataclass(frozen=True, slots=True)
class ReceivedRegisteredOpcUaObservation:
    """Registered OPC UA snapshot plus platform acceptance-time evidence."""

    observation: RegisteredOpcUaObservation
    receipt: SourceReceiptEvidence

    def __post_init__(self) -> None:
        if not isinstance(self.observation, RegisteredOpcUaObservation):
            raise ValueError("observation must be a RegisteredOpcUaObservation")
        if not isinstance(self.receipt, SourceReceiptEvidence):
            raise ValueError("receipt must be SourceReceiptEvidence")
        if self.observation.source_id != self.receipt.source_id:
            raise ValueError("observation and receipt must share one source_id")


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


async def receive_registered_opcua_source_observation(
    source: RegisteredSource,
    *,
    received_at: datetime | None = None,
) -> ReceivedRegisteredOpcUaObservation:
    """Read one registered OPC UA snapshot and record platform acceptance evidence.

    A source-level observation time is exposed only when every mapped DataValue carries
    a SourceTimestamp. The earliest mapped SourceTimestamp is used as a conservative
    complete-channel watermark so freshness cannot be overstated by one newer channel.
    Missing protocol timestamps remain unavailable instead of being replaced with
    platform receipt/completion time.
    """
    config = source.config
    if not isinstance(config, OpcUaSourceConfig):
        raise ValueError("registered OPC UA source must use OpcUaSourceConfig")

    snapshot = await read_opcua_snapshot(config.to_opcua_read_config())
    observation = RegisteredOpcUaObservation(
        source_id=source.source_id,
        asset_id=config.asset_id,
        measurement_point_id=config.measurement_point_id,
        snapshot=snapshot,
    )
    acceptance_time = datetime.now(UTC) if received_at is None else received_at
    if not isinstance(acceptance_time, datetime) or acceptance_time.utcoffset() is None:
        raise ValueError("received_at must be a timezone-aware datetime")
    if acceptance_time < snapshot.completed_at:
        raise ValueError("received_at must not be before OPC UA snapshot completion")

    receipt = SourceReceiptEvidence(
        source_id=source.source_id,
        received_at=acceptance_time,
        observed_at=observation.observed_at,
    )
    return ReceivedRegisteredOpcUaObservation(
        observation=observation,
        receipt=receipt,
    )


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
    acceptance_time = datetime.now(UTC) if received_at is None else received_at
    receipt = SourceReceiptEvidence(
        source_id=source.source_id,
        received_at=acceptance_time,
        observed_at=observation.latest.observed_end_at,
    )
    return ReceivedRegisteredFileObservation(
        observation=observation,
        receipt=receipt,
    )


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
