"""SQLite WAL latest telemetry repository for continuous acquisition runtime."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import cast

from industrial_phm.application.acquisition_telemetry import (
    AcquisitionFailureComponent,
    AcquisitionFailureTelemetry,
    AcquisitionFlowTelemetry,
    AcquisitionHistoryTelemetry,
    AcquisitionSessionTelemetry,
    AcquisitionTelemetrySnapshot,
    AcquisitionWindowTelemetry,
    CollectionServiceRuntimeState,
    CollectionServiceRuntimeTelemetry,
)
from industrial_phm.application.history_writer import SpoolHistoryBatchWriteResult
from industrial_phm.application.observation_window import ObservationWindowEventDisposition
from industrial_phm.application.opcua_persistent import (
    OpcUaPersistentDataChangeEvent,
    OpcUaPersistentSessionEvidence,
    OpcUaPersistentSessionState,
)
from industrial_phm.application.window_coordinator import (
    ObservationWindowCoordinatorCycleResult,
)

_SCHEMA_VERSION = "industrial-phm-acquisition-telemetry-v1"
_SESSION = "session"
_FLOW = "flow"
_HISTORY = "history"
_WINDOW = "window"
_FAILURE = "failure"
_CONFIG = "config"


class AcquisitionTelemetryFormatError(ValueError):
    """Raised when durable telemetry payload/schema is malformed or unsupported."""


class SqliteAcquisitionTelemetryRepository:
    """Multi-process-friendly latest telemetry, separate from data-plane truth."""

    def __init__(self, path: Path, *, busy_timeout_ms: int = 5_000) -> None:
        if not isinstance(path, Path):
            raise ValueError("path must be pathlib.Path")
        _validate_positive_int(busy_timeout_ms, "busy_timeout_ms")
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

    def get(self, source_id: str) -> AcquisitionTelemetrySnapshot:
        _validate_identifier(source_id, "source_id")
        connection = self._connect()
        try:
            self._ensure_schema(connection)
            rows = connection.execute(
                """
                SELECT component, payload_json
                FROM telemetry_component
                WHERE source_id = ?
                """,
                (source_id,),
            ).fetchall()
        finally:
            connection.close()
        payloads = {
            _require_str(component, "component"): _require_mapping_json(
                _require_str(payload_json, "payload_json")
            )
            for component, payload_json in rows
        }
        return AcquisitionTelemetrySnapshot(
            source_id=source_id,
            session=(None if _SESSION not in payloads else _parse_session(payloads[_SESSION])),
            flow=None if _FLOW not in payloads else _parse_flow(payloads[_FLOW]),
            history=(None if _HISTORY not in payloads else _parse_history(payloads[_HISTORY])),
            window=(None if _WINDOW not in payloads else _parse_window(payloads[_WINDOW])),
            failure=(None if _FAILURE not in payloads else _parse_failure(payloads[_FAILURE])),
        )

    def list_snapshots(self) -> tuple[AcquisitionTelemetrySnapshot, ...]:
        connection = self._connect()
        try:
            self._ensure_schema(connection)
            rows = connection.execute(
                "SELECT DISTINCT source_id FROM telemetry_component ORDER BY source_id"
            ).fetchall()
        finally:
            connection.close()
        return tuple(self.get(_require_str(row[0], "source_id")) for row in rows)

    def get_collection_service_runtime(self) -> CollectionServiceRuntimeTelemetry | None:
        connection = self._connect()
        try:
            self._ensure_schema(connection)
            row = connection.execute(
                """
                SELECT payload_json
                FROM collection_service_runtime
                WHERE singleton_id = 1
                """
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return _parse_collection_service_runtime(
            _require_mapping_json(_require_str(row[0], "payload_json"))
        )

    def record_collection_service_start(
        self,
        *,
        started_at: datetime,
    ) -> None:
        _validate_aware_datetime(started_at, "started_at")
        self._write_collection_service_runtime(
            CollectionServiceRuntimeTelemetry(
                state=CollectionServiceRuntimeState.RUNNING,
                started_at=started_at,
                heartbeat_at=started_at,
                reconcile_count=0,
                owned_source_count=0,
            )
        )

    def record_collection_service_heartbeat(
        self,
        *,
        heartbeat_at: datetime,
        reconcile_count: int,
        owned_source_count: int,
    ) -> None:
        _validate_aware_datetime(heartbeat_at, "heartbeat_at")
        _validate_non_negative_int(reconcile_count, "reconcile_count")
        _validate_non_negative_int(owned_source_count, "owned_source_count")
        current = self.get_collection_service_runtime()
        if current is None:
            raise ValueError("collection service runtime has not been started")
        if heartbeat_at < current.heartbeat_at:
            raise ValueError("collection service heartbeat must not move backwards")
        self._write_collection_service_runtime(
            CollectionServiceRuntimeTelemetry(
                state=CollectionServiceRuntimeState.RUNNING,
                started_at=current.started_at,
                heartbeat_at=heartbeat_at,
                reconcile_count=reconcile_count,
                owned_source_count=owned_source_count,
                last_failure_at=current.last_failure_at,
                last_failure=current.last_failure,
            )
        )

    def record_collection_service_failure(
        self,
        detail: str,
        *,
        occurred_at: datetime,
    ) -> None:
        _validate_detail(detail, "detail")
        _validate_aware_datetime(occurred_at, "occurred_at")
        current = self.get_collection_service_runtime()
        if current is None:
            raise ValueError("collection service runtime has not been started")
        if occurred_at < current.heartbeat_at:
            raise ValueError("collection service failure time must not move backwards")
        self._write_collection_service_runtime(
            CollectionServiceRuntimeTelemetry(
                state=CollectionServiceRuntimeState.FAILED,
                started_at=current.started_at,
                heartbeat_at=occurred_at,
                reconcile_count=current.reconcile_count,
                owned_source_count=current.owned_source_count,
                last_failure_at=occurred_at,
                last_failure=detail,
            )
        )

    def record_collection_service_stop(
        self,
        *,
        stopped_at: datetime,
        reconcile_count: int,
    ) -> None:
        _validate_aware_datetime(stopped_at, "stopped_at")
        _validate_non_negative_int(reconcile_count, "reconcile_count")
        current = self.get_collection_service_runtime()
        if current is None:
            raise ValueError("collection service runtime has not been started")
        if stopped_at < current.heartbeat_at:
            raise ValueError("collection service stop time must not move backwards")
        self._write_collection_service_runtime(
            CollectionServiceRuntimeTelemetry(
                state=CollectionServiceRuntimeState.STOPPED,
                started_at=current.started_at,
                heartbeat_at=stopped_at,
                reconcile_count=reconcile_count,
                owned_source_count=0,
                last_failure_at=current.last_failure_at,
                last_failure=current.last_failure,
            )
        )

    def record_session_configuration(
        self,
        source_id: str,
        *,
        callback_queue_maxsize: int,
        recorded_at: datetime,
    ) -> None:
        _validate_identifier(source_id, "source_id")
        _validate_positive_int(callback_queue_maxsize, "callback_queue_maxsize")
        _validate_aware_datetime(recorded_at, "recorded_at")
        self._write_component(
            source_id,
            _CONFIG,
            recorded_at,
            {
                "callback_queue_maxsize": callback_queue_maxsize,
                "recorded_at": recorded_at.isoformat(),
            },
        )

    def record_session_evidence(
        self,
        evidence: OpcUaPersistentSessionEvidence,
    ) -> None:
        if not isinstance(evidence, OpcUaPersistentSessionEvidence):
            raise ValueError("evidence must be OpcUaPersistentSessionEvidence")

        current = self.get(evidence.source_id).session
        queue_maxsize = self._configured_queue_maxsize(evidence.source_id)

        is_new_worker = evidence.state == OpcUaPersistentSessionState.DISCONNECTED
        if is_new_worker:
            session = AcquisitionSessionTelemetry(
                source_id=evidence.source_id,
                worker_started_at=evidence.changed_at,
                state=evidence.state,
                state_changed_at=evidence.changed_at,
                connection_epoch=evidence.connection_epoch,
                reconnect_attempt_index=evidence.reconnect_attempt_index,
                callback_queue_overflow_count=0,
                callback_queue_maxsize=queue_maxsize,
                detail=evidence.detail,
            )
            self._write_component(
                evidence.source_id,
                _SESSION,
                evidence.changed_at,
                _serialize_session(session),
            )
            self._write_component(
                evidence.source_id,
                _FLOW,
                evidence.changed_at,
                _serialize_flow(
                    AcquisitionFlowTelemetry(
                        source_id=evidence.source_id,
                        worker_started_at=evidence.changed_at,
                        accepted_event_count=0,
                        replayed_event_count=0,
                        bad_status_event_count=0,
                        updated_at=evidence.changed_at,
                    )
                ),
            )
            return

        if current is None:
            raise ValueError("session telemetry must begin with DISCONNECTED evidence")
        if evidence.changed_at < current.state_changed_at:
            raise ValueError("session evidence changed_at must not move backwards")

        connected_since: datetime | None = None
        last_disconnect_at = current.last_disconnect_at
        if evidence.state == OpcUaPersistentSessionState.CONNECTED:
            connected_since = (
                current.connected_since
                if current.state == OpcUaPersistentSessionState.CONNECTED
                else evidence.changed_at
            )
        if (
            evidence.state == OpcUaPersistentSessionState.RECONNECT_WAIT
            and current.state == OpcUaPersistentSessionState.CONNECTED
        ):
            last_disconnect_at = evidence.changed_at

        session = AcquisitionSessionTelemetry(
            source_id=evidence.source_id,
            worker_started_at=current.worker_started_at,
            state=evidence.state,
            state_changed_at=evidence.changed_at,
            connection_epoch=evidence.connection_epoch,
            reconnect_attempt_index=evidence.reconnect_attempt_index,
            callback_queue_overflow_count=current.callback_queue_overflow_count,
            connected_since=connected_since,
            last_disconnect_at=last_disconnect_at,
            detail=evidence.detail,
            callback_queue_maxsize=(
                queue_maxsize if queue_maxsize is not None else current.callback_queue_maxsize
            ),
            callback_queue_depth=current.callback_queue_depth,
            callback_queue_high_watermark=current.callback_queue_high_watermark,
        )
        self._write_component(
            evidence.source_id,
            _SESSION,
            evidence.changed_at,
            _serialize_session(session),
        )

    def record_callback_queue_overflow(
        self,
        source_id: str,
        *,
        occurred_at: datetime,
    ) -> None:
        _validate_identifier(source_id, "source_id")
        _validate_aware_datetime(occurred_at, "occurred_at")
        current = self.get(source_id).session
        if current is None:
            raise ValueError("queue overflow telemetry requires session telemetry")
        if occurred_at < current.state_changed_at:
            raise ValueError("queue overflow occurred_at must not predate current session state")
        session = AcquisitionSessionTelemetry(
            source_id=current.source_id,
            worker_started_at=current.worker_started_at,
            state=current.state,
            state_changed_at=current.state_changed_at,
            connection_epoch=current.connection_epoch,
            reconnect_attempt_index=current.reconnect_attempt_index,
            callback_queue_overflow_count=current.callback_queue_overflow_count + 1,
            connected_since=current.connected_since,
            last_disconnect_at=current.last_disconnect_at,
            detail=current.detail,
            callback_queue_maxsize=current.callback_queue_maxsize,
            callback_queue_depth=current.callback_queue_depth,
            callback_queue_high_watermark=current.callback_queue_high_watermark,
        )
        self._write_component(
            source_id,
            _SESSION,
            occurred_at,
            _serialize_session(session),
        )

    def record_opcua_event(self, event: OpcUaPersistentDataChangeEvent) -> None:
        if not isinstance(event, OpcUaPersistentDataChangeEvent):
            raise ValueError("event must be OpcUaPersistentDataChangeEvent")
        source_id = event.source_id
        snapshot = self.get(source_id)
        session = snapshot.session
        if session is None:
            raise ValueError("OPC UA flow telemetry requires session telemetry")
        current = snapshot.flow
        if current is None:
            current = AcquisitionFlowTelemetry(
                source_id=source_id,
                worker_started_at=session.worker_started_at,
                accepted_event_count=0,
                replayed_event_count=0,
                bad_status_event_count=0,
                updated_at=session.worker_started_at,
            )
        identity = event.local_delivery_identity
        if current.last_delivery_identity == identity:
            return
        if current.last_delivery_identity is not None:
            current_epoch = current.last_delivery_identity[1:]
            next_epoch = identity[1:]
            if next_epoch < current_epoch:
                raise ValueError("OPC UA delivery identity must not regress within one worker")

        observation = event.event.notification.observation
        source_timestamp = (
            observation.source_timestamp
            if observation.source_timestamp is not None
            else current.last_source_timestamp
        )
        flow = AcquisitionFlowTelemetry(
            source_id=source_id,
            worker_started_at=current.worker_started_at,
            accepted_event_count=current.accepted_event_count + 1,
            replayed_event_count=(
                current.replayed_event_count + int(event.event.notification.replayed)
            ),
            bad_status_event_count=(
                current.bad_status_event_count + int(not observation.status_good)
            ),
            updated_at=event.event_time.ingested_at,
            last_delivery_identity=identity,
            last_source_timestamp=source_timestamp,
            last_received_at=observation.received_at,
            last_ingested_at=event.event_time.ingested_at,
        )
        self._write_component(
            source_id,
            _FLOW,
            flow.updated_at,
            _serialize_flow(flow),
        )

    def record_history_batch(
        self,
        result: SpoolHistoryBatchWriteResult,
        *,
        source_event_counts: Mapping[str, int],
    ) -> None:
        if not isinstance(result, SpoolHistoryBatchWriteResult):
            raise ValueError("result must be SpoolHistoryBatchWriteResult")
        if not source_event_counts:
            raise ValueError("source_event_counts must not be empty")
        total = 0
        for source_id, count in source_event_counts.items():
            _validate_identifier(source_id, "source_event_counts source_id")
            _validate_positive_int(count, "source_event_counts count")
            total += count
        if total != result.event_count:
            raise ValueError("source_event_counts must sum to result.event_count")

        for source_id, count in source_event_counts.items():
            telemetry = AcquisitionHistoryTelemetry(
                source_id=source_id,
                batch_id=result.batch_id,
                snapshot_id=result.snapshot_id,
                batch_event_count=result.event_count,
                source_event_count=count,
                committed_at=result.commit.committed_at,
                acknowledged_at=result.acknowledged_at,
                recovered_existing_commit=result.recovered_existing_commit,
            )
            self._write_component(
                source_id,
                _HISTORY,
                result.acknowledged_at,
                _serialize_history(telemetry),
            )

    def record_window_cycle(
        self,
        cycle: ObservationWindowCoordinatorCycleResult,
        *,
        recorded_at: datetime,
    ) -> None:
        if not isinstance(cycle, ObservationWindowCoordinatorCycleResult):
            raise ValueError("cycle must be ObservationWindowCoordinatorCycleResult")
        _validate_aware_datetime(recorded_at, "recorded_at")
        last_window = (
            None
            if not cycle.finalized_windows
            else max(
                cycle.finalized_windows,
                key=lambda item: (item.window_end, item.window_id),
            )
        )
        telemetry = AcquisitionWindowTelemetry(
            source_id=cycle.source_id,
            updated_at=recorded_at,
            watermark=cycle.watermark,
            active_window_count=cycle.active_window_count,
            finalized_window_count=cycle.finalized_window_count,
            historical_event_count=cycle.historical_event_count,
            in_order_count=cycle.disposition_count(ObservationWindowEventDisposition.IN_ORDER),
            out_of_order_count=cycle.disposition_count(
                ObservationWindowEventDisposition.OUT_OF_ORDER
            ),
            late_count=cycle.disposition_count(ObservationWindowEventDisposition.LATE),
            timing_unavailable_count=cycle.disposition_count(
                ObservationWindowEventDisposition.TIMING_UNAVAILABLE
            ),
            unexpected_channel_count=cycle.disposition_count(
                ObservationWindowEventDisposition.UNEXPECTED_CHANNEL
            ),
            future_timestamp_count=cycle.disposition_count(
                ObservationWindowEventDisposition.FUTURE_TIMESTAMP
            ),
            buffer_full_count=cycle.disposition_count(
                ObservationWindowEventDisposition.BUFFER_FULL
            ),
            duplicate_count=cycle.disposition_count(ObservationWindowEventDisposition.DUPLICATE),
            last_finalized_window_id=(None if last_window is None else last_window.window_id),
            last_finalized_window_end=(None if last_window is None else last_window.window_end),
        )
        self._write_component(
            cycle.source_id,
            _WINDOW,
            recorded_at,
            _serialize_window(telemetry),
        )

    def record_failure(self, failure: AcquisitionFailureTelemetry) -> None:
        if not isinstance(failure, AcquisitionFailureTelemetry):
            raise ValueError("failure must be AcquisitionFailureTelemetry")
        self._write_component(
            failure.source_id,
            _FAILURE,
            failure.occurred_at,
            _serialize_failure(failure),
        )

    def _write_collection_service_runtime(
        self,
        value: CollectionServiceRuntimeTelemetry,
    ) -> None:
        payload = _serialize_collection_service_runtime(value)
        rendered = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        connection = self._connect()
        try:
            self._ensure_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                """
                SELECT updated_at, payload_json
                FROM collection_service_runtime
                WHERE singleton_id = 1
                """
            ).fetchone()
            if current is not None:
                current_at = _parse_datetime(
                    _require_str(current[0], "updated_at"),
                    "updated_at",
                )
                current_payload = _require_str(current[1], "payload_json")
                if value.heartbeat_at < current_at:
                    raise ValueError("collection service runtime heartbeat must not move backwards")
                if value.heartbeat_at == current_at and rendered == current_payload:
                    connection.execute("COMMIT")
                    return
            connection.execute(
                """
                INSERT INTO collection_service_runtime(
                    singleton_id, updated_at, payload_json
                ) VALUES (1, ?, ?)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    payload_json = excluded.payload_json
                """,
                (value.heartbeat_at.isoformat(), rendered),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def _configured_queue_maxsize(self, source_id: str) -> int | None:
        row = self._read_component(source_id, _CONFIG)
        if row is None:
            return None
        payload = row[1]
        value = payload.get("callback_queue_maxsize")
        return _require_int(value, "callback_queue_maxsize")

    def _read_component(
        self,
        source_id: str,
        component: str,
    ) -> tuple[datetime, Mapping[str, object]] | None:
        connection = self._connect()
        try:
            self._ensure_schema(connection)
            row = connection.execute(
                """
                SELECT updated_at, payload_json
                FROM telemetry_component
                WHERE source_id = ? AND component = ?
                """,
                (source_id, component),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return (
            _parse_datetime(_require_str(row[0], "updated_at"), "updated_at"),
            _require_mapping_json(_require_str(row[1], "payload_json")),
        )

    def _write_component(
        self,
        source_id: str,
        component: str,
        updated_at: datetime,
        payload: Mapping[str, object],
    ) -> None:
        _validate_identifier(source_id, "source_id")
        _validate_identifier(component, "component")
        _validate_aware_datetime(updated_at, "updated_at")
        rendered = json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        connection = self._connect()
        try:
            self._ensure_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                """
                SELECT updated_at, payload_json
                FROM telemetry_component
                WHERE source_id = ? AND component = ?
                """,
                (source_id, component),
            ).fetchone()
            if current is not None:
                current_at = _parse_datetime(
                    _require_str(current[0], "updated_at"),
                    "updated_at",
                )
                current_payload = _require_str(current[1], "payload_json")
                if updated_at < current_at:
                    raise ValueError(f"{component} telemetry updated_at must not move backwards")
                if updated_at == current_at:
                    if rendered != current_payload:
                        raise ValueError(
                            f"{component} telemetry with the same updated_at must match"
                        )
                    connection.execute("COMMIT")
                    return

            connection.execute(
                """
                INSERT INTO telemetry_component (
                    source_id, component, updated_at, payload_json
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(source_id, component) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    payload_json = excluded.payload_json
                """,
                (source_id, component, updated_at.isoformat(), rendered),
            )
            connection.execute("COMMIT")
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

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
            CREATE TABLE IF NOT EXISTS telemetry_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        schema = connection.execute(
            "SELECT value FROM telemetry_metadata WHERE key = 'schema'"
        ).fetchone()
        if schema is None:
            connection.execute(
                "INSERT INTO telemetry_metadata (key, value) VALUES ('schema', ?)",
                (_SCHEMA_VERSION,),
            )
        elif schema[0] != _SCHEMA_VERSION:
            raise AcquisitionTelemetryFormatError(
                f"unsupported acquisition telemetry schema: {schema[0]!r}"
            )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS collection_service_runtime (
                singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
                updated_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS telemetry_component (
                source_id TEXT NOT NULL,
                component TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (source_id, component)
            )
            """
        )
        connection.commit()


