"""Immutable, explicitly captured condition-outlook evidence for later human review.

The server recomputes and validates the selection. A browser never submits numerical
facts. This is capability evidence, not an AI answer or a simulated raw snapshot.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs
from uuid import UUID

from industrial_phm.application.forecast import ForecastUnavailable
from industrial_phm.application.maintenance_review import (
    FindingReviewAction,
    FindingReviewStatus,
    next_human_review_status,
)
from industrial_phm.application.phm_analysis import PhmAnalysisError
from industrial_phm.runtime.operations_live import OperationsReadError
from industrial_phm.runtime.operations_web_forecast import (
    acquisition_points,
    history_points,
    measurement_version,
)
from industrial_phm.runtime.operations_web_outlook import condition_outlook, outlook_arguments
from industrial_phm.runtime.operations_web_review import WebReviewConflict, WebReviewNotFound
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

CAPTURES_ROUTE = "/api/v1/outlook/captures"
CAPTURE_ACTION_ROUTE = "/api/v1/outlook/captures/confirm"
REVIEW_ACTION_ROUTE = "/api/v1/outlook/captures/review/action"
_SELECTION = frozenset(
    {
        "asset_id",
        "kind",
        "series",
        "management_limit",
        "end_limit",
        "direction",
        "changepoint_prior_scale",
        "changepoint_range",
        "training_points",
        "seasonality",
        "assumed_period_seconds",
    }
)
_VERSIONS = frozenset({"measurement_version", "data_version"})
_MAX_SNAPSHOT_BYTES = 64 * 1024


def _digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class OutlookCaptureCorrupted(RuntimeError):
    """Stored bytes fail their persisted content identity."""


class OutlookCaptureStore:
    """Durable capture content remains unchanged, even after later observations arrive."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS capture("
            "id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, "
            "captured_at TEXT NOT NULL, digest TEXT NOT NULL, "
            "snapshot TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_capture_asset ON capture(asset_id, captured_at DESC)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS review_event("
            "event_id TEXT PRIMARY KEY, capture_id TEXT NOT NULL, "
            "action TEXT NOT NULL, note TEXT NOT NULL, recorded_at TEXT NOT NULL, "
            "FOREIGN KEY(capture_id) REFERENCES capture(id))"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_outlook_review_capture ON review_event(capture_id)"
        )
        return connection

    def save(self, snapshot: dict[str, Any]) -> dict[str, str]:
        rendered = json.dumps(
            snapshot, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        if len(rendered.encode("utf-8")) > _MAX_SNAPSHOT_BYTES:
            raise ValueError("outlook capture exceeds bounded evidence size")
        digest = _digest(rendered)
        identity = json.dumps(snapshot["identity"], sort_keys=True, separators=(",", ":"))
        identifier = "outlook-capture-" + _digest(identity)
        asset_id = snapshot["outlook"]["asset_id"]
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO capture(id, asset_id, captured_at, digest, snapshot)"
                " VALUES (?, ?, ?, ?, ?)",
                (identifier, asset_id, datetime.now(UTC).isoformat(), digest, rendered),
            )
            stored = connection.execute(
                "SELECT digest, snapshot, captured_at FROM capture WHERE id=?", (identifier,)
            ).fetchone()
            if stored is None or _digest(stored[1]) != stored[0]:
                raise OutlookCaptureCorrupted("stored outlook evidence digest mismatch")
            previous = json.loads(stored[1])
            previous_id = "outlook-capture-" + _digest(
                json.dumps(previous["identity"], sort_keys=True, separators=(",", ":"))
            )
            if previous_id != identifier:
                raise OutlookCaptureCorrupted("stored outlook identity mismatch")
            # Numerical model retraining can differ at floating-point precision even
            # with identical observations and options. Preserve the first saved bytes.
        return {"capture_id": identifier, "captured_at": stored[2]}

    def list_for(
        self,
        asset_id: str,
        *,
        capture_id: str | None = None,
        before_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        # Listing is read-only even in standalone Web previews.
        with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=10) as connection:
            if capture_id:
                records = connection.execute(
                    "SELECT id, captured_at, digest, snapshot FROM capture "
                    "WHERE asset_id=? AND id=?",
                    (asset_id, capture_id),
                ).fetchall()
            else:
                cursor = None
                if before_id:
                    cursor = connection.execute(
                        "SELECT captured_at, id FROM capture WHERE asset_id=? AND id=?",
                        (asset_id, before_id),
                    ).fetchone()
                    if cursor is None:
                        raise LookupError("capture page cursor does not belong to asset")
                if cursor is None:
                    records = connection.execute(
                        "SELECT id, captured_at, digest, snapshot FROM capture "
                        "WHERE asset_id=? ORDER BY captured_at DESC, id DESC LIMIT ?",
                        (asset_id, limit),
                    ).fetchall()
                else:
                    records = connection.execute(
                        "SELECT id, captured_at, digest, snapshot FROM capture "
                        "WHERE asset_id=? AND (captured_at < ? "
                        "OR (captured_at = ? AND id < ?)) "
                        "ORDER BY captured_at DESC, id DESC LIMIT ?",
                        (asset_id, cursor[0], cursor[0], cursor[1], limit),
                    ).fetchall()
        result = []
        for identifier, captured_at, digest, rendered in records:
            if _digest(rendered) != digest:
                raise OutlookCaptureCorrupted("stored outlook evidence digest mismatch")
            try:
                snapshot = json.loads(rendered)
                expected_id = "outlook-capture-" + _digest(
                    json.dumps(snapshot["identity"], sort_keys=True, separators=(",", ":"))
                )
            except (ValueError, TypeError, KeyError) as error:
                raise OutlookCaptureCorrupted("invalid captured evidence shape") from error
            if identifier != expected_id:
                raise OutlookCaptureCorrupted("stored outlook identity mismatch")
            if not isinstance(snapshot.get("outlook"), dict):
                raise OutlookCaptureCorrupted("invalid captured evidence shape")
            if snapshot["outlook"].get("asset_id") != asset_id:
                raise OutlookCaptureCorrupted("stored outlook identity mismatch")
            result.append(
                {
                    "capture_id": identifier,
                    "captured_at": captured_at,
                    "snapshot": snapshot,
                    "review": self.read_review(identifier),
                }
            )
        return result

    @staticmethod
    def _review_on_connection(connection: sqlite3.Connection, capture_id: str) -> dict[str, Any]:
        rows = connection.execute(
            "SELECT event_id, action, note, recorded_at FROM review_event "
            "WHERE capture_id=? ORDER BY rowid",
            (capture_id,),
        ).fetchall()
        status = FindingReviewStatus.OPEN
        events = []
        try:
            for event_id, action, note, recorded_at in rows:
                status = next_human_review_status(status, FindingReviewAction(action))
                events.append(
                    {
                        "event_id": event_id,
                        "action": action,
                        "note": note,
                        "recorded_at": recorded_at,
                    }
                )
        except ValueError as error:
            raise OutlookCaptureCorrupted("persisted outlook review has invalid actions") from error
        return {"status": status.value, "events": events}

    def read_review(self, capture_id: str) -> dict[str, Any]:
        """Read persisted human actions without initializing writable state."""
        if not self.path.exists():
            raise LookupError("captured outlook does not exist")
        with sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True) as connection:
            return self._review_on_connection(connection, capture_id)

    def write_review(
        self, asset_id: str, capture_id: str, action: FindingReviewAction, note: str, event_id: str
    ) -> dict[str, Any]:
        with self._connect() as connection:
            # Serialize checking the current status with inserting the next action.
            # The same writer lock is required even for two different Web processes.
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id FROM capture WHERE id=? AND asset_id=?", (capture_id, asset_id)
            ).fetchone()
            if row is None:
                raise WebReviewNotFound("captured outlook evidence does not belong to asset")
            previous = connection.execute(
                "SELECT capture_id, action, note FROM review_event WHERE event_id=?", (event_id,)
            ).fetchone()
            if previous is not None:
                if previous != (capture_id, action.value, note):
                    raise WebReviewConflict("review event identity conflicts with saved action")
                outcome = self._review_on_connection(connection, capture_id)
                return {"event_id": event_id, **outcome}
            state = FindingReviewStatus(
                self._review_on_connection(connection, capture_id)["status"]
            )
            try:
                next_human_review_status(state, action)
            except ValueError as error:
                raise WebReviewConflict("review action is invalid for current status") from error
            connection.execute(
                "INSERT INTO review_event(event_id, capture_id, action, note, recorded_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (event_id, capture_id, action.value, note, datetime.now(UTC).isoformat()),
            )
            outcome = self._review_on_connection(connection, capture_id)
            return {"event_id": event_id, **outcome}


