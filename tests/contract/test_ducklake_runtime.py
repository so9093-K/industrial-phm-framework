from datetime import UTC, datetime, timedelta
from importlib.util import find_spec

import pytest

from industrial_phm.application import (
    HistoricalBatchConflictError,
    HistoryIngestionMode,
    OpcUaEventTimePolicy,
    RegisteredOpcUaDataChangeEvent,
    project_opcua_persistent_data_change_event,
)
from industrial_phm.connectors import (
    OpcUaNodeObservation,
    OpcUaSubscriptionNotification,
)
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig

BASE = datetime(2026, 9, 28, 1, 0, tzinfo=UTC)


def _require_duckdb() -> None:
    if find_spec("duckdb") is None:
        pytest.skip("DuckLake history runtime is not installed")


def _event(
    *,
    channel_id: str,
    event_at: datetime,
    event_index: int,
    replayed: bool = False,
) -> object:
    received_at = event_at + timedelta(milliseconds=20)
    observation = OpcUaNodeObservation(
        channel_id=channel_id,
        node_id=f"ns=2;s={channel_id}",
        value=1.25 + event_index,
        status_code=0,
        status_good=True,
        status_text="Good",
        variant_type="Double",
        source_timestamp=event_at,
        server_timestamp=event_at + timedelta(milliseconds=5),
        received_at=received_at,
    )
    registered = RegisteredOpcUaDataChangeEvent(
        source_id="source-a",
        asset_id="pump-01",
        endpoint_url="opc.tcp://127.0.0.1:4840",
        measurement_point_id="drive-end",
        collection_index=event_index,
        notification=OpcUaSubscriptionNotification(
            observation=observation,
            replayed=replayed,
        ),
    )
    return project_opcua_persistent_data_change_event(
        registered,
        connection_epoch=2,
        event_index=event_index,
        ingested_at=received_at + timedelta(milliseconds=5),
        event_time_policy=OpcUaEventTimePolicy(
            allow_server_timestamp_fallback=True,
        ),
    )


def test_ducklake_asset_history_round_trip(tmp_path) -> None:
    _require_duckdb()
    repository = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(
            catalog_path=tmp_path / "catalog.sqlite",
            data_path=tmp_path / "data",
        )
    )
    repository.initialize()
    repository.initialize()

    first = _event(
        channel_id="vibration_x",
        event_at=BASE + timedelta(seconds=1),
        event_index=0,
    )
    second = _event(
        channel_id="temperature",
        event_at=BASE + timedelta(seconds=2),
        event_index=1,
        replayed=True,
    )

    commit = repository.append_opcua_batch(
        (first, second),
        batch_id="batch-1",
        ingestion_mode=HistoryIngestionMode.LIVE,
    )

    assert commit.event_count == 2
    assert commit.snapshot_id >= 0
    assert commit.committed_at.utcoffset() is not None
    assert (tmp_path / "catalog.sqlite").is_file()

    measurements = repository.query_measurements(
        "pump-01",
        start_at=BASE,
        end_at=BASE + timedelta(minutes=1),
    )
    assert [measurement.channel_id for measurement in measurements] == [
        "vibration_x",
        "temperature",
    ]
    assert all(
        measurement.ingestion_mode == HistoryIngestionMode.LIVE for measurement in measurements
    )

    restored_first = repository.get_opcua_event(
        "source-a",
        connection_epoch=2,
        event_index=0,
    )
    restored_second = repository.get_opcua_event(
        "source-a",
        connection_epoch=2,
        event_index=1,
    )
    assert restored_first == first
    assert restored_second == second
    assert restored_second.event.notification.replayed is True

    assert (
        repository.get_opcua_event(
            "source-a",
            connection_epoch=3,
            event_index=0,
        )
        is None
    )

    recovered = repository.get_opcua_batch_commit(
        (first, second),
        batch_id="batch-1",
        ingestion_mode=HistoryIngestionMode.LIVE,
    )
    assert recovered == commit

    repeated = repository.append_opcua_batch(
        (first, second),
        batch_id="batch-1",
        ingestion_mode=HistoryIngestionMode.LIVE,
    )
    assert repeated == commit

    changed_first = _event(
        channel_id="vibration_x",
        event_at=BASE + timedelta(seconds=10),
        event_index=0,
    )
    with pytest.raises(HistoricalBatchConflictError, match="commit provenance"):
        repository.append_opcua_batch(
            (changed_first, second),
            batch_id="batch-1",
            ingestion_mode=HistoryIngestionMode.LIVE,
        )

    with pytest.raises(ValueError, match="historical delivery already exists"):
        repository.append_opcua_batch(
            (first,),
            batch_id="batch-2",
            ingestion_mode=HistoryIngestionMode.LIVE,
        )


def test_ducklake_asset_history_backfill_provenance(tmp_path) -> None:
    _require_duckdb()
    repository = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(
            catalog_path=tmp_path / "catalog.sqlite",
            data_path=tmp_path / "data",
        )
    )
    event = _event(
        channel_id="vibration_x",
        event_at=BASE + timedelta(seconds=3),
        event_index=2,
    )

    repository.append_opcua_batch(
        (event,),
        batch_id="backfill-1",
        ingestion_mode=HistoryIngestionMode.BACKFILL,
    )

    measurement = repository.query_measurements(
        "pump-01",
        start_at=BASE,
        end_at=BASE + timedelta(minutes=1),
    )[0]
    assert measurement.ingestion_mode == HistoryIngestionMode.BACKFILL

    live = _event(
        channel_id="temperature",
        event_at=BASE + timedelta(seconds=4),
        event_index=3,
    )
    later_commit = repository.append_opcua_batch(
        (live,),
        batch_id="live-after-backfill",
        ingestion_mode=HistoryIngestionMode.LIVE,
    )
    recovered_backfill = repository.get_opcua_batch_commit(
        (event,),
        batch_id="backfill-1",
        ingestion_mode=HistoryIngestionMode.BACKFILL,
    )
    assert recovered_backfill is not None
    assert recovered_backfill.snapshot_id < later_commit.snapshot_id