def _serialize_collection_service_runtime(
    value: CollectionServiceRuntimeTelemetry,
) -> dict[str, object]:
    return {
        "state": value.state.value,
        "started_at": value.started_at.isoformat(),
        "heartbeat_at": value.heartbeat_at.isoformat(),
        "reconcile_count": value.reconcile_count,
        "owned_source_count": value.owned_source_count,
        "last_failure_at": _format_optional_datetime(value.last_failure_at),
        "last_failure": value.last_failure,
    }


def _parse_collection_service_runtime(
    value: Mapping[str, object],
) -> CollectionServiceRuntimeTelemetry:
    return CollectionServiceRuntimeTelemetry(
        state=CollectionServiceRuntimeState(
            _require_str(value.get("state"), "state")
        ),
        started_at=_require_datetime(value.get("started_at"), "started_at"),
        heartbeat_at=_require_datetime(value.get("heartbeat_at"), "heartbeat_at"),
        reconcile_count=_require_int(value.get("reconcile_count"), "reconcile_count"),
        owned_source_count=_require_int(
            value.get("owned_source_count"),
            "owned_source_count",
        ),
        last_failure_at=_optional_datetime(
            value.get("last_failure_at"),
            "last_failure_at",
        ),
        last_failure=_optional_str(value.get("last_failure"), "last_failure"),
    )


