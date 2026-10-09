"""Bounded evidence-linked human review commands for the local Operations Web UI.

This does not infer a fault or change an asset health state. Both actions run
only inside the existing workspace writer or supervisor command boundary.
"""

from __future__ import annotations

from pathlib import Path

from industrial_phm.application import (
    FindingReviewAction,
    FindingReviewStatus,
    JsonFindingReviewRepository,
    JsonOperationalFindingRepository,
    SqlitePhaseUnbalanceRepository,
)
from industrial_phm.runtime.operations_app_actions import OperationsAppActions
from industrial_phm.runtime.operations_app_wiring import OperationsAppPaths
from industrial_phm.runtime.operations_workspace import OperationsWorkspace


class WebReviewNotFound(LookupError):
    """Requested exact persisted analysis or finding identity does not exist."""


class WebReviewConflict(ValueError):
    """Existing human review state forbids the requested state transition."""


def _id(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 128
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise ValueError("invalid review identity")
    return value


def request_web_analysis_review(root: Path, payload: dict[str, object]) -> dict[str, object]:
    """Request human review of an exact, persisted phase-unbalance evidence result."""
    if set(payload) != {"analysis_run_id", "evidence_id"}:
        raise ValueError("unexpected analysis review fields")
    run_id = _id(payload, "analysis_run_id")
    evidence_id = _id(payload, "evidence_id")
    workspace = OperationsWorkspace(root)
    paths = OperationsAppPaths(workspace)
    results = SqlitePhaseUnbalanceRepository(paths.phase_analysis).find_results({run_id})
    if len(results) != 1 or results[0].evidence.evidence_id != evidence_id:
        raise WebReviewNotFound("exact analysis evidence unavailable")
    finding, _ = OperationsAppActions(paths).request_review(results[0])
    # The finding is idempotent, but its human disposition may have advanced.
    status = JsonFindingReviewRepository(paths.review).status_for(finding.finding_id)
    return {
        "schema_version": 1,
        "finding_id": finding.finding_id,
        "analysis_run_id": finding.analysis_run_id,
        "asset_id": finding.asset_id,
        "evidence_ids": list(finding.evidence_refs),
        "status": status.value,
        "meaning": "human-review-request-not-maintenance-completion-or-diagnosis",
    }


def record_web_review_action(root: Path, payload: dict[str, object]) -> dict[str, object]:
    """Record only explicit note, acknowledgement and close of an existing finding."""
    if set(payload) != {"finding_id", "action", "note"}:
        raise ValueError("unexpected review action fields")
    finding_id = _id(payload, "finding_id")
    action = payload["action"]
    note = payload["note"]
    if not isinstance(action, str) or action not in {"note", "acknowledge", "close"}:
        raise ValueError("invalid review action")
    if (
        not isinstance(note, str)
        or len(note) > 1000
        or len(note.encode("utf-8")) > 2048
        or note != note.strip()
        or any(ord(char) < 32 and char not in "\n\t" for char in note)
    ):
        raise ValueError("invalid review note")
    if action == "note" and not note:
        raise ValueError("note action requires a note")
    paths = OperationsAppPaths(OperationsWorkspace(root))
    finding = next(
        (
            item
            for item in JsonOperationalFindingRepository(paths.findings).list_findings()
            if item.finding_id == finding_id
        ),
        None,
    )
    if finding is None:
        raise WebReviewNotFound("finding identity unavailable")
    reviews = JsonFindingReviewRepository(paths.review)
    status = reviews.status_for(finding_id)
    if (
        status == FindingReviewStatus.CLOSED
        or (action == "acknowledge" and status != FindingReviewStatus.OPEN)
        or (action == "close" and status != FindingReviewStatus.ACKNOWLEDGED)
    ):
        raise WebReviewConflict("review transition forbidden")
    event, _ = OperationsAppActions(paths).record_review_action(
        finding, action=FindingReviewAction(action), note=note
    )
    return {
        "schema_version": 1,
        "finding_id": finding_id,
        "event_id": event.event_id,
        "action": event.action.value,
        "recorded_at": event.recorded_at.isoformat(),
        "status": reviews.status_for(finding_id).value,
        "meaning": "human-review-disposition-not-maintenance-execution",
    }
