"""DuckLake-backed historical Asset History adapter.

DuckLake is the long-term historical data plane. This adapter deliberately does not
implement callback buffering, retry queues, or ingress durability; those responsibilities
belong to the acquisition spool.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import sqlite3
import sys
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from pathlib import Path
from typing import Any

from industrial_phm.application.analysis_input import ChannelObservation
from industrial_phm.application.asset_history import (
    HistoricalBatchAppendResult,
    HistoricalBatchCommit,
    HistoricalBatchConflictError,
    HistoricalEventTimeBasis,
    HistoricalMeasurement,
    HistoryIngestionMode,
    validate_asset_history_query,
)
from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.application.measurement_history import (
    HistoryAssetSummary,
    MeasurementHistoryAggregation,
    MeasurementHistoryBucket,
    MeasurementHistoryPage,
    MeasurementHistoryPoint,
)
from industrial_phm.application.measurement_semantics import (
    ChannelSemanticBinding,
    ChannelSemanticCandidate,
    parse_channel_semantic_binding,
    serialize_channel_semantic_binding,
)
from industrial_phm.application.opcua_persistent import (
    OpcUaEventTimeBasis,
    OpcUaEventTimeEvidence,
    OpcUaPersistentDataChangeEvent,
)
from industrial_phm.application.source_registration import SourceType
from industrial_phm.application.source_subscription import RegisteredOpcUaDataChangeEvent
from industrial_phm.application.window_coordinator import OpcUaHistoricalEventCursor
from industrial_phm.connectors import OpcUaNodeObservation, OpcUaSubscriptionNotification

_CATALOG_NAME = "phm_history"
_COMMIT_AUTHOR = "industrial-phm"
_COMMIT_EXTRA_SCHEMA = "industrial-phm-history-batch-v1"
# OPC UA commits written with this version fingerprint the semantic snapshot too.
# Commits without a version (before it existed, including semantics-bearing spool
# batches) are verified with the legacy fingerprint that excludes semantics.
_OPCUA_FINGERPRINT_VERSION = "opcua-semantic-v2"
_BATCH_PROVENANCE_INDEX_SCHEMA = 1

_HISTORY_DATA_TABLES = (
    ("raw", "opcua_data_change"),
    ("raw", "file_measurement"),
    ("history", "measurement"),
    ("history", "ingestion_batch"),
)
_SNAPSHOT_FINGERPRINT_TABLES = (
    ("raw", "opcua_data_change", "raw_evidence_id"),
    ("raw", "file_measurement", "raw_evidence_id"),
    ("history", "measurement", "raw_evidence_id"),
    ("history", "ingestion_batch", "batch_id, ingestion_mode"),
)


class DuckLakeRuntimeUnavailableError(RuntimeError):
    """Raised when the optional DuckDB/DuckLake history runtime is unavailable."""


@dataclass(frozen=True, slots=True)
class DuckLakeInlinedDataFlush:
    """Result of moving catalog-inlined rows into managed Parquet files.

    Flush rewrites physical storage only. Earlier snapshots keep the same rows
    for time travel, and batch commit provenance keeps its original snapshot.
    """

    snapshot_id: int
    flushed_rows: tuple[tuple[str, int], ...]

    @property
    def flushed_row_count(self) -> int:
        return sum(count for _, count in self.flushed_rows)


@dataclass(frozen=True, slots=True)
class DuckLakeRuntimeFingerprint:
    """Runtime versions that affect DuckLake maintenance behavior."""

    duckdb_version: str
    ducklake_extension_version: str | None
    ducklake_installed_from: str | None
    ducklake_install_mode: str | None


@dataclass(frozen=True, slots=True)
class DuckLakeStorageInspection:
    """Physical and logical storage state observed under the catalog lease."""

    snapshot_count: int
    current_snapshot_id: int
    active_data_file_count: int
    active_data_file_bytes: int
    active_file_size_min_bytes: int | None
    active_file_size_median_bytes: int | None
    active_file_size_max_bytes: int | None
    scheduled_for_deletion_count: int
    physical_parquet_file_count: int
    physical_parquet_bytes: int
    catalog_bytes: int


@dataclass(frozen=True, slots=True)
class DuckLakeCompactedTable:
    """One table's output from a merge-adjacent-files operation."""

    schema_name: str
    table_name: str
    files_processed: int
    files_created: int


@dataclass(frozen=True, slots=True)
class DuckLakeCompactionResult:
    """Non-destructive compaction result.

    Compaction may create a new snapshot. It does not expire snapshots or clean
    physical files; earlier snapshot IDs must remain queryable.
    """

    snapshot_before: int
    snapshot_after: int
    duration_seconds: float
    target_file_size_bytes: int
    tables: tuple[DuckLakeCompactedTable, ...]
    storage_before: DuckLakeStorageInspection
    storage_after: DuckLakeStorageInspection

    @property
    def files_processed(self) -> int:
        return sum(table.files_processed for table in self.tables)

    @property
    def files_created(self) -> int:
        return sum(table.files_created for table in self.tables)


@dataclass(frozen=True, slots=True)
class DuckLakeAssetHistoryConfig:
    """Local-first DuckLake configuration for the v1 history boundary."""

    catalog_path: Path
    data_path: Path
    catalog_lock_timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if (
            isinstance(self.catalog_lock_timeout_seconds, bool)
            or not isinstance(self.catalog_lock_timeout_seconds, (int, float))
            or not isfinite(self.catalog_lock_timeout_seconds)
            or self.catalog_lock_timeout_seconds <= 0
        ):
            raise ValueError("catalog_lock_timeout_seconds must be positive and finite")
        if not isinstance(self.catalog_path, Path):
            raise ValueError("catalog_path must be pathlib.Path")
        if not isinstance(self.data_path, Path):
            raise ValueError("data_path must be pathlib.Path")
        catalog_path = self.catalog_path.expanduser().resolve(strict=False)
        data_path = self.data_path.expanduser().resolve(strict=False)
        if catalog_path == data_path:
            raise ValueError("DuckLake catalog_path and data_path must be distinct")


@contextmanager
def _cache_absent_pandas_import() -> Iterator[None]:
    """Make DuckDB's per-parameter pandas probe fail fast when pandas is absent.

    DuckDB attempts ``import pandas`` for each bound Python value. Without pandas,
    every attempt rescans sys.path; this was about 60% of measured AI-Hub import
    time. A None module entry raises the same ImportError without the scan. It is
    set only while pandas is not importable and removed afterwards.
    """
    if "pandas" in sys.modules or importlib.util.find_spec("pandas") is not None:
        yield
        return
    sys.modules["pandas"] = None  # type: ignore[assignment]
    try:
        yield
    finally:
        if "pandas" in sys.modules and sys.modules["pandas"] is None:
            del sys.modules["pandas"]


class _LockedConnection:
    """Keep the local catalog lease until all DuckLake handles are closed."""

    def __init__(self, connection: Any, lock: Any) -> None:
        self._connection = connection
        self._lock = lock

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def close(self) -> None:
        try:
            self._connection.close()
        finally:
            self._lock.release()


