from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from industrial_phm.application import (
    ChannelSemanticBinding,
    DurableObservationWindow,
    JsonObservationWindowRepository,
    MeasurementDefinition,
    ObservationWindowBuffer,
    ObservationWindowCompleteness,
    ObservationWindowEventDisposition,
    ObservationWindowFormatError,
    OpcUaEventTimePolicy,
    RegisteredOpcUaDataChangeEvent,
    project_opcua_persistent_data_change_event,
)
from industrial_phm.connectors import (
    OpcUaNodeObservation,
    OpcUaSubscriptionNotification,
)

WINDOW_START = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)
WINDOW_END = WINDOW_START + timedelta(minutes=1)


def _event(
    *,
    channel_id: str = "vibration_x",
    event_at: datetime | None = WINDOW_START + timedelta(seconds=10),
    server_timestamp: datetime | None = None,
    received_at: datetime | None = None,
    ingested_at: datetime | None = None,
    connection_epoch: int = 1,
    event_index: int = 0,
    replayed: bool = False,
):
    callback_time = WINDOW_START + timedelta(seconds=20) if received_at is None else received_at
    accepted_time = (
        callback_time + timedelta(milliseconds=5) if ingested_at is None else ingested_at
    )
    observation = OpcUaNodeObservation(
        channel_id=channel_id,
        node_id=f"ns=2;s={channel_id}",
        value=1.25,
        status_code=0,
        status_good=True,
        status_text="Good",
        variant_type="Double",
        source_timestamp=event_at,
        server_timestamp=server_timestamp,
        received_at=callback_time,
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
        semantic_binding=ChannelSemanticBinding(
            source_id="source-a",
            channel_id=channel_id,
            version="site-a-semantics-v1",
            definition=MeasurementDefinition(
                observed_property="test measurement",
                unit="unit",
                unit_evidence="synthetic test mapping",
            ),
            interpretation_evidence="synthetic test mapping",
        ),
    )
    return project_opcua_persistent_data_change_event(
        registered,
        connection_epoch=connection_epoch,
        event_index=event_index,
        ingested_at=accepted_time,
        event_time_policy=OpcUaEventTimePolicy(
            allow_server_timestamp_fallback=True,
        ),
    )


def _buffer(*, max_buffered_events: int = 8) -> ObservationWindowBuffer:
    return ObservationWindowBuffer(
        window_id="window-1",
        source_id="source-a",
        asset_id="pump-01",
        measurement_point_id="drive-end",
        expected_channel_ids=("vibration_x", "temperature"),
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        max_buffered_events=max_buffered_events,
        max_future_skew_seconds=5.0,
    )


def test_buffer_accepts_in_order_and_out_of_order_events() -> None:
    buffer = _buffer()
    first = _event(
        event_at=WINDOW_START + timedelta(seconds=20),
        event_index=0,
    )
    second = _event(
        channel_id="temperature",
        event_at=WINDOW_START + timedelta(seconds=15),
        event_index=1,
    )

    first_result = buffer.ingest(first)
    second_result = buffer.ingest(second)

    assert first_result.disposition == ObservationWindowEventDisposition.IN_ORDER
    assert first_result.accepted is True
    assert second_result.disposition == ObservationWindowEventDisposition.OUT_OF_ORDER
    assert second_result.accepted is True
    assert buffer.buffered_event_count == 2


def test_event_before_watermark_is_late_and_repeat_is_duplicate() -> None:
    buffer = _buffer()
    buffer.advance_watermark(WINDOW_START + timedelta(seconds=30))
    event = _event(
        event_at=WINDOW_START + timedelta(seconds=20),
        event_index=4,
    )

    first = buffer.ingest(event)
    second = buffer.ingest(event)

    assert first.disposition == ObservationWindowEventDisposition.LATE
    assert first.accepted is False
    assert second.disposition == ObservationWindowEventDisposition.DUPLICATE
    assert second.accepted is False


def test_event_without_event_time_is_rejected_without_received_at_fallback() -> None:
    buffer = _buffer()
    event = _event(
        event_at=None,
        server_timestamp=None,
        event_index=1,
    )

    result = buffer.ingest(event)

    assert result.disposition == ObservationWindowEventDisposition.TIMING_UNAVAILABLE
    assert result.event_at is None
    assert result.accepted is False


def test_future_timestamp_is_distinct_from_event_time_availability() -> None:
    buffer = _buffer()
    event = _event(
        event_at=WINDOW_START + timedelta(seconds=30),
        received_at=WINDOW_START + timedelta(seconds=20),
        ingested_at=WINDOW_START + timedelta(seconds=20, milliseconds=5),
        event_index=3,
    )

    result = buffer.ingest(event)

    assert result.disposition == ObservationWindowEventDisposition.FUTURE_TIMESTAMP
    assert result.event_at == WINDOW_START + timedelta(seconds=30)
    assert result.accepted is False
    buffer.advance_watermark(WINDOW_END)
    window = buffer.finalize(finalized_at=WINDOW_END + timedelta(seconds=1))
    assert window.future_timestamp_rejected_count == 1


