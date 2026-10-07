"""Live-evidence retention policy and the evidence an open review keeps.

Live OPC UA observations and finalized windows are kept for a bounded period by
event time. Explicitly imported FILE history is not subject to this policy. Evidence
behind a review request that is not closed yet stays until the review closes, so a
reviewer can still open its observations, window and input snapshot.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from industrial_phm.application.analysis_input import WindowInputReference
from industrial_phm.application.asset_history import HistoricalInputReference
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

DEFAULT_LIVE_RETENTION = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class ProtectedEvidenceRange:
    """One source's observed range that retention must not delete (inclusive)."""

    source_id: str
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        for value, name in ((self.start_at, "start_at"), (self.end_at, "end_at")):
            if not isinstance(value, datetime) or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.start_at > self.end_at:
            raise ValueError("start_at must not be after end_at")

    def covers(self, source_id: str, start_at: datetime, end_at: datetime) -> bool:
        """Whether [start_at, end_at] of this source overlaps the protected range."""
        return source_id == self.source_id and start_at <= self.end_at and end_at >= self.start_at


@dataclass(frozen=True, slots=True)
class RetentionProtection:
    """Evidence kept regardless of age: observed ranges, windows and snapshots."""

    ranges: tuple[ProtectedEvidenceRange, ...] = ()
    window_ids: frozenset[str] = frozenset()
    snapshot_ids: frozenset[int] = frozenset()

    def covers(self, source_id: str, start_at: datetime, end_at: datetime) -> bool:
        return any(item.covers(source_id, start_at, end_at) for item in self.ranges)


def retention_cutoff(now: datetime, retention: timedelta = DEFAULT_LIVE_RETENTION) -> datetime:
    """Live evidence whose event time is before this instant is eligible for deletion."""
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if not isinstance(retention, timedelta) or retention <= timedelta(0):
        raise ValueError("retention must be a positive duration")
    return now - retention


def open_review_protection(
    *,
    analysis_results: Sequence[OperationalAnalysisResult],
    findings: Sequence[OperationalFinding],
    review_events: Sequence[FindingReviewEvent],
) -> RetentionProtection:
    """Protect the inputs of every review request that is not closed.

    Fails closed: a review request whose analysis result cannot be found raises,
    because its evidence could not be protected.
    """
    results = {
        (result.run.analysis_run_id, result.evidence.capability_id): result
        for result in analysis_results
    }
    events = tuple(review_events)
    ranges: list[ProtectedEvidenceRange] = []
    window_ids: set[str] = set()
    snapshot_ids: set[int] = set()
    for finding in findings:
        if finding.finding_semantics_id != HUMAN_REVIEW_FINDING_SEMANTICS_ID:
            continue
        if finding_review_status(events, finding.finding_id) == FindingReviewStatus.CLOSED:
            continue
        result = results.get((finding.analysis_run_id, finding.capability_id))
        if result is None:
            raise ValueError(
                "open review references an analysis result that is not stored: "
                f"{finding.analysis_run_id}; refusing to delete its evidence"
            )
        run = result.run
        ranges.append(
            ProtectedEvidenceRange(run.source_id, run.observed_start_at, run.observed_end_at)
        )
        reference = getattr(result.evidence, "input_reference", None)
        if isinstance(reference, WindowInputReference):
            window_ids.add(reference.window_id)
            ranges.append(
                ProtectedEvidenceRange(
                    reference.source_id, reference.window_start, reference.window_end
                )
            )
        elif isinstance(reference, HistoricalInputReference):
            snapshot_ids.add(reference.snapshot_id)
    return RetentionProtection(tuple(ranges), frozenset(window_ids), frozenset(snapshot_ids))
