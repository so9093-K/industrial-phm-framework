"""Immutable, explicitly captured condition-outlook evidence for later human review.

The server recomputes and validates the selection. A browser never submits numerical
facts. This is capability evidence, not an AI answer or a simulated raw snapshot.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs

from industrial_phm.application.forecast import ForecastUnavailable
from industrial_phm.runtime.operations_web_outlook import condition_outlook, outlook_arguments
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

CAPTURES_ROUTE = "/api/v1/outlook/captures"
CAPTURE_ACTION_ROUTE = "/api/v1/outlook/captures/confirm"
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

    def list_for(self, asset_id: str, *, capture_id: str | None = None) -> list[dict[str, Any]]:
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
                records = connection.execute(
                    "SELECT id, captured_at, digest, snapshot FROM capture "
                    "WHERE asset_id=? ORDER BY captured_at DESC LIMIT 20",
                    (asset_id,),
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
            if identifier != expected_id or snapshot["outlook"]["asset_id"] != asset_id:
                raise OutlookCaptureCorrupted("stored outlook identity mismatch")
            result.append(
                {"capture_id": identifier, "captured_at": captured_at, "snapshot": snapshot}
            )
        return result


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


def handle_outlook_captures_read(
    workspace: OperationsWorkspace, raw_query: str
) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        if len(raw_query) > 800:
            raise ValueError("capture query too long")
        query = parse_qs(raw_query, strict_parsing=True)
        if set(query) - {"asset_id", "capture_id"} or any(
            len(values) != 1 for values in query.values()
        ):
            raise ValueError("invalid capture query")
        asset_id = query.get("asset_id", [""])[0]
        capture_id = query.get("capture_id", [""])[0] or None
        if not 1 <= len(asset_id) <= 512 or (
            capture_id is not None
            and (
                not capture_id.startswith("outlook-capture-")
                or len(capture_id) != len("outlook-capture-") + 64
            )
        ):
            raise ValueError("invalid capture identity")
        records = OutlookCaptureStore(workspace.outlook_capture_path).list_for(
            asset_id, capture_id=capture_id
        )
        if capture_id and not records:
            return HTTPStatus.NOT_FOUND, {"error": "outlook_capture_not_found"}
        return HTTPStatus.OK, {"schema_version": 1, "captures": records}
    except ValueError, TypeError:
        return HTTPStatus.BAD_REQUEST, {"error": "invalid_outlook_capture_query"}
    except OSError, sqlite3.Error, OutlookCaptureCorrupted:
        return HTTPStatus.SERVICE_UNAVAILABLE, {"error": "outlook_capture_store_unavailable"}