def test_unexpected_channel_and_outside_window_are_distinct() -> None:
    buffer = _buffer()
    unexpected = _event(
        channel_id="pressure",
        event_at=WINDOW_START + timedelta(seconds=5),
        event_index=1,
    )
    outside = _event(
        event_at=WINDOW_END,
        event_index=2,
    )

    unexpected_result = buffer.ingest(unexpected)
    outside_result = buffer.ingest(outside)

    assert unexpected_result.disposition == ObservationWindowEventDisposition.UNEXPECTED_CHANNEL
    assert outside_result.disposition == ObservationWindowEventDisposition.OUTSIDE_WINDOW


def test_replayed_value_with_new_local_identity_is_not_auto_deduplicated() -> None:
    buffer = _buffer()
    first = _event(
        event_at=WINDOW_START + timedelta(seconds=10),
        connection_epoch=1,
        event_index=0,
    )
    replayed = _event(
        event_at=WINDOW_START + timedelta(seconds=10),
        connection_epoch=2,
        event_index=0,
        replayed=True,
    )

    assert buffer.ingest(first).disposition == ObservationWindowEventDisposition.IN_ORDER
    replayed_result = buffer.ingest(replayed)

    assert replayed_result.disposition == ObservationWindowEventDisposition.IN_ORDER
    assert replayed_result.accepted is True
    assert replayed.event.notification.replayed is True


def test_buffer_full_rejects_event_without_unbounded_growth() -> None:
    buffer = _buffer(max_buffered_events=1)
    first = _event(event_index=0)
    second = _event(
        channel_id="temperature",
        event_at=WINDOW_START + timedelta(seconds=11),
        event_index=1,
    )

    assert buffer.ingest(first).accepted is True
    result = buffer.ingest(second)

    assert result.disposition == ObservationWindowEventDisposition.BUFFER_FULL
    assert buffer.buffered_event_count == 1


def test_watermark_is_caller_owned_and_cannot_move_backwards() -> None:
    buffer = _buffer()
    buffer.advance_watermark(WINDOW_START + timedelta(seconds=40))

    with pytest.raises(ValueError, match="watermark must not move backwards"):
        buffer.advance_watermark(WINDOW_START + timedelta(seconds=39))


def test_finalize_requires_watermark_to_reach_window_end() -> None:
    buffer = _buffer()
    buffer.advance_watermark(WINDOW_END - timedelta(microseconds=1))

    with pytest.raises(ValueError, match="reach or pass window_end"):
        buffer.finalize(finalized_at=WINDOW_END + timedelta(seconds=1))


def test_finalized_window_records_complete_channel_coverage_and_counts() -> None:
    buffer = _buffer()
    first = _event(
        event_at=WINDOW_START + timedelta(seconds=20),
        event_index=0,
    )
    out_of_order = _event(
        channel_id="temperature",
        event_at=WINDOW_START + timedelta(seconds=15),
        event_index=1,
    )
    late = _event(
        event_at=WINDOW_START + timedelta(seconds=5),
        event_index=2,
    )

    assert buffer.ingest(first).accepted is True
    assert buffer.ingest(out_of_order).accepted is True
    buffer.advance_watermark(WINDOW_START + timedelta(seconds=10))
    assert buffer.ingest(late).disposition == ObservationWindowEventDisposition.LATE
    buffer.advance_watermark(WINDOW_END)

    window = buffer.finalize(finalized_at=WINDOW_END + timedelta(seconds=30))

    assert window.completeness == ObservationWindowCompleteness.COMPLETE
    assert window.observed_channel_ids == ("vibration_x", "temperature")
    assert window.missing_channel_ids == ()
    assert window.accepted_event_count == 2
    assert window.out_of_order_accepted_count == 1
    assert window.late_rejected_count == 1
    assert window.rejected_event_count == 1
    assert [item.event_time.event_at for item in window.events] == [
        WINDOW_START + timedelta(seconds=15),
        WINDOW_START + timedelta(seconds=20),
    ]
    assert not hasattr(window, "analysis_ready")
    assert not hasattr(window, "gap_free")


def test_finalized_window_partial_means_channel_coverage_only() -> None:
    buffer = _buffer()
    buffer.ingest(_event(event_index=0))
    buffer.advance_watermark(WINDOW_END)

    window = buffer.finalize(finalized_at=WINDOW_END + timedelta(seconds=1))

    assert window.completeness == ObservationWindowCompleteness.PARTIAL
    assert window.observed_channel_ids == ("vibration_x",)
    assert window.missing_channel_ids == ("temperature",)