def review_captured_outlook(root: Path, payload: dict[str, object]) -> dict[str, Any]:
    """Apply one human review event to one exact immutable captured outlook."""
    if set(payload) != {"asset_id", "capture_id", "action", "note", "event_id"}:
        raise ValueError("unexpected outlook review fields")
    if not all(isinstance(v, str) for v in payload.values()):
        raise ValueError("review fields must be strings")
    asset = cast(str, payload["asset_id"])
    capture = cast(str, payload["capture_id"])
    action = FindingReviewAction(cast(str, payload["action"]))
    note = cast(str, payload["note"])
    event_id = cast(str, payload["event_id"])
    if not 1 <= len(asset) <= 512 or not capture.startswith("outlook-capture-"):
        raise ValueError("invalid outlook review identity")
    if len(capture) != len("outlook-capture-") + 64 or any(
        char not in "0123456789abcdef" for char in capture[len("outlook-capture-") :]
    ):
        raise ValueError("invalid captured evidence ID")
    if UUID(event_id).version != 4 or not 0 <= len(note) <= 1000:
        raise ValueError("invalid review event identity or note")
    if len(note.encode("utf-8")) > 2048 or note != note.strip():
        raise ValueError("invalid review note")
    if any(ord(char) < 32 and char not in "\n\t" for char in note):
        raise ValueError("invalid review note characters")
    if action == FindingReviewAction.NOTE and not note:
        raise ValueError("review note is required")
    result = OutlookCaptureStore(OperationsWorkspace(root).outlook_capture_path).write_review(
        asset, capture, action, note, event_id
    )
    return {
        "schema_version": 1,
        "capture_id": capture,
        "asset_id": asset,
        "event_id": result["event_id"],
        "status": result["status"],
        "meaning": "human-review-not-maintenance-or-diagnosis",
    }


