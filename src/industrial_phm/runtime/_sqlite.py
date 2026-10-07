"""Bounded WAL connection bootstrap; data transactions are never replayed here."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path


def connect_wal(
    path: Path, *, busy_timeout_ms: int, foreign_keys: bool = False
) -> sqlite3.Connection:
    """Let competing first openers finish WAL activation within the existing budget.

    Journal-mode changes can return SQLITE_BUSY without invoking SQLite's busy
    handler. Close the failed connection before retrying this configuration-only
    boundary. Already-WAL databases need no mode-changing statement.
    """
    deadline = time.monotonic() + busy_timeout_ms / 1000
    while True:
        remaining = max(0.0, deadline - time.monotonic())
        connection = sqlite3.connect(path, timeout=remaining)
        try:
            mode = connection.execute("PRAGMA journal_mode").fetchone()
            if mode is None or mode[0] != "wal":
                mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()
                if mode is None or mode[0] != "wal":
                    raise sqlite3.OperationalError("SQLite did not activate WAL journal mode")
            connection.execute("PRAGMA synchronous = FULL")
            if foreign_keys:
                connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
            return connection
        except sqlite3.OperationalError as error:
            connection.close()
            remaining = deadline - time.monotonic()
            code = getattr(error, "sqlite_errorcode", 0)
            if code & 0xFF != sqlite3.SQLITE_BUSY or remaining <= 0:
                error.add_note(f"SQLite WAL bootstrap failed for {path}")
                raise
            time.sleep(min(0.01, remaining))
        except BaseException:
            connection.close()
            raise
