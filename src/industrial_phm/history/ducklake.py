"""DuckLake-backed historical Asset History adapter.

DuckLake is the long-term historical data plane. This adapter deliberately does not
implement callback buffering, retry queues, or ingress durability; those responsibilities
belong to the acquisition spool.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from industrial_phm.application.backfill import FileBackfillEvent
from industrial_phm.application.asset_history import (
    HistoricalBatchCommit,
    HistoricalBatchConflictError,
    HistoricalEventTimeBasis,
    HistoricalMeasurement,
    HistoryIngestionMode,
    validate_asset_history_query,
)
from industrial_phm.application.opcua_persistent import (
    OpcUaEventTimeBasis,
    OpcUaEventTimeEvidence,
    OpcUaPersistentDataChangeEvent,
)
from industrial_phm.application.source_registration import SourceType
from industrial_phm.application.source_subscription import RegisteredOpcUaDataChangeEvent
from industrial_phm.connectors import OpcUaNodeObservation, OpcUaSubscriptionNotification

_CATALOG_NAME = "phm_history"
_COMMIT_AUTHOR = "industrial-phm"
_COMMIT_EXTRA_SCHEMA = "industrial-phm-history-batch-v1"


class DuckLakeRuntimeUnavailableError(RuntimeError):
    """Raised when the optional DuckDB/DuckLake history runtime is unavailable."""


@dataclass(frozen=True, slots=True)
class DuckLakeAssetHistoryConfig:
    """Local-first DuckLake configuration for the v1 history boundary."""

    catalog_path: Path
    data_path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.catalog_path, Path):
            raise ValueError("catalog_path must be pathlib.Path")
        if not isinstance(self.data_path, Path):
            raise ValueError("data_path must be pathlib.Path")
        catalog_path = self.catalog_path.expanduser().resolve(strict=False)
        data_path = self.data_path.expanduser().resolve(strict=False)
        if catalog_path == data_path:
            raise ValueError("DuckLake catalog_path and data_path must be distinct")


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
        batch = _validate_opcua_batch_input(
            events,
            batch_id=batch_id,
            ingestion_mode=ingestion_mode,
        )
        fingerprint = _opcua_batch_fingerprint(batch)

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
                connection.executemany(
                    _raw_insert_sql(),
                    [
                        _raw_event_row(
                            event,
                            batch_id=batch_id,
                            ingestion_mode=ingestion_mode,
                        )
                        for event in batch
                    ],
                )
                connection.executemany(
                    _measurement_insert_sql(),
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

            time_row = connection.execute(
                f"""
                SELECT snapshot_time
                FROM {_CATALOG_NAME}.snapshots()
                WHERE snapshot_id = ?
                """,
                [snapshot_id],
            ).fetchone()
            if time_row is None:
                raise RuntimeError("DuckLake committed snapshot metadata is unavailable")
            committed_at = time_row[0]
            if not isinstance(committed_at, datetime) or committed_at.utcoffset() is None:
                raise RuntimeError("DuckLake snapshot_time must be timezone-aware")

            return HistoricalBatchCommit(
                batch_id=batch_id,
                snapshot_id=snapshot_id,
                event_count=len(batch),
                committed_at=committed_at,
            )
        finally:
            connection.close()

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
                connection.executemany(
                    _file_raw_insert_sql(),
                    [
                        _file_raw_event_row(
                            event,
                            batch_id=batch_id,
                            ingestion_mode=ingestion_mode,
                        )
                        for event in batch
                    ],
                )
                connection.executemany(
                    _file_measurement_insert_sql(),
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
                    value
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
                f"SELECT id FROM {_CATALOG_NAME}.last_committed_snapshot()"
            ).fetchone()
        finally:
            connection.close()
        if row is None or row[0] is None:
            return 0
        return _require_int(row[0], "snapshot_id")

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
                    replayed
                FROM {_CATALOG_NAME}.raw.opcua_data_change
                WHERE source_id = ?
                ORDER BY ingested_at, connection_epoch, event_index, raw_evidence_id
                """,
                [source_id],
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
                    replayed
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

    def _connect(self) -> Any:
        duckdb = _load_duckdb_module()
        catalog_path = self._config.catalog_path.expanduser().resolve(strict=False)
        data_path = self._config.data_path.expanduser().resolve(strict=False)
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        data_path.mkdir(parents=True, exist_ok=True)

        connection = duckdb.connect()
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
        except Exception:
            connection.close()
            raise
        return connection

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
                replayed BOOLEAN NOT NULL
            )
            """
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
                value DOUBLE NOT NULL
            )
            """
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
        placeholders = ", ".join("?" for _ in raw_evidence_ids)
        row = connection.execute(
            f"""
            SELECT raw_evidence_id
            FROM {_CATALOG_NAME}.raw.opcua_data_change
            WHERE raw_evidence_id IN ({placeholders})
            LIMIT 1
            """,
            list(raw_evidence_ids),
        ).fetchone()
        if row is not None:
            existing_id = _require_str(row[0], "raw_evidence_id")
            raise ValueError(f"historical delivery already exists: {existing_id}")

    def _reject_existing_file_evidence(
        self,
        connection: Any,
        events: Sequence[FileBackfillEvent],
    ) -> None:
        raw_evidence_ids = tuple(event.raw_evidence_id for event in events)
        placeholders = ", ".join("?" for _ in raw_evidence_ids)
        row = connection.execute(
            f"""
            SELECT raw_evidence_id
            FROM {_CATALOG_NAME}.raw.file_measurement
            WHERE raw_evidence_id IN ({placeholders})
            LIMIT 1
            """,
            list(raw_evidence_ids),
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
        time_row = connection.execute(
            f"""
            SELECT snapshot_time
            FROM {_CATALOG_NAME}.snapshots()
            WHERE snapshot_id = ?
            """,
            [snapshot_id],
        ).fetchone()
        if time_row is None:
            raise RuntimeError("DuckLake committed snapshot metadata is unavailable")
        committed_at = _require_datetime(time_row[0], "snapshot_time")
        return HistoricalBatchCommit(
            batch_id=batch_id,
            snapshot_id=snapshot_id,
            event_count=event_count,
            committed_at=committed_at,
        )

    def _lookup_existing_batch_commit(
        self,
        connection: Any,
        *,
        batch_id: str,
        ingestion_mode: HistoryIngestionMode,
        event_count: int,
        fingerprint: str,
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
            extra = _parse_commit_extra_info(extra_raw)
            if extra is None or extra.get("batch_id") != batch_id:
                continue
            if (
                extra.get("schema") != _COMMIT_EXTRA_SCHEMA
                or extra.get("ingestion_mode") != ingestion_mode.value
                or extra.get("event_count") != event_count
                or extra.get("fingerprint") != fingerprint
            ):
                raise HistoricalBatchConflictError(
                    f"historical batch identity conflicts with commit provenance: {batch_id}"
                )
            snapshot_id = _require_int(snapshot_id_raw, "snapshot_id")
            snapshot_time = _require_datetime(snapshot_time_raw, "snapshot_time")
            matching_snapshots.append((snapshot_id, snapshot_time))

        if len(matching_snapshots) != 1:
            raise HistoricalBatchConflictError(
                f"historical batch commit provenance is unavailable or ambiguous: {batch_id}"
            )
        snapshot_id, committed_at = matching_snapshots[0]
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
) -> str:
    return json.dumps(
        {
            "schema": _COMMIT_EXTRA_SCHEMA,
            "batch_id": batch_id,
            "ingestion_mode": ingestion_mode.value,
            "event_count": event_count,
            "fingerprint": fingerprint,
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
        True,
        ingestion_mode.value,
    )


def _file_event_from_row(row: Sequence[object]) -> FileBackfillEvent:
    if len(row) != 11:
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
        value=_require_float(row[10], "value"),
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


def _opcua_event_from_row(row: Sequence[object]) -> OpcUaPersistentDataChangeEvent:
    if len(row) != 21:
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


def _raw_insert_sql() -> str:
    return f"""
        INSERT INTO {_CATALOG_NAME}.raw.opcua_data_change (
            raw_evidence_id,
            batch_id,
            ingestion_mode,
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
            replayed
        ) VALUES ({", ".join("?" for _ in range(24))})
    """


def _file_raw_insert_sql() -> str:
    return f"""
        INSERT INTO {_CATALOG_NAME}.raw.file_measurement (
            raw_evidence_id,
            batch_id,
            ingestion_mode,
            source_id,
            asset_id,
            measurement_point_id,
            source_file,
            source_sha256,
            source_size_bytes,
            sample_index,
            channel_id,
            source_timestamp,
            value
        ) VALUES ({", ".join("?" for _ in range(13))})
    """


def _file_measurement_insert_sql() -> str:
    return _measurement_insert_sql()


def _measurement_insert_sql() -> str:
    return f"""
        INSERT INTO {_CATALOG_NAME}.history.measurement (
            raw_evidence_id,
            batch_id,
            source_id,
            source_type,
            asset_id,
            measurement_point_id,
            channel_id,
            event_at,
            event_time_basis,
            value,
            status_good,
            ingestion_mode
        ) VALUES ({", ".join("?" for _ in range(12))})
    """


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
