from datetime import UTC, datetime, timedelta
from importlib.util import find_spec
from pathlib import Path

import pytest

from industrial_phm.application import (
    OpcUaEventTimePolicy,
    RegisteredOpcUaDataChangeEvent,
    SpoolToHistoryWriterPolicy,
)
from industrial_phm.connectors import (
    OpcUaNodeObservation,
    OpcUaSubscriptionNotification,
)
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime import (
    SqliteAcquisitionSpool,
    SqliteAcquisitionSpoolConfig,
    write_next_spool_batch,
)

BASE = datetime(2026, 9, 28, 4, 0, tzinfo=UTC)


def _require_duckdb() -> None:
    if find_spec("duckdb") is None:
        pytest.skip("DuckLake history runtime is not installed")


def _registered_event() -> RegisteredOpcUaDataChangeEvent:
    received_at = BASE + timedelta(seconds=1)
    return RegisteredOpcUaDataChangeEvent(
        source_id="source-a",
        asset_id="pump-01",
        endpoint_url="opc.tcp://127.0.0.1:4840",
        measurement_point_id="drive-end",
        collection_index=0,
        notification=OpcUaSubscriptionNotification(
            observation=OpcUaNodeObservation(
                channel_id="vibration_x",
                node_id="ns=2;s=vibration_x",
                value=12.5,
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


class _FailOnceAcknowledgeSpool:
    def __init__(self, delegate: SqliteAcquisitionSpool) -> None:
        self.delegate = delegate
        self.failed = False

    def accept_opcua_event(self, *args, **kwargs):
        return self.delegate.accept_opcua_event(*args, **kwargs)

    def assign_next_batch(self, **kwargs):
        return self.delegate.assign_next_batch(**kwargs)

    def pending_unassigned_stats(self):
        return self.delegate.pending_unassigned_stats()

    def pending_event_count(self) -> int:
        return self.delegate.pending_event_count()

    def get_active_batch(self):
        return self.delegate.get_active_batch()

    def acknowledge_batch(self, batch_id: str, *, acknowledged_at: datetime) -> int:
        if not self.failed:
            self.failed = True
            raise RuntimeError("simulated crash before spool ACK")
        return self.delegate.acknowledge_batch(
            batch_id,
            acknowledged_at=acknowledged_at,
        )


def test_writer_recovers_ducklake_commit_after_ack_crash_without_duplicate(
    tmp_path: Path,
) -> None:
    _require_duckdb()
    spool = SqliteAcquisitionSpool(
        SqliteAcquisitionSpoolConfig(path=tmp_path / "spool.sqlite")
    )
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(
            catalog_path=tmp_path / "catalog.sqlite",
            data_path=tmp_path / "data",
        )
    )
    accepted = spool.accept_opcua_event(
        _registered_event(),
        connection_epoch=1,
        event_index=0,
        accepted_at=BASE + timedelta(seconds=2),
        event_time_policy=OpcUaEventTimePolicy(),
    )
    failing_spool = _FailOnceAcknowledgeSpool(spool)
    policy = SpoolToHistoryWriterPolicy(max_events=1)

    with pytest.raises(RuntimeError, match="simulated crash"):
        write_next_spool_batch(
            failing_spool,
            history,
            policy=policy,
            batch_id_factory=lambda: "batch-crash-window",
            now_fn=lambda: BASE + timedelta(seconds=3),
        )

    active = spool.get_active_batch()
    assert active is not None
    assert active.batch_id == "batch-crash-window"
    assert active.events == (accepted,)
    committed_before_recovery = history.get_opcua_batch_commit(
        active.events,
        batch_id=active.batch_id,
    )
    assert committed_before_recovery is not None

    recovered = write_next_spool_batch(
        spool,
        history,
        policy=policy,
        batch_id_factory=lambda: "must-not-replace-active",
        now_fn=lambda: BASE + timedelta(seconds=4),
    )
    assert recovered is not None
    assert recovered.recovered_existing_commit is True
    assert recovered.commit == committed_before_recovery
    assert spool.pending_event_count() == 0
    assert spool.get_active_batch() is None

    measurements = history.query_measurements(
        "pump-01",
        start_at=BASE,
        end_at=BASE + timedelta(minutes=1),
    )
    assert len(measurements) == 1
    assert measurements[0].value == 12.5
