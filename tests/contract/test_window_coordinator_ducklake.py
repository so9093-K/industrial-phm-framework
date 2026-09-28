from datetime import UTC, datetime, timedelta
from importlib.util import find_spec

import pytest

from industrial_phm.application import (
    InMemorySourceRepository,
    JsonObservationWindowRepository,
    ObservationWindowCoordinatorPolicy,
    OpcUaEventTimePolicy,
    OpcUaSourceConfig,
    RegisteredOpcUaDataChangeEvent,
    RegisteredSource,
    project_opcua_persistent_data_change_event,
)
from industrial_phm.connectors import (
    OpcUaNodeMapping,
    OpcUaNodeObservation,
    OpcUaSubscriptionNotification,
)
from industrial_phm.history import DuckLakeAssetHistory, DuckLakeAssetHistoryConfig
from industrial_phm.runtime import rebuild_registered_opcua_observation_windows

BASE = datetime(2026, 9, 28, 5, 0, tzinfo=UTC)


def _require_duckdb() -> None:
    if find_spec("duckdb") is None:
        pytest.skip("DuckLake history runtime is not installed")


def _source_repository() -> InMemorySourceRepository:
    repository = InMemorySourceRepository()
    repository.register(
        RegisteredSource(
            source_id="source-a",
            name="Pump OPC UA",
            config=OpcUaSourceConfig(
                endpoint_url="opc.tcp://127.0.0.1:4840",
                asset_id="pump-01",
                measurement_point_id="drive-end",
                node_mappings=(
                    OpcUaNodeMapping("vibration_x", "ns=2;s=vibration_x"),
                    OpcUaNodeMapping("temperature", "ns=2;s=temperature"),
                ),
            ),
            registered_at=BASE,
        )
    )
    return repository


def _event(
    *,
    event_index: int,
    channel_id: str,
    event_at: datetime,
    ingested_at: datetime,
):
    observation = OpcUaNodeObservation(
        channel_id=channel_id,
        node_id=f"ns=2;s={channel_id}",
        value=float(event_index + 1),
        status_code=0,
        status_good=True,
        status_text="Good",
        variant_type="Double",
        source_timestamp=event_at,
        server_timestamp=event_at + timedelta(milliseconds=1),
        received_at=ingested_at - timedelta(milliseconds=5),
    )
    registered = RegisteredOpcUaDataChangeEvent(
        source_id="source-a",
        asset_id="pump-01",
        endpoint_url="opc.tcp://127.0.0.1:4840",
        measurement_point_id="drive-end",
        collection_index=event_index,
        notification=OpcUaSubscriptionNotification(
            observation=observation,
            replayed=False,
        ),
    )
    return project_opcua_persistent_data_change_event(
        registered,
        connection_epoch=1,
        event_index=event_index,
        ingested_at=ingested_at,
        event_time_policy=OpcUaEventTimePolicy(),
    )


def test_ducklake_history_rebuilds_same_finalized_windows_after_restart(tmp_path) -> None:
    _require_duckdb()
    history = DuckLakeAssetHistory(
        DuckLakeAssetHistoryConfig(
            catalog_path=tmp_path / "catalog.sqlite",
            data_path=tmp_path / "data",
        )
    )
    events = (
        _event(
            event_index=0,
            channel_id="vibration_x",
            event_at=BASE + timedelta(seconds=2),
            ingested_at=BASE + timedelta(seconds=2.1),
        ),
        _event(
            event_index=1,
            channel_id="temperature",
            event_at=BASE + timedelta(seconds=8),
            ingested_at=BASE + timedelta(seconds=8.1),
        ),
        _event(
            event_index=2,
            channel_id="vibration_x",
            event_at=BASE + timedelta(seconds=5),
            ingested_at=BASE + timedelta(seconds=9),
        ),
        _event(
            event_index=3,
            channel_id="vibration_x",
            event_at=BASE + timedelta(seconds=15),
            ingested_at=BASE + timedelta(seconds=15.1),
        ),
    )
    history.append_opcua_batch(events, batch_id="window-input")

    restored = history.query_opcua_events("source-a")
    assert restored == events

    source_repository = _source_repository()
    window_repository = JsonObservationWindowRepository(tmp_path / "windows.json")
    policy = ObservationWindowCoordinatorPolicy(
        window_duration_seconds=10.0,
        allowed_lateness_seconds=3.0,
        max_buffered_events=100,
        max_future_skew_seconds=5.0,
        poll_interval_seconds=0.01,
        alignment_origin=BASE,
    )

    first = rebuild_registered_opcua_observation_windows(
        source_repository,
        history,
        window_repository,
        "source-a",
        policy=policy,
    )
    assert first.finalized_window_count == 1
    persisted = window_repository.list_windows()
    assert len(persisted) == 1
    assert persisted[0].accepted_event_count == 3
    assert persisted[0].out_of_order_accepted_count == 1

    # Simulate coordinator restart: no in-memory state survives.
    second = rebuild_registered_opcua_observation_windows(
        source_repository,
        history,
        JsonObservationWindowRepository(tmp_path / "windows.json"),
        "source-a",
        policy=policy,
    )
    assert second.finalized_windows == first.finalized_windows
    assert JsonObservationWindowRepository(tmp_path / "windows.json").list_windows() == persisted
