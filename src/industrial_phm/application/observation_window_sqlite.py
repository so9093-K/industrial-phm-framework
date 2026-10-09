"""SQLite persistence for finalized observation windows and bounded incremental reads."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from threading import Lock
from datetime import datetime
from pathlib import Path

from industrial_phm._sqlite import connect_wal
from industrial_phm.application.observation_window import (
    DurableObservationWindow,
    ObservationWindowBufferSnapshot,
    ObservationWindowFormatError,
    _parse_persistent_event,
    _parse_window,
    _serialize_persistent_event,
    _serialize_window,
)
from industrial_phm.application.window_coordinator import (
    ObservationWindowCoordinatorState,
    OpcUaHistoricalEventCursor,
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
        self._schema_lock = Lock()
        self._schema_initialized = False
        if path.exists() and path.is_file():
            with path.open("rb") as stream:
                header = stream.read(16)
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
            where = "WHERE window_end > ? OR (window_end = ? AND window_id > ?)"
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

    def list_window_bounds(self) -> tuple[tuple[str, str, datetime, datetime], ...]:
        """(window_id, source_id, window_start, window_end) of every stored window."""
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT window_id, source_id, window_start, window_end
                FROM finalized_window
                ORDER BY window_end, window_id
                """
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            (row[0], row[1], datetime.fromisoformat(row[2]), datetime.fromisoformat(row[3]))
            for row in rows
        )

    def delete_windows(self, window_ids: Sequence[str]) -> int:
        """Delete finalized windows and their delivery identities; return the count."""
        ids = tuple(dict.fromkeys(window_ids))
        if any(not isinstance(item, str) or not item.strip() for item in ids):
            raise ValueError("window_ids must contain non-empty strings")
        if not ids:
            return 0
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            # delivery_identity rows cascade with their window.
            deleted = connection.executemany(
                "DELETE FROM finalized_window WHERE window_id = ?",
                [(item,) for item in ids],
            ).rowcount
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return int(deleted)

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

    def load_coordinator_state(
        self,
        source_id: str,
    ) -> ObservationWindowCoordinatorState | None:
        if not isinstance(source_id, str) or not source_id.strip():
            raise ValueError("source_id must not be empty")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT state_json FROM coordinator_state WHERE source_id = ?",
                [source_id],
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return _parse_coordinator_state(row[0], source_id=source_id)

    def record_coordinator_cycle(
        self,
        windows: Sequence[DurableObservationWindow],
        state: ObservationWindowCoordinatorState,
    ) -> None:
        values = tuple(windows)
        if any(not isinstance(item, DurableObservationWindow) for item in values):
            raise ValueError("windows must contain DurableObservationWindow values")
        if not isinstance(state, ObservationWindowCoordinatorState):
            raise ValueError("state must be ObservationWindowCoordinatorState")
        if any(item.source_id != state.source_id for item in values):
            raise ValueError("finalized window source_id must match coordinator state")

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            for window in values:
                self._record_window(connection, window)
            connection.execute(
                """
                INSERT INTO coordinator_state(source_id, state_json)
                VALUES (?, ?)
                ON CONFLICT(source_id) DO UPDATE SET state_json = excluded.state_json
                """,
                [state.source_id, _serialize_coordinator_state(state)],
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

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
        """Serialize schema creation, without a writer lock on later read connections.

        The collection coordinator, analysis runner and Operations status reader
        may all open a fresh workspace at the same time. Schema visibility and
        schema_version insertion must commit in one transaction: a separate
        SELECT followed by INSERT races against competing first openers.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = connect_wal(self._path, busy_timeout_ms=30_000, foreign_keys=True)
        try:
            with self._schema_lock:
                if not self._schema_initialized:
                    connection.execute("BEGIN IMMEDIATE")
                    try:
                        self._ensure_schema(connection)
                        connection.commit()
                    except BaseException:
                        connection.rollback()
                        raise
                    self._schema_initialized = True
            return connection
        except BaseException:
            connection.close()
            raise

    @staticmethod
    def _ensure_schema(connection: sqlite3.Connection) -> None:
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
            CREATE TABLE IF NOT EXISTS coordinator_state(
                source_id TEXT PRIMARY KEY,
                state_json TEXT NOT NULL
            )
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

    @staticmethod
    def _parse_payload(payload: str, *, context: str) -> DurableObservationWindow:
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ObservationWindowFormatError(
                f"{context} payload must contain valid JSON"
            ) from error
        return _parse_window(raw, index=0)


def _serialize_coordinator_state(state: ObservationWindowCoordinatorState) -> str:
    cursor = state.cursor
    payload = {
        "schema": "industrial-phm-window-coordinator-state-v1",
        "source_id": state.source_id,
        "cursor": (
            None
            if cursor is None
            else {
                "ingested_at": cursor.ingested_at.isoformat(),
                "connection_epoch": cursor.connection_epoch,
                "event_index": cursor.event_index,
            }
        ),
        "watermark": None if state.watermark is None else state.watermark.isoformat(),
        "max_valid_event_at": (
            None if state.max_valid_event_at is None else state.max_valid_event_at.isoformat()
        ),
        "active_buffers": [_serialize_buffer_snapshot(item) for item in state.active_buffers],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _serialize_buffer_snapshot(snapshot: ObservationWindowBufferSnapshot) -> dict[str, object]:
    return {
        "window_id": snapshot.window_id,
        "source_id": snapshot.source_id,
        "asset_id": snapshot.asset_id,
        "measurement_point_id": snapshot.measurement_point_id,
        "expected_channel_ids": list(snapshot.expected_channel_ids),
        "window_start": snapshot.window_start.isoformat(),
        "window_end": snapshot.window_end.isoformat(),
        "max_buffered_events": snapshot.max_buffered_events,
        "max_future_skew_seconds": snapshot.max_future_skew_seconds,
        "watermark": None if snapshot.watermark is None else snapshot.watermark.isoformat(),
        "events": [_serialize_persistent_event(event) for event in snapshot.events],
        "seen_delivery_identities": [list(item) for item in snapshot.seen_delivery_identities],
        "out_of_order_accepted_count": snapshot.out_of_order_accepted_count,
        "late_rejected_count": snapshot.late_rejected_count,
        "duplicate_rejected_count": snapshot.duplicate_rejected_count,
        "timing_unavailable_rejected_count": snapshot.timing_unavailable_rejected_count,
        "unexpected_channel_rejected_count": snapshot.unexpected_channel_rejected_count,
        "outside_window_rejected_count": snapshot.outside_window_rejected_count,
        "future_timestamp_rejected_count": snapshot.future_timestamp_rejected_count,
        "buffer_full_rejected_count": snapshot.buffer_full_rejected_count,
    }


def _parse_coordinator_state(
    payload: str,
    *,
    source_id: str,
) -> ObservationWindowCoordinatorState:
    try:
        raw = json.loads(payload)
        if raw.get("schema") != "industrial-phm-window-coordinator-state-v1":
            raise ObservationWindowFormatError("unsupported coordinator state schema")
        if raw.get("source_id") != source_id:
            raise ObservationWindowFormatError("coordinator state source_id mismatch")
        cursor_raw = raw.get("cursor")
        cursor = (
            None
            if cursor_raw is None
            else OpcUaHistoricalEventCursor(
                ingested_at=datetime.fromisoformat(cursor_raw["ingested_at"]),
                connection_epoch=int(cursor_raw["connection_epoch"]),
                event_index=int(cursor_raw["event_index"]),
            )
        )
        buffers = tuple(
            _parse_buffer_snapshot(item, index=index)
            for index, item in enumerate(raw.get("active_buffers", []))
        )
        watermark_raw = raw.get("watermark")
        max_valid_raw = raw.get("max_valid_event_at")
        return ObservationWindowCoordinatorState(
            source_id=source_id,
            cursor=cursor,
            watermark=None if watermark_raw is None else datetime.fromisoformat(watermark_raw),
            max_valid_event_at=(
                None if max_valid_raw is None else datetime.fromisoformat(max_valid_raw)
            ),
            active_buffers=buffers,
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ObservationWindowFormatError):
            raise
        raise ObservationWindowFormatError(
            f"invalid coordinator state for source {source_id}: {error}"
        ) from error


def _parse_buffer_snapshot(
    raw: object,
    *,
    index: int,
) -> ObservationWindowBufferSnapshot:
    if not isinstance(raw, dict):
        raise ObservationWindowFormatError(f"coordinator active_buffers[{index}] must be an object")
    try:
        events = tuple(
            _parse_persistent_event(
                item,
                context=f"coordinator active_buffers[{index}].events[{event_index}]",
            )
            for event_index, item in enumerate(raw["events"])
        )
        seen = tuple(
            (str(item[0]), int(item[1]), int(item[2])) for item in raw["seen_delivery_identities"]
        )
        watermark_raw = raw["watermark"]
        return ObservationWindowBufferSnapshot(
            window_id=str(raw["window_id"]),
            source_id=str(raw["source_id"]),
            asset_id=str(raw["asset_id"]),
            measurement_point_id=(
                None if raw["measurement_point_id"] is None else str(raw["measurement_point_id"])
            ),
            expected_channel_ids=tuple(str(item) for item in raw["expected_channel_ids"]),
            window_start=datetime.fromisoformat(str(raw["window_start"])),
            window_end=datetime.fromisoformat(str(raw["window_end"])),
            max_buffered_events=int(raw["max_buffered_events"]),
            max_future_skew_seconds=float(raw["max_future_skew_seconds"]),
            watermark=None if watermark_raw is None else datetime.fromisoformat(str(watermark_raw)),
            events=events,
            seen_delivery_identities=seen,
            out_of_order_accepted_count=int(raw["out_of_order_accepted_count"]),
            late_rejected_count=int(raw["late_rejected_count"]),
            duplicate_rejected_count=int(raw["duplicate_rejected_count"]),
            timing_unavailable_rejected_count=int(raw["timing_unavailable_rejected_count"]),
            unexpected_channel_rejected_count=int(raw["unexpected_channel_rejected_count"]),
            outside_window_rejected_count=int(raw["outside_window_rejected_count"]),
            future_timestamp_rejected_count=int(raw["future_timestamp_rejected_count"]),
            buffer_full_rejected_count=int(raw["buffer_full_rejected_count"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ObservationWindowFormatError):
            raise
        raise ObservationWindowFormatError(
            f"invalid coordinator active buffer {index}: {error}"
        ) from error
