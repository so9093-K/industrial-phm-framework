"""Bounded evidence-linked human review commands for the local Operations Web UI.

This does not infer a fault or change an asset health state. Both actions run
only inside the existing workspace writer or supervisor command boundary.
"""

from __future__ import annotations

import sqlite3
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs
from uuid import UUID

from industrial_phm.application import (
    FindingReviewAction,
    FindingReviewStatus,
    JsonFileFeatureAnalysisRepository,
    JsonFindingReviewRepository,
    JsonOperationalFindingRepository,
    SqlitePhaseUnbalanceRepository,
)
from industrial_phm.application.finding_review import (
    HUMAN_REVIEW_FINDING_SEMANTICS_ID,
    HUMAN_REVIEW_FINDING_STATE,
)
from industrial_phm.application.maintenance_review import (
    FindingReviewEvent,
    ReviewDecision,
    check_review_decision,
    finding_review_status,
)
from industrial_phm.application.operational import OperationalAnalysisResult
from industrial_phm.application.phm_analysis import PhmAnalysisError, SqlitePhmAnalysisStore
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
    """Request review of one exact persisted phase or FILE feature result."""
    if set(payload) != {"analysis_run_id", "evidence_id"}:
        raise ValueError("unexpected analysis review fields")
    run_id = _id(payload, "analysis_run_id")
    evidence_id = _id(payload, "evidence_id")
    workspace = OperationsWorkspace(root)
    paths = OperationsAppPaths(workspace)
    phase_results = SqlitePhaseUnbalanceRepository(paths.phase_analysis).find_results({run_id})
    matches: list[OperationalAnalysisResult] = []
    for item in phase_results:
        if item.evidence.evidence_id == evidence_id:
            matches.append(item)
    if not matches:
        file_repository = JsonFileFeatureAnalysisRepository(paths.file_feature_analysis)
        for file_result in file_repository.list_results():
            if (
                file_result.run.analysis_run_id == run_id
                and file_result.evidence.evidence_id == evidence_id
            ):
                matches.append(file_result)
    if len(matches) != 1:
        raise WebReviewNotFound("exact analysis evidence unavailable")
    finding, _ = OperationsAppActions(paths).request_review(matches[0])
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
    """Record only explicit note, acknowledgement and close of an existing finding.

    An optional ``event_id`` (UUIDv4) makes a retried request safe: the same
    identity with the same action is answered from the saved event, and with
    a different action it is a conflict rather than a second record.
    """
    if (
        not {"finding_id", "action", "note"}
        <= set(payload)
        <= {
            "finding_id",
            "action",
            "note",
            "event_id",
            "decision",
        }
    ):
        raise ValueError("unexpected review action fields")
    finding_id = _id(payload, "finding_id")
    action = payload["action"]
    note = payload["note"]
    request_id = _request_id(payload.get("event_id"))
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
    decision = review_decision(payload.get("decision"), FindingReviewAction(action))
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
    if request_id is not None:
        saved = next(
            (
                item
                for item in reviews.list_events()
                if item.event_id == f"finding-review-event-{request_id}"
            ),
            None,
        )
        if saved is not None:
            if (saved.finding_id, saved.action.value, saved.note, saved.decision) != (
                finding_id,
                action,
                note,
                decision,
            ):
                raise WebReviewConflict("review event identity conflicts with saved action")
            return _action_outcome(finding_id, saved, reviews)
    status = reviews.status_for(finding_id)
    if (
        status == FindingReviewStatus.CLOSED
        or (action == "acknowledge" and status != FindingReviewStatus.OPEN)
        or (action == "close" and status != FindingReviewStatus.ACKNOWLEDGED)
    ):
        raise WebReviewConflict("review transition forbidden")
    event, _ = OperationsAppActions(paths).record_review_action(
        finding,
        action=FindingReviewAction(action),
        note=note,
        request_id=request_id,
        decision=decision,
    )
    return _action_outcome(finding_id, event, reviews)


