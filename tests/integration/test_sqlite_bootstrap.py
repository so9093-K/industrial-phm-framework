"""Real SQLite lock schedules at the runtime's cold-start boundary."""

import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier, Event

import pytest

from industrial_phm.application import SqliteObservationWindowRepository
from industrial_phm.runtime import (
    SqliteAcquisitionSpool,
    SqliteAcquisitionSpoolConfig,
    SqliteAcquisitionTelemetryRepository,
    SqliteCollectionControlRepository,
)


def _repository(kind, path, budget=1000):
    if kind == "spool":
        return SqliteAcquisitionSpool(SqliteAcquisitionSpoolConfig(path, busy_timeout_ms=budget))
    if kind == "telemetry":
        return SqliteAcquisitionTelemetryRepository(path, busy_timeout_ms=budget)
    return SqliteCollectionControlRepository(path, busy_timeout_ms=budget)


def _read(repo, kind):
    return repo.get_last_connection_epoch("source") if kind == "spool" else repo.get("source")


def _holder(path):
    # A distinct writer process owns the rollback-journal RESERVED lock. A new
    # opener's WAL activation returns immediate SQLITE_BUSY despite busy_timeout.
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            """
import sqlite3, sys
connection = sqlite3.connect(sys.argv[1])
connection.execute('CREATE TABLE writer_guard(value INTEGER)')
connection.execute('BEGIN IMMEDIATE')
connection.execute('INSERT INTO writer_guard VALUES (1)')
print('LOCKED', flush=True)
sys.stdin.buffer.read(1)
connection.commit()
connection.close()
""",
            str(path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout.readline().strip() == b"LOCKED"
    return process


def _release(process):
    if process.poll() is None:
        process.stdin.write(b"r")
        process.stdin.flush()
    process.communicate(timeout=5)
    assert process.returncode == 0


@pytest.mark.parametrize("kind", ["spool", "telemetry", "control"])
def test_first_open_survives_immediate_busy_from_another_process(tmp_path, monkeypatch, kind):
    path = tmp_path / f"{kind}.sqlite"
    process = _holder(path)
    observed_busy = Event()
    failed_connections = []
    original_connect = sqlite3.connect

    class TracedConnection(sqlite3.Connection):
        closed = False

        def execute(self, sql, parameters=()):
            try:
                return super().execute(sql, parameters)
            except sqlite3.OperationalError as error:
                if error.sqlite_errorcode == sqlite3.SQLITE_BUSY:
                    failed_connections.append(self)
                    observed_busy.set()
                raise

        def close(self):
            self.closed = True
            super().close()

    def connect(*args, **kwargs):
        return original_connect(*args, **kwargs, factory=TracedConnection)

    monkeypatch.setattr(sqlite3, "connect", connect)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_read, _repository(kind, path), kind)
            assert observed_busy.wait(5), "the real cold-start lock schedule was not exercised"
            _release(process)
            result = future.result(timeout=5)
        assert result is None if kind == "control" else result is not None
        assert failed_connections and all(connection.closed for connection in failed_connections)
        with closing(original_connect(path)) as connection:
            assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
            assert connection.execute("PRAGMA synchronous").fetchone() == (2,)
            assert connection.execute("SELECT * FROM writer_guard").fetchall() == [(1,)]
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        _release(process)


@pytest.mark.parametrize("kind", ["spool", "telemetry", "control"])
def test_bootstrap_lock_budget_expires_and_closes_failed_connections(tmp_path, kind):
    path = tmp_path / f"{kind}.sqlite"
    process = _holder(path)
    try:
        with pytest.raises(sqlite3.OperationalError, match="database is locked") as caught:
            _read(_repository(kind, path, budget=50), kind)
        assert caught.value.sqlite_errorcode == sqlite3.SQLITE_BUSY
        assert str(path) in " ".join(caught.value.__notes__)
    finally:
        _release(process)
    # A failed activation left neither an open lock nor a partially committed
    # repository schema. The same caller can use the store after the owner exits.
    _read(_repository(kind, path), kind)


