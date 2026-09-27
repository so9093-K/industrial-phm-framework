"""Evidence-backed Operations overview read model.

This module aggregates already-loaded application facts for presentation. It does not
read repositories, invent asset health, derive PHM severity, or promote source state to
an operational diagnosis.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from industrial_phm.application.finding_review import (
    HUMAN_REVIEW_FINDING_SEMANTICS_ID,
    HUMAN_REVIEW_FINDING_STATE,
)
from industrial_phm.application.maintenance_review import (
    FindingReviewEvent,
    FindingReviewStatus,
    finding_review_status,
)
from industrial_phm.application.operational import AnalysisRun, OperationalFinding
from industrial_phm.application.source_freshness import SourceFreshnessPolicy
from industrial_phm.application.source_health import (
    SourceDataFlowState,
    SourceHealthAssessment,
    assess_source_health,
)
from industrial_phm.application.source_lifecycle import (
    SourceLifecycleRecord,
    SourceLifecycleState,
)
from industrial_phm.application.source_receipt import SourceReceiptEvidence
from industrial_phm.application.source_registration import RegisteredSource
from industrial_phm.application.source_runtime import SourceConnectionAttemptEvidence


@dataclass(frozen=True, slots=True)
class OperationsReviewSummary:
    """Current human-review disposition for one explicit review-request finding."""

    finding: OperationalFinding
    status: FindingReviewStatus

    def __post_init__(self) -> None:
        if not isinstance(self.finding, OperationalFinding):
            raise ValueError("finding must be an OperationalFinding")
        if self.finding.finding_semantics_id != HUMAN_REVIEW_FINDING_SEMANTICS_ID:
            raise ValueError("review summary finding must use human-review-request semantics")
        if self.finding.state != HUMAN_REVIEW_FINDING_STATE:
            raise ValueError("review summary finding must use REVIEW_REQUIRED state")
        if not isinstance(self.status, FindingReviewStatus):
            raise ValueError("status must be a FindingReviewStatus")


@dataclass(frozen=True, slots=True)
class OperationsOverview:
    """Product-facing summary of factual operational evidence.

    Source data-flow dimensions remain separate from asset health. Review counts describe
    explicit human-review workflow state only. Analysis counts describe recorded
    AnalysisRun values and do not imply a condition, fault, alarm, or risk verdict.
    """

    assessed_at: datetime
    source_health_assessments: Sequence[SourceHealthAssessment]
    analysis_run_count: int
    latest_analysis_run: AnalysisRun | None
    review_summaries: Sequence[OperationsReviewSummary]

    def __post_init__(self) -> None:
        source_health = tuple(self.source_health_assessments)
        reviews = tuple(self.review_summaries)

        if not isinstance(self.assessed_at, datetime) or self.assessed_at.utcoffset() is None:
            raise ValueError("assessed_at must be a timezone-aware datetime")
        if any(not isinstance(item, SourceHealthAssessment) for item in source_health):
            raise ValueError(
                "source_health_assessments must contain only SourceHealthAssessment values"
            )
        source_ids = tuple(item.source_id for item in source_health)
        if len(set(source_ids)) != len(source_ids):
            raise ValueError("source_health_assessments must contain unique source IDs")
        if tuple(sorted(source_ids)) != source_ids:
            raise ValueError("source_health_assessments must use deterministic source-ID order")

        if (
            isinstance(self.analysis_run_count, bool)
            or not isinstance(self.analysis_run_count, int)
            or self.analysis_run_count < 0
        ):
            raise ValueError("analysis_run_count must be a non-negative integer")
        if self.latest_analysis_run is not None and not isinstance(
            self.latest_analysis_run,
            AnalysisRun,
        ):
            raise ValueError("latest_analysis_run must be an AnalysisRun when provided")
        if self.analysis_run_count == 0 and self.latest_analysis_run is not None:
            raise ValueError("latest_analysis_run must be unavailable when no analysis is recorded")
        if self.analysis_run_count > 0 and self.latest_analysis_run is None:
            raise ValueError("latest_analysis_run is required when analysis runs are recorded")

        if any(not isinstance(item, OperationsReviewSummary) for item in reviews):
            raise ValueError("review_summaries must contain only OperationsReviewSummary values")
        finding_ids = tuple(item.finding.finding_id for item in reviews)
        if len(set(finding_ids)) != len(finding_ids):
            raise ValueError("review_summaries must contain unique findings")

        object.__setattr__(self, "source_health_assessments", source_health)
        object.__setattr__(self, "review_summaries", reviews)

    @property
    def registered_source_count(self) -> int:
        """Return the number of registered sources represented by this overview."""
        return len(self.source_health_assessments)

    @property
    def active_source_count(self) -> int:
        """Return sources administratively enabled for runtime consumption."""
        return sum(
            item.lifecycle.state == SourceLifecycleState.ACTIVE
            for item in self.source_health_assessments
        )

    def source_data_flow_count(self, state: SourceDataFlowState) -> int:
        """Count sources in one factual data-flow state."""
        if not isinstance(state, SourceDataFlowState):
            raise ValueError("state must be a SourceDataFlowState")
        return sum(item.data_flow_state == state for item in self.source_health_assessments)

    @property
    def pending_review_count(self) -> int:
        """Return explicit review requests whose human workflow is not closed."""
        return sum(item.status != FindingReviewStatus.CLOSED for item in self.review_summaries)

    @property
    def open_review_count(self) -> int:
        return sum(item.status == FindingReviewStatus.OPEN for item in self.review_summaries)

    @property
    def acknowledged_review_count(self) -> int:
        return sum(
            item.status == FindingReviewStatus.ACKNOWLEDGED for item in self.review_summaries
        )

    @property
    def closed_review_count(self) -> int:
        return sum(item.status == FindingReviewStatus.CLOSED for item in self.review_summaries)


def build_operations_overview(
    *,
    sources: Sequence[RegisteredSource],
    lifecycle_records: Sequence[SourceLifecycleRecord],
    receipts: Sequence[SourceReceiptEvidence],
    freshness_policies: Sequence[SourceFreshnessPolicy],
    connection_attempts: Sequence[SourceConnectionAttemptEvidence],
    analysis_runs: Sequence[AnalysisRun],
    findings: Sequence[OperationalFinding],
    review_events: Sequence[FindingReviewEvent],
    as_of: datetime,
) -> OperationsOverview:
    """Build one deterministic overview from already-loaded operational facts.

    Control-plane/runtime repositories remain authoritative for persistence. This
    function validates the joined current-source population and creates only a read
    model for presentation.
    """
    if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
        raise ValueError("as_of must be a timezone-aware datetime")

    source_values = _require_unique(
        sources,
        RegisteredSource,
        key=lambda item: item.source_id,
        label="sources",
    )
    source_ids = {item.source_id for item in source_values}

    lifecycle_values = _require_unique(
        lifecycle_records,
        SourceLifecycleRecord,
        key=lambda item: item.source_id,
        label="lifecycle_records",
    )
    lifecycle_by_source = {item.source_id: item for item in lifecycle_values}
    if set(lifecycle_by_source) != source_ids:
        raise ValueError(
            "lifecycle_records must contain exactly one record for every registered source"
        )

    receipt_values = _require_unique(
        receipts,
        SourceReceiptEvidence,
        key=lambda item: item.source_id,
        label="receipts",
    )
    policy_values = _require_unique(
        freshness_policies,
        SourceFreshnessPolicy,
        key=lambda item: item.source_id,
        label="freshness_policies",
    )
    attempt_values = _require_unique(
        connection_attempts,
        SourceConnectionAttemptEvidence,
        key=lambda item: item.source_id,
        label="connection_attempts",
    )
    _require_registered_source_refs(receipt_values, source_ids, label="receipt")
    _require_registered_source_refs(policy_values, source_ids, label="freshness policy")
    _require_registered_source_refs(attempt_values, source_ids, label="connection attempt")

    receipts_by_source = {item.source_id: item for item in receipt_values}
    policies_by_source = {item.source_id: item for item in policy_values}
    attempts_by_source = {item.source_id: item for item in attempt_values}
    source_health = tuple(
        assess_source_health(
            lifecycle_by_source[source.source_id],
            receipts_by_source.get(source.source_id),
            policies_by_source.get(source.source_id),
            connection_attempt=attempts_by_source.get(source.source_id),
            as_of=as_of,
        )
        for source in sorted(source_values, key=lambda item: item.source_id)
    )

    runs = tuple(analysis_runs)
    if any(not isinstance(item, AnalysisRun) for item in runs):
        raise ValueError("analysis_runs must contain only AnalysisRun values")
    run_ids = tuple(item.analysis_run_id for item in runs)
    if len(set(run_ids)) != len(run_ids):
        raise ValueError("analysis_runs must contain unique analysis_run_id values")
    latest_analysis = (
        None if not runs else max(runs, key=lambda item: (item.completed_at, item.analysis_run_id))
    )

    finding_values = tuple(findings)
    if any(not isinstance(item, OperationalFinding) for item in finding_values):
        raise ValueError("findings must contain only OperationalFinding values")
    finding_ids = tuple(item.finding_id for item in finding_values)
    if len(set(finding_ids)) != len(finding_ids):
        raise ValueError("findings must contain unique finding_id values")

    event_values = tuple(review_events)
    if any(not isinstance(item, FindingReviewEvent) for item in event_values):
        raise ValueError("review_events must contain only FindingReviewEvent values")

    review_findings = tuple(
        item
        for item in finding_values
        if item.finding_semantics_id == HUMAN_REVIEW_FINDING_SEMANTICS_ID
        and item.state == HUMAN_REVIEW_FINDING_STATE
    )
    review_summaries = tuple(
        OperationsReviewSummary(
            finding=finding,
            status=finding_review_status(event_values, finding.finding_id),
        )
        for finding in sorted(
            review_findings,
            key=lambda item: (item.observed_at, item.finding_id),
        )
    )

    return OperationsOverview(
        assessed_at=as_of,
        source_health_assessments=source_health,
        analysis_run_count=len(runs),
        latest_analysis_run=latest_analysis,
        review_summaries=review_summaries,
    )


class _SourceScoped(Protocol):
    @property
    def source_id(self) -> str:
        """Return the registered source identity."""
        ...


def _require_unique[T](
    values: Sequence[T],
    expected_type: type[T],
    *,
    key: Callable[[T], str],
    label: str,
) -> tuple[T, ...]:
    items = tuple(values)
    if any(not isinstance(item, expected_type) for item in items):
        raise ValueError(f"{label} contains an unsupported value")
    keys = tuple(key(item) for item in items)
    if len(set(keys)) != len(keys):
        raise ValueError(f"{label} must contain unique source/record identities")
    return items


def _require_registered_source_refs[T: _SourceScoped](
    values: Sequence[T],
    source_ids: set[str],
    *,
    label: str,
) -> None:
    for item in values:
        if item.source_id not in source_ids:
            raise ValueError(f"{label} references an unregistered source: {item.source_id}")
