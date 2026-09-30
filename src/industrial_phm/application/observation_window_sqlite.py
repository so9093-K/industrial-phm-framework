"""SQLite persistence for finalized observation windows and bounded incremental reads."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from industrial_phm.application.observation_window import (
    DurableObservationWindow,
    ObservationWindowFormatError,
    _parse_window,
    _serialize_window,
)

_SCHEMA_VERSION = 1


class SqliteObservationWindowRepository:
    """WAL-backed finalized-window repository.

    Each finalized window is one row, so recording a new window never rewrites prior
    payloads. Delivery identities are indexed separately to preserve the existing
    one-source/one-window ownership contract.
    """

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise ValueError("path must be pathlib.Path")
        self._path = path
        if path.exists() and path.is_file():
            header = path.read_bytes()[:16]
            if header and header != b"SQLite format 3\x00":
                raise ValueError(
                    "window state is not SQLite; choose a new --window-state path "
                    "instead of reusing legacy JSON state"
                )

    @property
    def path(self) -> Path:
        return self._path

    def get(self, window_id: str) -> DurableObservationWindow:
        if not isinstance(window_id, str) or not window_id.strip():
            raise ValueError("window_id must not be empty")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT payload_json FROM finalized_window WHERE window_id = ?",
                [window_id],
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise KeyError(f"observation window does not exist: {window_id}")
        return self._parse_payload(row[0], context=f"window {window_id}")

    def list_windows(self) -> tuple[DurableObservationWindow, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM finalized_window
                ORDER BY source_id, window_start, window_id
                """
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            self._parse_payload(row[0], context=f"window[{index}]")
            for index, row in enumerate(rows)
        )

    def list_windows_after(
        self,
        *,
        after_window_end: datetime | None = None,
        after_window_id: str | None = None,
        limit: int = 1000,
    ) -> tuple[DurableObservationWindow, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        if limit > 10_000:
            raise ValueError("limit must not exceed 10000")
        if (after_window_end is None) != (after_window_id is None):
            raise ValueError("window cursor requires both end time and window id")
        params: list[object] = []
        where = ""
        if after_window_end is not None:
            if after_window_end.utcoffset() is None:
                raise ValueError("after_window_end must be timezone-aware")
            where = (
                "WHERE window_end > ? OR (window_end = ? AND window_id > ?)"
            )
            stamp = after_window_end.isoformat()
            params.extend((stamp, stamp, after_window_id))
        params.append(limit)
        connection = self._connect()
        try:
            rows = connection.execute(
                f"""
                SELECT payload_json
                FROM finalized_window
                {where}
                ORDER BY window_end, window_id
                LIMIT ?
                """,
                params,
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            self._parse_payload(row[0], context=f"window page[{index}]")
            for index, row in enumerate(rows)
        )

    def recent_windows_for_source(
        self,
        source_id: str,
        *,
        limit: int = 2,
    ) -> tuple[DurableObservationWindow, ...]:
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_id must not be empty")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM finalized_window
                WHERE source_id = ?
                ORDER BY window_end DESC, window_id DESC
                LIMIT ?
                """,
                [source_id, limit],
            ).fetchall()
        finally:
            connection.close()
        values = tuple(
            self._parse_payload(row[0], context=f"recent window[{index}]")
            for index, row in enumerate(rows)
        )
        return tuple(reversed(values))

    def record_window(self, window: DurableObservationWindow) -> None:
        self.record_windows((window,))

    def record_windows(self, windows: Sequence[DurableObservationWindow]) -> None:
        values = tuple(windows)
        if any(not isinstance(item, DurableObservationWindow) for item in values):
            raise ValueError("windows must contain DurableObservationWindow values")
        if not values:
            return

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            for window in values:
                self._record_window(connection, window)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _record_window(
        self,
        connection: sqlite3.Connection,
        window: DurableObservationWindow,
    ) -> None:
        payload = json.dumps(
            _serialize_window(window),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        row = connection.execute(
            "SELECT payload_json FROM finalized_window WHERE window_id = ?",
            [window.window_id],
        ).fetchone()
        if row is not None:
            current = self._parse_payload(row[0], context=f"window {window.window_id}")
            if current != window:
                raise ValueError(
                    "observation window with the same window_id must match persisted evidence"
                )
            return

        for event in window.events:
            identity = event.local_delivery_identity
            owner = connection.execute(
                """
                SELECT window_id
                FROM delivery_identity
                WHERE source_id = ? AND connection_epoch = ? AND event_index = ?
                """,
                [window.source_id, identity[1], identity[2]],
            ).fetchone()
            if owner is not None and owner[0] != window.window_id:
                raise ValueError(
                    "local delivery identity must not be persisted in multiple windows "
                    f"for one source: {identity!r}"
                )

        connection.execute(
            """
            INSERT INTO finalized_window(
                window_id, source_id, window_start, window_end, payload_json
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                window.window_id,
                window.source_id,
                window.window_start.isoformat(),
                window.window_end.isoformat(),
                payload,
            ],
        )
        connection.executemany(
            """
            INSERT INTO delivery_identity(
                source_id, connection_epoch, event_index, window_id
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (
                    window.source_id,
                    event.connection_epoch,
                    event.event_index,
                    window.window_id,
                )
                for event in window.events
            ],
        )

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path, timeout=30.0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS repository_meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        current = connection.execute(
            "SELECT value FROM repository_meta WHERE key = 'schema_version'"
        ).fetchone()
        if current is None:
            connection.execute(
                "INSERT INTO repository_meta(key, value) VALUES ('schema_version', ?)",
                [str(_SCHEMA_VERSION)],
            )
        elif current[0] != str(_SCHEMA_VERSION):
            connection.close()
            raise ObservationWindowFormatError(
                f"unsupported SQLite observation-window schema: {current[0]!r}"
            )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS finalized_window(
                window_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS finalized_window_source_time
            ON finalized_window(source_id, window_end, window_id)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS delivery_identity(
                source_id TEXT NOT NULL,
                connection_epoch INTEGER NOT NULL,
                event_index INTEGER NOT NULL,
                window_id TEXT NOT NULL REFERENCES finalized_window(window_id) ON DELETE CASCADE,
                PRIMARY KEY(source_id, connection_epoch, event_index)
            )
            """
        )
        connection.commit()
        return connection

    @staticmethod
    def _parse_payload(payload: str, *, context: str) -> DurableObservationWindow:
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ObservationWindowFormatError(
                f"{context} payload must contain valid JSON"
            ) from error
        return _parse_window(raw, index=0)