def review_decision(raw: object, action: FindingReviewAction) -> ReviewDecision | None:
    """The person's judgement on a confirm or close, checked the same way for every subject."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("invalid review decision")
    decision = ReviewDecision(raw)
    check_review_decision(action, decision)
    return decision


def _request_id(raw: object) -> UUID | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or len(raw) != 36:
        raise ValueError("invalid review event identity")
    value = UUID(raw)
    if value.version != 4 or str(value) != raw:
        raise ValueError("invalid review event identity")
    return value


def _action_outcome(
    finding_id: str, event: FindingReviewEvent, reviews: JsonFindingReviewRepository
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "finding_id": finding_id,
        "event_id": event.event_id,
        "action": event.action.value,
        "recorded_at": event.recorded_at.isoformat(),
        "status": reviews.status_for(finding_id).value,
        "meaning": "human-review-disposition-not-maintenance-execution",
    }


REVIEWS_ROUTE = "/api/v1/reviews"
PHM_REVIEW_FINDING_SEMANTICS_ID = "phm-human-review-request-v1"
_REVIEW_LIMIT = 100
_EVENT_LIMIT = 50


def handle_reviews_read(
    workspace: OperationsWorkspace, raw_query: str
) -> tuple[HTTPStatus, dict[str, object]]:
    """Human review records of one asset's analysis and model results, with their history.

    Only explicitly requested reviews appear. A model result names where it is
    stored (binding and step position) so the screen can open that exact result.
    """
    try:
        if len(raw_query) > 800:
            raise ValueError("review query too long")
        query = parse_qs(raw_query, strict_parsing=True)
        if (set(query) not in ({"asset_id"}, {"asset_id", "finding_id"})
                or len(query["asset_id"]) != 1):
            raise ValueError("invalid review query")
        asset_id = query["asset_id"][0]
        exact = query.get("finding_id", [None])
        if len(exact) != 1:
            raise ValueError("invalid finding identity")
        finding_id = exact[0]
        if not 1 <= len(asset_id) <= 512 or any(ord(char) < 32 for char in asset_id):
            raise ValueError("invalid asset identity")
        if finding_id is not None and (
            not 1 <= len(finding_id) <= 512 or any(ord(char) < 32 for char in finding_id)
        ):
            raise ValueError("invalid finding identity")
    except ValueError:
        return HTTPStatus.BAD_REQUEST, {"error": "invalid_review_query"}
    semantics = {HUMAN_REVIEW_FINDING_SEMANTICS_ID, PHM_REVIEW_FINDING_SEMANTICS_ID}
    try:
        findings = sorted(
            (
                item
                for item in JsonOperationalFindingRepository(
                    workspace.finding_state_path
                ).list_findings()
                if item.asset_id == asset_id
                and (finding_id is None or item.finding_id == finding_id)
                and item.finding_semantics_id in semantics
                and item.state == HUMAN_REVIEW_FINDING_STATE
            ),
            key=lambda item: (item.observed_at, item.finding_id),
            reverse=True,
        )
        # Exact ID lookup is independent of the recent-list limit and never
        # returns another asset's record, even if its finding ID is known.
        if finding_id is not None and not findings:
            return HTTPStatus.NOT_FOUND, {"error": "review_not_found"}
        shown = findings[:_REVIEW_LIMIT]
        events: dict[str, list[FindingReviewEvent]] = {item.finding_id: [] for item in shown}
        history = JsonFindingReviewRepository(workspace.maintenance_review_state_path)
        for event in history.list_events():
            if event.finding_id in events:
                events[event.finding_id].append(event)
        model_runs = [
            item.analysis_run_id
            for item in shown
            if item.finding_semantics_id == PHM_REVIEW_FINDING_SEMANTICS_ID
        ]
        positions = (
            SqlitePhmAnalysisStore(workspace.phm_analysis_path).run_positions(model_runs)
            if model_runs
            else {}
        )
    except ValueError, OSError, PhmAnalysisError, sqlite3.Error:
        return HTTPStatus.SERVICE_UNAVAILABLE, {"error": "review_state_unavailable"}
    items: list[dict[str, object]] = []
    for item in shown:
        model = item.finding_semantics_id == PHM_REVIEW_FINDING_SEMANTICS_ID
        location = positions.get(item.analysis_run_id) if model else None
        own = events[item.finding_id]
        items.append(
            {
                "finding_id": item.finding_id,
                "subject": "model" if model else "analysis",
                "analysis_run_id": item.analysis_run_id,
                "evidence_ids": list(item.evidence_refs),
                "capability_id": item.capability_id,
                "measurement_point_id": item.measurement_point_id,
                "observed_at": item.observed_at.isoformat(),
                "status": finding_review_status(own, item.finding_id).value,
                "model": (
                    None
                    if location is None
                    else {"binding_id": location[0], "position": location[1]}
                ),
                "events": [
                    {
                        "event_id": event.event_id,
                        "action": event.action.value,
                        "note": event.note,
                        "decision": None if event.decision is None else event.decision.value,
                        "recorded_at": event.recorded_at.isoformat(),
                    }
                    for event in own[-_EVENT_LIMIT:]
                ],
                "events_total": len(own),
            }
        )
    return HTTPStatus.OK, {
        "schema_version": 1,
        "asset_id": asset_id,
        "meaning": "human-review-records-not-maintenance-or-diagnosis",
        "reviews": {
            "items": items,
            "total": len(findings),
            "truncated": len(findings) > len(shown),
        },
    }
