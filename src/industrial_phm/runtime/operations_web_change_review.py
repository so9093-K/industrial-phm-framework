"""Human judgments attached to exact source-owned changes, preserved for revisits."""

from __future__ import annotations

import json
import re
import sqlite3
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs
from uuid import UUID

from industrial_phm.application.maintenance_review import FindingReviewAction
from industrial_phm.runtime.operations_web_explore import record_findings
from industrial_phm.runtime.operations_web_outlook_capture import (
    OutlookCaptureCorrupted,
    OutlookCaptureStore,
    _digest,
)
from industrial_phm.runtime.operations_web_review import WebReviewConflict, review_decision
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

CHANGE_REVIEWS_ROUTE = "/api/v1/explore/change-reviews"


class ChangeReviewStore(OutlookCaptureStore):
    """Reuse the append-only review policy and transactional capture storage."""

    payload_key = "change"
    id_prefix = "change-review-"


def _identity(asset: str, key: str) -> dict[str, str]:
    if not asset or len(asset) > 512 or not re.fullmatch(r"[0-9a-f]{64}", key):
        raise ValueError("invalid change identity")
    return {"asset_id": asset, "finding_id": key}


def capture_change(root: Path, payload: dict[str, object]) -> dict[str, Any]:
    if set(payload) != {"asset_id", "finding_id"} or not all(
        isinstance(v, str) for v in payload.values()
    ):
        raise ValueError("invalid change selection")
    asset, key = str(payload["asset_id"]), str(payload["finding_id"])
    identity = _identity(asset, key)
    workspace = OperationsWorkspace(root)
    store = ChangeReviewStore(workspace.change_review_path)
    identifier = store.id_prefix + _digest(
        json.dumps(identity, sort_keys=True, separators=(",", ":"))
    )
    # Idempotent retries keep an already captured observation even after new measurements arrive.
    existing = store.list_for(asset, capture_id=identifier)
    if existing:
        return {"schema_version": 1, "asset_id": asset, "capture_id": identifier}
    found = record_findings(workspace, asset)
    selected = next((item for item in found["intervals"] if item["review_key"] == key), None)
    if selected is None:
        raise WebReviewConflict(
            "the change or its reference period changed; reload before reviewing"
        )
    saved = store.save({"identity": identity, "change": {"asset_id": asset, "finding": selected}})
    return {"schema_version": 1, "asset_id": asset, **saved}


def review_change(root: Path, payload: dict[str, object]) -> dict[str, Any]:
    required = {"asset_id", "capture_id", "action", "note", "event_id"}
    if not required <= set(payload) <= required | {"decision"}:
        raise ValueError("unexpected change review fields")
    if not all(isinstance(v, str) for key, v in payload.items() if key != "decision"):
        raise ValueError("review fields must be strings")
    asset, identifier = str(payload["asset_id"]), str(payload["capture_id"])
    if not asset or len(asset) > 512 or not re.fullmatch(r"change-review-[0-9a-f]{64}", identifier):
        raise ValueError("invalid change review identity")
    action, note, event_id = (
        FindingReviewAction(str(payload["action"])),
        str(payload["note"]),
        str(payload["event_id"]),
    )
    if (
        UUID(event_id).version != 4
        or note != note.strip()
        or len(note) > 1000
        or len(note.encode()) > 2048
    ):
        raise ValueError("invalid review note or event")
    if any(ord(char) < 32 and char not in "\n\t" for char in note) or (
        action == FindingReviewAction.NOTE and not note
    ):
        raise ValueError("invalid review note")
    decision = review_decision(payload.get("decision"), action)
    result = ChangeReviewStore(OperationsWorkspace(root).change_review_path).write_review(
        asset, identifier, action, note, event_id, decision
    )
    return {
        "schema_version": 1,
        "asset_id": asset,
        "capture_id": identifier,
        **result,
        "meaning": "human-review-not-maintenance-or-diagnosis",
    }


def handle_change_reviews_read(
    workspace: OperationsWorkspace, query: str
) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        args = parse_qs(query, keep_blank_values=True, strict_parsing=True)
        if not {"asset_id"} <= set(args) <= {
            "asset_id",
            "finding_id",
            "capture_id",
            "before_id",
        } or any(len(v) != 1 for v in args.values()):
            raise ValueError("invalid change review query")
        asset = args["asset_id"][0]
        if not asset or len(asset) > 512:
            raise ValueError("invalid asset")
        store = ChangeReviewStore(workspace.change_review_path)
        identifier = args.get("capture_id", [None])[0]
        if "finding_id" in args:
            if identifier or "before_id" in args:
                raise ValueError("choose a single review selection")
            identity = _identity(asset, args["finding_id"][0])
            identifier = store.id_prefix + _digest(
                json.dumps(identity, sort_keys=True, separators=(",", ":"))
            )
        before = args.get("before_id", [None])[0]
        if identifier and before:
            raise ValueError("choose either a review or a page cursor")
        for value in (identifier, before):
            if value is not None and not re.fullmatch(r"change-review-[0-9a-f]{64}", value):
                raise ValueError("invalid review cursor")
        page = store.list_for(asset, capture_id=identifier, before_id=before, limit=21)
        return HTTPStatus.OK, {
            "schema_version": 1,
            "asset_id": asset,
            "captures": page[:20],
            "next_before": page[19]["capture_id"] if len(page) > 20 else None,
        }
    except ValueError, LookupError:
        return HTTPStatus.BAD_REQUEST, {"error": "invalid_change_review_query"}
    except OSError, sqlite3.Error, OutlookCaptureCorrupted:
        return HTTPStatus.SERVICE_UNAVAILABLE, {"error": "change_review_store_unavailable"}