def capture_outlook(root: Path, payload: dict[str, object]) -> dict[str, object]:
    """Capture only exact current server-calculated facts after an explicit write request."""
    if set(payload) - (_SELECTION | _VERSIONS) or not (
        {"asset_id", "kind", "series"} | _VERSIONS
    ) <= set(payload):
        raise ValueError("unexpected capture fields")
    if any(not isinstance(value, str) or len(value) > 512 for value in payload.values()):
        raise ValueError("invalid capture parameter")
    params = {key: cast(str, value) for key, value in payload.items() if key in _SELECTION}
    for name in _VERSIONS:
        version = payload[name]
        if not isinstance(version, str) or len(version) != 64:
            raise ValueError("invalid capture version")
        if any(char not in "0123456789abcdef" for char in version):
            raise ValueError("invalid capture version")
    try:
        outlook = condition_outlook(OperationsWorkspace(root), **outlook_arguments(params))
    except ForecastUnavailable as error:
        raise ValueError("selected outlook cannot be computed") from error
    if any(outlook[name] != payload[name] for name in _VERSIONS):
        raise ValueError("outlook changed before capture: refresh required")
    # Canonical model inputs identify a capture. Hashing the whole forecast would
    # create duplicate records when a numerical solver returns slightly different
    # floats for identical measurements, versions and forecasting settings.
    identity = {
        "asset_id": outlook["asset_id"],
        "kind": outlook["kind"],
        "series": outlook["series"],
        "source_id": outlook["source_id"],
        "measurement_point_id": outlook.get("measurement_point_id"),
        "axis": outlook["axis"],
        "time_basis": outlook.get("time_basis"),
        "assumed_period_seconds": (
            outlook.get("period_seconds") if outlook.get("time_basis") == "assumed" else None
        ),
        "record": outlook["record"],
        "conditions": outlook["conditions"],
        "settings": outlook["settings"],
        "measurement_version": outlook["measurement_version"],
        "data_version": outlook["data_version"],
    }
    snapshot = {
        "schema_version": 1,
        "identity": identity,
        "selection": dict(sorted(params.items())),
        "outlook": outlook,
        "meaning": "captured-condition-outlook-not-actual-failure-or-maintenance",
    }
    result = OutlookCaptureStore(OperationsWorkspace(root).outlook_capture_path).save(snapshot)
    return {"schema_version": 1, **result, "asset_id": outlook["asset_id"]}