def _serialize_session(value: AcquisitionSessionTelemetry) -> dict[str, object]:
    return {
        "source_id": value.source_id,
        "worker_started_at": value.worker_started_at.isoformat(),
        "state": value.state.value,
        "state_changed_at": value.state_changed_at.isoformat(),
        "connection_epoch": value.connection_epoch,
        "reconnect_attempt_index": value.reconnect_attempt_index,
        "callback_queue_overflow_count": value.callback_queue_overflow_count,
        "connected_since": _format_optional_datetime(value.connected_since),
        "last_disconnect_at": _format_optional_datetime(value.last_disconnect_at),
        "detail": value.detail,
        "callback_queue_maxsize": value.callback_queue_maxsize,
        "callback_queue_depth": value.callback_queue_depth,
        "callback_queue_high_watermark": value.callback_queue_high_watermark,
    }


def _parse_session(value: Mapping[str, object]) -> AcquisitionSessionTelemetry:
    return AcquisitionSessionTelemetry(
        source_id=_require_str(value.get("source_id"), "source_id"),
        worker_started_at=_require_datetime(
            value.get("worker_started_at"),
            "worker_started_at",
        ),
        state=OpcUaPersistentSessionState(_require_str(value.get("state"), "state")),
        state_changed_at=_require_datetime(
            value.get("state_changed_at"),
            "state_changed_at",
        ),
        connection_epoch=_require_int(
            value.get("connection_epoch"),
            "connection_epoch",
        ),
        reconnect_attempt_index=_require_int(
            value.get("reconnect_attempt_index"),
            "reconnect_attempt_index",
        ),
        callback_queue_overflow_count=_require_int(
            value.get("callback_queue_overflow_count"),
            "callback_queue_overflow_count",
        ),
        connected_since=_optional_datetime(
            value.get("connected_since"),
            "connected_since",
        ),
        last_disconnect_at=_optional_datetime(
            value.get("last_disconnect_at"),
            "last_disconnect_at",
        ),
        detail=_optional_str(value.get("detail"), "detail"),
        callback_queue_maxsize=_optional_int(
            value.get("callback_queue_maxsize"),
            "callback_queue_maxsize",
        ),
        callback_queue_depth=_optional_int(
            value.get("callback_queue_depth"),
            "callback_queue_depth",
        ),
        callback_queue_high_watermark=_optional_int(
            value.get("callback_queue_high_watermark"),
            "callback_queue_high_watermark",
        ),
    )


