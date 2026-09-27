"""Evidence-based Operations attention queue.

Attention items are factual projections of existing operational evidence. They are not
PHM severity, alarm priority, risk scores, diagnoses, or maintenance recommendations.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from industrial_phm.application.asset_identity import AssetIdentity
from industrial_phm.application.maintenance_review import FindingReviewStatus
from industrial_phm.application.observation import AssetObservationSummary
from industrial_phm.application.operations_overview import OperationsOverview
from industrial_phm.application.source_health import SourceDataFlowState


class AttentionKind(StrEnum):
    """Factual attention categories currently supported by Operations."""

    SOURCE_ERROR = "SOURCE_ERROR"
    NO_RECEIPT = "NO_RECEIPT"
    STALE = "STALE"
    DATA_QUALITY_ISSUE = "DATA_QUALITY_ISSUE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    SYSTEM_STATE_ERROR = "SYSTEM_STATE_ERROR"


class AttentionHandlingState(StrEnum):
    """Workflow handling state used only for deterministic queue ordering."""

    UNHANDLED = "UNHANDLED"
    ACTIVE = "ACTIVE"


@dataclass(frozen=True, slots=True)
class SystemStateErrorEvidence:
    """Current application-state read failure detected by the Operations surface."""

    scope: str
    detail: str
    detected_at: datetime

    def __post_init__(self) -> None:
        _validate_identifier(self.scope, "scope")
        _validate_identifier(self.detail, "detail")
        _validate_aware_datetime(self.detected_at, "detected_at")


@dataclass(frozen=True, slots=True)
class AttentionItem:
    """One factual reason for a person to inspect Operations evidence."""

    attention_id: str
    kind: AttentionKind
    handling_state: AttentionHandlingState
    occurred_at: datetime | None
    asset_identity: AssetIdentity | None = None
    source_id: str | None = None
    measurement_point_id: str | None = None
    finding_id: str | None = None
    review_status: FindingReviewStatus | None = None
    data_quality_issue_codes: Sequence[str] = ()
    detail: str | None = None
    system_scope: str | None = None

    def __post_init__(self) -> None:
        issue_codes = tuple(self.data_quality_issue_codes)

        _validate_identifier(self.attention_id, "attention_id")
        if not isinstance(self.kind, AttentionKind):
            raise ValueError("kind must be an AttentionKind")
        if not isinstance(self.handling_state, AttentionHandlingState):
            raise ValueError("handling_state must be an AttentionHandlingState")
        if self.occurred_at is not None:
            _validate_aware_datetime(self.occurred_at, "occurred_at")
        if self.asset_identity is not None and not isinstance(
            self.asset_identity,
            AssetIdentity,
        ):
            raise ValueError("asset_identity must be AssetIdentity when provided")
        for value, field_name in (
            (self.source_id, "source_id"),
            (self.measurement_point_id, "measurement_point_id"),
            (self.finding_id, "finding_id"),
            (self.detail, "detail"),
            (self.system_scope, "system_scope"),
        ):
            if value is not None:
                _validate_identifier(value, field_name)
        for issue_code in issue_codes:
            _validate_identifier(issue_code, "data_quality_issue_code")
        if len(set(issue_codes)) != len(issue_codes):
            raise ValueError("data_quality_issue_codes must contain unique values")

        _validate_kind_payload(self, issue_codes)
        object.__setattr__(self, "data_quality_issue_codes", issue_codes)


@dataclass(frozen=True, slots=True)
class OperationsAttentionQueue:
    """Deterministically ordered current attention projection."""

    items: Sequence[AttentionItem]

    def __post_init__(self) -> None:
        items = tuple(self.items)
        if any(not isinstance(item, AttentionItem) for item in items):
            raise ValueError("items must contain only AttentionItem values")
        ids = tuple(item.attention_id for item in items)
        if len(set(ids)) != len(ids):
            raise ValueError("items must contain unique attention_id values")
        if tuple(sorted(items, key=_attention_sort_key)) != items:
            raise ValueError("items must use deterministic attention ordering")
        object.__setattr__(self, "items", items)

    def count(self, kind: AttentionKind) -> int:
        """Return the number of current items in one factual attention category."""
        if not isinstance(kind, AttentionKind):
            raise ValueError("kind must be an AttentionKind")
        return sum(item.kind == kind for item in self.items)

    @property
    def unhandled_count(self) -> int:
        return sum(item.handling_state == AttentionHandlingState.UNHANDLED for item in self.items)


def build_operations_attention_queue(
    *,
    overview: OperationsOverview,
    latest_observations: Sequence[AssetObservationSummary] = (),
    system_errors: Sequence[SystemStateErrorEvidence] = (),
) -> OperationsAttentionQueue:
    """Project current evidence into a factual, severity-free attention queue."""
    if not isinstance(overview, OperationsOverview):
        raise ValueError("overview must be an OperationsOverview")

    observations = tuple(latest_observations)
    if any(not isinstance(item, AssetObservationSummary) for item in observations):
        raise ValueError("latest_observations must contain only AssetObservationSummary values")
    observation_scopes = tuple(
        (item.source_id, item.asset_id, item.measurement_point_id) for item in observations
    )
    if len(set(observation_scopes)) != len(observation_scopes):
        raise ValueError(
            "latest_observations must contain at most one value per source/asset/measurement point"
        )

    current_source_ids = {item.source_id for item in overview.source_health_assessments}
    for observation in observations:
        if observation.source_id not in current_source_ids:
            raise ValueError("latest_observations must reference a source in the current overview")

    errors = tuple(system_errors)
    if any(not isinstance(item, SystemStateErrorEvidence) for item in errors):
        raise ValueError("system_errors must contain only SystemStateErrorEvidence values")
    scopes = tuple(item.scope for item in errors)
    if len(set(scopes)) != len(scopes):
        raise ValueError("system_errors must contain unique scopes")

    items: list[AttentionItem] = []
    for health in overview.source_health_assessments:
        if health.data_flow_state == SourceDataFlowState.SOURCE_ERROR:
            items.append(
                AttentionItem(
                    attention_id=f"source-error:{health.source_id}",
                    kind=AttentionKind.SOURCE_ERROR,
                    handling_state=AttentionHandlingState.ACTIVE,
                    occurred_at=health.lifecycle.changed_at,
                    source_id=health.source_id,
                    detail=health.reason,
                )
            )
        elif health.data_flow_state == SourceDataFlowState.NO_RECEIPT:
            items.append(
                AttentionItem(
                    attention_id=f"no-receipt:{health.source_id}",
                    kind=AttentionKind.NO_RECEIPT,
                    handling_state=AttentionHandlingState.ACTIVE,
                    occurred_at=health.lifecycle.changed_at,
                    source_id=health.source_id,
                    detail=health.reason,
                )
            )
        elif health.data_flow_state == SourceDataFlowState.STALE:
            freshness = health.freshness
            if (
                freshness is None
                or freshness.observed_at is None
                or freshness.max_observation_age_seconds is None
            ):
                raise AssertionError("validated STALE source is missing freshness evidence")
            stale_since = freshness.observed_at + timedelta(
                seconds=freshness.max_observation_age_seconds
            )
            items.append(
                AttentionItem(
                    attention_id=f"stale:{health.source_id}",
                    kind=AttentionKind.STALE,
                    handling_state=AttentionHandlingState.ACTIVE,
                    occurred_at=stale_since,
                    source_id=health.source_id,
                )
            )

    for observation in observations:
        if observation.data_quality.issues:
            items.append(
                AttentionItem(
                    attention_id=_data_quality_attention_id(observation),
                    kind=AttentionKind.DATA_QUALITY_ISSUE,
                    handling_state=AttentionHandlingState.ACTIVE,
                    occurred_at=observation.observed_end_at,
                    asset_identity=observation.asset_identity,
                    source_id=observation.source_id,
                    measurement_point_id=observation.measurement_point_id,
                    data_quality_issue_codes=tuple(
                        dict.fromkeys(observation.data_quality.issue_codes)
                    ),
                )
            )

    for review in overview.review_summaries:
        if review.status == FindingReviewStatus.CLOSED:
            continue
        handling_state = (
            AttentionHandlingState.UNHANDLED
            if review.status == FindingReviewStatus.OPEN
            else AttentionHandlingState.ACTIVE
        )
        finding = review.finding
        items.append(
            AttentionItem(
                attention_id=f"review-required:{finding.finding_id}",
                kind=AttentionKind.REVIEW_REQUIRED,
                handling_state=handling_state,
                occurred_at=finding.observed_at,
                asset_identity=finding.asset_identity,
                measurement_point_id=finding.measurement_point_id,
                finding_id=finding.finding_id,
                review_status=review.status,
            )
        )

    for error in errors:
        items.append(
            AttentionItem(
                attention_id=f"system-state-error:{error.scope}",
                kind=AttentionKind.SYSTEM_STATE_ERROR,
                handling_state=AttentionHandlingState.ACTIVE,
                occurred_at=error.detected_at,
                detail=error.detail,
                system_scope=error.scope,
            )
        )

    return OperationsAttentionQueue(tuple(sorted(items, key=_attention_sort_key)))


def _validate_kind_payload(
    item: AttentionItem,
    issue_codes: tuple[str, ...],
) -> None:
    source_kinds = {
        AttentionKind.SOURCE_ERROR,
        AttentionKind.NO_RECEIPT,
        AttentionKind.STALE,
    }
    if item.kind in source_kinds:
        if item.source_id is None:
            raise ValueError(f"{item.kind.value} attention requires source_id")
        if item.finding_id is not None or item.review_status is not None:
            raise ValueError(f"{item.kind.value} attention must not carry review fields")
        if issue_codes:
            raise ValueError(f"{item.kind.value} attention must not carry quality issue codes")
        if item.system_scope is not None:
            raise ValueError(f"{item.kind.value} attention must not carry system_scope")
        return

    if item.kind == AttentionKind.DATA_QUALITY_ISSUE:
        if item.asset_identity is None or item.source_id is None or not issue_codes:
            raise ValueError(
                "data-quality attention requires asset, source and issue-code evidence"
            )
        if item.finding_id is not None or item.review_status is not None:
            raise ValueError("data-quality attention must not carry review fields")
        if item.system_scope is not None:
            raise ValueError("data-quality attention must not carry system_scope")
        return

    if item.kind == AttentionKind.REVIEW_REQUIRED:
        if (
            item.asset_identity is None
            or item.finding_id is None
            or item.review_status
            not in {FindingReviewStatus.OPEN, FindingReviewStatus.ACKNOWLEDGED}
        ):
            raise ValueError(
                "review attention requires asset, finding and unresolved review status"
            )
        if item.source_id is not None or issue_codes or item.system_scope is not None:
            raise ValueError("review attention carries unsupported source/quality/system fields")
        if (
            item.review_status == FindingReviewStatus.OPEN
            and item.handling_state != AttentionHandlingState.UNHANDLED
        ):
            raise ValueError("OPEN review attention must be UNHANDLED")
        if (
            item.review_status == FindingReviewStatus.ACKNOWLEDGED
            and item.handling_state != AttentionHandlingState.ACTIVE
        ):
            raise ValueError("ACKNOWLEDGED review attention must be ACTIVE")
        return

    if item.kind == AttentionKind.SYSTEM_STATE_ERROR:
        if item.system_scope is None or item.detail is None:
            raise ValueError("system-state attention requires scope and detail")
        if (
            item.asset_identity is not None
            or item.source_id is not None
            or item.finding_id is not None
            or item.review_status is not None
            or issue_codes
        ):
            raise ValueError("system-state attention must not carry operational entity fields")
        return

    raise AssertionError(f"unsupported attention kind: {item.kind!r}")


def _data_quality_attention_id(observation: AssetObservationSummary) -> str:
    point = observation.measurement_point_id or "-"
    return f"data-quality:{observation.source_id}:{observation.asset_id}:{point}"


def _attention_sort_key(item: AttentionItem) -> tuple[int, float, str]:
    handling_rank = 0 if item.handling_state == AttentionHandlingState.UNHANDLED else 1
    occurred_rank = float("inf") if item.occurred_at is None else -item.occurred_at.timestamp()
    return handling_rank, occurred_rank, item.attention_id


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")
