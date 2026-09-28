import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from industrial_phm.application import (
    InMemorySourceRepository,
    JsonObservationWindowRepository,
    ObservationWindowCompleteness,
    ObservationWindowCoordinatorPolicy,
    ObservationWindowEventDisposition,
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
from industrial_phm.runtime import (
    SqliteAcquisitionTelemetryRepository,
    rebuild_registered_opcua_observation_windows,
    run_continuous_registered_opcua_observation_windows,
)

BASE = datetime(2026, 9, 28, 0, 0, tzinfo=UTC)


class _History:
    def __init__(self, events) -> None:
        self.events = tuple(events)

    def query_opcua_events(self, source_id: str):
        return tuple(event for event in self.events if event.source_id == source_id)


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
    source_timestamp: datetime | None,
    ingested_at: datetime,
) -> object:
    observation = OpcUaNodeObservation(
        channel_id=channel_id,
        node_id=f"ns=2;s={channel_id}",
        value=float(event_index + 1),
        status_code=0,
        status_good=True,
        status_text="Good",
        variant_type="Double",
        source_timestamp=source_timestamp,
        server_timestamp=None,
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


def _policy(*, max_buffered_events: int = 100) -> ObservationWindowCoordinatorPolicy:
    return ObservationWindowCoordinatorPolicy(
        window_duration_seconds=10.0,
        allowed_lateness_seconds=3.0,
        max_buffered_events=max_buffered_events,
        max_future_skew_seconds=5.0,
        poll_interval_seconds=0.01,
        alignment_origin=BASE,
    )


def test_coordinator_rotates_windows_and_preserves_dispositions_across_rebuild(
    tmp_path: Path,
) -> None:
    events = (
        _event(
            event_index=0,
            channel_id="vibration_x",
            source_timestamp=BASE + timedelta(seconds=2),
            ingested_at=BASE + timedelta(seconds=2.5),
        ),
        _event(
            event_index=1,
            channel_id="temperature",
            source_timestamp=BASE + timedelta(seconds=8),
            ingested_at=BASE + timedelta(seconds=8.5),
        ),
        _event(
            event_index=2,
            channel_id="vibration_x",
            source_timestamp=BASE + timedelta(seconds=5),
            ingested_at=BASE + timedelta(seconds=9),
        ),
        _event(
            event_index=3,
            channel_id="vibration_x",
            source_timestamp=BASE + timedelta(seconds=4),
            ingested_at=BASE + timedelta(seconds=9.5),
        ),
        _event(
            event_index=4,
            channel_id="unexpected",
            source_timestamp=BASE + timedelta(seconds=6),
            ingested_at=BASE + timedelta(seconds=10),
        ),
        _event(
            event_index=5,
            channel_id="vibration_x",
            source_timestamp=None,
            ingested_at=BASE + timedelta(seconds=10.5),
        ),
        _event(
            event_index=6,
            channel_id="vibration_x",
            source_timestamp=BASE + timedelta(seconds=100),
            ingested_at=BASE + timedelta(seconds=11),
        ),
        _event(
            event_index=7,
            channel_id="vibration_x",
            source_timestamp=BASE + timedelta(seconds=15),
            ingested_at=BASE + timedelta(seconds=15.5),
        ),
        _event(
            event_index=8,
            channel_id="temperature",
            source_timestamp=BASE + timedelta(seconds=3),
            ingested_at=BASE + timedelta(seconds=16),
        ),
        _event(
            event_index=9,
            channel_id="temperature",
            source_timestamp=BASE + timedelta(seconds=25),
            ingested_at=BASE + timedelta(seconds=25.5),
        ),
    )
    repository = JsonObservationWindowRepository(tmp_path / "windows.json")
    source_repository = _source_repository()

    first = rebuild_registered_opcua_observation_windows(
        source_repository,
        _History(events),
        repository,
        "source-a",
        policy=_policy(),
    )

    assert first.watermark == BASE + timedelta(seconds=22)
    assert first.finalized_window_count == 2
    assert first.active_window_count == 1
    assert [result.disposition for result in first.event_results] == [
        ObservationWindowEventDisposition.IN_ORDER,
        ObservationWindowEventDisposition.IN_ORDER,
        ObservationWindowEventDisposition.OUT_OF_ORDER,
        ObservationWindowEventDisposition.LATE,
        ObservationWindowEventDisposition.UNEXPECTED_CHANNEL,
        ObservationWindowEventDisposition.TIMING_UNAVAILABLE,
        ObservationWindowEventDisposition.FUTURE_TIMESTAMP,
        ObservationWindowEventDisposition.IN_ORDER,
        ObservationWindowEventDisposition.LATE,
        ObservationWindowEventDisposition.IN_ORDER,
    ]

    windows = repository.list_windows()
    assert len(windows) == 2
    first_window, second_window = windows

    assert first_window.window_start == BASE
    assert first_window.window_end == BASE + timedelta(seconds=10)
    assert first_window.watermark_at_close == BASE + timedelta(seconds=12)
    assert first_window.finalized_at == BASE + timedelta(seconds=15.5)
    assert first_window.completeness == ObservationWindowCompleteness.COMPLETE
    assert first_window.out_of_order_accepted_count == 1
    assert first_window.late_rejected_count == 1
    assert first_window.unexpected_channel_rejected_count == 1
    assert first_window.accepted_event_count == 3

    assert second_window.window_start == BASE + timedelta(seconds=10)
    assert second_window.window_end == BASE + timedelta(seconds=20)
    assert second_window.watermark_at_close == BASE + timedelta(seconds=22)
    assert second_window.finalized_at == BASE + timedelta(seconds=25.5)
    assert second_window.completeness == ObservationWindowCompleteness.PARTIAL
    assert second_window.accepted_event_count == 1

    second = rebuild_registered_opcua_observation_windows(
        source_repository,
        _History(events),
        repository,
        "source-a",
        policy=_policy(),
    )
    assert second.finalized_windows == first.finalized_windows
    assert repository.list_windows() == windows


def test_coordinator_preserves_buffer_full_disposition(tmp_path: Path) -> None:
    events = (
        _event(
            event_index=0,
            channel_id="vibration_x",
            source_timestamp=BASE + timedelta(seconds=1),
            ingested_at=BASE + timedelta(seconds=1.1),
        ),
        _event(
            event_index=1,
            channel_id="temperature",
            source_timestamp=BASE + timedelta(seconds=2),
            ingested_at=BASE + timedelta(seconds=2.1),
        ),
        _event(
            event_index=2,
            channel_id="vibration_x",
            source_timestamp=BASE + timedelta(seconds=3),
            ingested_at=BASE + timedelta(seconds=3.1),
        ),
        _event(
            event_index=3,
            channel_id="vibration_x",
            source_timestamp=BASE + timedelta(seconds=20),
            ingested_at=BASE + timedelta(seconds=20.1),
        ),
    )
    repository = JsonObservationWindowRepository(tmp_path / "windows.json")

    result = rebuild_registered_opcua_observation_windows(
        _source_repository(),
        _History(events),
        repository,
        "source-a",
        policy=_policy(max_buffered_events=2),
    )

    assert result.disposition_count(ObservationWindowEventDisposition.BUFFER_FULL) == 1
    window = repository.list_windows()[0]
    assert window.buffer_full_rejected_count == 1
    assert window.accepted_event_count == 2


def test_continuous_window_coordinator_records_latest_telemetry(tmp_path: Path) -> None:
    async def _run() -> None:
        events = (
            _event(
                event_index=0,
                channel_id="vibration_x",
                source_timestamp=BASE + timedelta(seconds=2),
                ingested_at=BASE + timedelta(seconds=2.1),
            ),
            _event(
                event_index=1,
                channel_id="temperature",
                source_timestamp=BASE + timedelta(seconds=8),
                ingested_at=BASE + timedelta(seconds=8.1),
            ),
            _event(
                event_index=2,
                channel_id="vibration_x",
                source_timestamp=BASE + timedelta(seconds=15),
                ingested_at=BASE + timedelta(seconds=15.1),
            ),
        )
        telemetry = SqliteAcquisitionTelemetryRepository(tmp_path / "acquisition-telemetry.sqlite")
        stop_event = asyncio.Event()
        task = asyncio.create_task(
            run_continuous_registered_opcua_observation_windows(
                _source_repository(),
                _History(events),
                JsonObservationWindowRepository(tmp_path / "windows.json"),
                "source-a",
                stop_event=stop_event,
                policy=_policy(),
                telemetry_recorder=telemetry,
                now_fn=lambda: BASE + timedelta(seconds=30),
            )
        )

        for _ in range(500):
            if telemetry.get("source-a").window is not None:
                break
            await asyncio.sleep(0.001)
        else:
            raise AssertionError("window telemetry was not recorded")

        stop_event.set()
        result = await task
        assert result.cycle_count >= 1

        window = telemetry.get("source-a").window
        assert window is not None
        assert window.watermark == BASE + timedelta(seconds=12)
        assert window.finalized_window_count == 1
        assert window.active_window_count == 1
        assert window.historical_event_count == 3
        assert window.in_order_count == 3
        assert window.last_finalized_window_id is not None
        assert window.last_finalized_window_end == BASE + timedelta(seconds=10)

    asyncio.run(_run())


def test_unexpected_channel_does_not_advance_watermark_or_create_future_window(
    tmp_path: Path,
) -> None:
    events = (
        _event(
            event_index=0,
            channel_id="vibration_x",
            source_timestamp=BASE + timedelta(seconds=2),
            ingested_at=BASE + timedelta(seconds=2.1),
        ),
        _event(
            event_index=1,
            channel_id="unexpected",
            source_timestamp=BASE + timedelta(seconds=100),
            ingested_at=BASE + timedelta(seconds=100.1),
        ),
        _event(
            event_index=2,
            channel_id="temperature",
            source_timestamp=BASE + timedelta(seconds=15),
            ingested_at=BASE + timedelta(seconds=15.1),
        ),
    )
    repository = JsonObservationWindowRepository(tmp_path / "windows.json")
    source_repository = _source_repository()

    first = rebuild_registered_opcua_observation_windows(
        source_repository,
        _History(events),
        repository,
        "source-a",
        policy=_policy(),
    )

    assert [result.disposition for result in first.event_results] == [
        ObservationWindowEventDisposition.IN_ORDER,
        ObservationWindowEventDisposition.UNEXPECTED_CHANNEL,
        ObservationWindowEventDisposition.IN_ORDER,
    ]
    assert first.event_results[1].watermark_at_ingest == BASE - timedelta(seconds=1)
    assert first.watermark == BASE + timedelta(seconds=12)
    assert first.finalized_window_count == 1
    assert first.active_window_count == 1

    windows = repository.list_windows()
    assert len(windows) == 1
    assert windows[0].window_start == BASE
    assert windows[0].window_end == BASE + timedelta(seconds=10)
    assert windows[0].finalized_at == BASE + timedelta(seconds=15.1)
    assert windows[0].watermark_at_close == BASE + timedelta(seconds=12)

    second = rebuild_registered_opcua_observation_windows(
        source_repository,
        _History(events),
        JsonObservationWindowRepository(tmp_path / "windows.json"),
        "source-a",
        policy=_policy(),
    )
    assert second.event_results == first.event_results
    assert second.finalized_windows == first.finalized_windows
    assert second.watermark == first.watermark
    assert JsonObservationWindowRepository(tmp_path / "windows.json").list_windows() == windows
