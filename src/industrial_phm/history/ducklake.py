"""DuckLake-backed historical Asset History adapter.

DuckLake is the long-term historical data plane. This adapter deliberately does not
implement callback buffering, retry queues, or ingress durability; those responsibilities
belong to the acquisition spool.
"""

from __future__ import annotations

import importlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from industrial_phm.application.asset_history import (
    HistoricalBatchCommit,
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

    def append_opcua_batch(
        self,
        events: Sequence[OpcUaPersistentDataChangeEvent],
        *,
        batch_id: str,
        ingestion_mode: HistoryIngestionMode = HistoryIngestionMode.LIVE,
    ) -> HistoricalBatchCommit:
        """Atomically persist raw OPC UA evidence and normalized measurement history."""
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

        connection = self._connect()
        try:
            self._ensure_initialized(connection)
            self._reject_existing_batch(connection, batch_id)

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

    def _reject_existing_batch(self, connection: Any, batch_id: str) -> None:
        row = connection.execute(
            f"""
            SELECT COUNT(*)
            FROM {_CATALOG_NAME}.history.ingestion_batch
            WHERE batch_id = ?
            """,
            [batch_id],
        ).fetchone()
        if row is None:
            raise RuntimeError("DuckLake batch lookup did not return a count")
        if _require_int(row[0], "batch count") != 0:
            raise ValueError(f"historical batch already exists: {batch_id}")


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


def _optional_float(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"DuckLake {field_name} must be numeric or null")
    return float(value)


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