class DuckLakeAssetHistory:
    """Single-writer DuckLake adapter for OPC UA history and normalized measurements."""

    def __init__(self, config: DuckLakeAssetHistoryConfig) -> None:
        if not isinstance(config, DuckLakeAssetHistoryConfig):
            raise ValueError("config must be DuckLakeAssetHistoryConfig")
        self._config = config

    @property
    def config(self) -> DuckLakeAssetHistoryConfig:
        return self._config

    def initialize(self) -> None:
        """Create the v1 schemas and tables idempotently."""
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
        finally:
            connection.close()

    def get_opcua_batch_commit(
        self,
        events: Sequence[OpcUaPersistentDataChangeEvent],
        *,
        batch_id: str,
        ingestion_mode: HistoryIngestionMode = HistoryIngestionMode.LIVE,
    ) -> HistoricalBatchCommit | None:
        """Return an existing identical batch commit, or fail on identity conflict."""
        batch = _validate_opcua_batch_input(
            events,
            batch_id=batch_id,
            ingestion_mode=ingestion_mode,
        )
        fingerprint = _opcua_batch_fingerprint(batch)
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            return self._lookup_existing_batch_commit(
                connection,
                batch_id=batch_id,
                ingestion_mode=ingestion_mode,
                event_count=len(batch),
                fingerprint=fingerprint,
                fingerprint_version=_OPCUA_FINGERPRINT_VERSION,
                legacy_fingerprint=_opcua_batch_fingerprint(batch, include_semantics=False),
            )
        finally:
            connection.close()

    def append_or_recover_opcua_batch(
        self,
        events: Sequence[OpcUaPersistentDataChangeEvent],
        *,
        batch_id: str,
        ingestion_mode: HistoryIngestionMode = HistoryIngestionMode.LIVE,
    ) -> HistoricalBatchAppendResult:
        """Atomically persist a batch or report recovery of its identical prior commit."""
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            return self._append_or_recover_opcua_batch_with_connection(
                connection,
                events,
                batch_id=batch_id,
                ingestion_mode=ingestion_mode,
            )
        finally:
            connection.close()

    def append_opcua_batch(
        self,
        events: Sequence[OpcUaPersistentDataChangeEvent],
        *,
        batch_id: str,
        ingestion_mode: HistoryIngestionMode = HistoryIngestionMode.LIVE,
    ) -> HistoricalBatchCommit:
        """Atomically persist a batch or recover its already committed identical write."""
        return self.append_or_recover_opcua_batch(
            events,
            batch_id=batch_id,
            ingestion_mode=ingestion_mode,
        ).commit

    def _append_opcua_batch_with_connection(
        self,
        connection: Any,
        events: Sequence[OpcUaPersistentDataChangeEvent],
        *,
        batch_id: str,
        ingestion_mode: HistoryIngestionMode = HistoryIngestionMode.LIVE,
    ) -> HistoricalBatchCommit:
        """Persist one batch using an already leased/initialized connection."""
        return self._append_or_recover_opcua_batch_with_connection(
            connection,
            events,
            batch_id=batch_id,
            ingestion_mode=ingestion_mode,
        ).commit

    def _append_or_recover_opcua_batch_with_connection(
        self,
        connection: Any,
        events: Sequence[OpcUaPersistentDataChangeEvent],
        *,
        batch_id: str,
        ingestion_mode: HistoryIngestionMode = HistoryIngestionMode.LIVE,
    ) -> HistoricalBatchAppendResult:
        """Persist one batch or recover it using an already leased/initialized connection."""
        batch = _validate_opcua_batch_input(
            events,
            batch_id=batch_id,
            ingestion_mode=ingestion_mode,
        )
        fingerprint = _opcua_batch_fingerprint(batch)
        existing = self._lookup_existing_batch_commit(
            connection,
            batch_id=batch_id,
            ingestion_mode=ingestion_mode,
            event_count=len(batch),
            fingerprint=fingerprint,
            fingerprint_version=_OPCUA_FINGERPRINT_VERSION,
            legacy_fingerprint=_opcua_batch_fingerprint(batch, include_semantics=False),
        )
        if existing is not None:
            # A legacy commit is recovered as stored: its raw rows keep no semantic
            # snapshot and are never backfilled with the current binding.
            return HistoricalBatchAppendResult(
                commit=existing,
                recovered_existing_commit=True,
            )
        self._reject_existing_deliveries(connection, batch)

        transaction_open = False
        try:
            connection.execute("BEGIN TRANSACTION")
            transaction_open = True
            connection.execute(
                f"""
                INSERT INTO {_CATALOG_NAME}.history.ingestion_batch
                    (batch_id, ingestion_mode, event_count)
                VALUES (?, ?, ?)
                """,
                [batch_id, ingestion_mode.value, len(batch)],
            )
            _insert_columns(
                connection,
                "raw.opcua_data_change",
                _OPCUA_RAW_COLUMNS,
                [
                    _raw_event_row(
                        event,
                        batch_id=batch_id,
                        ingestion_mode=ingestion_mode,
                    )
                    for event in batch
                ],
            )
            _insert_columns(
                connection,
                "history.measurement",
                _MEASUREMENT_COLUMNS,
                [
                    _measurement_row(
                        event,
                        batch_id=batch_id,
                        ingestion_mode=ingestion_mode,
                    )
                    for event in batch
                ],
            )
            commit_extra_info = _batch_commit_extra_info(
                batch_id=batch_id,
                ingestion_mode=ingestion_mode,
                event_count=len(batch),
                fingerprint=fingerprint,
                fingerprint_version=_OPCUA_FINGERPRINT_VERSION,
            )
            connection.execute(
                f"CALL {_CATALOG_NAME}.set_commit_message("
                + _quote_sql_literal(_COMMIT_AUTHOR)
                + ", "
                + _quote_sql_literal(f"ingestion batch {batch_id}")
                + ", extra_info => "
                + _quote_sql_literal(commit_extra_info)
                + ")"
            )
            connection.execute("COMMIT")
            transaction_open = False
        except Exception:
            if transaction_open:
                connection.execute("ROLLBACK")
            raise

        snapshot_row = connection.execute(
            f"SELECT id FROM {_CATALOG_NAME}.last_committed_snapshot()"
        ).fetchone()
        if snapshot_row is None or snapshot_row[0] is None:
            raise RuntimeError("DuckLake did not report the committed batch snapshot")
        snapshot_id = _require_int(snapshot_row[0], "snapshot_id")

        committed_at = self._snapshot_time_by_id(connection, snapshot_id)

        self._record_batch_snapshot_index(batch_id, snapshot_id)
        return HistoricalBatchAppendResult(
            commit=HistoricalBatchCommit(
                batch_id=batch_id,
                snapshot_id=snapshot_id,
                event_count=len(batch),
                committed_at=committed_at,
            ),
            recovered_existing_commit=False,
        )

    def get_file_batch_commit(
        self,
        events: Sequence[FileBackfillEvent],
        *,
        batch_id: str,
        ingestion_mode: HistoryIngestionMode = HistoryIngestionMode.BACKFILL,
    ) -> HistoricalBatchCommit | None:
        """Return an existing identical FILE batch commit, or fail on conflict."""
        batch = _validate_file_batch_input(
            events,
            batch_id=batch_id,
            ingestion_mode=ingestion_mode,
        )
        fingerprint = _file_batch_fingerprint(batch)
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            return self._lookup_existing_batch_commit(
                connection,
                batch_id=batch_id,
                ingestion_mode=ingestion_mode,
                event_count=len(batch),
                fingerprint=fingerprint,
            )
        finally:
            connection.close()

    def append_file_batch(
        self,
        events: Sequence[FileBackfillEvent],
        *,
        batch_id: str,
        ingestion_mode: HistoryIngestionMode = HistoryIngestionMode.BACKFILL,
    ) -> HistoricalBatchCommit:
        """Persist one FILE backfill segment into raw evidence and common measurement history."""
        batch = _validate_file_batch_input(
            events,
            batch_id=batch_id,
            ingestion_mode=ingestion_mode,
        )
        fingerprint = _file_batch_fingerprint(batch)

        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            existing = self._lookup_existing_batch_commit(
                connection,
                batch_id=batch_id,
                ingestion_mode=ingestion_mode,
                event_count=len(batch),
                fingerprint=fingerprint,
            )
            if existing is not None:
                return existing
            self._reject_existing_file_evidence(connection, batch)

            transaction_open = False
            try:
                connection.execute("BEGIN TRANSACTION")
                transaction_open = True
                connection.execute(
                    f"""
                    INSERT INTO {_CATALOG_NAME}.history.ingestion_batch
                        (batch_id, ingestion_mode, event_count)
                    VALUES (?, ?, ?)
                    """,
                    [batch_id, ingestion_mode.value, len(batch)],
                )
                _insert_columns(
                    connection,
                    "raw.file_measurement",
                    _FILE_RAW_COLUMNS,
                    [
                        _file_raw_event_row(
                            event,
                            batch_id=batch_id,
                            ingestion_mode=ingestion_mode,
                        )
                        for event in batch
                    ],
                )
                _insert_columns(
                    connection,
                    "history.measurement",
                    _MEASUREMENT_COLUMNS,
                    [
                        _file_measurement_row(
                            event,
                            batch_id=batch_id,
                            ingestion_mode=ingestion_mode,
                        )
                        for event in batch
                    ],
                )
                commit_extra_info = _batch_commit_extra_info(
                    batch_id=batch_id,
                    ingestion_mode=ingestion_mode,
                    event_count=len(batch),
                    fingerprint=fingerprint,
                )
                connection.execute(
                    f"CALL {_CATALOG_NAME}.set_commit_message("
                    + _quote_sql_literal(_COMMIT_AUTHOR)
                    + ", "
                    + _quote_sql_literal(f"ingestion batch {batch_id}")
                    + ", extra_info => "
                    + _quote_sql_literal(commit_extra_info)
                    + ")"
                )
                connection.execute("COMMIT")
                transaction_open = False
            except Exception:
                if transaction_open:
                    connection.execute("ROLLBACK")
                raise

            return self._last_committed_batch(connection, batch_id, len(batch))
        finally:
            connection.close()

    def query_file_events(self, source_id: str) -> tuple[FileBackfillEvent, ...]:
        """Return raw FILE evidence in deterministic source-time/provenance order."""
        _validate_identifier(source_id, "source_id")
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            rows = connection.execute(
                f"""
                SELECT
                    raw_evidence_id,
                    source_id,
                    asset_id,
                    measurement_point_id,
                    source_file,
                    source_sha256,
                    source_size_bytes,
                    sample_index,
                    channel_id,
                    source_timestamp,
                    value,
                    source_metadata_json
                FROM {_CATALOG_NAME}.raw.file_measurement
                WHERE source_id = ?
                ORDER BY source_timestamp, source_file, sample_index, channel_id, raw_evidence_id
                """,
                [source_id],
            ).fetchall()
        finally:
            connection.close()
        return tuple(_file_event_from_row(row) for row in rows)

    def current_snapshot_id(self) -> int:
        """Return the current DuckLake snapshot for input-range provenance."""
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            row = connection.execute(
                f"SELECT max(snapshot_id) FROM {_CATALOG_NAME}.snapshots()"
            ).fetchone()
        finally:
            connection.close()
        if row is None or row[0] is None:
            return 0
        return _require_int(row[0], "snapshot_id")

    def runtime_fingerprint(self) -> DuckLakeRuntimeFingerprint:
        """Return DuckDB/DuckLake versions used by this history adapter."""
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            version_row = connection.execute("SELECT version()").fetchone()
            extension_row = connection.execute(
                """
                SELECT extension_version, installed_from, install_mode
                FROM duckdb_extensions()
                WHERE extension_name = 'ducklake'
                """
            ).fetchone()
        finally:
            connection.close()
        if version_row is None:
            raise RuntimeError("DuckDB did not report its version")
        if extension_row is None:
            raise RuntimeError("DuckLake extension metadata is unavailable")
        return DuckLakeRuntimeFingerprint(
            duckdb_version=_require_str(version_row[0], "duckdb_version"),
            ducklake_extension_version=_optional_str(
                extension_row[0], "ducklake_extension_version"
            ),
            ducklake_installed_from=_optional_str(extension_row[1], "ducklake_installed_from"),
            ducklake_install_mode=_optional_str(extension_row[2], "ducklake_install_mode"),
        )

    def inspect_storage(self) -> DuckLakeStorageInspection:
        """Inspect active/logical and physical storage without mutating history."""
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            return self._inspect_storage_with_connection(connection)
        finally:
            connection.close()

    def snapshot_evidence_fingerprint(self, snapshot_id: int) -> str:
        """Hash canonical raw/history rows visible at one existing snapshot."""
        _validate_non_negative_int(snapshot_id, "snapshot_id")
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            try:
                self._snapshot_time_by_id(connection, snapshot_id)
            except RuntimeError as error:
                raise ValueError(f"history snapshot does not exist: {snapshot_id}") from error

            digest = hashlib.sha256()
            for schema, table, order_by in _SNAPSHOT_FINGERPRINT_TABLES:
                cursor = connection.execute(
                    f"SELECT * FROM {_CATALOG_NAME}.{schema}.{table} "
                    f"AT (VERSION => {snapshot_id}) ORDER BY {order_by}"
                )
                columns = [description[0] for description in cursor.description]
                digest.update(
                    json.dumps(
                        [schema, table, columns],
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode()
                )
                while True:
                    rows = cursor.fetchmany(1000)
                    if not rows:
                        break
                    for row in rows:
                        digest.update(
                            json.dumps(
                                [_canonical_fingerprint_value(value) for value in row],
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ).encode()
                        )
            return digest.hexdigest()
        finally:
            connection.close()

    def compact_adjacent_files(
        self,
        *,
        max_compacted_files: int,
        target_file_size_bytes: int,
        min_file_size_bytes: int | None = None,
        max_file_size_bytes: int | None = None,
    ) -> DuckLakeCompactionResult:
        """Merge active adjacent Parquet files without expiring snapshots or deleting files.

        Each DuckLake table is compacted in a separate provider call and connection.
        This deliberately releases the local catalog lease between tables so writer
        availability and native-memory working sets are not coupled to a whole-catalog
        compaction. The operation is therefore not cross-table atomic; each completed
        DuckLake call remains a valid snapshot and a retry safely continues remaining
        eligible files.

        max_compacted_files follows DuckLake's provider contract: it limits the
        number of compaction output operations produced per table, not the number
        of input files merged into one output. target_file_size_bytes is an explicit,
        persistent physical-layout policy for future writes/compactions, not a
        retention policy. Resource bounds are established by measured scale tests.
        """
        _validate_positive_int(max_compacted_files, "max_compacted_files")
        _validate_positive_int(target_file_size_bytes, "target_file_size_bytes")
        _validate_optional_positive_int(min_file_size_bytes, "min_file_size_bytes")
        _validate_optional_positive_int(max_file_size_bytes, "max_file_size_bytes")
        if (
            min_file_size_bytes is not None
            and max_file_size_bytes is not None
            and min_file_size_bytes >= max_file_size_bytes
        ):
            raise ValueError("min_file_size_bytes must be less than max_file_size_bytes")

        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            connection.execute(
                f"CALL {_CATALOG_NAME}.set_option('target_file_size', "
                + _quote_sql_literal(f"{target_file_size_bytes}B")
                + ")"
            )
            storage_before = self._inspect_storage_with_connection(connection)
            snapshot_before = storage_before.current_snapshot_id
        finally:
            connection.close()

        options = [f"max_compacted_files => {max_compacted_files}"]
        if min_file_size_bytes is not None:
            options.append(f"min_file_size => {min_file_size_bytes}")
        if max_file_size_bytes is not None:
            options.append(f"max_file_size => {max_file_size_bytes}")

        rows: list[tuple[object, object, object, object]] = []
        started = time.perf_counter()
        for schema, table in _HISTORY_DATA_TABLES:
            connection = self._connect()
            try:
                self._ensure_initialized(connection)
                table_rows = connection.execute(
                    f"CALL ducklake_merge_adjacent_files('{_CATALOG_NAME}', "
                    + _quote_sql_literal(table)
                    + ", schema => "
                    + _quote_sql_literal(schema)
                    + ", "
                    + ", ".join(options)
                    + ")"
                ).fetchall()
                rows.extend(table_rows)
            finally:
                connection.close()
        duration_seconds = time.perf_counter() - started
        storage_after = self.inspect_storage()

        tables = tuple(
            DuckLakeCompactedTable(
                schema_name=_require_str(schema, "schema_name"),
                table_name=_require_str(table, "table_name"),
                files_processed=_require_int(files_processed, "files_processed"),
                files_created=_require_int(files_created, "files_created"),
            )
            for schema, table, files_processed, files_created in rows
        )
        return DuckLakeCompactionResult(
            snapshot_before=snapshot_before,
            snapshot_after=storage_after.current_snapshot_id,
            duration_seconds=duration_seconds,
            target_file_size_bytes=target_file_size_bytes,
            tables=tables,
            storage_before=storage_before,
            storage_after=storage_after,
        )

    def _inspect_storage_with_connection(self, connection: Any) -> DuckLakeStorageInspection:
        snapshot_row = connection.execute(
            f"SELECT count(*), max(snapshot_id) FROM {_CATALOG_NAME}.snapshots()"
        ).fetchone()
        if snapshot_row is None:
            raise RuntimeError("DuckLake snapshot metadata is unavailable")
        snapshot_count = _require_int(snapshot_row[0], "snapshot_count")
        current_snapshot_id = (
            0 if snapshot_row[1] is None else _require_int(snapshot_row[1], "current_snapshot_id")
        )

        active_sizes: list[int] = []
        for schema, table in _HISTORY_DATA_TABLES:
            rows = connection.execute(
                f"SELECT data_file_size_bytes FROM ducklake_list_files("
                f"'{_CATALOG_NAME}', '{table}', schema => '{schema}')"
            ).fetchall()
            active_sizes.extend(
                _require_int(row[0], "data_file_size_bytes") for row in rows if row[0] is not None
            )
        active_sizes.sort()
        active_count = len(active_sizes)
        active_bytes = sum(active_sizes)
        minimum: int | None
        median: int | None
        maximum: int | None
        if active_sizes:
            minimum = active_sizes[0]
            median = active_sizes[(active_count - 1) // 2]
            maximum = active_sizes[-1]
        else:
            minimum = median = maximum = None

        catalog_path = self._config.catalog_path.expanduser().resolve(strict=False)
        scheduled_row = connection.execute(
            "SELECT count(*) FROM sqlite_scan("
            + _quote_sql_literal(str(catalog_path))
            + ", 'ducklake_files_scheduled_for_deletion')"
        ).fetchone()
        if scheduled_row is None:
            raise RuntimeError("DuckLake scheduled-deletion metadata is unavailable")
        scheduled = _require_int(scheduled_row[0], "scheduled_for_deletion_count")

        data_path = self._config.data_path.expanduser().resolve(strict=False)
        physical_files = tuple(data_path.rglob("*.parquet"))
        return DuckLakeStorageInspection(
            snapshot_count=snapshot_count,
            current_snapshot_id=current_snapshot_id,
            active_data_file_count=active_count,
            active_data_file_bytes=active_bytes,
            active_file_size_min_bytes=minimum,
            active_file_size_median_bytes=median,
            active_file_size_max_bytes=maximum,
            scheduled_for_deletion_count=scheduled,
            physical_parquet_file_count=len(physical_files),
            physical_parquet_bytes=sum(path.stat().st_size for path in physical_files),
            catalog_bytes=catalog_path.stat().st_size if catalog_path.is_file() else 0,
        )

    def flush_inlined_data(self) -> DuckLakeInlinedDataFlush:
        """Move rows DuckLake inlined into the SQLite catalog to Parquet.

        Every append is otherwise kept as catalog rows (about 2.4 KB per AI-Hub
        observation measured), which does not scale to full archives. The flush
        holds the same local catalog lease as writers and readers.
        """
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            rows = connection.execute(
                f"CALL ducklake_flush_inlined_data('{_CATALOG_NAME}')"
            ).fetchall()
            snapshot = connection.execute(
                f"SELECT max(snapshot_id) FROM {_CATALOG_NAME}.snapshots()"
            ).fetchone()
        finally:
            connection.close()
        flushed = tuple(
            sorted(
                (
                    f"{_require_str(schema, 'schema')}.{_require_str(table, 'table')}",
                    _require_int(count, "flushed_rows"),
                )
                for schema, table, count in rows
            )
        )
        if snapshot is None or snapshot[0] is None:
            raise RuntimeError("DuckLake did not report a snapshot after flush")
        return DuckLakeInlinedDataFlush(_require_int(snapshot[0], "snapshot_id"), flushed)

    def query_opcua_events(
        self,
        source_id: str,
    ) -> tuple[OpcUaPersistentDataChangeEvent, ...]:
        """Return one source's raw events in deterministic durable-ingestion order."""
        _validate_identifier(source_id, "source_id")
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            rows = connection.execute(
                f"""
                SELECT
                    source_id,
                    asset_id,
                    endpoint_url,
                    measurement_point_id,
                    channel_id,
                    node_id,
                    value,
                    status_code,
                    status_good,
                    status_text,
                    variant_type,
                    source_timestamp,
                    server_timestamp,
                    received_at,
                    ingested_at,
                    event_at,
                    event_time_basis,
                    collection_index,
                    connection_epoch,
                    event_index,
                    replayed,
                    semantic_binding_json
                FROM {_CATALOG_NAME}.raw.opcua_data_change
                WHERE source_id = ?
                ORDER BY ingested_at, connection_epoch, event_index, raw_evidence_id
                """,
                [source_id],
            ).fetchall()
        finally:
            connection.close()

        return tuple(_opcua_event_from_row(row) for row in rows)

    def query_opcua_events_after(
        self,
        source_id: str,
        *,
        cursor: OpcUaHistoricalEventCursor | None,
        limit: int,
    ) -> tuple[OpcUaPersistentDataChangeEvent, ...]:
        """Return the first bounded page or one page after a durable cursor."""
        _validate_identifier(source_id, "source_id")
        if cursor is not None and not isinstance(cursor, OpcUaHistoricalEventCursor):
            raise ValueError("cursor must be OpcUaHistoricalEventCursor when provided")
        _validate_positive_int(limit, "limit")
        if limit > 10000:
            raise ValueError("limit must not exceed 10000")
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            if cursor is None:
                rows = connection.execute(
                    f"""
                    SELECT
                        source_id, asset_id, endpoint_url, measurement_point_id,
                        channel_id, node_id, value, status_code, status_good,
                        status_text, variant_type, source_timestamp, server_timestamp,
                        received_at, ingested_at, event_at, event_time_basis,
                        collection_index, connection_epoch, event_index, replayed,
                        semantic_binding_json
                    FROM {_CATALOG_NAME}.raw.opcua_data_change
                    WHERE source_id = ?
                    ORDER BY ingested_at, connection_epoch, event_index, raw_evidence_id
                    LIMIT ?
                    """,
                    [source_id, limit],
                ).fetchall()
            else:
                rows = connection.execute(
                    f"""
                    SELECT
                        source_id,
                        asset_id,
                        endpoint_url,
                        measurement_point_id,
                        channel_id,
                        node_id,
                        value,
                        status_code,
                        status_good,
                        status_text,
                        variant_type,
                        source_timestamp,
                        server_timestamp,
                        received_at,
                        ingested_at,
                        event_at,
                        event_time_basis,
                        collection_index,
                        connection_epoch,
                        event_index,
                        replayed,
                        semantic_binding_json
                    FROM {_CATALOG_NAME}.raw.opcua_data_change
                    WHERE source_id = ?
                      AND (
                            ingested_at > ?
                         OR (ingested_at = ? AND connection_epoch > ?)
                         OR (
                                ingested_at = ?
                            AND connection_epoch = ?
                            AND event_index > ?
                         )
                      )
                    ORDER BY ingested_at, connection_epoch, event_index, raw_evidence_id
                    LIMIT ?
                    """,
                    [
                        source_id,
                        cursor.ingested_at,
                        cursor.ingested_at,
                        cursor.connection_epoch,
                        cursor.ingested_at,
                        cursor.connection_epoch,
                        cursor.event_index,
                        limit,
                    ],
                ).fetchall()
        finally:
            connection.close()
        return tuple(_opcua_event_from_row(row) for row in rows)

    def query_opcua_events_from_event_time(
        self,
        source_id: str,
        *,
        start_at: datetime | None,
    ) -> tuple[OpcUaPersistentDataChangeEvent, ...]:
        """Return a restart tail ordered by durable ingestion.

        When start_at is provided, timing-unavailable events are excluded because
        they cannot belong to an event-time window. The continuous cursor will
        still observe future timing-unavailable events after bootstrap.
        """
        _validate_identifier(source_id, "source_id")
        if start_at is not None and (
            not isinstance(start_at, datetime) or start_at.utcoffset() is None
        ):
            raise ValueError("start_at must be timezone-aware when provided")
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            if start_at is None:
                rows = connection.execute(
                    f"""
                    SELECT
                        source_id, asset_id, endpoint_url, measurement_point_id,
                        channel_id, node_id, value, status_code, status_good,
                        status_text, variant_type, source_timestamp, server_timestamp,
                        received_at, ingested_at, event_at, event_time_basis,
                        collection_index, connection_epoch, event_index, replayed,
                        semantic_binding_json
                    FROM {_CATALOG_NAME}.raw.opcua_data_change
                    WHERE source_id = ?
                    ORDER BY ingested_at, connection_epoch, event_index, raw_evidence_id
                    """,
                    [source_id],
                ).fetchall()
            else:
                rows = connection.execute(
                    f"""
                    SELECT
                        source_id, asset_id, endpoint_url, measurement_point_id,
                        channel_id, node_id, value, status_code, status_good,
                        status_text, variant_type, source_timestamp, server_timestamp,
                        received_at, ingested_at, event_at, event_time_basis,
                        collection_index, connection_epoch, event_index, replayed,
                        semantic_binding_json
                    FROM {_CATALOG_NAME}.raw.opcua_data_change
                    WHERE source_id = ?
                      AND event_at IS NOT NULL
                      AND event_at >= ?
                    ORDER BY ingested_at, connection_epoch, event_index, raw_evidence_id
                    """,
                    [source_id, start_at],
                ).fetchall()
        finally:
            connection.close()
        return tuple(_opcua_event_from_row(row) for row in rows)

    def get_opcua_event(
        self,
        source_id: str,
        *,
        connection_epoch: int,
        event_index: int,
    ) -> OpcUaPersistentDataChangeEvent | None:
        """Restore one raw OPC UA delivery by its application-local identity."""
        _validate_identifier(source_id, "source_id")
        _validate_positive_int(connection_epoch, "connection_epoch")
        _validate_non_negative_int(event_index, "event_index")
        raw_evidence_id = _raw_evidence_id_from_identity(
            source_id,
            connection_epoch,
            event_index,
        )

        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            row = connection.execute(
                f"""
                SELECT
                    source_id,
                    asset_id,
                    endpoint_url,
                    measurement_point_id,
                    channel_id,
                    node_id,
                    value,
                    status_code,
                    status_good,
                    status_text,
                    variant_type,
                    source_timestamp,
                    server_timestamp,
                    received_at,
                    ingested_at,
                    event_at,
                    event_time_basis,
                    collection_index,
                    connection_epoch,
                    event_index,
                    replayed,
                    semantic_binding_json
                FROM {_CATALOG_NAME}.raw.opcua_data_change
                WHERE raw_evidence_id = ?
                """,
                [raw_evidence_id],
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            return None
        return _opcua_event_from_row(row)

    def query_measurements(
        self,
        asset_id: str,
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> tuple[HistoricalMeasurement, ...]:
        """Return normalized measurements in event-time order for one asset."""
        validate_asset_history_query(
            asset_id,
            start_at=start_at,
            end_at=end_at,
        )
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            rows = connection.execute(
                f"""
                SELECT
                    raw_evidence_id,
                    source_id,
                    source_type,
                    asset_id,
                    measurement_point_id,
                    channel_id,
                    event_time_basis,
                    event_at,
                    value,
                    status_good,
                    ingestion_mode
                FROM {_CATALOG_NAME}.history.measurement
                WHERE asset_id = ?
                  AND event_at IS NOT NULL
                  AND event_at >= ?
                  AND event_at < ?
                ORDER BY event_at, raw_evidence_id
                """,
                [asset_id, start_at, end_at],
            ).fetchall()
        finally:
            connection.close()

        return tuple(_historical_measurement_from_row(row) for row in rows)

    def list_history_assets(self, *, limit: int = 1000) -> tuple[HistoryAssetSummary, ...]:
        """Discover a bounded asset population that actually has addressable history."""
        _validate_positive_int(limit, "limit")
        if limit > 1000:
            raise ValueError("asset discovery limit must not exceed 1000")
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            rows = connection.execute(
                f"""
                SELECT asset_id, min(event_at), max(event_at), count(*)
                FROM {_CATALOG_NAME}.history.measurement
                WHERE event_at IS NOT NULL GROUP BY asset_id ORDER BY asset_id LIMIT ?
            """,
                [limit + 1],
            ).fetchall()
        finally:
            connection.close()
        if len(rows) > limit:
            raise ValueError("history asset discovery exceeds limit; use a narrower catalog")
        return tuple(
            HistoryAssetSummary(
                _require_str(r[0], "asset_id"),
                _require_datetime(r[1], "start_at"),
                _require_datetime(r[2], "end_at"),
                _require_int(r[3], "measurement_count"),
            )
            for r in rows
        )

    def list_history_channels(self, asset_id: str) -> tuple[str, ...]:
        _validate_identifier(asset_id, "asset_id")
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            rows = connection.execute(
                f"""
                SELECT DISTINCT channel_id FROM {_CATALOG_NAME}.history.measurement
                WHERE asset_id = ? ORDER BY channel_id LIMIT 1001
            """,
                [asset_id],
            ).fetchall()
        finally:
            connection.close()
        if len(rows) > 1000:
            raise ValueError("history channel discovery exceeds 1000 channels")
        return tuple(_require_str(row[0], "channel_id") for row in rows)

    def list_history_sources(self, asset_id: str) -> tuple[str, ...]:
        """Sources that recorded history for one asset, for explicit analysis selection."""
        _validate_identifier(asset_id, "asset_id")
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            rows = connection.execute(
                f"""
                SELECT DISTINCT source_id FROM {_CATALOG_NAME}.history.measurement
                WHERE asset_id = ? ORDER BY source_id LIMIT 1001
            """,
                [asset_id],
            ).fetchall()
        finally:
            connection.close()
        if len(rows) > 1000:
            raise ValueError("history source discovery exceeds 1000 sources")
        return tuple(_require_str(row[0], "source_id") for row in rows)

    def query_measurement_page(
        self,
        asset_id: str,
        *,
        start_at: datetime,
        end_at: datetime,
        channel_id: str,
        point_budget: int = 2000,
        latest: bool = False,
    ) -> MeasurementHistoryPage:
        """Bounded raw points, with conflicts assessed before the response is limited.

        No interpolation, alignment, aggregation or cross-source deduplication.
        A conflict is multiple values (including null) for one source/point/channel/time.
        """
        validate_asset_history_query(asset_id, start_at=start_at, end_at=end_at)
        _validate_identifier(channel_id, "channel_id")
        _validate_positive_int(point_budget, "point_budget")
        if point_budget > 10000:
            raise ValueError("point_budget must not exceed 10000")
        if not isinstance(latest, bool):
            raise ValueError("latest must be boolean")
        direction = "DESC" if latest else "ASC"
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            rows = connection.execute(
                f"""
                WITH raw_file AS (
                    -- FILE raw rows share the measurement asset/channel/time. Filter
                    -- before the outer join so it never builds on the whole raw table;
                    -- equality-only join keys keep it a hash join.
                    SELECT raw_evidence_id, 'file' AS source_type, source_metadata_json,
                        source_file, source_sha256
                    FROM {_CATALOG_NAME}.raw.file_measurement
                    WHERE asset_id = ? AND channel_id = ?
                        AND source_timestamp >= ? AND source_timestamp < ?
                    UNION ALL
                    {_opcua_display_metadata_sql(ranged=True)}
                ), selected AS (
                    SELECT *,
                        count(DISTINCT value) OVER identity_window
                        + max(CASE WHEN value IS NULL THEN 1 ELSE 0 END) OVER identity_window
                        > 1 AS conflict
                    FROM {_CATALOG_NAME}.history.measurement
                    WHERE asset_id = ? AND channel_id = ? AND event_at >= ? AND event_at < ?
                    WINDOW identity_window AS (
                        PARTITION BY source_id, measurement_point_id, channel_id, event_at
                    )
                ), bounded AS (
                    SELECT * FROM selected ORDER BY event_at {direction}, raw_evidence_id LIMIT ?
                )
                SELECT m.raw_evidence_id, m.source_id, m.source_type, m.asset_id,
                    m.measurement_point_id, m.channel_id, m.event_time_basis, m.event_at,
                    m.value, m.status_good, m.ingestion_mode, m.conflict, f.source_metadata_json,
                    f.source_file, f.source_sha256
                FROM bounded m LEFT JOIN raw_file f
                    ON m.raw_evidence_id = f.raw_evidence_id AND m.source_type = f.source_type
                ORDER BY m.event_at {direction}, m.raw_evidence_id
            """,
                [*(asset_id, channel_id, start_at, end_at) * 3, point_budget + 1],
            ).fetchall()
        finally:
            connection.close()
        return MeasurementHistoryPage(
            points=tuple(
                MeasurementHistoryPoint(
                    _historical_measurement_from_row(row[:11]),
                    _require_bool(row[11], "conflict"),
                    _optional_str(row[12], "source_metadata_json"),
                    _optional_str(row[13], "source_file"),
                    _optional_str(row[14], "source_sha256"),
                )
                for row in sorted(rows[:point_budget], key=lambda row: (row[7], row[0]))
            ),
            truncated=len(rows) > point_budget,
            point_budget=point_budget,
        )

    def query_measurement_aggregation(
        self,
        asset_id: str,
        *,
        channel_id: str,
        start_at: datetime,
        end_at: datetime,
        bucket_count: int = 200,
    ) -> MeasurementHistoryAggregation:
        """Bounded presentation over the whole interval, with no source/meaning mixing.

        Null, protocol non-good and conflicting groups are counted but excluded
        from min/max/mean. Duplicate equal values remain observations. The mean
        is observation-weighted, never time-weighted or an energy estimate.
        """
        validate_asset_history_query(asset_id, start_at=start_at, end_at=end_at)
        _validate_identifier(channel_id, "channel_id")
        _validate_positive_int(bucket_count, "bucket_count")
        if bucket_count > 1000:
            raise ValueError("bucket_count must not exceed 1000")
        width = (end_at - start_at).total_seconds() / bucket_count
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            rows = connection.execute(
                f"""
                WITH raw_file AS (
                    -- FILE raw rows share the measurement asset/channel/time. Filter
                    -- before the outer join so it never builds on the whole raw table;
                    -- equality-only join keys keep it a hash join.
                    SELECT raw_evidence_id, 'file' AS source_type, source_metadata_json,
                        source_file, source_sha256
                    FROM {_CATALOG_NAME}.raw.file_measurement
                    WHERE asset_id = ? AND channel_id = ?
                        AND source_timestamp >= ? AND source_timestamp < ?
                    UNION ALL
                    {_opcua_display_metadata_sql(ranged=True)}
                ), selected AS (
                    SELECT *, count(DISTINCT value) OVER observation
                        + max(CASE WHEN value IS NULL THEN 1 ELSE 0 END)
                            OVER observation > 1 AS conflict
                    FROM {_CATALOG_NAME}.history.measurement
                    WHERE asset_id = ? AND channel_id = ? AND event_at >= ? AND event_at < ?
                    WINDOW observation AS (PARTITION BY source_id, measurement_point_id, event_at)
                ), prepared AS (
                    SELECT m.*, least(floor(epoch(m.event_at - ?) / ?)::BIGINT, ?) AS bucket_index,
                        json_object(
                            'binding', json_extract(f.source_metadata_json, '$.binding'),
                            'semantics', json_extract(f.source_metadata_json, '$.semantics')
                        )::VARCHAR AS interpretation,
                        m.source_type != 'file' AND NOT m.status_good AS non_good,
                        m.value IS NOT NULL AND NOT m.conflict
                            AND (m.source_type = 'file' OR m.status_good) AS usable
                    FROM selected m LEFT JOIN raw_file f
                        ON m.raw_evidence_id = f.raw_evidence_id AND m.source_type = f.source_type
                )
                SELECT source_id, source_type, measurement_point_id, bucket_index,
                    min(event_at), max(event_at), count(*), count(*) FILTER (WHERE usable),
                    count(*) FILTER (WHERE value IS NULL), count(*) FILTER (WHERE non_good),
                    count(*) FILTER (WHERE conflict), min(value) FILTER (WHERE usable),
                    max(value) FILTER (WHERE usable), avg(value) FILTER (WHERE usable),
                    interpretation
                FROM prepared
                GROUP BY source_id, source_type, measurement_point_id, bucket_index, interpretation
                ORDER BY bucket_index, source_id, measurement_point_id, interpretation LIMIT 2001
                """,
                [
                    *(asset_id, channel_id, start_at, end_at) * 3,
                    start_at,
                    width,
                    bucket_count - 1,
                ],
            ).fetchall()
            snapshot = connection.execute(
                f"SELECT max(snapshot_id) FROM ducklake_snapshots('{_CATALOG_NAME}')"
            ).fetchone()
        finally:
            connection.close()
        if len(rows) > 2000:
            raise ValueError(
                "aggregate exceeds 2000 source/point/interpretation buckets; narrow range"
            )
        return MeasurementHistoryAggregation(
            start_at,
            end_at,
            width,
            int(snapshot[0]),
            tuple(
                MeasurementHistoryBucket(
                    _require_str(r[0], "source_id"),
                    _require_str(r[1], "source_type"),
                    _optional_str(r[2], "measurement_point_id"),
                    start_at + timedelta(seconds=int(r[3]) * width),
                    min(end_at, start_at + timedelta(seconds=(int(r[3]) + 1) * width)),
                    _require_datetime(r[4], "first_event_at"),
                    _require_datetime(r[5], "last_event_at"),
                    int(r[6]),
                    int(r[7]),
                    int(r[8]),
                    int(r[9]),
                    int(r[10]),
                    _optional_float(r[11], "minimum"),
                    _optional_float(r[12], "maximum"),
                    _optional_float(r[13], "mean"),
                    _require_str(r[14], "interpretation"),
                )
                for r in rows
            ),
        )

    def list_channel_semantics(
        self,
        asset_id: str,
        *,
        source_id: str,
        start_at: datetime,
        end_at: datetime,
        snapshot_id: int,
    ) -> tuple[ChannelSemanticCandidate, ...]:
        """Interpretations bound to a source's channels in one range at one snapshot.

        Only identity-verified bindings with an observed property are returned; the
        same rules as query_channel_observations decide what counts as bound.
        """
        validate_asset_history_query(asset_id, start_at=start_at, end_at=end_at)
        _validate_identifier(source_id, "source_id")
        snapshot = _require_int(snapshot_id, "snapshot_id")
        at = f"AT (VERSION => {snapshot})"
        filters = [asset_id, source_id, start_at, end_at]
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            semantic = _snapshot_semantic_column(connection, at)
            rows = connection.execute(
                f"""
                WITH m AS (
                    SELECT raw_evidence_id, source_type, measurement_point_id, channel_id
                    FROM {_CATALOG_NAME}.history.measurement {at}
                    WHERE asset_id = ? AND source_id = ? AND event_at >= ? AND event_at < ?
                ), {_semantic_ctes(at, semantic, channel_filter=False)}
                SELECT m.measurement_point_id, m.channel_id, f.prop, f.scope, f.unit, f.ver,
                    count(*)
                FROM m JOIN f
                    ON m.raw_evidence_id = f.raw_evidence_id AND m.source_type = f.source_type
                WHERE f.prop IS NOT NULL AND f.ver IS NOT NULL
                GROUP BY ALL
                ORDER BY m.measurement_point_id, m.channel_id, f.ver, f.prop
                LIMIT 10001
                """,
                [*filters, *filters, *filters],
            ).fetchall()
        finally:
            connection.close()
        if len(rows) > 10000:
            raise ValueError("channel semantic discovery exceeds 10000 interpretations")
        return tuple(
            ChannelSemanticCandidate(
                measurement_point_id=_optional_str(point, "measurement_point_id"),
                channel_id=_require_str(channel, "channel_id"),
                observed_property=_require_str(prop, "observed_property"),
                scope=_optional_str(scope, "scope"),
                unit=_optional_str(unit, "unit"),
                semantic_version=_require_str(ver, "semantic_version"),
                observation_count=_require_int(count, "observation_count"),
            )
            for point, channel, prop, scope, unit, ver, count in rows
        )

    def query_channel_observations(
        self,
        asset_id: str,
        *,
        source_id: str,
        channel_ids: Sequence[str],
        start_at: datetime,
        end_at: datetime,
        snapshot_id: int,
        max_rows: int = 2_000_000,
    ) -> tuple[ChannelObservation, ...]:
        """Per (point, channel, event time) values and bound semantics at one snapshot.

        Reading at a recorded snapshot makes analysis input reproducible after more
        history is appended. Conflicting values are flagged, never averaged; a group
        whose rows disagree on interpretation carries no semantics.
        """
        validate_asset_history_query(asset_id, start_at=start_at, end_at=end_at)
        _validate_identifier(source_id, "source_id")
        channels = list(channel_ids)
        if not channels:
            raise ValueError("channel_ids must not be empty")
        for channel_id in channels:
            _validate_identifier(channel_id, "channel_id")
        snapshot = _require_int(snapshot_id, "snapshot_id")
        _validate_positive_int(max_rows, "max_rows")
        at = f"AT (VERSION => {snapshot})"
        filters = [asset_id, source_id, channels, start_at, end_at]
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            semantic = _snapshot_semantic_column(connection, at)
            with _cache_absent_pandas_import():
                rows = connection.execute(
                    f"""
                    WITH m AS (
                        SELECT raw_evidence_id, source_type, measurement_point_id, channel_id,
                            event_at, value, status_good
                        FROM {_CATALOG_NAME}.history.measurement {at}
                        WHERE asset_id = ? AND source_id = ?
                            AND channel_id IN (SELECT unnest(?::VARCHAR[]))
                            AND event_at >= ? AND event_at < ?
                    ), {_semantic_ctes(at, semantic, channel_filter=True)}, joined AS (
                        SELECT m.*, f.ver, f.prop, f.scope, f.unit,
                            concat_ws('|', f.ver, f.prop, f.scope, f.unit) AS interpretation
                        FROM m LEFT JOIN f
                            ON m.raw_evidence_id = f.raw_evidence_id
                            AND m.source_type = f.source_type
                    )
                    SELECT measurement_point_id, channel_id, event_at, min(value),
                        count(DISTINCT value) + max(CASE WHEN value IS NULL THEN 1 ELSE 0 END) > 1,
                        bool_and(source_type = 'file' OR status_good),
                        count(DISTINCT interpretation) = 1 AND count(interpretation) = count(*),
                        min(prop), min(scope), min(unit), min(ver)
                    FROM joined
                    GROUP BY measurement_point_id, channel_id, event_at
                    ORDER BY event_at, measurement_point_id, channel_id
                    LIMIT ?
                    """,
                    [*filters, *filters, *filters, max_rows + 1],
                ).fetchall()
        finally:
            connection.close()
        if len(rows) > max_rows:
            raise ValueError(f"analysis input exceeds {max_rows} observation groups; narrow range")
        result = []
        for point, channel, event_at, value, conflict, good, agreed, prop, scope, unit, ver in rows:
            interpreted = bool(agreed)
            result.append(
                ChannelObservation(
                    source_id=source_id,
                    measurement_point_id=_optional_str(point, "measurement_point_id"),
                    channel_id=_require_str(channel, "channel_id"),
                    # UTC keeps persisted evidence independent of the reader's zone.
                    event_at=_require_datetime(event_at, "event_at").astimezone(UTC),
                    value=_optional_float(value, "value"),
                    conflicting=bool(conflict),
                    source_quality_good=bool(good),
                    observed_property=_optional_str(prop, "prop") if interpreted else None,
                    scope=_optional_str(scope, "scope") if interpreted else None,
                    unit=_optional_str(unit, "unit") if interpreted else None,
                    semantic_version=_optional_str(ver, "version") if interpreted else None,
                )
            )
        return tuple(result)

    def query_latest_asset_measurements(
        self,
        asset_id: str,
        *,
        limit: int = 1000,
    ) -> tuple[MeasurementHistoryPoint, ...]:
        """Latest stored event per source/point/channel for one asset in one bounded read.

        This is the Monitor overview read path. It deliberately avoids issuing one
        latest query per channel; exact raw metadata is joined only for the bounded
        latest rows selected from history.
        """
        _validate_identifier(asset_id, "asset_id")
        _validate_positive_int(limit, "limit")
        if limit > 1000:
            raise ValueError("latest asset measurement limit must not exceed 1000")
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            rows = connection.execute(
                f"""
                WITH ranked AS (
                    SELECT *, row_number() OVER (
                        PARTITION BY source_id, measurement_point_id, channel_id
                        ORDER BY event_at DESC, raw_evidence_id
                    ) observation_rank,
                    count(DISTINCT value) OVER observation
                    + max(CASE WHEN value IS NULL THEN 1 ELSE 0 END)
                        OVER observation > 1 AS has_conflict
                    FROM {_CATALOG_NAME}.history.measurement
                    WHERE asset_id = ? AND event_at IS NOT NULL
                    WINDOW observation AS (
                        PARTITION BY source_id, measurement_point_id, channel_id, event_at
                    )
                ), latest AS (
                    SELECT * FROM ranked
                    WHERE observation_rank = 1
                    ORDER BY channel_id, source_id, measurement_point_id
                    LIMIT ?
                ), raw_metadata AS (
                    SELECT f.raw_evidence_id, 'file' AS source_type, f.source_metadata_json,
                        f.source_file, f.source_sha256
                    FROM {_CATALOG_NAME}.raw.file_measurement f
                    INNER JOIN latest l
                        ON f.raw_evidence_id = l.raw_evidence_id AND l.source_type = 'file'
                    UNION ALL
                    SELECT o.raw_evidence_id, 'opcua' AS source_type,
                        CASE WHEN json_extract_string(o.semantic_binding_json, '$.source_id')
                                = o.source_id
                            AND json_extract_string(o.semantic_binding_json, '$.channel_id')
                                = o.channel_id
                        THEN json_object(
                            'schema', 'opcua-semantic-snapshot',
                            'semantics', json(o.semantic_binding_json)
                        )::VARCHAR END AS source_metadata_json,
                        NULL::VARCHAR AS source_file, NULL::VARCHAR AS source_sha256
                    FROM {_CATALOG_NAME}.raw.opcua_data_change o
                    INNER JOIN latest l
                        ON o.raw_evidence_id = l.raw_evidence_id AND l.source_type = 'opcua'
                )
                SELECT m.raw_evidence_id, m.source_id, m.source_type, m.asset_id,
                    m.measurement_point_id, m.channel_id, m.event_time_basis, m.event_at,
                    m.value, m.status_good, m.ingestion_mode, m.has_conflict,
                    f.source_metadata_json, f.source_file, f.source_sha256
                FROM latest m LEFT JOIN raw_metadata f
                    ON m.raw_evidence_id = f.raw_evidence_id AND m.source_type = f.source_type
                ORDER BY m.channel_id, m.source_id, m.measurement_point_id
                """,
                [asset_id, limit + 1],
            ).fetchall()
        finally:
            connection.close()
        if len(rows) > limit:
            raise ValueError(
                "latest asset measurement population exceeds limit; narrow the monitored asset"
            )
        return tuple(
            MeasurementHistoryPoint(
                _historical_measurement_from_row(row[:11]),
                _require_bool(row[11], "conflict"),
                _optional_str(row[12], "source_metadata_json"),
                _optional_str(row[13], "source_file"),
                _optional_str(row[14], "source_sha256"),
            )
            for row in rows
        )

    def query_latest_measurements(
        self,
        asset_id: str,
        *,
        channel_id: str,
    ) -> tuple[MeasurementHistoryPoint, ...]:
        """Latest stored event per source/measurement point, independent of chart limits.

        Conflicting values at that time remain explicitly marked; the deterministic
        representative row must not be presented as a resolved latest value.
        """
        _validate_identifier(asset_id, "asset_id")
        _validate_identifier(channel_id, "channel_id")
        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            rows = connection.execute(
                f"""
                WITH raw_file AS (
                    SELECT raw_evidence_id, 'file' AS source_type, source_metadata_json,
                        source_file, source_sha256
                    FROM {_CATALOG_NAME}.raw.file_measurement
                    WHERE asset_id = ? AND channel_id = ?
                    UNION ALL
                    {_opcua_display_metadata_sql(ranged=False)}
                ), ranked AS (
                    SELECT *, row_number() OVER (
                        PARTITION BY source_id, measurement_point_id
                        ORDER BY event_at DESC, raw_evidence_id
                    ) observation_rank,
                    count(DISTINCT value) OVER observation
                    + max(CASE WHEN value IS NULL THEN 1 ELSE 0 END)
                        OVER observation > 1 AS has_conflict
                    FROM {_CATALOG_NAME}.history.measurement
                    WHERE asset_id = ? AND channel_id = ? AND event_at IS NOT NULL
                    WINDOW observation AS (PARTITION BY source_id, measurement_point_id, event_at)
                )
                SELECT m.raw_evidence_id, m.source_id, m.source_type, m.asset_id,
                    m.measurement_point_id, m.channel_id, m.event_time_basis, m.event_at,
                    m.value, m.status_good, m.ingestion_mode, m.has_conflict,
                    f.source_metadata_json, f.source_file, f.source_sha256
                FROM ranked m LEFT JOIN raw_file f
                    ON m.raw_evidence_id = f.raw_evidence_id AND m.source_type = f.source_type
                WHERE m.observation_rank = 1
                ORDER BY m.source_id, m.measurement_point_id LIMIT 1001
            """,
                [asset_id, channel_id, asset_id, channel_id, asset_id, channel_id],
            ).fetchall()
        finally:
            connection.close()
        if len(rows) > 1000:
            raise ValueError("latest measurement population exceeds 1000 source/point groups")
        return tuple(
            MeasurementHistoryPoint(
                _historical_measurement_from_row(row[:11]),
                _require_bool(row[11], "conflict"),
                _optional_str(row[12], "source_metadata_json"),
                _optional_str(row[13], "source_file"),
                _optional_str(row[14], "source_sha256"),
            )
            for row in rows
        )

    def _connect(self) -> Any:
        duckdb = _load_duckdb_module()
        catalog_path = self._config.catalog_path.expanduser().resolve(strict=False)
        data_path = self._config.data_path.expanduser().resolve(strict=False)
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.mkdir(parents=True, exist_ok=True)

        try:
            filelock = importlib.import_module("filelock")
        except ModuleNotFoundError as error:
            raise DuckLakeRuntimeUnavailableError("install the complete 'history' extra") from error
        lock = filelock.FileLock(str(catalog_path) + ".phm.lock")
        try:
            lock.acquire(timeout=self._config.catalog_lock_timeout_seconds)
        except filelock.Timeout as error:
            raise TimeoutError(
                f"timed out waiting for local history catalog: {catalog_path}"
            ) from error
        try:
            connection = duckdb.connect()
        except BaseException:
            lock.release()
            raise
        try:
            connection.execute("INSTALL ducklake")
            connection.execute("LOAD ducklake")
            connection.execute("INSTALL sqlite")
            connection.execute("LOAD sqlite")
            connection.execute(
                "ATTACH "
                + _quote_sql_literal(f"ducklake:sqlite:{catalog_path}")
                + f" AS {_CATALOG_NAME} "
                + f"(DATA_PATH {_quote_sql_literal(str(data_path))})"
            )
        except BaseException:
            try:
                connection.close()
            finally:
                lock.release()
            raise
        return _LockedConnection(connection, lock)

    def _ensure_initialized(self, connection: Any) -> None:
        connection.execute(f"CREATE SCHEMA IF NOT EXISTS {_CATALOG_NAME}.raw")
        connection.execute(f"CREATE SCHEMA IF NOT EXISTS {_CATALOG_NAME}.history")
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_CATALOG_NAME}.history.ingestion_batch (
                batch_id VARCHAR NOT NULL,
                ingestion_mode VARCHAR NOT NULL,
                event_count BIGINT NOT NULL
            )
            """
        )
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_CATALOG_NAME}.raw.opcua_data_change (
                raw_evidence_id VARCHAR NOT NULL,
                batch_id VARCHAR NOT NULL,
                ingestion_mode VARCHAR NOT NULL,
                source_id VARCHAR NOT NULL,
                asset_id VARCHAR NOT NULL,
                endpoint_url VARCHAR NOT NULL,
                measurement_point_id VARCHAR,
                channel_id VARCHAR NOT NULL,
                node_id VARCHAR NOT NULL,
                value DOUBLE,
                status_code UBIGINT NOT NULL,
                status_good BOOLEAN NOT NULL,
                status_text VARCHAR NOT NULL,
                variant_type VARCHAR,
                source_timestamp TIMESTAMPTZ,
                server_timestamp TIMESTAMPTZ,
                received_at TIMESTAMPTZ NOT NULL,
                ingested_at TIMESTAMPTZ NOT NULL,
                event_at TIMESTAMPTZ,
                event_time_basis VARCHAR NOT NULL,
                collection_index BIGINT NOT NULL,
                connection_epoch BIGINT NOT NULL,
                event_index BIGINT NOT NULL,
                replayed BOOLEAN NOT NULL,
                semantic_binding_json VARCHAR
            )
            """
        )
        # Catalogs created before semantic snapshots gain a nullable column once;
        # existing rows stay without semantics rather than being reinterpreted.
        opcua_columns = {
            row[0]
            for row in connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_catalog = ? AND table_schema = 'raw' "
                "AND table_name = 'opcua_data_change'",
                [_CATALOG_NAME],
            ).fetchall()
        }
        if "semantic_binding_json" not in opcua_columns:
            connection.execute(
                f"ALTER TABLE {_CATALOG_NAME}.raw.opcua_data_change "
                "ADD COLUMN semantic_binding_json VARCHAR"
            )
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_CATALOG_NAME}.raw.file_measurement (
                raw_evidence_id VARCHAR NOT NULL,
                batch_id VARCHAR NOT NULL,
                ingestion_mode VARCHAR NOT NULL,
                source_id VARCHAR NOT NULL,
                asset_id VARCHAR NOT NULL,
                measurement_point_id VARCHAR,
                source_file VARCHAR NOT NULL,
                source_sha256 VARCHAR NOT NULL,
                source_size_bytes BIGINT NOT NULL,
                sample_index BIGINT NOT NULL,
                channel_id VARCHAR NOT NULL,
                source_timestamp TIMESTAMPTZ NOT NULL,
                value DOUBLE,
                source_metadata_json VARCHAR
            )
            """
        )
        # Existing v1 catalogs keep their rows and commit fingerprints. Migrate
        # only when necessary; read calls must not create fresh schema snapshots.
        columns = dict(
            connection.execute(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_catalog = ? AND table_schema = 'raw' "
                "AND table_name = 'file_measurement'",
                [_CATALOG_NAME],
            ).fetchall()
        )
        if columns.get("value") == "NO":
            connection.execute(
                f"ALTER TABLE {_CATALOG_NAME}.raw.file_measurement ALTER COLUMN value DROP NOT NULL"
            )
        if "source_metadata_json" not in columns:
            connection.execute(
                f"ALTER TABLE {_CATALOG_NAME}.raw.file_measurement "
                "ADD COLUMN source_metadata_json VARCHAR"
            )
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_CATALOG_NAME}.history.measurement (
                raw_evidence_id VARCHAR NOT NULL,
                batch_id VARCHAR NOT NULL,
                source_id VARCHAR NOT NULL,
                source_type VARCHAR NOT NULL,
                asset_id VARCHAR NOT NULL,
                measurement_point_id VARCHAR,
                channel_id VARCHAR NOT NULL,
                event_at TIMESTAMPTZ,
                event_time_basis VARCHAR NOT NULL,
                value DOUBLE,
                status_good BOOLEAN NOT NULL,
                ingestion_mode VARCHAR NOT NULL
            )
            """
        )

    def _reject_existing_deliveries(
        self,
        connection: Any,
        events: Sequence[OpcUaPersistentDataChangeEvent],
    ) -> None:
        raw_evidence_ids = tuple(_raw_evidence_id(event) for event in events)
        with _cache_absent_pandas_import():
            row = connection.execute(
                f"""
                SELECT raw_evidence_id
                FROM {_CATALOG_NAME}.raw.opcua_data_change
                WHERE raw_evidence_id IN (SELECT unnest(?::VARCHAR[]))
                LIMIT 1
                """,
                [list(raw_evidence_ids)],
            ).fetchone()
        if row is not None:
            existing_id = _require_str(row[0], "raw_evidence_id")
            raise ValueError(f"historical delivery already exists: {existing_id}")

    def _reject_existing_file_evidence(
        self,
        connection: Any,
        events: Sequence[FileBackfillEvent],
    ) -> None:
        # FILE raw identity is a function of (source_id, source_sha256, sample_index,
        # ...): equal raw_evidence_id implies equal values for those three columns (see
        # FileBackfillEvent). Scoping the lookup to them returns the same answer, and
        # their per-file statistics let DuckLake skip unrelated Parquet files. A lookup
        # by the hash ID alone cannot be pruned and costs O(stored rows) per batch.
        groups: dict[tuple[str, str], list[FileBackfillEvent]] = {}
        for event in events:
            groups.setdefault((event.source_id, event.source_sha256), []).append(event)
        for (source_id, source_sha256), group in groups.items():
            sample_indexes = [event.sample_index for event in group]
            with _cache_absent_pandas_import():
                row = connection.execute(
                    f"""
                    SELECT raw_evidence_id
                    FROM {_CATALOG_NAME}.raw.file_measurement
                    WHERE source_id = ?
                      AND source_sha256 = ?
                      AND sample_index BETWEEN ? AND ?
                      AND raw_evidence_id IN (SELECT unnest(?::VARCHAR[]))
                    LIMIT 1
                    """,
                    [
                        source_id,
                        source_sha256,
                        min(sample_indexes),
                        max(sample_indexes),
                        [event.raw_evidence_id for event in group],
                    ],
                ).fetchone()
            if row is not None:
                existing_id = _require_str(row[0], "raw_evidence_id")
                raise ValueError(f"historical FILE evidence already exists: {existing_id}")

    def _last_committed_batch(
        self,
        connection: Any,
        batch_id: str,
        event_count: int,
    ) -> HistoricalBatchCommit:
        snapshot_row = connection.execute(
            f"SELECT id FROM {_CATALOG_NAME}.last_committed_snapshot()"
        ).fetchone()
        if snapshot_row is None or snapshot_row[0] is None:
            raise RuntimeError("DuckLake did not report the committed batch snapshot")
        snapshot_id = _require_int(snapshot_row[0], "snapshot_id")
        committed_at = self._snapshot_time_by_id(connection, snapshot_id)
        self._record_batch_snapshot_index(batch_id, snapshot_id)
        return HistoricalBatchCommit(
            batch_id=batch_id,
            snapshot_id=snapshot_id,
            event_count=event_count,
            committed_at=committed_at,
        )

    def _snapshot_metadata_by_id(
        self,
        connection: Any,
        snapshot_id: int,
    ) -> tuple[datetime, str | None, object]:
        """Read one DuckLake snapshot/provenance row from catalog primary keys."""
        catalog_path = self._config.catalog_path.expanduser().resolve(strict=False)
        snapshot_row = connection.execute(
            "SELECT CAST(snapshot_time AS TIMESTAMPTZ) "
            "FROM sqlite_scan(" + _quote_sql_literal(str(catalog_path)) + ", 'ducklake_snapshot') "
            "WHERE snapshot_id = ?",
            [snapshot_id],
        ).fetchone()
        if snapshot_row is None:
            raise RuntimeError("DuckLake committed snapshot metadata is unavailable")
        change_row = connection.execute(
            "SELECT author, commit_extra_info "
            "FROM sqlite_scan("
            + _quote_sql_literal(str(catalog_path))
            + ", 'ducklake_snapshot_changes') "
            "WHERE snapshot_id = ?",
            [snapshot_id],
        ).fetchone()
        if change_row is None:
            raise RuntimeError("DuckLake committed snapshot provenance is unavailable")
        author = None if change_row[0] is None else _require_str(change_row[0], "author")
        return _require_datetime(snapshot_row[0], "snapshot_time"), author, change_row[1]

    def _snapshot_time_by_id(self, connection: Any, snapshot_id: int) -> datetime:
        """Read one DuckLake snapshot timestamp directly from the SQLite catalog primary key."""
        snapshot_time, _, _ = self._snapshot_metadata_by_id(connection, snapshot_id)
        return snapshot_time

    def _batch_provenance_index_path(self) -> Path:
        catalog_path = self._config.catalog_path.expanduser().resolve(strict=False)
        return catalog_path.with_name(catalog_path.name + ".phm-batch-index.sqlite")

    def _lookup_batch_snapshot_index(self, batch_id: str) -> int | None:
        """Return a derived batch→snapshot accelerator entry when available.

        The sidecar is not evidence. Missing/corrupt entries fall back to DuckLake
        commit provenance and are rebuilt from that source of truth.
        """
        path = self._batch_provenance_index_path()
        if not path.is_file():
            return None
        try:
            connection = sqlite3.connect(path)
            try:
                row = connection.execute(
                    "SELECT snapshot_id FROM batch_provenance_index WHERE batch_id = ?",
                    [batch_id],
                ).fetchone()
            finally:
                connection.close()
        except OSError, sqlite3.Error:
            return None
        if row is None:
            return None
        value = row[0]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return None
        return value

    def _record_batch_snapshot_index(self, batch_id: str, snapshot_id: int) -> None:
        """Best-effort update of the rebuildable batch provenance accelerator."""
        path = self._batch_provenance_index_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path)
            try:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS repository_meta(
                        schema_version INTEGER NOT NULL
                    )
                    """
                )
                row = connection.execute(
                    "SELECT schema_version FROM repository_meta LIMIT 1"
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO repository_meta(schema_version) VALUES (?)",
                        [_BATCH_PROVENANCE_INDEX_SCHEMA],
                    )
                elif row[0] != _BATCH_PROVENANCE_INDEX_SCHEMA:
                    return
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS batch_provenance_index(
                        batch_id TEXT PRIMARY KEY,
                        snapshot_id INTEGER NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO batch_provenance_index(batch_id, snapshot_id)
                    VALUES (?, ?)
                    ON CONFLICT(batch_id) DO UPDATE SET snapshot_id = excluded.snapshot_id
                    """,
                    [batch_id, snapshot_id],
                )
                connection.commit()
            finally:
                connection.close()
        except OSError, sqlite3.Error:
            # This is a derived accelerator only. Durable history/provenance remains
            # in DuckLake and the next recovery can fall back to a source scan.
            return

    def _lookup_existing_batch_commit(
        self,
        connection: Any,
        *,
        batch_id: str,
        ingestion_mode: HistoryIngestionMode,
        event_count: int,
        fingerprint: str,
        fingerprint_version: str | None = None,
        legacy_fingerprint: str | None = None,
    ) -> HistoricalBatchCommit | None:
        batch_rows = connection.execute(
            f"""
            SELECT ingestion_mode, event_count
            FROM {_CATALOG_NAME}.history.ingestion_batch
            WHERE batch_id = ?
            """,
            [batch_id],
        ).fetchall()
        if not batch_rows:
            return None
        if len(batch_rows) != 1:
            raise HistoricalBatchConflictError(
                f"historical batch identity is ambiguous: {batch_id}"
            )

        stored_mode = HistoryIngestionMode(_require_str(batch_rows[0][0], "ingestion_mode"))
        stored_count = _require_int(batch_rows[0][1], "event_count")
        if stored_mode != ingestion_mode or stored_count != event_count:
            raise HistoricalBatchConflictError(
                f"historical batch identity conflicts with stored metadata: {batch_id}"
            )

        def validate_commit_extra(extra_raw: object) -> bool:
            extra = _parse_commit_extra_info(extra_raw)
            if extra is None or extra.get("batch_id") != batch_id:
                return False
            stored_version = extra.get("fingerprint_version")
            if stored_version is None:
                expected = fingerprint if legacy_fingerprint is None else legacy_fingerprint
            elif stored_version == fingerprint_version:
                expected = fingerprint
            else:
                expected = None
            if (
                extra.get("schema") != _COMMIT_EXTRA_SCHEMA
                or extra.get("ingestion_mode") != ingestion_mode.value
                or extra.get("event_count") != event_count
                or expected is None
                or extra.get("fingerprint") != expected
            ):
                raise HistoricalBatchConflictError(
                    f"historical batch identity conflicts with commit provenance: {batch_id}"
                )
            return True

        indexed_snapshot_id = self._lookup_batch_snapshot_index(batch_id)
        if indexed_snapshot_id is not None:
            try:
                snapshot_time, author, extra_raw = self._snapshot_metadata_by_id(
                    connection,
                    indexed_snapshot_id,
                )
            except RuntimeError:
                pass
            else:
                if author == _COMMIT_AUTHOR and validate_commit_extra(extra_raw):
                    return HistoricalBatchCommit(
                        batch_id=batch_id,
                        snapshot_id=indexed_snapshot_id,
                        event_count=event_count,
                        committed_at=snapshot_time,
                    )

        matching_snapshots: list[tuple[int, datetime]] = []
        snapshot_rows = connection.execute(
            f"""
            SELECT snapshot_id, snapshot_time, commit_extra_info
            FROM {_CATALOG_NAME}.snapshots()
            WHERE author = ? AND commit_extra_info IS NOT NULL
            ORDER BY snapshot_id
            """,
            [_COMMIT_AUTHOR],
        ).fetchall()
        for snapshot_id_raw, snapshot_time_raw, extra_raw in snapshot_rows:
            if not validate_commit_extra(extra_raw):
                continue
            snapshot_id = _require_int(snapshot_id_raw, "snapshot_id")
            snapshot_time = _require_datetime(snapshot_time_raw, "snapshot_time")
            matching_snapshots.append((snapshot_id, snapshot_time))

        if len(matching_snapshots) != 1:
            raise HistoricalBatchConflictError(
                f"historical batch commit provenance is unavailable or ambiguous: {batch_id}"
            )
        snapshot_id, committed_at = matching_snapshots[0]
        self._record_batch_snapshot_index(batch_id, snapshot_id)
        return HistoricalBatchCommit(
            batch_id=batch_id,
            snapshot_id=snapshot_id,
            event_count=event_count,
            committed_at=committed_at,
        )


