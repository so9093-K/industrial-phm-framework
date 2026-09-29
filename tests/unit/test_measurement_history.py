from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from industrial_phm.application.asset_history import (
    HistoricalEventTimeBasis,
    HistoricalMeasurement,
    HistoryIngestionMode,
)
from industrial_phm.application.measurement_history import (
    MeasurementCurrency,
    MeasurementHistoryPoint,
    assess_latest_measurement,
    resolve_measurement_range,
)
from industrial_phm.application.source_registration import SourceType

NOW = datetime(2026, 9, 28, tzinfo=UTC)


def test_event_currency_does_not_infer_value_quality_or_asset_health():
    measurement = HistoricalMeasurement(
        raw_evidence_id="raw",
        source_id="source",
        source_type=SourceType.OPCUA,
        asset_id="asset",
        channel_id="power",
        event_time_basis=HistoricalEventTimeBasis.SOURCE_TIMESTAMP,
        event_at=NOW - timedelta(seconds=10),
        value=None,
        status_good=False,
        ingestion_mode=HistoryIngestionMode.LIVE,
    )
    point = MeasurementHistoryPoint(measurement, conflicting_duplicate=False)
    assert (
        assess_latest_measurement(point, as_of=NOW, stale_after_seconds=10).currency
        == MeasurementCurrency.RECENT
    )
    assert (
        assess_latest_measurement(point, as_of=NOW, stale_after_seconds=9).currency
        == MeasurementCurrency.STALE
    )
    future = replace(point, measurement=replace(measurement, event_at=NOW + timedelta(seconds=1)))
    status = assess_latest_measurement(future, as_of=NOW, stale_after_seconds=10)
    assert status.currency == MeasurementCurrency.FUTURE
    assert status.age_seconds == -1


def test_recent_range_moves_with_each_query_and_custom_range_is_explicit():
    old = NOW - timedelta(days=365)
    start, end = resolve_measurement_range("15m", as_of=NOW, start_at=old, end_at=old)
    assert (start, end) == (NOW - timedelta(minutes=15), NOW)
    later = NOW + timedelta(minutes=1)
    assert resolve_measurement_range("24h", as_of=later, start_at=old, end_at=old) == (
        later - timedelta(hours=24),
        later,
    )
    with pytest.raises(ValueError, match="increasing"):
        resolve_measurement_range("custom", as_of=NOW, start_at=old, end_at=old)


def test_latest_rows_preserve_known_units_and_expose_missing_event_time():
    import json

    from industrial_phm.presentation.measurement_history import latest_measurement_rows

    measurement = HistoricalMeasurement(
        raw_evidence_id="raw",
        source_id="source",
        source_type=SourceType.FILE,
        asset_id="asset",
        channel_id="power",
        event_time_basis=HistoricalEventTimeBasis.UNAVAILABLE,
        event_at=None,
        value=2.0,
        status_good=True,
        ingestion_mode=HistoryIngestionMode.IMPORT,
    )
    point = MeasurementHistoryPoint(
        measurement,
        conflicting_duplicate=False,
        source_metadata_json=json.dumps(
            {
                "semantics": {
                    "version": "v2",
                    "interpretation_evidence": "instrument documentation",
                    "definition": {"unit": "kW", "unit_evidence": "instrument manual section 4"},
                }
            }
        ),
    )
    row = latest_measurement_rows((point,), as_of=NOW, stale_after_seconds=10)[0]
    assert row["value"] == 2.0
    assert row["unit"] == "kW"
    assert row["unit_evidence"] == "instrument manual section 4"
    assert row["semantic_version"] == "v2"
    assert row["currency"] == "time-unavailable"
    assert row["event_time_basis"] == "unavailable"
    assert row["time"] is None
    assert row["age_seconds"] is None
    unknown = latest_measurement_rows(
        (replace(point, source_metadata_json=None),), as_of=NOW, stale_after_seconds=10
    )[0]
    assert unknown["unit"] == "unknown"
    assert unknown["unit_evidence"] is None
