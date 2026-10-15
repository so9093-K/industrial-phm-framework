"""Supervisor-run AI briefings of a condition outlook, and their read route.

A request names the same selection the outlook screen reads. The supervisor recomputes the
outlook itself (the browser's numbers are never trusted), asks the configured model in the
background, and stores the checked answer with the facts it rests on. The Web polls the stored
briefings of its selection.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from http import HTTPStatus
from pathlib import Path
from threading import Lock, Thread
from typing import Any
from urllib.parse import parse_qs, urlencode
from uuid import uuid4

from industrial_phm.application.forecast import ForecastUnavailable
from industrial_phm.application.phm_analysis import PhmAnalysisError
from industrial_phm.genai.analysis_explanation import AnalysisExplanationError
from industrial_phm.genai.outlook_answer import DEFAULT_QUESTION, generate_outlook_briefing
from industrial_phm.runtime.operations_live import OperationsReadError
from industrial_phm.runtime.operations_web_outlook import condition_outlook, outlook_arguments
from industrial_phm.runtime.operations_web_phm_explanation import configured_provider
from industrial_phm.runtime.operations_workspace import OperationsWorkspace

BRIEFINGS_ROUTE = "/api/v1/outlook/briefings"
REQUEST_ROUTE = "/api/v1/outlook/briefings/request"
SELECTION_FIELDS = (
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
    "data_version",
)
_MAX_PENDING = 4


def selection_key(params: dict[str, str]) -> str:
    """One canonical text per selection, so the same screen finds its own briefings."""
    return urlencode(sorted((k, v) for k, v in params.items() if k in SELECTION_FIELDS and v))


class OutlookBriefingStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS briefing(id TEXT PRIMARY KEY, asset_id TEXT, "
            "selection TEXT, question TEXT, model TEXT, owner TEXT, status TEXT, answer TEXT, "
            "error TEXT, requested_at TEXT, finished_at TEXT)"
        )
        return connection

    def request(
        self, asset_id: str, selection: str, question: str, *, model: str, owner: str
    ) -> str:
        identifier = "briefing-" + uuid4().hex
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            pending = connection.execute(
                "SELECT COUNT(*) FROM briefing WHERE status = 'pending'"
            ).fetchone()[0]
            if pending >= _MAX_PENDING:
                raise ValueError("briefing capacity reached")
            connection.execute(
                "INSERT INTO briefing(id, asset_id, selection, question, model, owner, status, "
                "answer, error, requested_at, finished_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    asset_id,
                    selection,
                    question,
                    model,
                    owner,
                    "pending",
                    None,
                    None,
                    datetime.now(UTC).isoformat(),
                    None,
                ),
            )
        return identifier

    def finish(
        self,
        identifier: str,
        *,
        owner: str,
        answer: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE briefing SET status=?, answer=?, error=?, finished_at=? "
                "WHERE id=? AND owner=? AND status='pending'",
                (
                    "failed" if error else "complete",
                    None if answer is None else json.dumps(answer, ensure_ascii=False),
                    error,
                    datetime.now(UTC).isoformat(),
                    identifier,
                    owner,
                ),
            )

    def recover(self, owner: str) -> None:
        if not self.path.exists():
            return
        with self._connect() as connection:
            connection.execute(
                "UPDATE briefing SET status='failed', error='generation interrupted', "
                "finished_at=? WHERE status='pending' AND owner!=?",
                (datetime.now(UTC).isoformat(), owner),
            )

    def list_for(self, asset_id: str, selection: str) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT id, question, model, status, answer, error, requested_at, finished_at "
                "FROM briefing WHERE asset_id=? AND selection=? ORDER BY requested_at DESC LIMIT 5",
                (asset_id, selection),
            ).fetchall()
        return [
            {**dict(row), "answer": json.loads(row["answer"]) if row["answer"] else None}
            for row in rows
        ]


class BriefingManager:
    def __init__(self, root: Path) -> None:
        self.workspace = OperationsWorkspace(root)
        self.owner = uuid4().hex
        self.store = OutlookBriefingStore(self.workspace.outlook_briefing_path)
        self.store.recover(self.owner)

    def request(self, params: dict[str, str], question: str) -> dict[str, object]:
        arguments = outlook_arguments(params)
        provider = configured_provider()
        selection = selection_key(params)
        identifier = self.store.request(
            params["asset_id"], selection, question, model=provider.model, owner=self.owner
        )

        def generate() -> None:
            try:
                outlook = condition_outlook(self.workspace, **arguments)
                if outlook["data_version"] != params["data_version"]:
                    raise ValueError("outlook evidence changed before briefing was generated")
                answer = generate_outlook_briefing(outlook, question, provider)
            except (
                ForecastUnavailable,
                LookupError,
                ValueError,
                OperationsReadError,
                PhmAnalysisError,
                OSError,
                sqlite3.Error,
                AnalysisExplanationError,
            ):
                self.store.finish(identifier, owner=self.owner, error="briefing unavailable")
            else:
                self.store.finish(identifier, owner=self.owner, answer=answer)

        Thread(target=generate, name="outlook-briefing", daemon=True).start()
        return {"briefing_id": identifier, "status": "pending", "selection": selection}


_MANAGERS: dict[Path, BriefingManager] = {}
_LOCK = Lock()


def request_outlook_briefing(root: Path, payload: dict[str, object]) -> dict[str, object]:
    if set(payload) - {*SELECTION_FIELDS, "question"} or not {"asset_id", "kind", "series"} <= set(
        payload
    ):
        raise ValueError("unexpected briefing fields")
    if any(not isinstance(payload[name], str) for name in payload):
        raise ValueError("briefing fields are text")
    question = str(payload.get("question") or DEFAULT_QUESTION).strip()
    if not 1 <= len(question) <= 600:
        raise ValueError("invalid briefing question")
    params = {name: str(value) for name, value in payload.items() if name != "question"}
    version = params.get("data_version", "")
    if len(version) != 64 or any(ch not in "0123456789abcdef" for ch in version):
        raise ValueError("outlook data version is required")
    with _LOCK:
        manager = _MANAGERS.get(root)
        if manager is None:
            manager = _MANAGERS[root] = BriefingManager(root)
    return manager.request(params, question)


def handle_briefings_read(
    workspace: OperationsWorkspace, raw_query: str
) -> tuple[HTTPStatus, dict[str, Any]]:
    try:
        query = parse_qs(raw_query, strict_parsing=False)
        if any(len(values) != 1 for values in query.values()) or set(query) - set(SELECTION_FIELDS):
            raise ValueError("invalid briefing query")
        params = {name: values[0] for name, values in query.items()}
        if not 0 < len(params.get("asset_id", "")) <= 512:
            raise ValueError("asset_id is required")
        version = params.get("data_version", "")
        if len(version) != 64 or any(ch not in "0123456789abcdef" for ch in version):
            raise ValueError("outlook data version is required")
        briefings = OutlookBriefingStore(workspace.outlook_briefing_path).list_for(
            params["asset_id"], selection_key(params)
        )
        return HTTPStatus.OK, {"schema_version": 1, "briefings": briefings}
    except ValueError:
        return HTTPStatus.BAD_REQUEST, {"error": "invalid_briefing_query"}
    except OSError, sqlite3.Error:
        return HTTPStatus.SERVICE_UNAVAILABLE, {"error": "briefing_store_unavailable"}