def _validate_opcua_batch_input(
    events: Sequence[OpcUaPersistentDataChangeEvent],
    *,
    batch_id: str,
    ingestion_mode: HistoryIngestionMode,
) -> tuple[OpcUaPersistentDataChangeEvent, ...]:
    _validate_identifier(batch_id, "batch_id")
    if not isinstance(ingestion_mode, HistoryIngestionMode):
        raise ValueError("ingestion_mode must be a HistoryIngestionMode")

    batch = tuple(events)
    if not batch:
        raise ValueError("events must not be empty")
    if not all(isinstance(event, OpcUaPersistentDataChangeEvent) for event in batch):
        raise ValueError("events must contain OpcUaPersistentDataChangeEvent values")
    identities = tuple(event.local_delivery_identity for event in batch)
    if len(set(identities)) != len(identities):
        raise ValueError("events must have distinct local delivery identities")
    return batch


def _validate_file_batch_input(
    events: Sequence[FileBackfillEvent],
    *,
    batch_id: str,
    ingestion_mode: HistoryIngestionMode,
) -> tuple[FileBackfillEvent, ...]:
    _validate_identifier(batch_id, "batch_id")
    if ingestion_mode not in {
        HistoryIngestionMode.BACKFILL,
        HistoryIngestionMode.IMPORT,
    }:
        raise ValueError("FILE historical batches require BACKFILL or IMPORT ingestion mode")
    batch = tuple(events)
    if not batch:
        raise ValueError("events must not be empty")
    if not all(isinstance(event, FileBackfillEvent) for event in batch):
        raise ValueError("events must contain FileBackfillEvent values")
    raw_ids = tuple(event.raw_evidence_id for event in batch)
    if len(set(raw_ids)) != len(raw_ids):
        raise ValueError("FILE events must have distinct raw_evidence_id values")
    return batch