@pytest.mark.parametrize("kind", ["spool", "telemetry", "control"])
def test_two_initializers_recheck_empty_metadata_after_reserving_writer(
    tmp_path, monkeypatch, kind
):
    path = tmp_path / f"{kind}.sqlite"
    table = {
        "spool": "spool_metadata",
        "telemetry": "telemetry_metadata",
        "control": "collection_control_metadata",
    }[kind]
    original_connect = sqlite3.connect
    with closing(original_connect(path)) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(f"CREATE TABLE {table}(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    barrier = Barrier(2)

    class SchemaCursor(sqlite3.Cursor):
        def execute(self, sql, parameters=()):
            self.sql = sql
            return super().execute(sql, parameters)

        def fetchone(self):
            row = super().fetchone()
            if (
                self.sql.startswith(f"SELECT value FROM {table}")
                and row is None
                and not self.connection.in_transaction
            ):
                barrier.wait(timeout=5)
            return row

    class SchemaConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            return self.cursor(factory=SchemaCursor).execute(sql, parameters)

    def connect(*args, **kwargs):
        return original_connect(*args, **kwargs, factory=SchemaConnection)

    monkeypatch.setattr(sqlite3, "connect", connect)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_read, _repository(kind, path), kind) for _ in range(2)]
        for future in futures:
            future.result(timeout=5)
    with closing(original_connect(path)) as connection:
        assert connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE key='schema'"
        ).fetchone() == (1,)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)


@pytest.mark.parametrize("kind", ["spool", "telemetry", "control"])
def test_initialized_wal_read_does_not_wait_for_an_active_writer(tmp_path, kind):
    path = tmp_path / f"{kind}.sqlite"
    repository = _repository(kind, path, budget=50)
    repository.initialize()
    with closing(sqlite3.connect(path)) as writer:
        writer.execute("BEGIN IMMEDIATE")
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(_read, repository, kind).result(timeout=2)
            assert writer.in_transaction
        finally:
            writer.rollback()


def test_spool_initialize_closes_its_connection(tmp_path, monkeypatch):
    connections = []
    original_connect = sqlite3.connect

    class ObservedConnection(sqlite3.Connection):
        closed = False

        def close(self):
            self.closed = True
            super().close()

    def connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs, factory=ObservedConnection)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", connect)
    _repository("spool", tmp_path / "spool.sqlite").initialize()
    assert connections and all(connection.closed for connection in connections)


def test_window_first_open_waits_for_competing_process_writer(tmp_path):
    """A cold-start Operations reader waits instead of failing during WAL activation."""
    path = tmp_path / "windows.sqlite"
    process = _holder(path)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(SqliteObservationWindowRepository(path).list_windows)
            _release(process)
            assert future.result(timeout=10) == ()
        with closing(sqlite3.connect(path)) as connection:
            assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
            assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            assert connection.execute(
                "SELECT value FROM repository_meta WHERE key='schema_version'"
            ).fetchone() == ("1",)
    finally:
        _release(process)


def test_window_schema_check_happens_after_writer_reservation(tmp_path, monkeypatch):
    """A metadata read must be protected from another first opener's commit."""
    path = tmp_path / "windows.sqlite"
    original_connect = sqlite3.connect
    reads = []

    class VerifiedConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql.startswith("SELECT value FROM repository_meta"):
                reads.append(self.in_transaction)
                assert self.in_transaction, "metadata read without schema writer reservation"
            return super().execute(sql, parameters)

    def checked_connect(*args, **kwargs):
        return original_connect(*args, **kwargs, factory=VerifiedConnection)

    monkeypatch.setattr(sqlite3, "connect", checked_connect)
    assert SqliteObservationWindowRepository(path).list_windows() == ()
    assert reads == [True]


def test_concurrent_window_first_open_is_idempotent(tmp_path):
    """Multiple coordinator/reader instances share one complete committed schema."""
    path = tmp_path / "windows.sqlite"
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: SqliteObservationWindowRepository(path).list_windows(),
                range(16),
            )
        )
    assert results == [()] * 16
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM repository_meta WHERE key='schema_version'"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND "
            "name IN ('finalized_window', 'coordinator_state', 'delivery_identity')"
        ).fetchone() == (3,)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
