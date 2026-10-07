"""SQLite WAL durable acquisition spool.

The spool is a short-lived crash-safe delivery boundary, not historical storage.
It retains at most one active single-writer batch so a process restart reuses the
same downstream batch identity until acknowledgement.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from industrial_phm.application.acquisition_spool import (
    AcquisitionSpoolBatch,
    AcquisitionSpoolFormatError,
    AcquisitionSpoolFullError,
    AcquisitionSpoolPendingStats,
    AcquisitionSpoolStateError,
)
from industrial_phm.application.acquisition_telemetry import AcquisitionSpoolTelemetrySnapshot
from industrial_phm.application.measurement_semantics import (
    parse_channel_semantic_binding,
    serialize_channel_semantic_binding,
)
from industrial_phm.application.opcua_persistent import (
    OpcUaEventTimeBasis,
    OpcUaEventTimeEvidence,
    OpcUaEventTimePolicy,
    OpcUaPersistentDataChangeEvent,
    project_opcua_persistent_data_change_event,
)
from industrial_phm.application.source_subscription import RegisteredOpcUaDataChangeEvent
from industrial_phm.connectors import OpcUaNodeObservation, OpcUaSubscriptionNotification
from industrial_phm.runtime._sqlite import connect_wal

_SCHEMA_VERSION = "industrial-phm-acquisition-spool-v1"


@dataclass(frozen=True, slots=True)
class SqliteAcquisitionSpoolConfig:
    path: Path
    max_events: int = 100_000
    busy_timeout_ms: int = 5_000

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise ValueError("path must be pathlib.Path")
        _validate_positive_int(self.max_events, "max_events")
        _validate_positive_int(self.busy_timeout_ms, "busy_timeout_ms")


class SqliteAcquisitionSpool:
    """Single-writer SQLite WAL spool with stable unacknowledged batch assignment."""

    def __init__(self, config: SqliteAcquisitionSpoolConfig) -> None:
        if not isinstance(config, SqliteAcquisitionSpoolConfig):
            raise ValueError("config must be SqliteAcquisitionSpoolConfig")
        self._config = config

    @property
    def config(self) -> SqliteAcquisitionSpoolConfig:
        return self._config

    def initialize(self) -> None:
        connection = self._connect()
        try:
            self._ensure_schema(connection)
            self._validate_state(connection)
        finally:
            connection.close()

    def get_last_connection_epoch(self, source_id: str) -> int:
        """Return the durable source epoch baseline across worker process restarts."""
        _validate_identifier(source_id, "source_id")
        connection = self._connect()
        try:
            self._ensure_schema(connection)
            row = connection.execute(
                "SELECT value FROM spool_metadata WHERE key = ?",
                (_connection_epoch_metadata_key(source_id),),
            ).fetchone()
            if row is None:
                return 0
            return _parse_non_negative_metadata_int(
                _require_str(row[0], "connection epoch metadata"),
                "connection epoch metadata",
            )
        finally:
            connection.close()

    def reserve_next_connection_epoch(
        self,
        source_id: str,
        *,
        expected_previous_epoch: int,
    ) -> int:
        """Atomically reserve the next durable source connection epoch."""
        _validate_identifier(source_id, "source_id")
        _validate_non_negative_int(expected_previous_epoch, "expected_previous_epoch")
        key = _connection_epoch_metadata_key(source_id)

        connection = self._connect()
        try:
            self._ensure_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT value FROM spool_metadata WHERE key = ?",
                (key,),
            ).fetchone()
            current = (
                0
                if row is None
                else _parse_non_negative_metadata_int(
                    _require_str(row[0], "connection epoch metadata"),
                    "connection epoch metadata",
                )
            )
            if current != expected_previous_epoch:
                raise AcquisitionSpoolStateError(
                    "durable source connection epoch changed concurrently: "
                    f"expected {expected_previous_epoch}, found {current}"
                )

            reserved = current + 1
            connection.execute(
                """
                INSERT INTO spool_metadata (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, str(reserved)),
            )
            connection.execute("COMMIT")
            return reserved
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def accept_opcua_event(
        self,
        event: RegisteredOpcUaDataChangeEvent,
        *,
        connection_epoch: int,
        event_index: int,
        accepted_at: datetime,
        event_time_policy: OpcUaEventTimePolicy | None = None,
    ) -> OpcUaPersistentDataChangeEvent:
        """Project and durably accept one DataChange, idempotent by local delivery identity."""
        persistent = project_opcua_persistent_data_change_event(
            event,
            connection_epoch=connection_epoch,
            event_index=event_index,
            ingested_at=accepted_at,
            event_time_policy=event_time_policy,
        )
        payload = _encode_event(persistent)
        source_id, epoch, index = persistent.local_delivery_identity

        connection = self._connect()
        try:
            self._ensure_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT payload_json
                FROM spool_event
                WHERE source_id = ? AND connection_epoch = ? AND event_index = ?
                """,
                (source_id, epoch, index),
            ).fetchone()
            if existing is not None:
                restored = _decode_event(_require_str(existing[0], "payload_json"))
                if not _same_delivery_content(restored, persistent):
                    raise AcquisitionSpoolStateError(
                        "same local delivery identity has conflicting durable payload"
                    )
                connection.execute("COMMIT")
                return restored

            count_row = connection.execute("SELECT COUNT(*) FROM spool_event").fetchone()
            if count_row is None:
                raise AcquisitionSpoolStateError("spool event count is unavailable")
            if _require_int(count_row[0], "spool event count") >= self._config.max_events:
                raise AcquisitionSpoolFullError(
                    f"durable acquisition spool reached max_events={self._config.max_events}"
                )

            connection.execute(
                """
                INSERT INTO spool_event (
                    source_id,
                    connection_epoch,
                    event_index,
                    accepted_at,
                    payload_json,
                    batch_id
                ) VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (
                    source_id,
                    epoch,
                    index,
                    accepted_at.isoformat(),
                    payload,
                ),
            )
            connection.execute("COMMIT")
            return persistent
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def telemetry_snapshot(
        self,
        *,
        sampled_at: datetime,
    ) -> AcquisitionSpoolTelemetrySnapshot:
        """Sample durable backlog facts without mutating spool delivery state.

        A spool read cannot be dated before the newest event it observed. A caller
        that picked ``sampled_at`` before other reads may see events the collector
        accepted after that instant; the snapshot is then dated at the newest
        accepted event so the backlog age never becomes negative.
        """
        _validate_aware_datetime(sampled_at, "sampled_at")
        connection = self._connect()
        try:
            self._ensure_schema(connection)
            # One read transaction: separate autocommit SELECTs could straddle a
            # concurrent accept and return an impossible count/oldest combination.
            connection.execute("BEGIN")
            row = connection.execute(
                """
                SELECT
                    COUNT(*),
                    COALESCE(SUM(length(CAST(payload_json AS BLOB))), 0)
                FROM spool_event
                """
            ).fetchone()
            if row is None:
                raise AcquisitionSpoolStateError("spool telemetry count is unavailable")
            pending_event_count = _require_int(row[0], "pending event count")
            payload_bytes = _require_int(row[1], "pending payload bytes")

            oldest_row = connection.execute(
                """
                SELECT accepted_at
                FROM spool_event
                ORDER BY julianday(accepted_at), sequence
                LIMIT 1
                """
            ).fetchone()
            oldest_accepted_at = (
                None
                if oldest_row is None
                else _parse_datetime(
                    _require_str(oldest_row[0], "oldest accepted_at"),
                    "oldest accepted_at",
                )
            )
            newest_row = connection.execute(
                """
                SELECT accepted_at
                FROM spool_event
                ORDER BY julianday(accepted_at) DESC, sequence DESC
                LIMIT 1
                """
            ).fetchone()
            observed_at = max(
                [sampled_at]
                + ([] if oldest_accepted_at is None else [oldest_accepted_at])
                + (
                    []
                    if newest_row is None
                    else [
                        _parse_datetime(
                            _require_str(newest_row[0], "newest accepted_at"),
                            "newest accepted_at",
                        )
                    ]
                )
            )

            batch_row = connection.execute(
                "SELECT batch_id, created_at, event_count FROM spool_batch LIMIT 1"
            ).fetchone()
            active_batch = None
            if batch_row is not None:
                active_batch = self._load_batch(
                    connection,
                    batch_id=_require_str(batch_row[0], "batch_id"),
                    created_at=_parse_datetime(
                        _require_str(batch_row[1], "created_at"),
                        "created_at",
                    ),
                    expected_count=_require_int(batch_row[2], "event_count"),
                )
        finally:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            connection.close()

        return AcquisitionSpoolTelemetrySnapshot(
            sampled_at=observed_at,
            pending_event_count=pending_event_count,
            payload_bytes=payload_bytes,
            oldest_accepted_at=oldest_accepted_at,
            active_batch_id=(None if active_batch is None else active_batch.batch_id),
            active_batch_event_count=(0 if active_batch is None else active_batch.event_count),
            active_batch_payload_bytes=(0 if active_batch is None else active_batch.payload_bytes),
        )

    def pending_unassigned_stats(self) -> AcquisitionSpoolPendingStats:
        connection = self._connect()
        try:
            self._ensure_schema(connection)
            # One read transaction: separate autocommit SELECTs could straddle a
            # concurrent accept and return an impossible count/oldest combination.
            connection.execute("BEGIN")
            row = connection.execute(
                """
                SELECT
                    COUNT(*),
                    COALESCE(SUM(length(CAST(payload_json AS BLOB))), 0)
                FROM spool_event
                WHERE batch_id IS NULL
                """
            ).fetchone()
            if row is None:
                raise AcquisitionSpoolStateError("pending spool stats are unavailable")
            event_count = _require_int(row[0], "pending event count")
            payload_bytes = _require_int(row[1], "pending payload bytes")
            oldest_row = connection.execute(
                """
                SELECT accepted_at
                FROM spool_event
                WHERE batch_id IS NULL
                ORDER BY julianday(accepted_at), sequence
                LIMIT 1
                """
            ).fetchone()
            oldest_raw = None if oldest_row is None else oldest_row[0]
            oldest_accepted_at = (
                None
                if oldest_raw is None
                else _parse_datetime(
                    _require_str(oldest_raw, "oldest accepted_at"),
                    "oldest accepted_at",
                )
            )
            return AcquisitionSpoolPendingStats(
                event_count=event_count,
                payload_bytes=payload_bytes,
                oldest_accepted_at=oldest_accepted_at,
            )
        finally:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            connection.close()

    def pending_event_count(self) -> int:
        connection = self._connect()
        try:
            self._ensure_schema(connection)
            row = connection.execute("SELECT COUNT(*) FROM spool_event").fetchone()
            if row is None:
                raise AcquisitionSpoolStateError("spool event count is unavailable")
            return _require_int(row[0], "spool event count")
        finally:
            connection.close()

    def get_active_batch(self) -> AcquisitionSpoolBatch | None:
        connection = self._connect()
        try:
            self._ensure_schema(connection)
            self._validate_state(connection)
            row = connection.execute(
                "SELECT batch_id, created_at, event_count FROM spool_batch LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            return self._load_batch(
                connection,
                batch_id=_require_str(row[0], "batch_id"),
                created_at=_parse_datetime(_require_str(row[1], "created_at"), "created_at"),
                expected_count=_require_int(row[2], "event_count"),
            )
        finally:
            connection.close()

    def assign_next_batch(
        self,
        *,
        batch_id: str,
        max_events: int,
        max_bytes: int | None = None,
        created_at: datetime,
    ) -> AcquisitionSpoolBatch | None:
        """Return the existing active batch or atomically assign oldest pending events."""
        _validate_identifier(batch_id, "batch_id")
        _validate_positive_int(max_events, "max_events")
        if max_bytes is not None:
            _validate_positive_int(max_bytes, "max_bytes")
        _validate_aware_datetime(created_at, "created_at")

        connection = self._connect()
        try:
            self._ensure_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            self._validate_state(connection)

            active = connection.execute(
                "SELECT batch_id, created_at, event_count FROM spool_batch LIMIT 1"
            ).fetchone()
            if active is not None:
                result = self._load_batch(
                    connection,
                    batch_id=_require_str(active[0], "batch_id"),
                    created_at=_parse_datetime(
                        _require_str(active[1], "created_at"),
                        "created_at",
                    ),
                    expected_count=_require_int(active[2], "event_count"),
                )
                connection.execute("COMMIT")
                return result

            if (
                connection.execute(
                    "SELECT 1 FROM spool_batch WHERE batch_id = ?",
                    (batch_id,),
                ).fetchone()
                is not None
            ):
                raise AcquisitionSpoolStateError(f"batch_id is already active: {batch_id}")

            rows = connection.execute(
                """
                SELECT sequence, payload_json
                FROM spool_event
                WHERE batch_id IS NULL
                ORDER BY sequence
                LIMIT ?
                """,
                (max_events,),
            ).fetchall()
            if not rows:
                connection.execute("COMMIT")
                return None

            sequences_list: list[int] = []
            selected_bytes = 0
            for sequence_raw, payload_raw in rows:
                sequence = _require_int(sequence_raw, "sequence")
                payload_json = _require_str(payload_raw, "payload_json")
                payload_bytes = len(payload_json.encode("utf-8"))
                if (
                    max_bytes is not None
                    and sequences_list
                    and selected_bytes + payload_bytes > max_bytes
                ):
                    break
                sequences_list.append(sequence)
                selected_bytes += payload_bytes
                if max_bytes is not None and selected_bytes >= max_bytes:
                    break

            sequences = tuple(sequences_list)
            placeholders = ", ".join("?" for _ in sequences)
            connection.execute(
                """
                INSERT INTO spool_batch (batch_id, created_at, event_count)
                VALUES (?, ?, ?)
                """,
                (batch_id, created_at.isoformat(), len(sequences)),
            )
            connection.execute(
                f"UPDATE spool_event SET batch_id = ? WHERE sequence IN ({placeholders})",
                (batch_id, *sequences),
            )
            result = self._load_batch(
                connection,
                batch_id=batch_id,
                created_at=created_at,
                expected_count=len(sequences),
            )
            connection.execute("COMMIT")
            return result
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def acknowledge_batch(self, batch_id: str, *, acknowledged_at: datetime) -> int:
        """Delete one downstream-committed batch only after explicit acknowledgement."""
        _validate_identifier(batch_id, "batch_id")
        _validate_aware_datetime(acknowledged_at, "acknowledged_at")
        connection = self._connect()
        try:
            self._ensure_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            self._validate_state(connection)
            row = connection.execute(
                "SELECT created_at, event_count FROM spool_batch WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
            if row is None:
                raise AcquisitionSpoolStateError(f"active spool batch does not exist: {batch_id}")
            created_at = _parse_datetime(_require_str(row[0], "created_at"), "created_at")
            if acknowledged_at < created_at:
                raise ValueError("acknowledged_at must not be before batch created_at")
            expected_count = _require_int(row[1], "event_count")
            event_count_row = connection.execute(
                "SELECT COUNT(*) FROM spool_event WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
            if event_count_row is None:
                raise AcquisitionSpoolStateError("active batch event count is unavailable")
            actual_count = _require_int(event_count_row[0], "active batch event count")
            if actual_count != expected_count:
                raise AcquisitionSpoolStateError(
                    "active batch event_count does not match assigned spool events"
                )

            connection.execute("DELETE FROM spool_event WHERE batch_id = ?", (batch_id,))
            connection.execute("DELETE FROM spool_batch WHERE batch_id = ?", (batch_id,))
            connection.execute("COMMIT")
            return actual_count
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        path = self._config.path.expanduser().resolve(strict=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        return connect_wal(path, busy_timeout_ms=self._config.busy_timeout_ms, foreign_keys=True)

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spool_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        schema = connection.execute(
            "SELECT value FROM spool_metadata WHERE key = 'schema'"
        ).fetchone()
        if schema is None:
            connection.execute("BEGIN IMMEDIATE")
            schema = connection.execute(
                "SELECT value FROM spool_metadata WHERE key = 'schema'"
            ).fetchone()
        if schema is None:
            connection.execute(
                "INSERT INTO spool_metadata (key, value) VALUES ('schema', ?)",
                (_SCHEMA_VERSION,),
            )
        elif schema[0] != _SCHEMA_VERSION:
            raise AcquisitionSpoolFormatError(
                f"unsupported acquisition spool schema: {schema[0]!r}"
            )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spool_batch (
                batch_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                event_count INTEGER NOT NULL CHECK (event_count > 0)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spool_event (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                connection_epoch INTEGER NOT NULL,
                event_index INTEGER NOT NULL,
                accepted_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                batch_id TEXT,
                UNIQUE (source_id, connection_epoch, event_index),
                FOREIGN KEY (batch_id) REFERENCES spool_batch(batch_id)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS spool_event_batch_idx ON spool_event(batch_id, sequence)"
        )
        connection.commit()

    def _validate_state(self, connection: sqlite3.Connection) -> None:
        batches = connection.execute(
            "SELECT batch_id, event_count FROM spool_batch ORDER BY created_at, batch_id"
        ).fetchall()
        if len(batches) > 1:
            raise AcquisitionSpoolStateError(
                "single-writer acquisition spool must not contain multiple active batches"
            )
        for batch_id_raw, expected_raw in batches:
            batch_id = _require_str(batch_id_raw, "batch_id")
            expected = _require_int(expected_raw, "event_count")
            row = connection.execute(
                "SELECT COUNT(*) FROM spool_event WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
            if row is None or _require_int(row[0], "batch event count") != expected:
                raise AcquisitionSpoolStateError(
                    "active batch event_count does not match assigned spool events"
                )

    def _load_batch(
        self,
        connection: sqlite3.Connection,
        *,
        batch_id: str,
        created_at: datetime,
        expected_count: int,
    ) -> AcquisitionSpoolBatch:
        rows = connection.execute(
            """
            SELECT payload_json
            FROM spool_event
            WHERE batch_id = ?
            ORDER BY sequence
            """,
            (batch_id,),
        ).fetchall()
        payloads = tuple(_require_str(row[0], "payload_json") for row in rows)
        events = tuple(_decode_event(payload_json) for payload_json in payloads)
        if len(events) != expected_count:
            raise AcquisitionSpoolStateError(
                "active batch event_count does not match durable event payloads"
            )
        return AcquisitionSpoolBatch(
            batch_id=batch_id,
            created_at=created_at,
            events=events,
            payload_bytes=sum(len(payload_json.encode("utf-8")) for payload_json in payloads),
        )


def _same_delivery_content(
    stored: OpcUaPersistentDataChangeEvent,
    candidate: OpcUaPersistentDataChangeEvent,
) -> bool:
    """Compare one local delivery while preserving the first durable acceptance time."""
    return (
        stored.local_delivery_identity == candidate.local_delivery_identity
        and stored.event == candidate.event
        and stored.event_time.basis == candidate.event_time.basis
        and stored.event_time.source_timestamp == candidate.event_time.source_timestamp
        and stored.event_time.server_timestamp == candidate.event_time.server_timestamp
        and stored.event_time.received_at == candidate.event_time.received_at
        and stored.event_time.event_at == candidate.event_time.event_at
    )


def _encode_event(event: OpcUaPersistentDataChangeEvent) -> str:
    registered = event.event
    observation = registered.notification.observation
    timing = event.event_time
    payload = {
        "schema": _SCHEMA_VERSION,
        "connection_epoch": event.connection_epoch,
        "event_index": event.event_index,
        "registered_event": {
            "source_id": registered.source_id,
            "asset_id": registered.asset_id,
            "endpoint_url": registered.endpoint_url,
            "measurement_point_id": registered.measurement_point_id,
            "collection_index": registered.collection_index,
            "semantic_binding": (
                None
                if registered.semantic_binding is None
                else serialize_channel_semantic_binding(registered.semantic_binding)
            ),
            "notification": {
                "replayed": registered.notification.replayed,
                "observation": {
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
                },
            },
        },
        "event_time": {
            "basis": timing.basis.value,
            "source_timestamp": _format_optional_datetime(timing.source_timestamp),
            "server_timestamp": _format_optional_datetime(timing.server_timestamp),
            "received_at": timing.received_at.isoformat(),
            "ingested_at": timing.ingested_at.isoformat(),
            "event_at": _format_optional_datetime(timing.event_at),
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _decode_event(payload_json: str) -> OpcUaPersistentDataChangeEvent:
    try:
        raw = json.loads(payload_json)
    except json.JSONDecodeError as error:
        raise AcquisitionSpoolFormatError("spool event payload must be valid JSON") from error
    if not isinstance(raw, dict):
        raise AcquisitionSpoolFormatError("spool event payload must be a JSON object")
    payload = cast(Mapping[str, object], raw)
    if payload.get("schema") != _SCHEMA_VERSION:
        raise AcquisitionSpoolFormatError("unsupported spool event payload schema")

    registered_raw = _require_mapping(payload.get("registered_event"), "registered_event")
    notification_raw = _require_mapping(
        registered_raw.get("notification"),
        "notification",
    )
    observation_raw = _require_mapping(
        notification_raw.get("observation"),
        "observation",
    )
    timing_raw = _require_mapping(payload.get("event_time"), "event_time")

    observation = OpcUaNodeObservation(
        channel_id=_require_str(observation_raw.get("channel_id"), "channel_id"),
        node_id=_require_str(observation_raw.get("node_id"), "node_id"),
        value=_optional_float(observation_raw.get("value"), "value"),
        status_code=_require_int(observation_raw.get("status_code"), "status_code"),
        status_good=_require_bool(observation_raw.get("status_good"), "status_good"),
        status_text=_require_str(observation_raw.get("status_text"), "status_text"),
        variant_type=_optional_str(observation_raw.get("variant_type"), "variant_type"),
        source_timestamp=_optional_datetime(
            observation_raw.get("source_timestamp"),
            "source_timestamp",
        ),
        server_timestamp=_optional_datetime(
            observation_raw.get("server_timestamp"),
            "server_timestamp",
        ),
        received_at=_require_datetime(
            observation_raw.get("received_at"),
            "received_at",
        ),
    )
    semantic_raw = registered_raw.get("semantic_binding")
    try:
        semantic_binding = (
            None if semantic_raw is None else parse_channel_semantic_binding(semantic_raw)
        )
    except ValueError as error:
        raise AcquisitionSpoolFormatError(f"invalid semantic binding: {error}") from error

    registered = RegisteredOpcUaDataChangeEvent(
        source_id=_require_str(registered_raw.get("source_id"), "source_id"),
        asset_id=_require_str(registered_raw.get("asset_id"), "asset_id"),
        endpoint_url=_require_str(registered_raw.get("endpoint_url"), "endpoint_url"),
        measurement_point_id=_optional_str(
            registered_raw.get("measurement_point_id"),
            "measurement_point_id",
        ),
        collection_index=_require_int(
            registered_raw.get("collection_index"),
            "collection_index",
        ),
        notification=OpcUaSubscriptionNotification(
            observation=observation,
            replayed=_require_bool(notification_raw.get("replayed"), "replayed"),
        ),
        semantic_binding=semantic_binding,
    )
    event_time = OpcUaEventTimeEvidence(
        basis=OpcUaEventTimeBasis(_require_str(timing_raw.get("basis"), "basis")),
        source_timestamp=_optional_datetime(
            timing_raw.get("source_timestamp"),
            "source_timestamp",
        ),
        server_timestamp=_optional_datetime(
            timing_raw.get("server_timestamp"),
            "server_timestamp",
        ),
        received_at=_require_datetime(timing_raw.get("received_at"), "received_at"),
        ingested_at=_require_datetime(timing_raw.get("ingested_at"), "ingested_at"),
        event_at=_optional_datetime(timing_raw.get("event_at"), "event_at"),
    )
    return OpcUaPersistentDataChangeEvent(
        event=registered,
        connection_epoch=_require_int(payload.get("connection_epoch"), "connection_epoch"),
        event_index=_require_int(payload.get("event_index"), "event_index"),
        event_time=event_time,
    )


def _connection_epoch_metadata_key(source_id: str) -> str:
    return f"opcua-connection-epoch:{source_id}"


def _parse_non_negative_metadata_int(value: str, field_name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise AcquisitionSpoolFormatError(f"{field_name} must be an integer") from error
    if parsed < 0:
        raise AcquisitionSpoolFormatError(f"{field_name} must not be negative")
    return parsed


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise AcquisitionSpoolFormatError(f"{field_name} must be an object")
    return cast(Mapping[str, object], value)


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise AcquisitionSpoolFormatError(f"{field_name} must be a string")
    return value


def _optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_str(value, field_name)


def _require_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AcquisitionSpoolFormatError(f"{field_name} must be an integer")
    return value


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise AcquisitionSpoolFormatError(f"{field_name} must be boolean")
    return value


def _optional_float(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AcquisitionSpoolFormatError(f"{field_name} must be numeric or null")
    return float(value)


def _require_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise AcquisitionSpoolFormatError(f"{field_name} must be an ISO datetime string")
    return _parse_datetime(value, field_name)


def _optional_datetime(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _require_datetime(value, field_name)


def _parse_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise AcquisitionSpoolFormatError(f"{field_name} must be valid ISO datetime") from error
    _validate_aware_datetime(parsed, field_name)
    return parsed


def _format_optional_datetime(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _validate_identifier(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")


def _validate_aware_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware datetime")


def _validate_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")


def _validate_positive_int(value: int, field_name: str) -> None:
    _validate_non_negative_int(value, field_name)
    if value < 1:
        raise ValueError(f"{field_name} must be at least 1")