def test_json_repository_round_trip_preserves_protocol_and_timing_evidence(
    tmp_path: Path,
) -> None:
    buffer = _buffer()
    event = _event(
        event_at=WINDOW_START + timedelta(seconds=12),
        server_timestamp=WINDOW_START + timedelta(seconds=13),
        event_index=3,
        replayed=True,
    )
    buffer.ingest(event)
    buffer.advance_watermark(WINDOW_END)
    window = buffer.finalize(finalized_at=WINDOW_END + timedelta(seconds=1))
    repository = JsonObservationWindowRepository(tmp_path / "windows.json")

    repository.record_window(window)
    restored = repository.get(window.window_id)

    assert restored == window
    restored_event = restored.events[0]
    assert restored_event.event.notification.replayed is True
    restored_binding = restored_event.event.semantic_binding
    assert restored_binding is not None
    assert restored_binding.version == "site-a-semantics-v1"
    assert restored_event.event.notification.observation.value == 1.25
    assert restored_event.event.notification.observation.status_text == "Good"
    assert restored_event.event_time.source_timestamp == event.event_time.source_timestamp
    assert restored_event.event_time.server_timestamp == event.event_time.server_timestamp
    assert restored_event.event_time.received_at == event.event_time.received_at
    assert restored_event.event_time.ingested_at == event.event_time.ingested_at


def test_json_repository_is_idempotent_for_identical_window(
    tmp_path: Path,
) -> None:
    buffer = _buffer()
    buffer.ingest(_event(event_index=0))
    buffer.advance_watermark(WINDOW_END)
    window = buffer.finalize(finalized_at=WINDOW_END + timedelta(seconds=1))
    repository = JsonObservationWindowRepository(tmp_path / "windows.json")

    repository.record_window(window)
    repository.record_window(window)

    assert repository.list_windows() == (window,)


def test_json_repository_rejects_conflicting_same_window_id(
    tmp_path: Path,
) -> None:
    first = DurableObservationWindow(
        window_id="window-1",
        source_id="source-a",
        asset_id="pump-01",
        measurement_point_id="drive-end",
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        watermark_at_close=WINDOW_END,
        finalized_at=WINDOW_END + timedelta(seconds=1),
        expected_channel_ids=("vibration_x",),
        events=(_event(event_index=0),),
    )
    second = DurableObservationWindow(
        window_id="window-1",
        source_id="source-a",
        asset_id="pump-01",
        measurement_point_id="drive-end",
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        watermark_at_close=WINDOW_END,
        finalized_at=WINDOW_END + timedelta(seconds=2),
        expected_channel_ids=("vibration_x",),
        events=(_event(event_index=0),),
    )
    repository = JsonObservationWindowRepository(tmp_path / "windows.json")
    repository.record_window(first)

    with pytest.raises(ValueError, match="same window_id"):
        repository.record_window(second)


def test_json_repository_rejects_delivery_identity_in_multiple_windows(
    tmp_path: Path,
) -> None:
    shared_event = _event(event_index=0)
    first = DurableObservationWindow(
        window_id="window-1",
        source_id="source-a",
        asset_id="pump-01",
        measurement_point_id="drive-end",
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        watermark_at_close=WINDOW_END,
        finalized_at=WINDOW_END + timedelta(seconds=1),
        expected_channel_ids=("vibration_x",),
        events=(shared_event,),
    )
    second = DurableObservationWindow(
        window_id="window-2",
        source_id="source-a",
        asset_id="pump-01",
        measurement_point_id="drive-end",
        window_start=WINDOW_START,
        window_end=WINDOW_END + timedelta(minutes=1),
        watermark_at_close=WINDOW_END + timedelta(minutes=1),
        finalized_at=WINDOW_END + timedelta(minutes=1, seconds=1),
        expected_channel_ids=("vibration_x",),
        events=(shared_event,),
    )
    repository = JsonObservationWindowRepository(tmp_path / "windows.json")
    repository.record_window(first)

    with pytest.raises(ValueError, match="multiple windows"):
        repository.record_window(second)


def test_json_repository_rejects_unsupported_schema(tmp_path: Path) -> None:
    path = tmp_path / "windows.json"
    path.write_text(
        '{"schema":"industrial-phm-observation-window-v0","windows":[]}\n',
        encoding="utf-8",
    )
    repository = JsonObservationWindowRepository(path)

    with pytest.raises(ObservationWindowFormatError, match="unsupported"):
        repository.list_windows()


def test_json_repository_rejects_malformed_json(tmp_path: Path) -> None:
    path = tmp_path / "windows.json"
    path.write_text("{not-json", encoding="utf-8")
    repository = JsonObservationWindowRepository(path)

    with pytest.raises(ObservationWindowFormatError, match="valid JSON"):
        repository.list_windows()