def _serialize_flow(value: AcquisitionFlowTelemetry) -> dict[str, object]:
    return {
        "source_id": value.source_id,
        "worker_started_at": value.worker_started_at.isoformat(),
        "accepted_event_count": value.accepted_event_count,
        "replayed_event_count": value.replayed_event_count,
        "bad_status_event_count": value.bad_status_event_count,
        "updated_at": value.updated_at.isoformat(),
        "last_delivery_identity": (
            None if value.last_delivery_identity is None else list(value.last_delivery_identity)
        ),
        "last_source_timestamp": _format_optional_datetime(value.last_source_timestamp),
        "last_received_at": _format_optional_datetime(value.last_received_at),
        "last_ingested_at": _format_optional_datetime(value.last_ingested_at),
    }


def _parse_flow(value: Mapping[str, object]) -> AcquisitionFlowTelemetry:
    identity_raw = value.get("last_delivery_identity")
    identity: tuple[str, int, int] | None
    if identity_raw is None:
        identity = None
    else:
        if not isinstance(identity_raw, list) or len(identity_raw) != 3:
            raise AcquisitionTelemetryFormatError(
                "last_delivery_identity must be a 3-item array or null"
            )
        identity = (
            _require_str(identity_raw[0], "last_delivery_identity[0]"),
            _require_int(identity_raw[1], "last_delivery_identity[1]"),
            _require_int(identity_raw[2], "last_delivery_identity[2]"),
        )
    return AcquisitionFlowTelemetry(
        source_id=_require_str(value.get("source_id"), "source_id"),
        worker_started_at=_require_datetime(
            value.get("worker_started_at"),
            "worker_started_at",
        ),
        accepted_event_count=_require_int(
            value.get("accepted_event_count"),
            "accepted_event_count",
        ),
        replayed_event_count=_require_int(
            value.get("replayed_event_count"),
            "replayed_event_count",
        ),
        bad_status_event_count=_require_int(
            value.get("bad_status_event_count"),
            "bad_status_event_count",
        ),
        updated_at=_require_datetime(value.get("updated_at"), "updated_at"),
        last_delivery_identity=identity,
        last_source_timestamp=_optional_datetime(
            value.get("last_source_timestamp"),
            "last_source_timestamp",
        ),
        last_received_at=_optional_datetime(
            value.get("last_received_at"),
            "last_received_at",
        ),
        last_ingested_at=_optional_datetime(
            value.get("last_ingested_at"),
            "last_ingested_at",
        ),
    )


