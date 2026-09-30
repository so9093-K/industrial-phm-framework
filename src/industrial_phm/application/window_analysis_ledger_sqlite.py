"""SQLite skip ledger and policy-specific progress for live window analysis."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from industrial_phm.application.live_window_analysis import (
    WindowAnalysisCursor,
    WindowAnalysisOutcome,
    WindowAnalysisState,
)

_SCHEMA_VERSION = 1


class SqliteWindowAnalysisLedger:
    """WAL-backed skipped-outcome ledger plus monotonic analysis cursors."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise ValueError("path must be pathlib.Path")
        self._path = path
        if path.exists() and path.is_file():
            with path.open("rb") as stream:
                header = stream.read(16)
            if header and header != b"SQLite format 3\x00":
                raise ValueError(
                    "analysis ledger is not SQLite; choose a new --ledger-state path "
                    "instead of reusing legacy JSON state"
                )

    @property
    def path(self) -> Path:
        return self._path

    def list_skipped(self) -> tuple[WindowAnalysisOutcome, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT
                    window_id,
                    capability_id,
                    algorithm_version,
                    analysis_policy_digest,
                    recorded_at,
                    reason
                FROM skipped_outcome
                ORDER BY recorded_at, window_id
                """
            ).fetchall()
        finally:
            connection.close()
        return tuple(
            WindowAnalysisOutcome(
                window_id=row[0],
                capability_id=row[1],
                algorithm_version=row[2],
                analysis_policy_digest=row[3],
                state=WindowAnalysisState.SKIPPED,
                recorded_at=datetime.fromisoformat(row[4]),
                reason=row[5],
            )
            for row in rows
        )

    def load_cursor(
        self,
        capability_id: str,
        algorithm_version: str,
        analysis_policy_digest: str,
    ) -> WindowAnalysisCursor | None:
        for name, value in (
            ("capability_id", capability_id),
            ("algorithm_version", algorithm_version),
            ("analysis_policy_digest", analysis_policy_digest),
        ):
            _validate_identifier(value, name)
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT window_end, window_id
                FROM analysis_cursor
                WHERE capability_id = ?
                  AND algorithm_version = ?
                  AND analysis_policy_digest = ?
                """,
                [capability_id, algorithm_version, analysis_policy_digest],
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return WindowAnalysisCursor(
            capability_id=capability_id,
            algorithm_version=algorithm_version,
            analysis_policy_digest=analysis_policy_digest,
            window_end=datetime.fromisoformat(row[0]),
            window_id=row[1],
        )

    def advance_cursor(self, cursor: WindowAnalysisCursor) -> None:
        if not isinstance(cursor, WindowAnalysisCursor):
            raise ValueError("cursor must be WindowAnalysisCursor")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._advance_cursor(connection, cursor)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def record_skip_and_advance(
        self,
        outcome: WindowAnalysisOutcome,
        cursor: WindowAnalysisCursor,
    ) -> None:
        if not isinstance(outcome, WindowAnalysisOutcome):
            raise ValueError("outcome must be WindowAnalysisOutcome")
        if outcome.state != WindowAnalysisState.SKIPPED:
            raise ValueError("only skipped outcomes belong in the skip ledger")
        if not isinstance(cursor, WindowAnalysisCursor):
            raise ValueError("cursor must be WindowAnalysisCursor")
        if outcome.window_id != cursor.window_id:
            raise ValueError("skip outcome and cursor window_id must match")
        if outcome.key[1:] != cursor.analysis_identity:
            raise ValueError("skip outcome and cursor analysis identity must match")
        if outcome.reason is None:
            raise ValueError("skipped outcome reason is required")

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO skipped_outcome(
                    window_id,
                    capability_id,
                    algorithm_version,
                    analysis_policy_digest,
                    recorded_at,
                    reason
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(
                    window_id,
                    capability_id,
                    algorithm_version,
                    analysis_policy_digest
                ) DO NOTHING
                """,
                [
                    outcome.window_id,
                    outcome.capability_id,
                    outcome.algorithm_version,
                    outcome.analysis_policy_digest,
                    outcome.recorded_at.isoformat(),
                    outcome.reason,
                ],
            )
            self._advance_cursor(connection, cursor)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _advance_cursor(
        self,
        connection: sqlite3.Connection,
        cursor: WindowAnalysisCursor,
    ) -> None:
        row = connection.execute(
            """
            SELECT window_end, window_id
            FROM analysis_cursor
            WHERE capability_id = ?
              AND algorithm_version = ?
              AND analysis_policy_digest = ?
            """,
            [
                cursor.capability_id,
                cursor.algorithm_version,
                cursor.analysis_policy_digest,
            ],
        ).fetchone()
        if row is not None:
            current = (datetime.fromisoformat(row[0]), row[1])
            requested = (cursor.window_end, cursor.window_id)
            if requested < current:
                raise ValueError("analysis cursor must not move backwards")
            if requested == current:
                return
        connection.execute(
            """
            INSERT INTO analysis_cursor(
                capability_id,
                algorithm_version,
                analysis_policy_digest,
                window_end,
                window_id
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(capability_id, algorithm_version, analysis_policy_digest)
            DO UPDATE SET
                window_end = excluded.window_end,
                window_id = excluded.window_id
            """,
            [
                cursor.capability_id,
                cursor.algorithm_version,
                cursor.analysis_policy_digest,
                cursor.window_end.isoformat(),
                cursor.window_id,
            ],
        )

    def _connect(self) -> sqlite3.Connection:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._path, timeout=30.0)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ledger_meta(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        current = connection.execute(
            "SELECT value FROM ledger_meta WHERE key = 'schema_version'"
        ).fetchone()
        if current is None:
            connection.execute(
                "INSERT INTO ledger_meta(key, value) VALUES ('schema_version', ?)",
                [str(_SCHEMA_VERSION)],
            )
        elif current[0] != str(_SCHEMA_VERSION):
            connection.close()
            raise ValueError(f"unsupported analysis ledger schema: {current[0]!r}")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS skipped_outcome(
                window_id TEXT NOT NULL,
                capability_id TEXT NOT NULL,
                algorithm_version TEXT NOT NULL,
                analysis_policy_digest TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                reason TEXT NOT NULL,
                PRIMARY KEY(
                    window_id,
                    capability_id,
                    algorithm_version,
                    analysis_policy_digest
                )
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_cursor(
                capability_id TEXT NOT NULL,
                algorithm_version TEXT NOT NULL,
                analysis_policy_digest TEXT NOT NULL,
                window_end TEXT NOT NULL,
                window_id TEXT NOT NULL,
                PRIMARY KEY(capability_id, algorithm_version, analysis_policy_digest)
            )
            """
        )
        connection.commit()
        return connection


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
