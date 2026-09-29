from datetime import UTC, datetime, timedelta
from importlib.util import find_spec

import pytest

from industrial_phm.application import (
    FileSourceConfig,
    HistoricalBatchConflictError,
    HistoryIngestionMode,
    InMemorySourceRepository,
    JsonSourceRepository,
    OpcUaEventTimePolicy,
    RegisteredOpcUaDataChangeEvent,
    RegisteredSource,
    backfill_registered_file_source,
    project_opcua_persistent_data_change_event,
)
from industrial_phm.cli import main
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


def test_ducklake_file_backfill_and_live_share_asset_history(tmp_path) -> None:
    _require_duckdb()
    source_path = tmp_path / "historical.csv"
    source_path.write_text(
        "timestamp,vibration_x\n2026-09-28T01:00:01+00:00,10.0\n2026-09-28T01:00:02+00:00,11.0\n",
        encoding="utf-8",
    )
    sources = InMemorySourceRepository()
    sources.register(
        RegisteredSource(
            source_id="file-source",
            name="Historical vibration",
            config=FileSourceConfig(
                source_path=str(source_path),
                asset_id="pump-01",
                measurement_point_id="drive-end",
                channel_columns=("vibration_x",),
                timestamp_column="timestamp",
            ),
            registered_at=BASE,
        )
    )
    repository = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(
            catalog_path=tmp_path / "catalog.sqlite",
            data_path=tmp_path / "data",
        )
    )

    backfill = backfill_registered_file_source(
        sources,
        repository,
        "file-source",
    )
    assert backfill.event_count == 2
    assert backfill.recovered_segment_count == 0

    live = _event(
        channel_id="vibration_x",
        event_at=BASE + timedelta(seconds=2),
        event_index=9,
    )
    repository.append_opcua_batch(
        (live,),
        batch_id="live-overlap",
        ingestion_mode=HistoryIngestionMode.LIVE,
    )

    measurements = repository.query_measurements(
        "pump-01",
        start_at=BASE,
        end_at=BASE + timedelta(minutes=1),
    )
    assert len(measurements) == 3
    assert {item.ingestion_mode for item in measurements} == {
        HistoryIngestionMode.BACKFILL,
        HistoryIngestionMode.LIVE,
    }
    assert {item.source_type.value for item in measurements} == {"file", "opcua"}
    overlap = [item for item in measurements if item.event_at == BASE + timedelta(seconds=2)]
    assert len(overlap) == 2
    assert {item.source_id for item in overlap} == {"file-source", "source-a"}

    page = repository.query_measurement_page(
        "pump-01",
        start_at=BASE,
        end_at=BASE + timedelta(minutes=1),
        channel_id="vibration_x",
    )
    assert len(page.points) == 3
    assert not page.truncated
    assert not any(point.conflicting_duplicate for point in page.points)

    raw_file_events = repository.query_file_events("file-source")
    assert len(raw_file_events) == 2
    assert raw_file_events[0].source_file == "historical.csv"
    assert raw_file_events[0].value == 10.0
    assert raw_file_events[1].value == 11.0

    repeated = backfill_registered_file_source(
        sources,
        repository,
        "file-source",
    )
    assert repeated.recovered_segment_count == 1
    assert (
        len(
            repository.query_measurements(
                "pump-01",
                start_at=BASE,
                end_at=BASE + timedelta(minutes=1),
            )
        )
        == 3
    )
    assert repeated.history_snapshot_id >= backfill.history_snapshot_id

    source_path.write_text(
        "timestamp,vibration_x\n2026-09-28T01:00:01+00:00,20.0\n2026-09-28T01:00:02+00:00,21.0\n",
        encoding="utf-8",
    )
    changed_snapshot = backfill_registered_file_source(
        sources,
        repository,
        "file-source",
    )
    assert changed_snapshot.recovered_segment_count == 0
    assert changed_snapshot.segments[0].batch_id != backfill.segments[0].batch_id

    after_change = repository.query_measurements(
        "pump-01",
        start_at=BASE,
        end_at=BASE + timedelta(minutes=1),
    )
    assert len(after_change) == 5
    same_file_time = [
        item
        for item in after_change
        if item.source_id == "file-source" and item.event_at == BASE + timedelta(seconds=2)
    ]
    assert len(same_file_time) == 2
    assert {item.value for item in same_file_time} == {11.0, 21.0}
    assert len({item.raw_evidence_id for item in same_file_time}) == 2


def test_backfill_source_cli_reports_snapshot_and_recovers(tmp_path, capsys) -> None:
    _require_duckdb()
    source_path = tmp_path / "historical.csv"
    source_path.write_text(
        "timestamp,vibration_x\n2026-09-28T01:00:01+00:00,1.0\n2026-09-28T01:00:02+00:00,2.0\n",
        encoding="utf-8",
    )
    registry_path = tmp_path / "sources.json"
    registry = JsonSourceRepository(registry_path)
    registry.register(
        RegisteredSource(
            source_id="file-source",
            name="Historical vibration",
            config=FileSourceConfig(
                source_path=str(source_path),
                asset_id="pump-01",
                measurement_point_id="drive-end",
                channel_columns=("vibration_x",),
                timestamp_column="timestamp",
            ),
            registered_at=BASE,
        )
    )
    args = [
        "operations",
        "backfill-source",
        "--registry",
        str(registry_path),
        "--source-id",
        "file-source",
        "--ducklake-catalog",
        str(tmp_path / "catalog.sqlite"),
        "--ducklake-data",
        str(tmp_path / "data"),
    ]

    assert main(args) == 0
    first = capsys.readouterr().out
    assert "state=committed" in first
    assert "history_snapshot=" in first
    assert "input_start=" in first
    assert "input_end=" in first

    assert main(args) == 0
    second = capsys.readouterr().out
    assert "state=recovered" in second


def test_aggregate_excludes_protocol_non_good_and_keeps_empty_numeric_bucket(tmp_path):
    from dataclasses import replace

    _require_duckdb()
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(tmp_path / "catalog", tmp_path / "data")
    )
    good = _event(channel_id="power", event_at=BASE, event_index=0)
    original = _event(channel_id="power", event_at=BASE + timedelta(seconds=5), event_index=1)
    observation = replace(
        original.event.notification.observation,
        status_good=False,
        status_code=0x80000000,
        status_text="Bad",
        value=None,
    )
    bad = replace(
        original,
        event=replace(
            original.event,
            notification=replace(original.event.notification, observation=observation),
        ),
    )
    history.append_opcua_batch((good, bad), batch_id="quality")
    result = history.query_measurement_aggregation(
        "pump-01",
        channel_id="power",
        start_at=BASE,
        end_at=BASE + timedelta(seconds=10),
        bucket_count=2,
    )
    assert result.buckets[0].mean == 1.25
    assert result.buckets[1].observation_count == 1
    assert result.buckets[1].non_good_count == 1
    assert result.buckets[1].usable_count == 0
    assert result.buckets[1].mean is None
    assert result.buckets[1].minimum is None
    assert result.buckets[1].maximum is None