def _serialize_history(value: AcquisitionHistoryTelemetry) -> dict[str, object]:
    return {
        "source_id": value.source_id,
        "batch_id": value.batch_id,
        "snapshot_id": value.snapshot_id,
        "batch_event_count": value.batch_event_count,
        "source_event_count": value.source_event_count,
        "committed_at": value.committed_at.isoformat(),
        "acknowledged_at": value.acknowledged_at.isoformat(),
        "recovered_existing_commit": value.recovered_existing_commit,
    }


def _parse_history(value: Mapping[str, object]) -> AcquisitionHistoryTelemetry:
    return AcquisitionHistoryTelemetry(
        source_id=_require_str(value.get("source_id"), "source_id"),
        batch_id=_require_str(value.get("batch_id"), "batch_id"),
        snapshot_id=_require_int(value.get("snapshot_id"), "snapshot_id"),
        batch_event_count=_require_int(
            value.get("batch_event_count"),
            "batch_event_count",
        ),
        source_event_count=_require_int(
            value.get("source_event_count"),
            "source_event_count",
        ),
        committed_at=_require_datetime(value.get("committed_at"), "committed_at"),
        acknowledged_at=_require_datetime(
            value.get("acknowledged_at"),
            "acknowledged_at",
        ),
        recovered_existing_commit=_require_bool(
            value.get("recovered_existing_commit"),
            "recovered_existing_commit",
        ),
    )