def _file_batch_fingerprint(events: Sequence[FileBackfillEvent]) -> str:
    payload = [
        {
            "raw_evidence_id": event.raw_evidence_id,
            "source_id": event.source_id,
            "asset_id": event.asset_id,
            "measurement_point_id": event.measurement_point_id,
            "source_file": event.source_file,
            "source_sha256": event.source_sha256,
            "source_size_bytes": event.source_size_bytes,
            "sample_index": event.sample_index,
            "channel_id": event.channel_id,
            "event_at": event.event_at.isoformat(),
            "value": event.value,
            **(
                {"source_metadata_json": event.source_metadata_json}
                if event.source_metadata_json is not None
                else {}
            ),
        }
        for event in events
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _batch_commit_extra_info(
    *,
    batch_id: str,
    ingestion_mode: HistoryIngestionMode,
    event_count: int,
    fingerprint: str,
    fingerprint_version: str | None = None,
) -> str:
    return json.dumps(
        {
            "schema": _COMMIT_EXTRA_SCHEMA,
            "batch_id": batch_id,
            "ingestion_mode": ingestion_mode.value,
            "event_count": event_count,
            "fingerprint": fingerprint,
            **({} if fingerprint_version is None else {"fingerprint_version": fingerprint_version}),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_commit_extra_info(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    raw = _require_str(value, "commit_extra_info")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HistoricalBatchConflictError(
            "DuckLake commit_extra_info must contain valid JSON"
        ) from error
    if not isinstance(parsed, dict):
        raise HistoricalBatchConflictError("DuckLake commit_extra_info must contain a JSON object")
    return parsed


def _opcua_batch_fingerprint(
    events: Sequence[OpcUaPersistentDataChangeEvent],
    *,
    include_semantics: bool = True,
) -> str:
    payload: list[dict[str, object]] = []
    for event in events:
        registered = event.event
        observation = registered.notification.observation
        timing = event.event_time
        payload.append(
            {
                "source_id": registered.source_id,
                "asset_id": registered.asset_id,
                "endpoint_url": registered.endpoint_url,
                "measurement_point_id": registered.measurement_point_id,
                "collection_index": registered.collection_index,
                "channel_id": observation.channel_id,
                "node_id": observation.node_id,
                "value": observation.value,
                "status_code": observation.status_code,
                "status_good": observation.status_good,
                "status_text": observation.status_text,
                "variant_type": observation.variant_type,
                "source_timestamp": _format_optional_datetime(observation.source_timestamp),
                "server_timestamp": _format_optional_datetime(observation.server_timestamp),
                "received_at": observation.received_at.isoformat(),
                "ingested_at": timing.ingested_at.isoformat(),
                "event_at": _format_optional_datetime(timing.event_at),
                "event_time_basis": timing.basis.value,
                "connection_epoch": event.connection_epoch,
                "event_index": event.event_index,
                "replayed": registered.notification.replayed,
                # Versioned fingerprints include the snapshot; the legacy variant
                # (include_semantics=False) verifies commits made before the version.
                **(
                    {"semantic_binding": serialize_channel_semantic_binding(binding)}
                    if include_semantics and (binding := registered.semantic_binding) is not None
                    else {}
                ),
            }
        )
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_duckdb_module() -> Any:
    try:
        return importlib.import_module("duckdb")
    except ModuleNotFoundError as error:
        if error.name != "duckdb":
            raise
        raise DuckLakeRuntimeUnavailableError(
            "DuckLake history runtime is not installed; install the 'history' extra"
        ) from error


def _raw_event_row(
    event: OpcUaPersistentDataChangeEvent,
    *,
    batch_id: str,
    ingestion_mode: HistoryIngestionMode,
) -> tuple[object, ...]:
    registered = event.event
    observation = registered.notification.observation
    event_time = event.event_time
    return (
        _raw_evidence_id(event),
        batch_id,
        ingestion_mode.value,
        event.source_id,
        registered.asset_id,
        registered.endpoint_url,
        registered.measurement_point_id,
        observation.channel_id,
        observation.node_id,
        observation.value,
        observation.status_code,
        observation.status_good,
        observation.status_text,
        observation.variant_type,
        observation.source_timestamp,
        observation.server_timestamp,
        observation.received_at,
        event_time.ingested_at,
        event_time.event_at,
        event_time.basis.value,
        registered.collection_index,
        event.connection_epoch,
        event.event_index,
        registered.notification.replayed,
        _semantic_binding_json(registered.semantic_binding),
    )


def _semantic_binding_json(binding: ChannelSemanticBinding | None) -> str | None:
    if binding is None:
        return None
    return json.dumps(
        serialize_channel_semantic_binding(binding),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _measurement_row(
    event: OpcUaPersistentDataChangeEvent,
    *,
    batch_id: str,
    ingestion_mode: HistoryIngestionMode,
) -> tuple[object, ...]:
    registered = event.event
    observation = registered.notification.observation
    return (
        _raw_evidence_id(event),
        batch_id,
        event.source_id,
        SourceType.OPCUA.value,
        registered.asset_id,
        registered.measurement_point_id,
        observation.channel_id,
        event.event_time.event_at,
        event.event_time.basis.value,
        observation.value,
        observation.status_good,
        ingestion_mode.value,
    )


def _file_raw_event_row(
    event: FileBackfillEvent,
    *,
    batch_id: str,
    ingestion_mode: HistoryIngestionMode,
) -> tuple[object, ...]:
    return (
        event.raw_evidence_id,
        batch_id,
        ingestion_mode.value,
        event.source_id,
        event.asset_id,
        event.measurement_point_id,
        event.source_file,
        event.source_sha256,
        event.source_size_bytes,
        event.sample_index,
        event.channel_id,
        event.event_at,
        event.value,
        event.source_metadata_json,
    )


def _file_measurement_row(
    event: FileBackfillEvent,
    *,
    batch_id: str,
    ingestion_mode: HistoryIngestionMode,
) -> tuple[object, ...]:
    return (
        event.raw_evidence_id,
        batch_id,
        event.source_id,
        SourceType.FILE.value,
        event.asset_id,
        event.measurement_point_id,
        event.channel_id,
        event.event_at,
        HistoricalEventTimeBasis.SOURCE_TIMESTAMP.value,
        event.value,
        # Legacy availability field; FILE has no asserted protocol quality.
        # HistoricalMeasurement.source_quality exposes UNKNOWN independently.
        event.value is not None,
        ingestion_mode.value,
    )


def _file_event_from_row(row: Sequence[object]) -> FileBackfillEvent:
    if len(row) != 12:
        raise RuntimeError("DuckLake FILE evidence row has an unexpected column count")
    return FileBackfillEvent(
        raw_evidence_id=_require_str(row[0], "raw_evidence_id"),
        source_id=_require_str(row[1], "source_id"),
        asset_id=_require_str(row[2], "asset_id"),
        measurement_point_id=_optional_str(row[3], "measurement_point_id"),
        source_file=_require_str(row[4], "source_file"),
        source_sha256=_require_str(row[5], "source_sha256"),
        source_size_bytes=_require_int(row[6], "source_size_bytes"),
        sample_index=_require_int(row[7], "sample_index"),
        channel_id=_require_str(row[8], "channel_id"),
        event_at=_require_datetime(row[9], "source_timestamp"),
        value=_optional_float(row[10], "value"),
        source_metadata_json=_optional_str(row[11], "source_metadata_json"),
    )


def _historical_measurement_from_row(row: Sequence[object]) -> HistoricalMeasurement:
    if len(row) != 11:
        raise RuntimeError("DuckLake measurement row has an unexpected column count")
    event_at = row[7]
    if event_at is not None and not isinstance(event_at, datetime):
        raise RuntimeError("DuckLake event_at must be a datetime or null")
    value = row[8]
    numeric_value: float | None
    if value is None:
        numeric_value = None
    elif isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError("DuckLake measurement value must be numeric or null")
    else:
        numeric_value = float(value)

    return HistoricalMeasurement(
        raw_evidence_id=_require_str(row[0], "raw_evidence_id"),
        source_id=_require_str(row[1], "source_id"),
        source_type=SourceType(_require_str(row[2], "source_type")),
        asset_id=_require_str(row[3], "asset_id"),
        measurement_point_id=_optional_str(row[4], "measurement_point_id"),
        channel_id=_require_str(row[5], "channel_id"),
        event_time_basis=HistoricalEventTimeBasis(_require_str(row[6], "event_time_basis")),
        event_at=event_at,
        value=numeric_value,
        status_good=_require_bool(row[9], "status_good"),
        ingestion_mode=HistoryIngestionMode(_require_str(row[10], "ingestion_mode")),
    )


def _raw_evidence_id(event: OpcUaPersistentDataChangeEvent) -> str:
    return _raw_evidence_id_from_identity(*event.local_delivery_identity)


def _raw_evidence_id_from_identity(
    source_id: str,
    connection_epoch: int,
    event_index: int,
) -> str:
    return "opcua:" + json.dumps(
        [source_id, connection_epoch, event_index],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _parse_semantic_binding_json(value: object) -> ChannelSemanticBinding | None:
    if value is None:
        return None
    try:
        return parse_channel_semantic_binding(json.loads(_require_str(value, "semantic_binding")))
    except (json.JSONDecodeError, ValueError) as error:
        raise RuntimeError(f"DuckLake OPC UA semantic binding is invalid: {error}") from error


def _opcua_event_from_row(row: Sequence[object]) -> OpcUaPersistentDataChangeEvent:
    if len(row) != 22:
        raise RuntimeError("DuckLake OPC UA evidence row has an unexpected column count")

    source_timestamp = _optional_datetime(row[11], "source_timestamp")
    server_timestamp = _optional_datetime(row[12], "server_timestamp")
    received_at = _require_datetime(row[13], "received_at")
    ingested_at = _require_datetime(row[14], "ingested_at")
    event_at = _optional_datetime(row[15], "event_at")
    basis = OpcUaEventTimeBasis(_require_str(row[16], "event_time_basis"))

    observation = OpcUaNodeObservation(
        channel_id=_require_str(row[4], "channel_id"),
        node_id=_require_str(row[5], "node_id"),
        value=_optional_float(row[6], "value"),
        status_code=_require_int(row[7], "status_code"),
        status_good=_require_bool(row[8], "status_good"),
        status_text=_require_str(row[9], "status_text"),
        variant_type=_optional_str(row[10], "variant_type"),
        source_timestamp=source_timestamp,
        server_timestamp=server_timestamp,
        received_at=received_at,
    )
    registered = RegisteredOpcUaDataChangeEvent(
        source_id=_require_str(row[0], "source_id"),
        asset_id=_require_str(row[1], "asset_id"),
        endpoint_url=_require_str(row[2], "endpoint_url"),
        measurement_point_id=_optional_str(row[3], "measurement_point_id"),
        collection_index=_require_int(row[17], "collection_index"),
        notification=OpcUaSubscriptionNotification(
            observation=observation,
            replayed=_require_bool(row[20], "replayed"),
        ),
        semantic_binding=_parse_semantic_binding_json(row[21]),
    )
    event_time = OpcUaEventTimeEvidence(
        basis=basis,
        source_timestamp=source_timestamp,
        server_timestamp=server_timestamp,
        received_at=received_at,
        ingested_at=ingested_at,
        event_at=event_at,
    )
    return OpcUaPersistentDataChangeEvent(
        event=registered,
        connection_epoch=_require_int(row[18], "connection_epoch"),
        event_index=_require_int(row[19], "event_index"),
        event_time=event_time,
    )


_OPCUA_RAW_COLUMNS = (
    ("raw_evidence_id", "VARCHAR"),
    ("batch_id", "VARCHAR"),
    ("ingestion_mode", "VARCHAR"),
    ("source_id", "VARCHAR"),
    ("asset_id", "VARCHAR"),
    ("endpoint_url", "VARCHAR"),
    ("measurement_point_id", "VARCHAR"),
    ("channel_id", "VARCHAR"),
    ("node_id", "VARCHAR"),
    ("value", "DOUBLE"),
    ("status_code", "UBIGINT"),
    ("status_good", "BOOLEAN"),
    ("status_text", "VARCHAR"),
    ("variant_type", "VARCHAR"),
    ("source_timestamp", "TIMESTAMPTZ"),
    ("server_timestamp", "TIMESTAMPTZ"),
    ("received_at", "TIMESTAMPTZ"),
    ("ingested_at", "TIMESTAMPTZ"),
    ("event_at", "TIMESTAMPTZ"),
    ("event_time_basis", "VARCHAR"),
    ("collection_index", "BIGINT"),
    ("connection_epoch", "BIGINT"),
    ("event_index", "BIGINT"),
    ("replayed", "BOOLEAN"),
    ("semantic_binding_json", "VARCHAR"),
)
_FILE_RAW_COLUMNS = (
    ("raw_evidence_id", "VARCHAR"),
    ("batch_id", "VARCHAR"),
    ("ingestion_mode", "VARCHAR"),
    ("source_id", "VARCHAR"),
    ("asset_id", "VARCHAR"),
    ("measurement_point_id", "VARCHAR"),
    ("source_file", "VARCHAR"),
    ("source_sha256", "VARCHAR"),
    ("source_size_bytes", "BIGINT"),
    ("sample_index", "BIGINT"),
    ("channel_id", "VARCHAR"),
    ("source_timestamp", "TIMESTAMPTZ"),
    ("value", "DOUBLE"),
    ("source_metadata_json", "VARCHAR"),
)
_MEASUREMENT_COLUMNS = (
    ("raw_evidence_id", "VARCHAR"),
    ("batch_id", "VARCHAR"),
    ("source_id", "VARCHAR"),
    ("source_type", "VARCHAR"),
    ("asset_id", "VARCHAR"),
    ("measurement_point_id", "VARCHAR"),
    ("channel_id", "VARCHAR"),
    ("event_at", "TIMESTAMPTZ"),
    ("event_time_basis", "VARCHAR"),
    ("value", "DOUBLE"),
    ("status_good", "BOOLEAN"),
    ("ingestion_mode", "VARCHAR"),
)


def _insert_columns(
    connection: Any,
    table: str,
    columns: tuple[tuple[str, str], ...],
    rows: Sequence[Sequence[object]],
) -> None:
    """Bind one typed list per column instead of one parameter set per row.

    Per-row executemany converted every value separately; column lists cut the
    measured AI-Hub insert time about threefold. Rows keep the column order.
    """
    if not rows:
        return
    if any(len(row) != len(columns) for row in rows):
        raise AssertionError(f"{table} row width does not match its column specification")
    names = ", ".join(name for name, _ in columns)
    values = ", ".join(f"unnest(?::{sql_type}[])" for _, sql_type in columns)
    with _cache_absent_pandas_import():
        connection.execute(
            f"INSERT INTO {_CATALOG_NAME}.{table} ({names}) SELECT {values}",
            [list(column) for column in zip(*rows, strict=True)],
        )


def _opcua_display_metadata_sql(*, ranged: bool) -> str:
    """OPC UA raw rows as display metadata shaped like FILE metadata semantics.

    Only a semantic snapshot naming the row's own source and channel is shown;
    parameters: asset_id, channel_id[, start_at, end_at].
    """
    time_filter = "AND event_at >= ? AND event_at < ?" if ranged else ""
    return f"""SELECT raw_evidence_id, 'opcua' AS source_type,
                        CASE WHEN json_extract_string(semantic_binding_json, '$.source_id')
                                = source_id
                            AND json_extract_string(semantic_binding_json, '$.channel_id')
                                = channel_id
                        THEN json_object(
                            'schema', 'opcua-semantic-snapshot',
                            'semantics', json(semantic_binding_json)
                        )::VARCHAR END AS source_metadata_json,
                        NULL::VARCHAR AS source_file, NULL::VARCHAR AS source_sha256
                    FROM {_CATALOG_NAME}.raw.opcua_data_change
                    WHERE asset_id = ? AND channel_id = ? {time_filter}"""


def _snapshot_semantic_column(connection: Any, at: str) -> str:
    """OPC UA semantic column expression valid at a (possibly old) snapshot.

    A snapshot recorded before the column existed has no OPC UA snapshots; read it
    as unresolved instead of failing time travel.
    """
    columns = {
        column[0]
        for column in connection.execute(
            f"SELECT * FROM {_CATALOG_NAME}.raw.opcua_data_change {at} LIMIT 0"
        ).description
    }
    return "semantic_binding_json" if "semantic_binding_json" in columns else "NULL::VARCHAR"


def _semantic_ctes(at: str, semantic: str, *, channel_filter: bool) -> str:
    """`bound` and `f` CTEs: FILE and OPC UA bindings in one identity-verified shape.

    Parameters per branch: asset_id, source_id, [channel list,] start_at, end_at.
    """
    channels = "AND channel_id IN (SELECT unnest(?::VARCHAR[]))" if channel_filter else ""
    return f"""bound AS (
                        SELECT raw_evidence_id, 'file' AS source_type, source_id, channel_id,
                            json_extract(source_metadata_json, '$.semantics') AS b
                        FROM {_CATALOG_NAME}.raw.file_measurement {at}
                        WHERE asset_id = ? AND source_id = ? {channels}
                            AND source_timestamp >= ? AND source_timestamp < ?
                        UNION ALL
                        SELECT raw_evidence_id, 'opcua' AS source_type, source_id, channel_id,
                            json({semantic}) AS b
                        FROM {_CATALOG_NAME}.raw.opcua_data_change {at}
                        WHERE asset_id = ? AND source_id = ? {channels}
                            AND event_at >= ? AND event_at < ?
                    ), f AS (
                        -- A binding counts only for the raw row it names; a snapshot for
                        -- another source or channel is treated as unresolved.
                        SELECT raw_evidence_id, source_type,
                            CASE WHEN identity THEN json_extract_string(b, '$.version') END AS ver,
                            CASE WHEN identity THEN json_extract_string(
                                b, '$.definition.observed_property'
                            ) END AS prop,
                            CASE WHEN identity
                                THEN json_extract_string(b, '$.definition.scope') END AS scope,
                            CASE WHEN identity
                                THEN json_extract_string(b, '$.definition.unit') END AS unit
                        FROM (
                            SELECT *, coalesce(
                                json_extract_string(b, '$.source_id') = source_id
                                AND json_extract_string(b, '$.channel_id') = channel_id,
                                false
                            ) AS identity
                            FROM bound
                        )
                    )"""


def _quote_sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise RuntimeError(f"DuckLake {field_name} must be a string")
    return value


def _optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_str(value, field_name)


def _require_float(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"DuckLake {field_name} must be numeric")
    return float(value)


def _optional_float(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"DuckLake {field_name} must be numeric or null")
    return float(value)


def _format_optional_datetime(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _require_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise RuntimeError(f"DuckLake {field_name} must be a timezone-aware datetime")
    return value


def _optional_datetime(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _require_datetime(value, field_name)


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise RuntimeError(f"DuckLake {field_name} must be boolean")
    return value


def _require_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"DuckLake {field_name} must be an integer")
    return value


def _validate_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")


def _validate_positive_int(value: int, field_name: str) -> None:
    _validate_non_negative_int(value, field_name)
    if value < 1:
        raise ValueError(f"{field_name} must be at least 1")


def _validate_optional_positive_int(value: int | None, field_name: str) -> None:
    if value is None:
        return
    _validate_positive_int(value, field_name)


def _canonical_fingerprint_value(value: object) -> object:
    if isinstance(value, datetime):
        return {"type": "datetime", "value": value.isoformat()}
    if isinstance(value, bytes):
        return {"type": "bytes", "value": value.hex()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return {"type": type(value).__name__, "value": str(value)}
