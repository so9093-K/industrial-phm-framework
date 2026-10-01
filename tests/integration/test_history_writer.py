from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from industrial_phm.application import (
    HistoricalBatchAppendResult,
    HistoricalBatchCommit,
    HistoryIngestionMode,
    OpcUaEventTimePolicy,
    RegisteredOpcUaDataChangeEvent,
    SpoolToHistoryWriterPolicy,
)
from industrial_phm.connectors import (
    OpcUaNodeObservation,
    OpcUaSubscriptionNotification,
)
from industrial_phm.runtime import (
    SqliteAcquisitionSpool,
    SqliteAcquisitionSpoolConfig,
    SqliteAcquisitionTelemetryRepository,
    write_next_spool_batch,
)

BASE = datetime(2026, 9, 28, 3, 0, tzinfo=UTC)


class _FakeHistory:
    def __init__(self) -> None:
        self.commits: dict[str, tuple[tuple[object, ...], HistoricalBatchCommit]] = {}
        self.fail_append = False

    def get_opcua_batch_commit(
        self,
        events,
        *,
        batch_id: str,
        ingestion_mode: HistoryIngestionMode = HistoryIngestionMode.LIVE,
    ) -> HistoricalBatchCommit | None:
        del ingestion_mode
        stored = self.commits.get(batch_id)
        if stored is None:
            return None
        stored_events, commit = stored
        if tuple(events) != stored_events:
            raise ValueError("batch content conflict")
        return commit

    def append_or_recover_opcua_batch(
        self,
        events,
        *,
        batch_id: str,
        ingestion_mode: HistoryIngestionMode = HistoryIngestionMode.LIVE,
    ) -> HistoricalBatchAppendResult:
        existing = self.get_opcua_batch_commit(
            events,
            batch_id=batch_id,
            ingestion_mode=ingestion_mode,
        )
        if existing is not None:
            return HistoricalBatchAppendResult(
                commit=existing,
                recovered_existing_commit=True,
            )
        commit = self.append_opcua_batch(
            events,
            batch_id=batch_id,
            ingestion_mode=ingestion_mode,
        )
        return HistoricalBatchAppendResult(
            commit=commit,
            recovered_existing_commit=False,
        )

    def append_opcua_batch(
        self,
        events,
        *,
        batch_id: str,
        ingestion_mode: HistoryIngestionMode = HistoryIngestionMode.LIVE,
    ) -> HistoricalBatchCommit:
        del ingestion_mode
        if self.fail_append:
            raise RuntimeError("history unavailable")
        commit = HistoricalBatchCommit(
            batch_id=batch_id,
            snapshot_id=len(self.commits) + 1,
            event_count=len(tuple(events)),
            committed_at=BASE + timedelta(seconds=2),
        )
        self.commits[batch_id] = (tuple(events), commit)
        return commit


def _registered_event(
    *,
    event_index: int = 0,
    channel_id: str = "vibration_x",
) -> RegisteredOpcUaDataChangeEvent:
    received_at = BASE + timedelta(seconds=event_index + 1)
    return RegisteredOpcUaDataChangeEvent(
        source_id="source-a",
        asset_id="pump-01",
        endpoint_url="opc.tcp://127.0.0.1:4840",
        measurement_point_id="drive-end",
        collection_index=event_index,
        notification=OpcUaSubscriptionNotification(
            observation=OpcUaNodeObservation(
                channel_id=channel_id,
                node_id=f"ns=2;s={channel_id}",
                value=float(event_index + 1),
                status_code=0,
                status_good=True,
                status_text="Good",
                variant_type="Double",
                source_timestamp=received_at - timedelta(milliseconds=20),
                server_timestamp=received_at - timedelta(milliseconds=10),
                received_at=received_at,
            ),
            replayed=False,
        ),
    )


def _spool(path: Path) -> SqliteAcquisitionSpool:
    return SqliteAcquisitionSpool(SqliteAcquisitionSpoolConfig(path=path))


