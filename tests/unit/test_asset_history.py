from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application import (
    HistoricalBatchCommit,
    HistoricalEventTimeBasis,
    HistoricalMeasurement,
    HistoryIngestionMode,
    SourceType,
    validate_asset_history_query,
)


def test_historical_measurement_preserves_event_time_and_provenance() -> None:
    event_at = datetime(2026, 9, 28, 1, 0, tzinfo=UTC)

    measurement = HistoricalMeasurement(
        raw_evidence_id='opcua:["source-a",1,0]',
        source_id="source-a",
        source_type=SourceType.OPCUA,
        asset_id="pump-01",
        measurement_point_id="drive-end",
        channel_id="vibration_x",
        event_time_basis=HistoricalEventTimeBasis.SOURCE_TIMESTAMP,
        event_at=event_at,
        value=1.25,
        status_good=True,
        ingestion_mode=HistoryIngestionMode.LIVE,
    )

    assert measurement.event_at == event_at
    assert measurement.ingestion_mode == HistoryIngestionMode.LIVE


def test_historical_measurement_does_not_invent_unavailable_event_time() -> None:
    measurement = HistoricalMeasurement(
        raw_evidence_id='opcua:["source-a",1,1]',
        source_id="source-a",
        source_type=SourceType.OPCUA,
        asset_id="pump-01",
        channel_id="temperature",
        event_time_basis=HistoricalEventTimeBasis.UNAVAILABLE,
        event_at=None,
        value=None,
        status_good=False,
        ingestion_mode=HistoryIngestionMode.LIVE,
    )

    assert measurement.event_at is None

    with pytest.raises(ValueError, match="unavailable event time"):
        HistoricalMeasurement(
            raw_evidence_id='opcua:["source-a",1,2]',
            source_id="source-a",
            source_type=SourceType.OPCUA,
            asset_id="pump-01",
            channel_id="temperature",
            event_time_basis=HistoricalEventTimeBasis.UNAVAILABLE,
            event_at=datetime(2026, 9, 28, 1, 1, tzinfo=UTC),
            value=10.0,
            status_good=True,
            ingestion_mode=HistoryIngestionMode.LIVE,
        )


def test_asset_history_query_requires_aware_ordered_range() -> None:
    start = datetime(2026, 9, 28, 1, 0, tzinfo=UTC)
    validate_asset_history_query(
        "pump-01",
        start_at=start,
        end_at=start + timedelta(minutes=1),
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        validate_asset_history_query(
            "pump-01",
            start_at=datetime(2026, 9, 28, 1, 0),
            end_at=start + timedelta(minutes=1),
        )

    with pytest.raises(ValueError, match="after start_at"):
        validate_asset_history_query(
            "pump-01",
            start_at=start,
            end_at=start,
        )


def test_historical_batch_commit_requires_positive_event_count() -> None:
    with pytest.raises(ValueError, match="event_count must be at least 1"):
        HistoricalBatchCommit(
            batch_id="batch-1",
            snapshot_id=1,
            event_count=0,
            committed_at=datetime(2026, 9, 28, 1, 0, tzinfo=UTC),
        )