def current_measurement_recheck(workspace: OperationsWorkspace, snapshot: dict[str, Any]) -> str:
    """Check only the current bounded measurement projection, not anomaly provenance.

    The archived computation remains trustworthy as an archived statement when
    the original measurements can no longer be independently rechecked.
    """
    identity = snapshot["identity"]
    selection = snapshot["selection"]
    asset_id, kind, series = identity["asset_id"], identity["kind"], identity["series"]
    try:
        if kind == "history":
            times, values, meta = history_points(workspace, asset_id, series)
        elif kind == "acquisition":
            assumed = selection.get("assumed_period_seconds")
            times, values, meta = acquisition_points(
                workspace,
                asset_id,
                series,
                assumed_period_seconds=float(assumed) if assumed is not None else None,
                count_mode=True,
            )
        else:
            return "unavailable"
        if (
            meta["source_id"] != identity["source_id"]
            or meta.get("measurement_point_id") != identity.get("measurement_point_id")
            or meta.get("time_basis") != identity.get("time_basis")
        ):
            return "different_source"
        finite = [
            (time, value) for time, value in zip(times, values, strict=True) if math.isfinite(value)
        ]
        if len(finite) < 20:
            return "unavailable"
        actual = measurement_version(
            asset_id,
            kind,
            series,
            [time for time, _ in finite],
            [value for _, value in finite],
            meta,
        )
        if actual == identity["measurement_version"]:
            return "same_measurement_projection"
        return "changed"
    except LookupError, ValueError, OSError, OperationsReadError, PhmAnalysisError, sqlite3.Error:
        return "unavailable"


def handle_outlook_captures_read(
    workspace: OperationsWorkspace, raw_query: str
) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        if len(raw_query) > 800:
            raise ValueError("capture query too long")
        query = parse_qs(raw_query, strict_parsing=True)
        if set(query) - {"asset_id", "capture_id", "before_id"} or any(
            len(values) != 1 for values in query.values()
        ):
            raise ValueError("invalid capture query")
        asset_id = query.get("asset_id", [""])[0]
        capture_id = query.get("capture_id", [""])[0] or None
        before_id = query.get("before_id", [""])[0] or None
        if capture_id and before_id:
            raise ValueError("capture_id and before_id cannot be combined")
        for identifier in (capture_id, before_id):
            if identifier and (
                not identifier.startswith("outlook-capture-")
                or len(identifier) != len("outlook-capture-") + 64
                or any(char not in "0123456789abcdef" for char in identifier[16:])
            ):
                raise ValueError("invalid capture identity")
        if not 1 <= len(asset_id) <= 512:
            raise ValueError("invalid asset identity")
        page = OutlookCaptureStore(workspace.outlook_capture_path).list_for(
            asset_id, capture_id=capture_id, before_id=before_id, limit=21
        )
        if capture_id and not page:
            return HTTPStatus.NOT_FOUND, {"error": "outlook_capture_not_found"}
        records = page[:20]
        for item in records:
            item["source_recheck"] = current_measurement_recheck(workspace, item["snapshot"])
        return HTTPStatus.OK, {
            "schema_version": 1,
            "captures": records,
            "next_before": records[-1]["capture_id"] if len(page) > 20 else None,
        }
    except ValueError, TypeError:
        return HTTPStatus.BAD_REQUEST, {"error": "invalid_outlook_capture_query"}
    except LookupError:
        return HTTPStatus.NOT_FOUND, {"error": "outlook_capture_not_found"}
    except OSError, sqlite3.Error, OutlookCaptureCorrupted:
        return HTTPStatus.SERVICE_UNAVAILABLE, {"error": "outlook_capture_store_unavailable"}