def _accept(
    spool: SqliteAcquisitionSpool,
    *,
    event_index: int = 0,
    channel_id: str = "vibration_x",
) -> None:
    received_at = BASE + timedelta(seconds=event_index + 1)
    spool.accept_opcua_event(
        _registered_event(event_index=event_index, channel_id=channel_id),
        connection_epoch=1,
        event_index=event_index,
        accepted_at=received_at + timedelta(milliseconds=5),
        event_time_policy=OpcUaEventTimePolicy(),
    )


def test_writer_waits_for_interval_then_commits_and_acknowledges(tmp_path: Path) -> None:
    spool = _spool(tmp_path / "spool.sqlite")
    history = _FakeHistory()
    telemetry = SqliteAcquisitionTelemetryRepository(tmp_path / "telemetry.sqlite")
    _accept(spool)

    policy = SpoolToHistoryWriterPolicy(
        max_events=10,
        max_bytes=10_000_000,
        max_interval_seconds=5.0,
        poll_interval_seconds=0.1,
    )

    assert (
        write_next_spool_batch(
            spool,
            history,
            policy=policy,
            batch_id_factory=lambda: "batch-001",
            now_fn=lambda: BASE + timedelta(seconds=2),
        )
        is None
    )
    assert spool.pending_event_count() == 1
    assert spool.get_active_batch() is None

    result = write_next_spool_batch(
        spool,
        history,
        policy=policy,
        batch_id_factory=lambda: "batch-001",
        now_fn=lambda: BASE + timedelta(seconds=7),
        telemetry_recorder=telemetry,
    )
    assert result is not None
    assert result.batch_id == "batch-001"
    assert result.event_count == 1
    assert result.payload_bytes > 0
    assert result.recovered_existing_commit is False
    assert spool.pending_event_count() == 0
    history_telemetry = telemetry.get("source-a").history
    assert history_telemetry is not None
    assert history_telemetry.batch_id == "batch-001"
    assert history_telemetry.snapshot_id == 1
    assert history_telemetry.source_event_count == 1


def test_writer_flushes_when_byte_threshold_is_reached(tmp_path: Path) -> None:
    spool = _spool(tmp_path / "spool.sqlite")
    history = _FakeHistory()
    _accept(spool, event_index=0)
    _accept(spool, event_index=1, channel_id="temperature")

    result = write_next_spool_batch(
        spool,
        history,
        policy=SpoolToHistoryWriterPolicy(
            max_events=100,
            max_bytes=1,
            max_interval_seconds=60.0,
            poll_interval_seconds=0.1,
        ),
        batch_id_factory=lambda: "batch-byte-limit",
        now_fn=lambda: BASE + timedelta(seconds=3),
    )
    assert result is not None
    assert result.event_count == 1
    assert spool.pending_event_count() == 1


def test_writer_keeps_stable_active_batch_when_history_fails(tmp_path: Path) -> None:
    spool = _spool(tmp_path / "spool.sqlite")
    history = _FakeHistory()
    telemetry = SqliteAcquisitionTelemetryRepository(tmp_path / "telemetry.sqlite")
    history.fail_append = True
    _accept(spool)

    with pytest.raises(RuntimeError, match="history unavailable"):
        write_next_spool_batch(
            spool,
            history,
            policy=SpoolToHistoryWriterPolicy(max_events=1),
            batch_id_factory=lambda: "batch-stable",
            now_fn=lambda: BASE + timedelta(seconds=3),
            telemetry_recorder=telemetry,
        )

    active = spool.get_active_batch()
    assert active is not None
    assert active.batch_id == "batch-stable"
    assert spool.pending_event_count() == 1
    failure = telemetry.get("source-a").failure
    assert failure is not None
    assert failure.component.value == "history-writer"
    assert failure.detail == "RuntimeError: history unavailable"

    history.fail_append = False
    result = write_next_spool_batch(
        spool,
        history,
        policy=SpoolToHistoryWriterPolicy(max_events=1),
        batch_id_factory=lambda: "must-not-replace-active",
        now_fn=lambda: BASE + timedelta(seconds=4),
        telemetry_recorder=telemetry,
    )
    assert result is not None
    assert result.batch_id == "batch-stable"
    assert spool.pending_event_count() == 0