def _serialize_window(value: AcquisitionWindowTelemetry) -> dict[str, object]:
    return {
        "source_id": value.source_id,
        "updated_at": value.updated_at.isoformat(),
        "watermark": _format_optional_datetime(value.watermark),
        "active_window_count": value.active_window_count,
        "finalized_window_count": value.finalized_window_count,
        "historical_event_count": value.historical_event_count,
        "in_order_count": value.in_order_count,
        "out_of_order_count": value.out_of_order_count,
        "late_count": value.late_count,
        "timing_unavailable_count": value.timing_unavailable_count,
        "unexpected_channel_count": value.unexpected_channel_count,
        "future_timestamp_count": value.future_timestamp_count,
        "buffer_full_count": value.buffer_full_count,
        "duplicate_count": value.duplicate_count,
        "last_finalized_window_id": value.last_finalized_window_id,
        "last_finalized_window_end": _format_optional_datetime(value.last_finalized_window_end),
    }


def _parse_window(value: Mapping[str, object]) -> AcquisitionWindowTelemetry:
    return AcquisitionWindowTelemetry(
        source_id=_require_str(value.get("source_id"), "source_id"),
        updated_at=_require_datetime(value.get("updated_at"), "updated_at"),
        watermark=_optional_datetime(value.get("watermark"), "watermark"),
        active_window_count=_require_int(
            value.get("active_window_count"),
            "active_window_count",
        ),
        finalized_window_count=_require_int(
            value.get("finalized_window_count"),
            "finalized_window_count",
        ),
        historical_event_count=_require_int(
            value.get("historical_event_count"),
            "historical_event_count",
        ),
        in_order_count=_require_int(value.get("in_order_count"), "in_order_count"),
        out_of_order_count=_require_int(
            value.get("out_of_order_count"),
            "out_of_order_count",
        ),
        late_count=_require_int(value.get("late_count"), "late_count"),
        timing_unavailable_count=_require_int(
            value.get("timing_unavailable_count"),
            "timing_unavailable_count",
        ),
        unexpected_channel_count=_require_int(
            value.get("unexpected_channel_count"),
            "unexpected_channel_count",
        ),
        future_timestamp_count=_require_int(
            value.get("future_timestamp_count"),
            "future_timestamp_count",
        ),
        buffer_full_count=_require_int(
            value.get("buffer_full_count"),
            "buffer_full_count",
        ),
        duplicate_count=_require_int(
            value.get("duplicate_count"),
            "duplicate_count",
        ),
        last_finalized_window_id=_optional_str(
            value.get("last_finalized_window_id"),
            "last_finalized_window_id",
        ),
        last_finalized_window_end=_optional_datetime(
            value.get("last_finalized_window_end"),
            "last_finalized_window_end",
        ),
    )


