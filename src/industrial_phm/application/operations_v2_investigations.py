"""Investigation queue projections for Operations V2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from industrial_phm.application.finding_review import HUMAN_REVIEW_FINDING_SEMANTICS_ID
from industrial_phm.application.maintenance_review import (
    FindingReviewEvent,
    FindingReviewStatus,
    finding_review_status,
)
from industrial_phm.application.operational import (
    OperationalAnalysisResult,
    OperationalFinding,
)


class InvestigationReviewState(StrEnum):
    """Review workflow state attached to an analysis result, never analysis severity."""

    NOT_REQUESTED = "not-requested"
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class InvestigationQueueItem:
    investigation_id: str
    analysis_run_id: str
    asset_id: str
    source_id: str
    measurement_point_id: str | None
    capability_id: str
    evidence_id: str
    observed_start_at: datetime
    observed_end_at: datetime
    completed_at: datetime
    data_quality: str
    review_state: InvestigationReviewState
    finding_id: str | None = None
    review_updated_at: datetime | None = None

    def __post_init__(self) -> None:
        for text_value, field_name in (
            (self.investigation_id, "investigation_id"),
            (self.analysis_run_id, "analysis_run_id"),
            (self.asset_id, "asset_id"),
            (self.source_id, "source_id"),
            (self.capability_id, "capability_id"),
            (self.evidence_id, "evidence_id"),
            (self.data_quality, "data_quality"),
        ):
            _require_text(text_value, field_name)
        if self.measurement_point_id is not None:
            _require_text(self.measurement_point_id, "measurement_point_id")
        if self.finding_id is not None:
            _require_text(self.finding_id, "finding_id")
        for time_value, field_name in (
            (self.observed_start_at, "observed_start_at"),
            (self.observed_end_at, "observed_end_at"),
            (self.completed_at, "completed_at"),
        ):
            _require_aware(time_value, field_name)
        if self.review_updated_at is not None:
            _require_aware(self.review_updated_at, "review_updated_at")
        if self.observed_start_at > self.observed_end_at:
            raise ValueError("observed_start_at must not be after observed_end_at")
        if not isinstance(self.review_state, InvestigationReviewState):
            raise ValueError("review_state must be an InvestigationReviewState")
        if self.review_state == InvestigationReviewState.NOT_REQUESTED:
            if self.finding_id is not None or self.review_updated_at is not None:
                raise ValueError("not-requested item must not carry review evidence")
        elif self.finding_id is None:
            raise ValueError("requested review state requires finding_id")


@dataclass(frozen=True, slots=True)
class InvestigationQueueView:
    items: Sequence[InvestigationQueueItem]

    def __post_init__(self) -> None:
        items = tuple(self.items)
        if any(not isinstance(item, InvestigationQueueItem) for item in items):
            raise ValueError("items must contain InvestigationQueueItem values")
        ids = tuple(item.investigation_id for item in items)
        if len(set(ids)) != len(ids):
            raise ValueError("items must have unique investigation_id values")
        expected = tuple(
            sorted(
                items,
                key=lambda item: (-item.completed_at.timestamp(), item.investigation_id),
            )
        )
        if items != expected:
            raise ValueError("items must use newest-first deterministic ordering")
        object.__setattr__(self, "items", items)

    @property
    def asset_ids(self) -> tuple[str, ...]:
        return tuple(sorted({item.asset_id for item in self.items}))

    @property
    def capability_ids(self) -> tuple[str, ...]:
        return tuple(sorted({item.capability_id for item in self.items}))

    def filter(
        self,
        *,
        review_state: InvestigationReviewState | None = None,
        asset_id: str | None = None,
        capability_id: str | None = None,
    ) -> tuple[InvestigationQueueItem, ...]:
        if review_state is not None and not isinstance(review_state, InvestigationReviewState):
            raise ValueError("review_state must be InvestigationReviewState or None")
        for value, field_name in (
            (asset_id, "asset_id"),
            (capability_id, "capability_id"),
        ):
            if value is not None:
                _require_text(value, field_name)
        return tuple(
            item
            for item in self.items
            if (review_state is None or item.review_state == review_state)
            and (asset_id is None or item.asset_id == asset_id)
            and (capability_id is None or item.capability_id == capability_id)
        )


def build_investigation_queue(
    *,
    analysis_results: Sequence[OperationalAnalysisResult],
    findings: Sequence[OperationalFinding],
    review_events: Sequence[FindingReviewEvent],
) -> InvestigationQueueView:
    """Join analysis evidence to explicit human-review workflow facts."""

    results = tuple(analysis_results)
    if any(not isinstance(item, OperationalAnalysisResult) for item in results):
        raise ValueError("analysis_results contains an unsupported value")
    finding_values = tuple(findings)
    if any(not isinstance(item, OperationalFinding) for item in finding_values):
        raise ValueError("findings must contain OperationalFinding values")
    event_values = tuple(review_events)
    if any(not isinstance(item, FindingReviewEvent) for item in event_values):
        raise ValueError("review_events must contain FindingReviewEvent values")

    review_findings: dict[tuple[str, str], OperationalFinding] = {}
    for finding in finding_values:
        if finding.finding_semantics_id != HUMAN_REVIEW_FINDING_SEMANTICS_ID:
            continue
        key = (finding.analysis_run_id, finding.capability_id)
        if key in review_findings:
            raise ValueError("multiple human-review findings exist for one analysis/capability")
        review_findings[key] = finding

    items = []
    seen_ids: set[str] = set()
    for result in results:
        run, evidence = result.run, result.evidence
        investigation_id = f"{run.analysis_run_id}:{evidence.capability_id}"
        if investigation_id in seen_ids:
            raise ValueError("duplicate analysis result identity")
        seen_ids.add(investigation_id)

        finding = review_findings.get((run.analysis_run_id, evidence.capability_id))
        if finding is None:
            state = InvestigationReviewState.NOT_REQUESTED
            finding_id = None
            updated_at = None
        else:
            matching_events = tuple(
                event for event in event_values if event.finding_id == finding.finding_id
            )
            status = finding_review_status(matching_events, finding.finding_id)
            state = _review_state(status)
            finding_id = finding.finding_id
            updated_at = max(
                (event.recorded_at for event in matching_events),
                default=None,
            )

        items.append(
            InvestigationQueueItem(
                investigation_id=investigation_id,
                analysis_run_id=run.analysis_run_id,
                asset_id=run.asset_id,
                source_id=run.source_id,
                measurement_point_id=run.measurement_point_id,
                capability_id=evidence.capability_id,
                evidence_id=evidence.evidence_id,
                observed_start_at=run.observed_start_at,
                observed_end_at=run.observed_end_at,
                completed_at=run.completed_at,
                data_quality=run.data_quality.state.value,
                review_state=state,
                finding_id=finding_id,
                review_updated_at=updated_at,
            )
        )

    return InvestigationQueueView(
        tuple(
            sorted(
                items,
                key=lambda item: (-item.completed_at.timestamp(), item.investigation_id),
            )
        )
    )


def _review_state(status: FindingReviewStatus) -> InvestigationReviewState:
    return {
        FindingReviewStatus.OPEN: InvestigationReviewState.OPEN,
        FindingReviewStatus.ACKNOWLEDGED: InvestigationReviewState.ACKNOWLEDGED,
        FindingReviewStatus.CLOSED: InvestigationReviewState.CLOSED,
    }[status]


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _require_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
