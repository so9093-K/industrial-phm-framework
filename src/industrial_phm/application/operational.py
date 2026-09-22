"""Minimal operational analysis contracts kept separate from research artifacts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from industrial_phm.application.observation import SourceSnapshotEvidence
from industrial_phm.contracts import DataQualityAssessment


@dataclass(frozen=True, slots=True)
class AnalysisRun:
    """Execution/provenance envelope for one operational analysis scope.

    Numerical outputs remain capability-specific. This type does not own anomaly scores,
    thresholds, diagnosis, prognostics, or maintenance decisions.
    """

    analysis_run_id: str
    asset_id: str
    source_id: str
    observed_start_at: datetime
    observed_end_at: datetime
    started_at: datetime
    completed_at: datetime
    data_quality: DataQualityAssessment
    measurement_point_id: str | None = None
    model_deployment_id: str | None = None
    source_snapshots: Sequence[SourceSnapshotEvidence] = ()
    capability_ids: Sequence[str] = ()

    def __post_init__(self) -> None:
        source_snapshots = tuple(self.source_snapshots)
        capability_ids = tuple(self.capability_ids)

        _validate_identifier(self.analysis_run_id, "analysis_run_id")
        _validate_identifier(self.asset_id, "asset_id")
        _validate_identifier(self.source_id, "source_id")
        if self.measurement_point_id is not None:
            _validate_identifier(self.measurement_point_id, "measurement_point_id")
        if self.model_deployment_id is not None:
            _validate_identifier(self.model_deployment_id, "model_deployment_id")

        _validate_time_window(
            self.observed_start_at,
            self.observed_end_at,
            "observed",
        )
        _validate_time_window(
            self.started_at,
            self.completed_at,
            "execution",
        )

        if not isinstance(self.data_quality, DataQualityAssessment):
            raise ValueError("data_quality must be a DataQualityAssessment")
        if any(not isinstance(snapshot, SourceSnapshotEvidence) for snapshot in source_snapshots):
            raise ValueError("source_snapshots must contain only SourceSnapshotEvidence values")
        snapshot_digests = tuple(snapshot.sha256 for snapshot in source_snapshots)
        if len(set(snapshot_digests)) != len(snapshot_digests):
            raise ValueError("source_snapshots must not repeat the same SHA-256")

        for capability_id in capability_ids:
            _validate_identifier(capability_id, "capability_id")
        if len(set(capability_ids)) != len(capability_ids):
            raise ValueError("capability_ids must contain unique values")

        object.__setattr__(self, "source_snapshots", source_snapshots)
        object.__setattr__(self, "capability_ids", capability_ids)


@dataclass(frozen=True, slots=True)
class OperationalFinding:
    """Validated state-like finding linked to capability-specific evidence.

    The state value is intentionally opaque to this generic envelope. Its meaning must
    be defined by finding_semantics_id. Numeric score/threshold payloads belong to the
    capability-specific evidence referenced by evidence_refs.
    """

    finding_id: str
    analysis_run_id: str
    asset_id: str
    observed_at: datetime
    capability_id: str
    finding_semantics_id: str
    state: str
    evidence_refs: Sequence[str]
    measurement_point_id: str | None = None

    def __post_init__(self) -> None:
        evidence_refs = tuple(self.evidence_refs)

        _validate_identifier(self.finding_id, "finding_id")
        _validate_identifier(self.analysis_run_id, "analysis_run_id")
        _validate_identifier(self.asset_id, "asset_id")
        _validate_identifier(self.capability_id, "capability_id")
        _validate_identifier(self.finding_semantics_id, "finding_semantics_id")
        _validate_identifier(self.state, "state")
        if self.measurement_point_id is not None:
            _validate_identifier(self.measurement_point_id, "measurement_point_id")

        if not evidence_refs:
            raise ValueError("evidence_refs must contain at least one evidence reference")
        for evidence_ref in evidence_refs:
            _validate_identifier(evidence_ref, "evidence_ref")
        if len(set(evidence_refs)) != len(evidence_refs):
            raise ValueError("evidence_refs must contain unique values")

        object.__setattr__(self, "evidence_refs", evidence_refs)


def validate_operational_finding_against_run(
    finding: OperationalFinding,
    run: AnalysisRun,
) -> None:
    """Validate identity and observation-time linkage without interpreting state."""
    if finding.analysis_run_id != run.analysis_run_id:
        raise ValueError("finding analysis_run_id does not match the analysis run")
    if finding.asset_id != run.asset_id:
        raise ValueError("finding asset_id does not match the analysis run")
    if finding.measurement_point_id != run.measurement_point_id:
        raise ValueError("finding measurement_point_id does not match the analysis run")

    try:
        outside_window = not (run.observed_start_at <= finding.observed_at <= run.observed_end_at)
    except TypeError as error:
        raise ValueError(
            "finding observed_at must use timezone awareness compatible with the run"
        ) from error
    if outside_window:
        raise ValueError("finding observed_at is outside the analysis observation window")


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _validate_time_window(start: datetime, end: datetime, label: str) -> None:
    if _is_timezone_aware(start) != _is_timezone_aware(end):
        raise ValueError(f"{label} time window must use the same timezone awareness")
    if start > end:
        raise ValueError(f"{label} start time must not be after end time")


def _is_timezone_aware(value: datetime) -> bool:
    return value.utcoffset() is not None