def _serialize_failure(value: AcquisitionFailureTelemetry) -> dict[str, object]:
    return {
        "source_id": value.source_id,
        "component": value.component.value,
        "occurred_at": value.occurred_at.isoformat(),
        "detail": value.detail,
    }


def _parse_failure(value: Mapping[str, object]) -> AcquisitionFailureTelemetry:
    return AcquisitionFailureTelemetry(
        source_id=_require_str(value.get("source_id"), "source_id"),
        component=AcquisitionFailureComponent(_require_str(value.get("component"), "component")),
        occurred_at=_require_datetime(value.get("occurred_at"), "occurred_at"),
        detail=_require_str(value.get("detail"), "detail"),
    )


def _require_mapping_json(value: str) -> Mapping[str, object]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise AcquisitionTelemetryFormatError(
            "telemetry payload_json must contain valid JSON"
        ) from error
    if not isinstance(parsed, dict):
        raise AcquisitionTelemetryFormatError("telemetry payload_json must contain a JSON object")
    return cast(Mapping[str, object], parsed)


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise AcquisitionTelemetryFormatError(f"{field_name} must be a string")
    return value


def _optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_str(value, field_name)


def _require_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AcquisitionTelemetryFormatError(f"{field_name} must be an integer")
    return value


def _optional_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _require_int(value, field_name)


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise AcquisitionTelemetryFormatError(f"{field_name} must be boolean")
    return value


def _require_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise AcquisitionTelemetryFormatError(f"{field_name} must be an ISO datetime string")
    return _parse_datetime(value, field_name)


def _optional_datetime(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _require_datetime(value, field_name)


def _parse_datetime(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise AcquisitionTelemetryFormatError(f"{field_name} must be valid ISO datetime") from error
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


def _validate_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be at least 1")
