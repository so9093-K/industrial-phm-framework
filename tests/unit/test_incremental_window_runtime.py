from datetime import UTC, datetime, timedelta

from industrial_phm.application import (
    InMemorySourceRepository,
    OpcUaSourceConfig,
    RegisteredSource,
    SqliteObservationWindowRepository,
)
from industrial_phm.application.opcua_persistent import (
    OpcUaEventTimeBasis,
    OpcUaEventTimeEvidence,
    OpcUaPersistentDataChangeEvent,
)
from industrial_phm.application.source_subscription import RegisteredOpcUaDataChangeEvent
from industrial_phm.application.window_coordinator import (
    ObservationWindowCoordinatorPolicy,
    OpcUaHistoricalEventCursor,
)
from industrial_phm.connectors import (
    OpcUaNodeMapping,
    OpcUaNodeObservation,
    OpcUaSubscriptionNotification,
)
from industrial_phm.runtime.window_coordinator import (
    IncrementalRegisteredOpcUaWindowCoordinator,
)

BASE = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


class _History:
    def __init__(self, events=()):
        self.events = list(events)
        self.cursors = []

    def query_opcua_events(self, source_id):
        return tuple(event for event in self.events if event.source_id == source_id)

    def query_opcua_events_after(self, source_id, *, cursor, limit):
        self.cursors.append(cursor)
        values = [event for event in self.events if event.source_id == source_id]
        if cursor is not None:
            key = (cursor.ingested_at, cursor.connection_epoch, cursor.event_index)
            values = [
                event
                for event in values
                if (
                    event.event_time.ingested_at,
                    event.connection_epoch,
                    event.event_index,
                )
                > key
            ]
        return tuple(values[:limit])

    def query_opcua_events_from_event_time(self, source_id, *, start_at):
        return tuple(
            event
            for event in self.events
            if event.source_id == source_id
            and (
                start_at is None
                or (event.event_time.event_at is not None and event.event_time.event_at >= start_at)
            )
        )


def _source():
    return RegisteredSource(
        source_id="source-a",
        name="Line A",
        config=OpcUaSourceConfig(
            endpoint_url="opc.tcp://127.0.0.1:4840",
            asset_id="asset-a",
            node_mappings=(OpcUaNodeMapping("voltage", "ns=2;s=voltage"),),
        ),
        registered_at=BASE,
    )


def _event(index: int, event_at: datetime) -> OpcUaPersistentDataChangeEvent:
    observation = OpcUaNodeObservation(
        channel_id="voltage",
        node_id="ns=2;s=voltage",
        value=220.0 + index,
        status_code=0,
        status_good=True,
        status_text="Good",
        variant_type="Double",
        source_timestamp=event_at,
        server_timestamp=event_at,
        received_at=event_at,
    )
    registered = RegisteredOpcUaDataChangeEvent(
        source_id="source-a",
        asset_id="asset-a",
        endpoint_url="opc.tcp://127.0.0.1:4840",
        collection_index=index,
        notification=OpcUaSubscriptionNotification(observation),
    )
    return OpcUaPersistentDataChangeEvent(
        event=registered,
        connection_epoch=1,
        event_index=index,
        event_time=OpcUaEventTimeEvidence(
            basis=OpcUaEventTimeBasis.SOURCE_TIMESTAMP,
            source_timestamp=event_at,
            server_timestamp=event_at,
            received_at=event_at,
            ingested_at=event_at,
            event_at=event_at,
        ),
    )


def test_incremental_coordinator_restores_active_buffer_and_reads_after_cursor(tmp_path):
    source = _source()
    repository = InMemorySourceRepository()
    repository.register(source)
    history = _History(
        (
            _event(0, BASE + timedelta(seconds=10)),
            _event(1, BASE + timedelta(minutes=1, seconds=5)),
        )
    )
    windows = SqliteObservationWindowRepository(tmp_path / "windows.sqlite")
    policy = ObservationWindowCoordinatorPolicy(
        window_duration_seconds=60,
        allowed_lateness_seconds=0,
        history_page_size=10,
    )

    first = IncrementalRegisteredOpcUaWindowCoordinator(
        repository,
        history,
        windows,
        source.source_id,
        policy=policy,
    )
    first_cycle = first.run_cycle()

    assert first_cycle.historical_event_count == 2
    assert first_cycle.finalized_window_count == 1
    assert first_cycle.active_window_count == 1
    state = windows.load_coordinator_state(source.source_id)
    assert state is not None
    assert state.cursor == OpcUaHistoricalEventCursor(
        BASE + timedelta(minutes=1, seconds=5),
        1,
        1,
    )
    assert len(state.active_buffers) == 1
    assert state.active_buffers[0].events == (history.events[1],)

    history.events.append(_event(2, BASE + timedelta(minutes=2, seconds=5)))
    restarted = IncrementalRegisteredOpcUaWindowCoordinator(
        repository,
        history,
        windows,
        source.source_id,
        policy=policy,
    )
    second_cycle = restarted.run_cycle()

    assert history.cursors[-1] == state.cursor
    assert second_cycle.historical_event_count == 1
    assert second_cycle.finalized_window_count == 1
    persisted = windows.list_windows()
    assert len(persisted) == 2
    assert persisted[0].events == (history.events[0],)
    assert persisted[1].events == (history.events[1],)
    assert persisted[0].window_end == BASE + timedelta(minutes=1)
    assert persisted[1].window_end == BASE + timedelta(minutes=2)


def test_sqlite_window_repository_rejects_legacy_json_state(tmp_path):
    path = tmp_path / "windows.json"
    path.write_text('{"schema": "legacy"}\n', encoding="utf-8")

    try:
        SqliteObservationWindowRepository(path)
    except ValueError as error:
        assert "legacy JSON state" in str(error)
    else:
        raise AssertionError("legacy JSON window state must not be opened as SQLite")
