"""SQLite WAL desired collection-state repository."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from industrial_phm.application.collection_control import (
    CollectionControlRecord,
    CollectionDesiredState,
)

_SCHEMA_VERSION = "industrial-phm-collection-control-v1"


class CollectionControlFormatError(ValueError):
    """Raised when persisted collection-control state is unsupported."""


class SqliteCollectionControlRepository:
    """Cross-process latest desired state for Operations and the runtime service."""

    def __init__(self, path: Path, *, busy_timeout_ms: int = 5_000) -> None:
        if not isinstance(path, Path):
            raise ValueError("path must be pathlib.Path")
        if isinstance(busy_timeout_ms, bool) or not isinstance(busy_timeout_ms, int):
            raise ValueError("busy_timeout_ms must be an integer")
        if busy_timeout_ms < 1:
            raise ValueError("busy_timeout_ms must be at least 1")
        self._path = path
        self._busy_timeout_ms = busy_timeout_ms

    @property
    def path(self) -> Path:
        return self._path

    def initialize(self) -> None:
        connection = self._connect()
        try:
            self._ensure_schema(connection)
        finally:
            connection.close()

    def get(self, source_id: str) -> CollectionControlRecord | None:
        _validate_identifier(source_id, "source_id")
        connection = self._connect()
        try:
            self._ensure_schema(connection)
            row = connection.execute(
                """
                SELECT desired_state, generation, requested_at
                FROM collection_control
                WHERE source_id = ?
                """,
                (source_id,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return CollectionControlRecord(
            source_id=source_id,
            desired_state=CollectionDesiredState(_require_str(row[0], "desired_state")),
            generation=_require_int(row[1], "generation"),
            requested_at=_parse_datetime(_require_str(row[2], "requested_at")),
        )

    def list_records(self) -> tuple[CollectionControlRecord, ...]:
        connection = self._connect()
        try:
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                SELECT source_id, desired_state, generation, requested_at
                FROM collection_control
                ORDER BY source_id
                """
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            CollectionControlRecord(
                source_id=_require_str(row[0], "source_id"),
                desired_state=CollectionDesiredState(_require_str(row[1], "desired_state")),
                generation=_require_int(row[2], "generation"),
                requested_at=_parse_datetime(_require_str(row[3], "requested_at")),
            )
            for row in rows
        )

    def request_state(
        self,
        source_id: str,
        desired_state: CollectionDesiredState,
        *,
        requested_at: datetime,
    ) -> CollectionControlRecord:
        _validate_identifier(source_id, "source_id")
        if not isinstance(desired_state, CollectionDesiredState):
            raise ValueError("desired_state must be CollectionDesiredState")
        _validate_aware_datetime(requested_at, "requested_at")

        connection = self._connect()
        try:
            self._ensure_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                """
                SELECT desired_state, generation, requested_at
                FROM collection_control
                WHERE source_id = ?
                """,
                (source_id,),
            ).fetchone()

            generation = 1
            if current is not None:
                current_state = CollectionDesiredState(
                    _require_str(current[0], "desired_state")
                )
                current_generation = _require_int(current[1], "generation")
                current_at = _parse_datetime(_require_str(current[2], "requested_at"))
                if requested_at < current_at:
                    raise ValueError("collection requested_at must not move backwards")
                if desired_state == current_state:
                    connection.execute("COMMIT")
                    return CollectionControlRecord(
                        source_id=source_id,
                        desired_state=current_state,
                        generation=current_generation,
                        requested_at=current_at,
                    )
                generation = current_generation + 1

            connection.execute(
                """
                INSERT INTO collection_control (
                    source_id, desired_state, generation, requested_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    desired_state = excluded.desired_state,
                    generation = excluded.generation,
                    requested_at = excluded.requested_at
                """,
                (
                    source_id,
                    desired_state.value,
                    generation,
                    requested_at.isoformat(),
                ),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

        return CollectionControlRecord(
            source_id=source_id,
            desired_state=desired_state,
            generation=generation,
            requested_at=requested_at,
        )

    def _connect(self) -> sqlite3.Connection:
        path = self._path.expanduser().resolve(strict=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            path,
            timeout=self._busy_timeout_ms / 1000,
        )
        connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS collection_control_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        schema = connection.execute(
            "SELECT value FROM collection_control_metadata WHERE key = 'schema'"
        ).fetchone()
        if schema is None:
            connection.execute(
                """
                INSERT INTO collection_control_metadata (key, value)
                VALUES ('schema', ?)
                """,
                (_SCHEMA_VERSION,),
            )
        elif schema[0] != _SCHEMA_VERSION:
            raise CollectionControlFormatError(
                f"unsupported collection-control schema: {schema[0]!r}"
            )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS collection_control (
                source_id TEXT PRIMARY KEY,
                desired_state TEXT NOT NULL,
                generation INTEGER NOT NULL CHECK (generation > 0),
                requested_at TEXT NOT NULL
            )
            """
        )
        connection.commit()


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise CollectionControlFormatError(f"{field_name} must be a string")
    return value


def _require_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CollectionControlFormatError(f"{field_name} must be an integer")
    return value


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise CollectionControlFormatError("requested_at must be valid ISO datetime") from error
    _validate_aware_datetime(parsed, "requested_at")
    return parsed
