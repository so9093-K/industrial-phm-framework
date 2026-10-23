"""Read-only, server-owned discovery of assets with stored human-review subjects.

The listing is paged by stable asset identity rather than inferred from the
monitor's bounded asset list. Detailed records remain owned by the existing
asset-scoped review/capture APIs and retain their exact identities.
"""

from __future__ import annotations

import sqlite3
import hashlib
import json
from http import HTTPStatus
from urllib.parse import parse_qs

from industrial_phm.application import JsonOperationalFindingRepository
from industrial_phm.application.finding_review import (
    HUMAN_REVIEW_FINDING_SEMANTICS_ID,
    HUMAN_REVIEW_FINDING_STATE,
)
from industrial_phm.runtime.operations_web_outlook_capture import OutlookCaptureStore
from industrial_phm.runtime.operations_web_review import PHM_REVIEW_FINDING_SEMANTICS_ID
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

REVIEW_ASSET_INDEX_ROUTE = "/api/v1/review-inbox/assets"
_PAGE = 20


def handle_review_asset_index(
    workspace: OperationsWorkspace, raw_query: str
) -> tuple[HTTPStatus, dict[str, object]]:
    """Return all owner identities, paged; never infer from monitor asset limits."""
    try:
        if len(raw_query) > 800:
            raise ValueError("review index query too long")
        query = parse_qs(raw_query, keep_blank_values=True, strict_parsing=True)
        if set(query) - {"after_asset"} or any(len(v) != 1 for v in query.values()):
            raise ValueError("invalid review index query")
        after = query.get("after_asset", [None])[0]
        if after is not None and (
            not after or len(after) > 512 or any(ord(char) < 32 for char in after)
        ):
            raise ValueError("invalid review asset cursor")
    except ValueError:
        return HTTPStatus.BAD_REQUEST, {"error": "invalid_review_asset_index_query"}
    try:
        findings = JsonOperationalFindingRepository(workspace.finding_state_path).list_findings()
        assets = {
            item.asset_id
            for item in findings
            if item.finding_semantics_id
            in {HUMAN_REVIEW_FINDING_SEMANTICS_ID, PHM_REVIEW_FINDING_SEMANTICS_ID}
            and item.state == HUMAN_REVIEW_FINDING_STATE
        }
        assets.update(OutlookCaptureStore(workspace.outlook_capture_path).review_asset_ids())
    except ValueError, OSError, sqlite3.Error:
        return HTTPStatus.SERVICE_UNAVAILABLE, {"error": "review_asset_index_unavailable"}
    ordered = sorted(assets)
    # Identical page sets have identical revisions even across independent reads.
    revision = hashlib.sha256(
        json.dumps(ordered, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if after is not None and after not in assets:
        # Removed/stale cursor is not silently treated as the first page.
        return HTTPStatus.BAD_REQUEST, {"error": "review_asset_cursor_changed"}
    remaining = [asset for asset in ordered if after is None or asset > after]
    page = remaining[:_PAGE]
    more = len(remaining) > len(page)
    return HTTPStatus.OK, {
        "schema_version": 1,
        "meaning": "stored-human-review-asset-identities-not-health",
        "asset_ids": page,
        "total_assets": len(ordered),
        "revision": revision,
        "next_after": page[-1] if more else None,
    }
